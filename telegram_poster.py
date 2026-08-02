# -*- coding: utf-8 -*-
"""Posta sul canale Telegram un contenuto di Dispensa Vintage.

MODALITA NORMALE (default): PRODOTTO del negozio (~70%) o GUIDA del blog (~30%),
con bottone "Vedi su Dispensa Vintage".
MODALITA AFFILIATI (env POST_MODE=affiliate): un PRODOTTO AFFILIATO Amazon dalla
selezione curata, con anteprima immagine + bottone "Acquista su Amazon" + disclosure.

Le emoji sono scritte come escape ASCII (\\Uxxxxxxxx) cosi il file resta puro ASCII
ed e' immune alla corruzione di codifica quando si incolla su GitHub.

Env: SHOPIFY_STORE, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL.
DRY_RUN=1 -> stampa i post senza inviarli. Solo libreria standard (gira su GitHub Actions)."""
import os, json, random, re, urllib.request, urllib.parse, html

STORE = os.environ.get("SHOPIFY_STORE", "f64efc-d9.myshopify.com")
API = f"https://{STORE}/admin/api/2025-10/graphql.json"
SITE = "https://dispensavintage.it"

# --- emoji/simboli come escape ASCII (immuni alla corruzione di codifica) ---
RED    = "\U0001F7E5"; STAR  = "\U00002B50"; FIRE  = "\U0001F525"; CHECK = "\U00002705"
BOOM   = "\U0001F4A5"; BOOK  = "\U0001F4D6"; BOOKS = "\U0001F4DA"; CART  = "\U0001F6D2"
BULB   = "\U0001F4A1"; BMARK = "\U0001F516"; LOVE  = "\U0001F970"; POINT = "\U0001F449"
DOWN   = "\U0001F447"; ARROWR = "\U000027A1\U0000FE0F"; EUR = "\U000020AC"; TO = "\U00002192"
GIFT   = "\U0001F381"; EYES = "\U0001F440"; TROPHY = "\U0001F3C6"; BRICK = "\U0001F9F1"

# titoli-hook per i post LEGO (onesti: consiglio/opinione, NON claim su prezzo/scorte/offerte)
LEGO_HEADERS = [
    f"{BRICK} DA NON PERDERE",
    f"{TROPHY} TOP PER I COLLEZIONISTI",
    f"{GIFT} PERFETTA IDEA REGALO",
    f"{FIRE} PEZZO DA AVERE IN COLLEZIONE",
    f"{EYES} DAI UN'OCCHIATA SU AMAZON",
]

# --- esclusioni prodotti ---
EXCLUDE_TYPES = {"Negozi vintage", "Annuncio privato", "Annunci", "Buoni regalo"}
EXCLUDE_TAGS = {"annunci"}
EXCLUDE_VENDORS = {"Annuncio privato"}

# --- modalita normale: quota guide (resto = prodotti). Gli affiliati hanno un flusso dedicato (POST_MODE=affiliate). ---
GUIDE_PROB = 0.30
MONEY_BLOGS = {"collezionismo", "guide", "restauro-e-idee", "tecnologia-vintage", "stile-design"}
EXCLUDE_BLOGS = {"eventi-e-fiere"}

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
    ("Pile a bottone assortite", "Per far ripartire orologi e sveglie al quarzo.", "https://link.amazon/B0bd6bUwo"),
    ("Kit attrezzi da orologiaio", "Per aprire il fondello e cambiare pila o cinturino in sicurezza.", "https://link.amazon/B0eUuwSWi"),
    ("Panno in microfibra per orologi", "Per lucidare cassa e vetro senza graffiare.", "https://link.amazon/B09OZHnH2"),
    ("Rullino pellicola 35mm", "Per tornare a scattare con le fotocamere analogiche.", "https://link.amazon/B01C8dsbF"),
    ("Kit pulizia obiettivi fotografici", "Soffietto e panno per togliere la polvere da lenti e corpo macchina.", "https://link.amazon/B0cnQIKt4"),
    ("Borsa/custodia per fotocamera", "Per proteggere la macchina da urti, polvere e umidita.", "https://link.amazon/B0fFlb7Ga"),
    ("Ganci per appendere quadri e targhe pesanti", "Per esporre targhe in metallo in sicurezza, senza cadute.", "https://link.amazon/B03O6iT9i"),
]

