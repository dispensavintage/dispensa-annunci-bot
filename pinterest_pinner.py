# -*- coding: utf-8 -*-
"""Pinner Pinterest per Dispensa Vintage.

Due cose da pinnare, su board per categoria:
  - PRODOTTI  -> link alla scheda del negozio (come dal 2026, immagine orizzontale)
  - ARTICOLI  -> link alla guida sul blog, con un pin VERTICALE 1000x1500
                 composto al volo (pin_grafica.py) e caricato in base64.

Perche' i pin degli articoli si compongono: le copertine del blog sono 1000x555
o 1600x900, e Pinterest mostra i pin in 2:3. Un'immagine orizzontale diventa una
strisciolina che non guarda nessuno. Il titolo sul pannello bordeaux si legge
anche in miniatura, che e' come si naviga su Pinterest.

Ogni run pinna un lotto di cose NON ancora pinnate (metafield custom.pinterest_pinned)
e le marca. Gira su GitHub Actions.

Env richiesti:
  SHOPIFY_STORE (opz., default sotto), SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET
  PINTEREST_APP_ID, PINTEREST_APP_SECRET, PINTEREST_REFRESH_TOKEN
  PIN_BATCH (opz., default 20) = quanti pin per run
  PIN_WHAT  (opz., default "articoli") = articoli | prodotti | misto
"""
import os, io, re, html, json, base64, urllib.request, urllib.parse, urllib.error

STORE = os.environ.get("SHOPIFY_STORE", "f64efc-d9.myshopify.com")
SHOP_API = f"https://{STORE}/admin/api/2025-10/graphql.json"
PIN_API = "https://api.pinterest.com/v5"
SITE = "https://dispensavintage.it"
BATCH = int(os.environ.get("PIN_BATCH", "20"))
MODO = os.environ.get("PIN_WHAT", "articoli").strip().lower()
FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "font")

EXCLUDE_TYPES = {"Negozi vintage", "Buoni regalo"}
EXCLUDE_VENDORS = {"Annuncio privato"}

# board (nome, keyword productType, descrizione). L'ultima senza keyword = catch-all.
BOARDS = [
    ("Targhe, Insegne e Pubblicità Vintage", ["targh","insegn","posacener","fiammif","apribottigl","cartell","pubblicit"],
     "Targhe smaltate, insegne e oggetti pubblicitari vintage da collezione."),
    ("Orologi e Sveglie Vintage", ["orolog","svegli"],
     "Orologi, sveglie e segnatempo vintage e da collezione."),
    ("Giocattoli e Giochi Vintage", ["giocatt","gioco","giochi","bambol","modellin","peluche","soldatin"],
     "Giocattoli, giochi da tavolo e modellini vintage."),
    ("Dischi, Vinili e Hi-Fi Vintage", ["vinil","disco","disch","radio","audio","hi-fi","musicassett","audiocassett","music","mangiadisch"],
     "Vinili, dischi, radio e audio vintage e da collezione."),
    ("Illuminazione e Arredo Vintage", ["lampad","illumin","specch","cornic","mobil","sedi","poltron","tavolin","arred","orologio da parete"],
     "Lampade, mobili e complementi d'arredo vintage e modernariato."),
    ("Collezionismo Vintage", ["portachiav","spill","ciondol","francoboll","scheda telefon","monet","medagl","santin","figurin","gettoni"],
     "Portachiavi, spille, francobolli, schede e piccolo collezionismo vintage."),
    ("Cucina e Casa Vintage", ["cucina","contenitor","scatol","vassoi","bottigl","caraff","ceramic","posate","tazz","barattol"],
     "Oggetti vintage per la cucina e la casa."),
    ("Fotografia Vintage", ["fotograf","fotocamer","polaroid","obiettiv","diaposit"],
     "Macchine fotografiche e fotografia vintage e analogica."),
    ("Libri, Riviste e Stampe Vintage", ["libr","rivist","fumett","giornal","manifest","poster","stampa","cartolin","mappa"],
     "Libri, riviste, fumetti, manifesti e stampe vintage."),
    ("Moda e Accessori Vintage", ["portafogl","bors","accessor","cintur","occhial","cravatt","abbigl","cappell","scarp","gioiell"],
     "Moda e accessori vintage."),
    ("Bundle e Idee Regalo Vintage", ["bundle","mistery","mystery","regalo"],
     "Bundle a tema e idee regalo vintage."),
    ("Modernariato e Oggetti Vintage", [],
     "Oggetti vintage, modernariato e pezzi unici da collezione."),
    # board di soli ARTICOLI: non intercettano prodotti (nessuna keyword)
    ("Mercatini e Fiere Vintage", [],
     "Mercatini dell'usato, fiere e calendari citta' per citta' in Italia."),
    ("Guide, Restauro e Valutazioni Vintage", [],
     "Come riconoscere, restaurare e valutare oggetti vintage e da collezione."),
]

