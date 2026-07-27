# -*- coding: utf-8 -*-
"""Posta sul canale Telegram un contenuto a caso di Dispensa Vintage:
- PRODOTTO del negozio (~60%)
- GUIDA del blog (~30%, dai blog monetizzanti: collezionismo/guide/restauro-e-idee/tecnologia-vintage/stile-design)
- PRODOTTO AFFILIATO Amazon (~10%, selezione curata a tema collezionismo, con disclosure)
Esclude annunci privati (tag 'annunci' / vendor 'Annuncio privato'), negozi, buoni regalo.
Env: SHOPIFY_STORE, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL.
DRY_RUN=1 -> stampa i post senza inviarli (per test). Solo libreria standard (gira su GitHub Actions)."""
import os, json, random, re, urllib.request, urllib.parse, html

STORE = os.environ.get("SHOPIFY_STORE", "f64efc-d9.myshopify.com")
API = f"https://{STORE}/admin/api/2025-10/graphql.json"
SITE = "https://dispensavintage.it"

# --- esclusioni prodotti ---
EXCLUDE_TYPES = {"Negozi vintage", "Annuncio privato", "Annunci", "Buoni regalo"}
EXCLUDE_TAGS = {"annunci"}                 # convenzione annunci utente (vedi memoria)
EXCLUDE_VENDORS = {"Annuncio privato"}

# --- mix dei contenuti (le probabilita' devono sommare a <=1; il resto = prodotti negozio) ---
AFFILIATE_PROB = 0.10                       # quota post = prodotto affiliato Amazon
GUIDE_PROB = 0.30                           # quota post = guida del blog
# prodotti negozio = 1 - AFFILIATE_PROB - GUIDE_PROB (~0.60)

# guide: pesca in via prioritaria da questi blog (contenuti monetizzanti); fallback a tutti i pubblicati
MONEY_BLOGS = {"collezionismo", "guide", "restauro-e-idee", "tecnologia-vintage", "stile-design"}
EXCLUDE_BLOGS = {"eventi-e-fiere"}          # blog da NON postare mai (eventi con date passate)

# --- selezione affiliata curata (nome, beneficio, short link Amazon con tag incorporato) ---
AFFILIATE = [
    ("Lente d'ingrandimento con luce LED", "Per esaminare marchi, conii e dettagli di monete, francobolli e piccoli oggetti.", "https://link.amazon/B0ehccAJT"),
    ("Capsule protettive per monete", "Proteggono le monete da graffi e ossidazione, preservandone il valore.", "https://link.amazon/B09J1gzYM"),
    ("Kit di pulizia per dischi in vinile", "Pulizia profonda e sicura dei 33 giri, per un ascolto senza fruscii.", "https://link.amazon/B0fMm6nWX"),
    ("Spazzola antistatica per vinili", "Rimuove polvere e cariche statiche dal disco prima dell'ascolto.", "https://link.amazon/B0eKMClcw"),
    ("Buste interne antistatiche per vinili", "Proteggono i dischi da polvere e micrograffi.", "https://link.amazon/B0b8YEnTD"),
    ("Lucidante per metalli (ottone, rame, bronzo)", "Ridona brillantezza agli oggetti in metallo senza rovinarli.", "https://link.amazon/B0aCswX9B"),
    ("Detergente specifico per argento", "Rimuove l'ossidazione da argento e argenteria in pochi minuti.", "https://link.amazon/B09Hy5wiq"),
    ("Album raccoglitore per collezioni", "Per conservare in ordine cartoline, figurine e piccola carta da collezione.", "https://link.amazon/B029rmryI"),
    ("Vetrinetta espositiva", "Espone e protegge dalla polvere i pezzi piu preziosi della collezione.", "https://link.amazon/B06GzXTSS"),
    ("Teca espositiva da collezione", "Mette in mostra spille, gadget e memorabilia.", "https://link.amazon/B05btODIN"),
    ("Raccoglitore per schede telefoniche", "Con fogli dedicati per ordinare la collezione di schede.", "https://link.amazon/B0fPmuqsE"),
    ("Fogli porta-schede trasparenti", "Tasche protettive per schede telefoniche e tessere.", "https://link.amazon/B0bqSOvG4"),
    ("Giradischi in stile vintage", "Per riascoltare i tuoi 33 e 45 giri con un look retro.", "https://link.amazon/B0b5HwQHs"),
    ("Fotocamera istantanea Polaroid", "Il fascino dell'istantanea, in versione moderna.", "https://link.amazon/B0iRyZ6rg"),
    ("Ricevitore Bluetooth per impianti hi-fi", "Collega amplificatori e casse vintage allo smartphone.", "https://link.amazon/B08NJJ6S6"),
    ("Speaker Bluetooth", "Diffusore compatto dal design retro.", "https://link.amazon/B0eCB5FEW"),
    ("Pinzette filateliche", "Per maneggiare i francobolli senza rovinarli.", "https://link.amazon/B06DyNser"),
    ("Classificatore per francobolli", "Album con taschine per ordinare e proteggere la collezione.", "https://link.amazon/B0bmwvaOK"),
    ("Album per banconote", "Conserva le banconote in Lire piatte e al riparo dall'umidita.", "https://link.amazon/B0gilta9L"),
    ("Fogli porta-banconote", "Tasche trasparenti per proteggere le banconote da collezione.", "https://link.amazon/B06gT0DYj"),
    ("Kit per sbiancare la plastica ingiallita", "Ridona il colore originale a console e giocattoli anni '80-'90.", "https://link.amazon/B02tRswhL"),
    ("Custodie protettive per VHS", "Proteggono le videocassette da polvere e graffi.", "https://link.amazon/B084SKoCg"),
    ("Crema per la cura della pelle vintage", "Nutre e protegge borse, cinture e portafogli in pelle.", "https://link.amazon/B0f6zg5Ak"),
    ("Cera per legno", "Nutre e protegge mobili e oggetti in legno d'epoca.", "https://link.amazon/B0fpmfZtb"),
    ("Convertitore di ruggine in gel", "Blocca e neutralizza la ruggine su ferro e metalli d'epoca.", "https://link.amazon/B0dnmI922"),
    ("Colla specifica per ceramica e porcellana", "Ripara con precisione ceramiche e porcellane.", "https://link.amazon/B0enPFEql"),
    ("Scanner per foto, diapositive e negativi", "Digitalizza e salva le vecchie fotografie di famiglia.", "https://link.amazon/B0aCMTDki"),
    ("Panno per lucidare l'oro e i gioielli", "Ravviva oro e gioielli senza abrasivi.", "https://link.amazon/B04cOxYkA"),
]