# --- selezione affiliata LEGO (tag brick067-21 gia incorporato negli short link). Usata con POST_MODE=lego. ---
# 4o campo = immagine prodotto (Amazon per ASIN) -> foto grande via sendPhoto.
_AIMG = "https://images-na.ssl-images-amazon.com/images/P/{}.jpg"
LEGO_AFFILIATE = [
    ("LEGO Trofeo Coppa del Mondo FIFA (43020)", "Il trofeo del calcio in mattoncini, da montare ed esporre. Idea regalo per tifosi.", "https://link.amazon/B0eoxeDcW", _AIMG.format("B0FPXDRR63")),
    ("Funko POP! Pokemon - Charizard", "La figure di Charizard da collezione, perfetta sullo scaffale dei fan Pokemon.", "https://link.amazon/B0dsDQDWs", _AIMG.format("B0BSNV3F6J")),
    ("LEGO One Piece - Nave Going Merry (75639)", "La nave Going Merry con 5 minifigure tra cui Luffy, Zoro e Nami. Per i fan di One Piece.", "https://link.amazon/B06EO57Xs", _AIMG.format("B0DWDQYB87")),
    ("LEGO Speed Champions Ferrari F1 SF-24 (77242)", "La monoposto di Formula 1 con minifigure del pilota, da costruire ed esporre.", "https://link.amazon/B06aoGIug", _AIMG.format("B0DHSBBV6R")),
    ("LEGO Speed Champions Mercedes-AMG F1 W15 (77244)", "La Mercedes di Formula 1 in mattoncini, con minifigure del pilota.", "https://link.amazon/B08t610eD", _AIMG.format("B0DHS9Y433")),
    ("LEGO Botanicals Albicocco Giapponese (10369)", "Fiore artificiale in mattoncini: decora casa senza acqua e senza cure.", "https://link.amazon/B00091OUL", _AIMG.format("B00CALQB1E")),
    ("LEGO Botanicals Albero Bonsai (10281)", "Il bonsai in mattoncini con vaso: decorativo e sempre in forma.", "https://link.amazon/B02wVyys8", _AIMG.format("B08G4PCG8F")),
    ("LEGO Super Mario Game Boy (72046)", "Il Game Boy in mattoncini con cartucce a schermo lenticolare. Regalo retro per i fan dei videogiochi.", "https://link.amazon/B0hgP3Igl", _AIMG.format("B0DWDGVHM6")),
    ("LEGO Technic Ferrari F1 SF-24 scala 1:8 (42207)", "Modello dettagliato in scala 1:8 con motore V6, cambio, sterzo e DRS.", "https://link.amazon/B0dMJSCpk", _AIMG.format("B0DHSCYDL2")),
    ("LEGO Botanicals Bonsai Acero Rosso Giapponese (10348)", "Bonsai con foglie rosse e arancio e vaso costruibile, da esporre.", "https://link.amazon/B0aScKUsS", _AIMG.format("B0DWF6VKYB")),
    ("LEGO Casco Lewis Hamilton Scuderia Ferrari F1 (43022)", "Il casco di Hamilton in mattoncini con minifigure da collezione. Per i fan della F1.", "https://link.amazon/B03TkiLyx", _AIMG.format("B0FPXFB54W")),
    ("LEGO Icons Signore degli Anelli - Elmo di Sauron (11373)", "L'elmo di Sauron con l'Unico Anello e una minifigure. Per i fan della saga.", "https://link.amazon/B0fEbjIDU", _AIMG.format("B01N4NJ3HX")),
    ("LEGO DeLorean Ritorno al Futuro (77256)", "La macchina del tempo con Doc Brown e Marty McFly. Per i fan del film.", "https://link.amazon/B0ioBsbUT", _AIMG.format("B0FPXDXXYR")),
]