# il catch-all dei PRODOTTI e' esplicito: le board in coda sono degli articoli
CATCHALL_PRODOTTI = "Modernariato e Oggetti Vintage"
BOARD_GUIDE = "Guide, Restauro e Valutazioni Vintage"
BOARD_MERCATINI = "Mercatini e Fiere Vintage"

# da quale blog arriva l'articolo, se il titolo non dice niente
BOARD_PER_BLOG = {
    "arredamento": "Illuminazione e Arredo Vintage",
    "stile-design": "Illuminazione e Arredo Vintage",
    "restauro-e-idee": BOARD_GUIDE,
    "guide": BOARD_GUIDE,
    "collezionismo": "Collezionismo Vintage",
    "eventi-e-fiere": BOARD_MERCATINI,
    "negozi-vintage": BOARD_MERCATINI,
    "tecnologia-vintage": "Dischi, Vinili e Hi-Fi Vintage",
}

# l'occhiello giallo in cima al pannello del pin
OCCHIELLO = {
    "guide": "Guida", "collezionismo": "Collezionismo", "restauro-e-idee": "Restauro",
    "arredamento": "Arredamento", "eventi-e-fiere": "Mercatini", "stile-design": "Stile",
    "tecnologia-vintage": "Tecnologia", "negozi-vintage": "Negozi",
}

def board_for(ptype):
    pt = (ptype or "").lower()
    for name, kws, _ in BOARDS:
        if kws and any(k in pt for k in kws):
            return name
    return CATCHALL_PRODOTTI

# hashtag per categoria (Pinterest = motore di ricerca: keyword+hashtag aiutano la scoperta)
HASHTAGS = {
    "Targhe, Insegne e Pubblicità Vintage": "#targhevintage #insegnevintage #pubblicitavintage",
    "Orologi e Sveglie Vintage": "#orologivintage #sveglievintage #modernariato",
    "Giocattoli e Giochi Vintage": "#giocattolivintage #giochivintage #retrogaming",
    "Dischi, Vinili e Hi-Fi Vintage": "#vinili #dischinvinile #hifivintage",
    "Illuminazione e Arredo Vintage": "#lampadevintage #arredovintage #midcentury",
    "Collezionismo Vintage": "#collezionismo #vintagecollection #modernariato",
    "Cucina e Casa Vintage": "#cucinavintage #casavintage #modernariato",
    "Fotografia Vintage": "#fotografiavintage #fotocamerevintage #analogico",
    "Libri, Riviste e Stampe Vintage": "#librivintage #rivistevintage #manifestivintage",
    "Moda e Accessori Vintage": "#modavintage #accessorivintage #retro",
    "Bundle e Idee Regalo Vintage": "#idearegalo #vintagegift #regalovintage",
    "Modernariato e Oggetti Vintage": "#modernariato #oggettivintage #retro",
    "Mercatini e Fiere Vintage": "#mercatini #mercatinidellusato #vintageitalia",
    "Guide, Restauro e Valutazioni Vintage": "#restauro #faidate #quantovale",
}
COMMON_TAGS = "#vintage #retro #dispensavintage"

# ---------- Shopify ----------
def shop_token():
    data = urllib.parse.urlencode({"grant_type": "client_credentials",
        "client_id": os.environ["SHOPIFY_CLIENT_ID"], "client_secret": os.environ["SHOPIFY_CLIENT_SECRET"]}).encode()
    return json.load(urllib.request.urlopen(urllib.request.Request(f"https://{STORE}/admin/oauth/access_token", data=data)))["access_token"]