FOOTER = (
    "\n\n- - - - - - - - - - \n"
    "🥰 Seguici anche su Instagram!\n"
    "👉 https://www.instagram.com/dispensa.vintage/\n\n"
    "- - - - - - - - - - \n"
    "➡️ Scarica l'app per iPhone su App Store\n"
    "👉 https://apps.apple.com/it/app/dispensa-vintage/id6754877811"
)

def get_token():
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": os.environ["SHOPIFY_CLIENT_ID"],
        "client_secret": os.environ["SHOPIFY_CLIENT_SECRET"],
    }).encode()
    req = urllib.request.Request(f"https://{STORE}/admin/oauth/access_token", data=data)
    return json.load(urllib.request.urlopen(req))["access_token"]

def gql(token, query, variables=None):
    req = urllib.request.Request(API, data=json.dumps({"query": query, "variables": variables or {}}).encode(),
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": token})
    return json.load(urllib.request.urlopen(req))

def clip(text, n=180, fallback=""):
    text = " ".join(re.sub("<[^>]+>", " ", text or "").split())
    if len(text) > n:
        text = text[:n].rsplit(" ", 1)[0] + "…"
    return text or fallback

# ---------- PRODOTTI NEGOZIO ----------
def pick_product(token):
    cands, cur = [], None
    while True:
        d = gql(token, '''query($c:String){products(first:250,after:$c,query:"status:active"){
            pageInfo{hasNextPage endCursor} nodes{id productType vendor tags totalInventory}}}''',
            {"c": cur})["data"]["products"]
        for n in d["nodes"]:
            if (n["productType"] or "") in EXCLUDE_TYPES: continue
            if (n.get("vendor") or "") in EXCLUDE_VENDORS: continue
            if EXCLUDE_TAGS & set(t.lower() for t in (n.get("tags") or [])): continue
            if (n["totalInventory"] or 0) > 0: cands.append(n["id"])
        if d["pageInfo"]["hasNextPage"]: cur = d["pageInfo"]["endCursor"]
        else: break
    if not cands: return None
    pid = random.choice(cands)
    p = gql(token, '''query($id:ID!){product(id:$id){title handle onlineStoreUrl description
        seo{description} featuredImage{url} variants(first:1){nodes{price compareAtPrice}}}}''',
        {"id": pid})["data"]["product"]
    return p

def build_product(p):
    title = p["title"].strip()
    v = p["variants"]["nodes"][0] if p["variants"]["nodes"] else {}
    price = v.get("price"); cmp = v.get("compareAtPrice")
    url = p.get("onlineStoreUrl") or f"{SITE}/products/{p['handle']}"
    img = (p.get("featuredImage") or {}).get("url")
    desc = clip((p.get("seo") or {}).get("description") or p.get("description"),
                fallback="Un pezzo vintage selezionato per te.")
    if price and cmp and float(cmp) > float(price):
        offer = f"🔥 In offerta: <s>{float(cmp):.0f}€</s> → <b>{float(price):.0f}€</b>"
    elif price:
        offer = f"🔥 Disponibile ora a <b>{float(price):.0f}€</b>"
    else:
        offer = "🔥 Disponibile ora!"
    caption = (f"🟥 <b>{html.escape(title, quote=False)}</b>\n"
               f"⭐ {html.escape(desc, quote=False)}\n\n"
               f"{offer}\n"
               f"✅ {url}" + FOOTER)
    return caption, img

# ---------- GUIDE BLOG ----------
def pick_guide(token):
    money, other, cur = [], [], None
    while True:
        d = gql(token, '''query($c:String){articles(first:250,after:$c){
            pageInfo{hasNextPage endCursor}
            nodes{title handle isPublished image{url} summary blog{handle}}}}''',
            {"c": cur})["data"]["articles"]
        for n in d["nodes"]:
            if not (n.get("isPublished") and n.get("blog")): continue
            bh = n["blog"]["handle"]
            if bh in EXCLUDE_BLOGS: continue
            (money if bh in MONEY_BLOGS else other).append(n)
        if d["pageInfo"]["hasNextPage"]: cur = d["pageInfo"]["endCursor"]
        else: break
    pool = money or other
    return random.choice(pool) if pool else None

def build_guide(a):
    title = a["title"].strip()
    url = f"{SITE}/blogs/{a['blog']['handle']}/{a['handle']}"
    img = (a.get("image") or {}).get("url")
    summ = clip(a.get("summary"), fallback="Un approfondimento dal nostro blog vintage.")
    caption = (f"📖 <b>{html.escape(title, quote=False)}</b>\n"
               f"⭐ {html.escape(summ, quote=False)}\n\n"
               f"📚 Leggi la guida completa sul blog 👇\n"
               f"✅ {url}" + FOOTER)
    return caption, img

# ---------- PRODOTTI AFFILIATI AMAZON ----------
def pick_affiliate():
    name, benefit, url = random.choice(AFFILIATE)
    return {"title": name, "benefit": benefit, "url": url}

def build_affiliate(a):
    caption = (f"🛒 <b>{html.escape(a['title'], quote=False)}</b>\n"
               f"⭐ {html.escape(a['benefit'], quote=False)}\n\n"
               f"💡 Un consiglio utile per curare e custodire i tuoi pezzi vintage.\n"
               f"✅ {a['url']}\n"
               f"<i>🔖 Link affiliato Amazon</i>" + FOOTER)
    return caption, None  # niente immagine: Telegram genera l'anteprima dal link Amazon

# ---------- TELEGRAM ----------
def tg(method, payload):
    tok = os.environ["TELEGRAM_BOT_TOKEN"]
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/{method}",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

def main():
    token = get_token()
    r = random.random()
    kind, item = None, None
    if r < AFFILIATE_PROB:
        item = pick_affiliate(); kind = "affiliate"
    elif r < AFFILIATE_PROB + GUIDE_PROB:
        item = pick_guide(token)
        if item: kind = "guide"
    if item is None:
        item = pick_product(token)
        if item: kind = "product"
    if item is None:
        print("Nessun contenuto disponibile."); return

    if kind == "affiliate":
        caption, img = build_affiliate(item)
    elif kind == "guide":
        caption, img = build_guide(item)
    else:
        caption, img = build_product(item)

    if os.environ.get("DRY_RUN"):
        print(f"--- DRY_RUN [{kind}] -> {item['title']} ---\n{caption}\n(img: {img})")
        return

    chat = os.environ["TELEGRAM_CHANNEL"]
    if img:
        r = tg("sendPhoto", {"chat_id": chat, "photo": img, "caption": caption[:1024], "parse_mode": "HTML"})
    else:
        r = tg("sendMessage", {"chat_id": chat, "text": caption, "parse_mode": "HTML", "disable_web_page_preview": False})
    print("OK" if r.get("ok") else "ERRORE", f"[{kind}] ->", item["title"], "| tg:", r.get("ok"), r.get("description", ""))

if __name__ == "__main__":
    main()