FOOTER = (
    "\n\n- - - - - - - - - - \n"
    f"{LOVE} Seguici anche su Instagram!\n"
    f"{POINT} https://www.instagram.com/dispensa.vintage/\n\n"
    "- - - - - - - - - - \n"
    f"{ARROWR} Scarica l'app per iPhone su App Store\n"
    f"{POINT} https://apps.apple.com/it/app/dispensa-vintage/id6754877811"
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
        text = text[:n].rsplit(" ", 1)[0] + "\u2026"
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
        offer = f"{FIRE} In offerta: <s>{float(cmp):.0f}{EUR}</s> {TO} <b>{float(price):.0f}{EUR}</b>"
    elif price:
        offer = f"{FIRE} Disponibile ora a <b>{float(price):.0f}{EUR}</b>"
    else:
        offer = f"{FIRE} Disponibile ora!"
    caption = (f"{RED} <b>{html.escape(title, quote=False)}</b>\n"
               f"{STAR} {html.escape(desc, quote=False)}\n\n"
               f"{offer}\n"
               f"{CHECK} {url}" + FOOTER)
    return caption, img, (f"{BOOM} Vedi su Dispensa Vintage {BOOM}", url)

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
    caption = (f"{BOOK} <b>{html.escape(title, quote=False)}</b>\n"
               f"{STAR} {html.escape(summ, quote=False)}\n\n"
               f"{BOOKS} Leggi la guida completa sul blog {DOWN}\n"
               f"{CHECK} {url}" + FOOTER)
    return caption, img, (f"{BOOK} Leggi la guida", url)

# ---------- PRODOTTI AFFILIATI AMAZON ----------
def pick_affiliate():
    name, benefit, url = random.choice(AFFILIATE)
    return {"title": name, "benefit": benefit, "url": url}

def pick_lego():
    name, benefit, url, img = random.choice(LEGO_AFFILIATE)
    return {"title": name, "benefit": benefit, "url": url, "image": img}

def build_affiliate(a, footer=FOOTER, header=None):
    head = f"<b>{header}</b>\n\n" if header else ""
    caption = (head +
               f"{CART} <b>{html.escape(a['title'], quote=False)}</b>\n"
               f"{STAR} {html.escape(a['benefit'], quote=False)}\n\n"
               f"{BULB} Prezzo e disponibilita cambiano spesso su Amazon: controlla l'offerta attuale {DOWN}\n"
               f"{CHECK} {a['url']}\n"
               f"<i>{BMARK} Link affiliato Amazon</i>" + footer)
    # con immagine -> sendPhoto (foto grande); senza -> anteprima automatica del link
    return caption, a.get("image"), (f"{CART} ACQUISTA SU AMAZON", a['url'])

# ---------- TELEGRAM ----------
def tg(method, payload):
    tok = os.environ["TELEGRAM_BOT_TOKEN"]
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/{method}",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

def send(chat, caption, img, button, preview_url=None):
    markup = {"inline_keyboard": [[{"text": button[0], "url": button[1]}]]} if button else None
    if img:
        payload = {"chat_id": chat, "photo": img, "caption": caption[:1024], "parse_mode": "HTML"}
        if markup: payload["reply_markup"] = markup
        return tg("sendPhoto", payload)
    payload = {"chat_id": chat, "text": caption, "parse_mode": "HTML"}
    if preview_url:
        # anteprima immagine GRANDE e sopra il testo (Telegram prende la foto dal link, in modo conforme)
        payload["link_preview_options"] = {"url": preview_url, "prefer_large_media": True, "show_above_text": True}
    else:
        payload["link_preview_options"] = {"is_disabled": True}
    if markup: payload["reply_markup"] = markup
    return tg("sendMessage", payload)

def main():
    mode = os.environ.get("POST_MODE", "")
    kind, item = None, None
    if mode == "affiliate":
        item = pick_affiliate(); kind = "affiliate"
    elif mode == "lego":
        item = pick_lego(); kind = "affiliate"
    else:
        token = get_token()  # serve solo per prodotti/guide (Shopify)
        if random.random() < GUIDE_PROB:
            item = pick_guide(token)
            if item: kind = "guide"
        if item is None:
            item = pick_product(token)
            if item: kind = "product"
    if item is None:
        print("Nessun contenuto disponibile."); return

    if kind == "affiliate":
        _header = random.choice(LEGO_HEADERS) if mode == "lego" else None
        caption, img, button = build_affiliate(item, footer=("" if mode == "lego" else FOOTER), header=_header)
    elif kind == "guide":
        caption, img, button = build_guide(item)
    else:
        caption, img, button = build_product(item)

    if os.environ.get("DRY_RUN"):
        print(f"--- DRY_RUN [{kind}] -> {item['title']} ---\n{caption}\n(img: {img})\n(button: {button})")
        return

    preview = item["url"] if kind == "affiliate" else None
    # TELEGRAM_CHANNEL puo' contenere piu' canali separati da virgola -> posta a tutti
    chats = [c.strip() for c in os.environ["TELEGRAM_CHANNEL"].split(",") if c.strip()]
    for chat in chats:
        r = send(chat, caption, img, button, preview)
        print("OK" if r.get("ok") else "ERRORE", f"[{kind}] {chat} ->", item["title"], "| tg:", r.get("ok"), r.get("description", ""))

if __name__ == "__main__":
    main()