def gql(token, query, variables=None):
    req = urllib.request.Request(SHOP_API, data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": token})
    return json.load(urllib.request.urlopen(req))

# ---------- Pinterest ----------
def pin_token():
    """Rinnova l'access token. Se Pinterest dice di no, il motivo sta nel CORPO
    della risposta: senza stamparlo un 401 puo' voler dire tre cose diverse."""
    chiavi = ("PINTEREST_APP_ID", "PINTEREST_APP_SECRET", "PINTEREST_REFRESH_TOKEN")
    vuoti = [k for k in chiavi if not os.environ.get(k, "").strip()]
    if vuoti:
        raise SystemExit("Segreti mancanti o vuoti: " + ", ".join(vuoti))
    # .strip(): un a capo incollato per sbaglio nel segreto fa fallire la Basic auth
    app_id, secret, rt = (os.environ[k].strip() for k in chiavi)

    auth = base64.b64encode(f"{app_id}:{secret}".encode()).decode()
    data = urllib.parse.urlencode({"grant_type": "refresh_token",
                                   "refresh_token": rt}).encode()
    req = urllib.request.Request(f"{PIN_API}/oauth/token", data=data,
        headers={"Authorization": "Basic " + auth,
                 "Content-Type": "application/x-www-form-urlencoded"})
    try:
        return json.load(urllib.request.urlopen(req, timeout=30))["access_token"]
    except urllib.error.HTTPError as e:
        corpo = e.read().decode()[:500]
        print("=" * 64)
        print(f"PINTEREST HA RIFIUTATO IL RINNOVO — HTTP {e.code}")
        print(f"risposta: {corpo}")
        print(f"misure (non i valori): App ID {len(app_id)} car., "
              f"App secret {len(secret)} car., refresh token {len(rt)} car.")
        print("Se parla di client/credenziali  -> App ID o App secret sbagliati.")
        print("Se parla del refresh token      -> va rigenerato.")
        print("=" * 64)
        raise SystemExit(1)

def pin_call(method, path, token, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(PIN_API + path, data=data, method=method,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

def ensure_boards(token):
    existing, bookmark = {}, None
    while True:
        path = "/boards?page_size=100" + (f"&bookmark={bookmark}" if bookmark else "")
        r = pin_call("GET", path, token)
        for b in r.get("items", []):
            existing[b["name"]] = b["id"]
        bookmark = r.get("bookmark")
        if not bookmark:
            break
    for name, _, desc in BOARDS:
        if name not in existing:
            r = pin_call("POST", "/boards", token, {"name": name, "description": desc[:500], "privacy": "PUBLIC"})
            existing[name] = r["id"]
            print("board creata:", name)
    return existing

def jpg(url):
    u = url.split("?")[0]
    return (u + "?width=1080") if u.lower().endswith((".jpg", ".jpeg")) else (u + ".jpg?width=1080")

def _base64_pin(url_immagine, titolo, occhiello):
    """Compone il pin verticale 1000x1500 e lo restituisce pronto per l'API."""
    from pin_grafica import componi
    im = componi(url_immagine, titolo, occhiello, FONT)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88, optimize=True)
    return {"source_type": "image_base64", "content_type": "image/jpeg",
            "data": base64.b64encode(buf.getvalue()).decode()}


def make_pin(token, board_id, p, board_name):
    tags = (HASHTAGS.get(board_name, "#modernariato #oggettivintage") + " " + COMMON_TAGS)
    desc = (f"{p['title']}. Pezzo vintage originale da collezione, disponibile su Dispensa Vintage "
            f"con spedizione in tutta Italia. {tags}")
    # stesso formato verticale degli articoli: su Pinterest si naviga in miniatura
    # e una foto prodotto quadrata senza titolo non dice cosa stai guardando.
    media = _base64_pin(jpg(p["featuredImage"]["url"]), p["title"], "In vendita")
    body = {"board_id": board_id, "title": p["title"][:100], "description": desc[:500],
            "link": f"{SITE}/products/{p['handle']}", "alt_text": p["title"][:500],
            "media_source": media}
    return pin_call("POST", "/pins", token, body)

# ---------- raccolta prodotti non pinnati ----------
def collect(token, n_needed):
    q = '''query($c:String){products(first:100,after:$c,query:"status:active"){
        pageInfo{hasNextPage endCursor}
        nodes{id title handle productType vendor tags featuredImage{url}
          pinned:metafield(namespace:"custom",key:"pinterest_pinned"){value}}}}'''
    out, cur = [], None
    while len(out) < n_needed:
        d = gql(token, q, {"c": cur})["data"]["products"]
        for n in d["nodes"]:
            if (n.get("productType") or "") in EXCLUDE_TYPES: continue
            if (n.get("vendor") or "") in EXCLUDE_VENDORS: continue
            if "annunci" in [t.lower() for t in (n.get("tags") or [])]: continue
            if not n.get("featuredImage"): continue
            if (n.get("pinned") or {}).get("value") == "true": continue
            out.append(n)
            if len(out) >= n_needed: break
        if d["pageInfo"]["hasNextPage"] and len(out) < n_needed:
            cur = d["pageInfo"]["endCursor"]
        else:
            break
    return out

# ---------- testo delle descrizioni ----------
# ⚠️ Il campo «sommario» di 79 articoli su 146 contiene HTML: <meta charset>,
# data-mce-fragment dell'editor Shopify e, in qualche caso, pezzi di DOM di
# ChatGPT incollati dentro. Sul sito non si vedono, in una descrizione Pinterest
# (testo semplice) finivano stampati nudi e si mangiavano i 500 caratteri.
_TAG = re.compile(r"<[^>]+>")
_SPAZI = re.compile(r"\s+")


def ripulisci(testo):
    if not testo:
        return ""
    t = _TAG.sub(" ", testo)          # via i tag
    t = html.unescape(t)              # &egrave; -> è
    t = _SPAZI.sub(" ", t)            # a capo e spazi multipli
    t = re.sub(r" +([,.;:!?])", r"\1", t)   # «industrial ?» -> «industrial?»
    return t.strip()


def tronca(testo, limite):
    """Taglia all'ultimo spazio prima del limite: niente parole mozzate."""
    if len(testo) <= limite:
        return testo
    t = testo[:limite]
    sp = t.rfind(" ")
    return (t[:sp] if sp > limite * 0.6 else t).rstrip(" ,;:-") + "…"


def descrizione_articolo(a, tags):
    """Titolo + sommario ripulito + hashtag, sempre dentro i 500 caratteri."""
    titolo = a["title"].strip().rstrip(".")
    # «...rendila unica!» + «.» faceva «unica!.»
    punto = "" if titolo.endswith(("!", "?")) else "."
    sommario = ripulisci(a.get("summary"))
    if len(sommario) < 25:            # 23 articoli non hanno sommario
        sommario = "Guida di Dispensa Vintage, con foto e consigli pratici."
    avanzo = 500 - len(titolo) - len(tags) - 4
    return f"{titolo}{punto} {tronca(sommario, max(0, avanzo))} {tags}".strip()


# ---------- articoli del blog ----------
# «Come pulire l'ottone» non e' un articolo di arredamento: e' un restauro.
# Senza questo controllo finiva nella board della categoria dell'oggetto.
VERBI_GUIDA = ("come pulire", "come lucidare", "come restaurare", "come togliere",
               "come lavare", "come conservare", "come riparare", "come smacchiare",
               "come curare", "come rimuovere")


def board_per_articolo(titolo, tags, blog):
    """Prima i tutorial, poi il titolo (segnale forte: «vinile» -> board dei
    dischi), infine il blog di provenienza."""
    t = (titolo or "").lower()
    if any(t.startswith(v) or (" " + v) in t for v in VERBI_GUIDA):
        return BOARD_GUIDE
    testo = t + " " + " ".join(x.lower() for x in (tags or []))
    for name, kws, _ in BOARDS:
        if kws and any(k in testo for k in kws):
            return name
    return BOARD_PER_BLOG.get(blog, BOARD_GUIDE)


def collect_articoli(token, n_needed):
    q = '''query($c:String){blogs(first:20,after:$c){
        pageInfo{hasNextPage endCursor}
        nodes{handle articles(first:250){nodes{
          id title handle isPublished tags summary image{url}
          pinned:metafield(namespace:"custom",key:"pinterest_pinned"){value}}}}}}'''
    per_blog, cur = {}, None
    while True:
        d = gql(token, q, {"c": cur})["data"]["blogs"]
        for b in d["nodes"]:
            for a in b["articles"]["nodes"]:
                if not a.get("isPublished"): continue
                if not (a.get("image") or {}).get("url"): continue
                if (a.get("pinned") or {}).get("value") == "true": continue
                a["blog"] = b["handle"]
                per_blog.setdefault(b["handle"], []).append(a)
        if not d["pageInfo"]["hasNextPage"]: break
        cur = d["pageInfo"]["endCursor"]

    # A giro fra i blog invece che in fila: altrimenti il primo lotto esce tutto
    # da «arredamento» e una board sola si riempie mentre le altre restano vuote.
    # Pinterest premia i profili che si muovono su piu' temi.
    out, code = [], list(per_blog.values())
    while code and len(out) < n_needed:
        for coda in list(code):
            if not coda:
                code.remove(coda); continue
            out.append(coda.pop(0))
            if len(out) >= n_needed: break
    return out


def make_pin_articolo(token, board_id, a, board_name):
    """Compone il pin verticale e lo carica in base64: cosi' non serve ospitare
    l'immagine da nessuna parte."""
    media = _base64_pin(a["image"]["url"], a["title"], OCCHIELLO.get(a["blog"], "Vintage"))

    tags = HASHTAGS.get(board_name, "#modernariato #oggettivintage") + " " + COMMON_TAGS
    desc = descrizione_articolo(a, tags)
    body = {"board_id": board_id, "title": a["title"][:100], "description": desc,
            "link": f"{SITE}/blogs/{a['blog']}/{a['handle']}",
            "alt_text": a["title"][:500],
            "media_source": media}
    return pin_call("POST", "/pins", token, body)


def mark_pinned(token, pid):
    gql(token, 'mutation($m:[MetafieldsSetInput!]!){metafieldsSet(metafields:$m){userErrors{message}}}',
        {"m": [{"ownerId": pid, "namespace": "custom", "key": "pinterest_pinned",
                "type": "boolean", "value": "true"}]})

def _pinna(lista, boards, stok, ptok, come):
    """come = 'articolo' | 'prodotto'. Restituisce quanti ne ha pinnati."""
    done = 0
    for n in lista:
        if come == "articolo":
            bname = board_per_articolo(n.get("title"), n.get("tags"), n["blog"])
            fai = lambda: make_pin_articolo(ptok, boards[bname], n, bname)
        else:
            bname = board_for(n.get("productType"))
            fai = lambda: make_pin(ptok, boards[bname], n, bname)
        try:
            fai()
            mark_pinned(stok, n["id"])
            done += 1
            print(f"PIN OK  [{bname[:24]}] {n['title'][:38]}")
        except Exception as e:
            print(f"PIN ERR [{bname[:24]}] {n['title'][:38]}: {str(e)[:160]}")
    return done


def main():
    stok = shop_token()
    ptok = pin_token()
    boards = ensure_boards(ptok)

    # "misto": gli articoli hanno la precedenza e i prodotti riempiono il lotto.
    # Cosi' quando i 146 articoli finiscono il giro continua da solo sui prodotti,
    # senza che nessuno debba ricordarsi di cambiare impostazione.
    quota_art = 0 if MODO == "prodotti" else BATCH
    quota_pro = 0 if MODO == "articoli" else BATCH

    articoli = collect_articoli(stok, quota_art) if quota_art else []
    if MODO == "misto":
        quota_pro = BATCH - len(articoli)
    prodotti = collect(stok, quota_pro) if quota_pro > 0 else []

    if not articoli and not prodotti:
        print("Niente da pinnare: articoli e prodotti sono tutti già pinnati."); return

    fatti = _pinna(articoli, boards, stok, ptok, "articolo")
    fatti += _pinna(prodotti, boards, stok, ptok, "prodotto")
    print(f"--- pinnati {fatti}/{len(articoli) + len(prodotti)} "
          f"({len(articoli)} articoli, {len(prodotti)} prodotti) ---")

if __name__ == "__main__":
    main()
