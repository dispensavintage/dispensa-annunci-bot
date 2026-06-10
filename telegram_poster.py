# -*- coding: utf-8 -*-
"""Posta sul canale Telegram un contenuto a caso di Dispensa Vintage:
un PRODOTTO del negozio (~85%) oppure un ARTICOLO del blog (~15%, escluso "Eventi e Fiere").
Esclude annunci privati degli utenti (tag 'annunci' / vendor 'Annuncio privato'),
negozi, buoni regalo. Env: SHOPIFY_STORE, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET,
TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL. Solo libreria standard (gira su GitHub Actions)."""
import os, json, random, re, urllib.request, urllib.parse, html

STORE = os.environ.get("SHOPIFY_STORE", "f64efc-d9.myshopify.com")
API = f"https://{STORE}/admin/api/2025-01/graphql.json"
SITE = "https://dispensavintage.it"

# --- esclusioni prodotti ---
EXCLUDE_TYPES = {"Negozi vintage", "Annuncio privato", "Annunci", "Buoni regalo"}
EXCLUDE_TAGS = {"annunci"}                 # convenzione annunci utente (vedi memoria)
EXCLUDE_VENDORS = {"Annuncio privato"}
ARTICLE_PROB = 0.15                        # quota di post che sono articoli (resto = prodotti)
EXCLUDE_BLOGS = {"eventi-e-fiere"}         # blog da NON postare (eventi con date passate)

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

# ---------- PRODOTTI ----------
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

# ---------- ARTICOLI BLOG ----------
def pick_article(token):
    arts, cur = [], None
    while True:
        d = gql(token, '''query($c:String){articles(first:250,after:$c){
            pageInfo{hasNextPage endCursor}
            nodes{title handle isPublished image{url} summary blog{handle}}}}''',
            {"c": cur})["data"]["articles"]
        for n in d["nodes"]:
            if n.get("isPublished") and n.get("blog") and n["blog"]["handle"] not in EXCLUDE_BLOGS:
                arts.append(n)
        if d["pageInfo"]["hasNextPage"]: cur = d["pageInfo"]["endCursor"]
        else: break
    return random.choice(arts) if arts else None

def build_article(a):
    title = a["title"].strip()
    url = f"{SITE}/blogs/{a['blog']['handle']}/{a['handle']}"
    img = (a.get("image") or {}).get("url")
    summ = clip(a.get("summary"), fallback="Un approfondimento dal nostro blog vintage.")
    caption = (f"📖 <b>{html.escape(title, quote=False)}</b>\n"
               f"⭐ {html.escape(summ, quote=False)}\n\n"
               f"📚 Leggi l'articolo completo sul blog 👇\n"
               f"✅ {url}" + FOOTER)
    return caption, img

# ---------- TELEGRAM ----------
def tg(method, payload):
    tok = os.environ["TELEGRAM_BOT_TOKEN"]
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/{method}",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

def main():
    token = get_token()
    kind, item = None, None
    if random.random() < ARTICLE_PROB:
        item = pick_article(token)
        if item: kind = "article"
    if item is None:
        item = pick_product(token)
        if item: kind = "product"
    if item is None:
        print("Nessun contenuto disponibile."); return

    caption, img = build_article(item) if kind == "article" else build_product(item)
    chat = os.environ["TELEGRAM_CHANNEL"]
    if img:
        r = tg("sendPhoto", {"chat_id": chat, "photo": img, "caption": caption[:1024], "parse_mode": "HTML"})
    else:
        r = tg("sendMessage", {"chat_id": chat, "text": caption, "parse_mode": "HTML", "disable_web_page_preview": False})
    print("OK" if r.get("ok") else "ERRORE", f"[{kind}] ->", item["title"], "| tg:", r.get("ok"), r.get("description", ""))

if __name__ == "__main__":
    main()
