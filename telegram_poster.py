# -*- coding: utf-8 -*-
"""Posta un prodotto disponibile a caso dello shop sul canale Telegram."""
import os, json, random, urllib.request, urllib.parse, html

STORE = os.environ.get("SHOPIFY_STORE", "f64efc-d9.myshopify.com")
API = f"https://{STORE}/admin/api/2025-01/graphql.json"
EXCLUDE_TYPES = {"Negozi vintage", "Annuncio privato", "Annunci", "Buoni regalo"}
SITE = "https://dispensavintage.it"

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

def pick_product(token):
    cands, cur = [], None
    while True:
        d = gql(token, '''query($c:String){products(first:250,after:$c,query:"status:active"){
            pageInfo{hasNextPage endCursor} nodes{id productType totalInventory}}}''', {"c": cur})["data"]["products"]
        for n in d["nodes"]:
            if (n["productType"] or "") in EXCLUDE_TYPES: continue
            if (n["totalInventory"] or 0) > 0: cands.append(n["id"])
        if d["pageInfo"]["hasNextPage"]: cur = d["pageInfo"]["endCursor"]
        else: break
    if not cands: return None
    pid = random.choice(cands)
    p = gql(token, '''query($id:ID!){product(id:$id){title handle onlineStoreUrl description
        seo{description} featuredImage{url} variants(first:1){nodes{price compareAtPrice}}}}''', {"id": pid})["data"]["product"]
    return p

def tg(method, payload):
    tok = os.environ["TELEGRAM_BOT_TOKEN"]
    req = urllib.request.Request(f"https://api.telegram.org/bot{tok}/{method}",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))

def main():
    token = get_token()
    p = pick_product(token)
    if not p:
        print("Nessun prodotto disponibile."); return
    title = p["title"].strip()
    v = p["variants"]["nodes"][0] if p["variants"]["nodes"] else {}
    price = v.get("price"); cmp = v.get("compareAtPrice")
    url = p.get("onlineStoreUrl") or f"{SITE}/products/{p['handle']}"
    img = (p.get("featuredImage") or {}).get("url")
    desc = ((p.get("seo") or {}).get("description") or p.get("description") or "").strip()
    desc = " ".join(desc.split())
    if len(desc) > 180:
        desc = desc[:180].rsplit(" ", 1)[0] + "…"
    if not desc:
        desc = "Un pezzo vintage selezionato per te."
    if price and cmp and float(cmp) > float(price):
        offer = f"🔥 In offerta: <s>{float(cmp):.0f}€</s> → <b>{float(price):.0f}€</b>"
    elif price:
        offer = f"🔥 Disponibile ora a <b>{float(price):.0f}€</b>"
    else:
        offer = "🔥 Disponibile ora!"
    caption = (
        f"🟥 <b>{html.escape(title)}</b>\n"
        f"⭐ {html.escape(desc)}\n\n"
        f"{offer}\n"
        f"✅ {url}\n\n"
        f"- - - - - - - - - - \n"
        f"🥰 Seguici anche su Instagram!\n"
        f"👉 https://www.instagram.com/dispensa.vintage/\n\n"
        f"- - - - - - - - - - \n"
        f"➡️ Scarica l'app per iPhone su App Store\n"
        f"👉 https://apps.apple.com/it/app/dispensa-vintage/id6754877811"
    )
    chat = os.environ["TELEGRAM_CHANNEL"]
    if img:
        r = tg("sendPhoto", {"chat_id": chat, "photo": img, "caption": caption[:1024], "parse_mode": "HTML"})
    else:
        r = tg("sendMessage", {"chat_id": chat, "text": caption, "parse_mode": "HTML", "disable_web_page_preview": False})
    print("OK" if r.get("ok") else "ERRORE", "->", title, "| tg:", r.get("ok"), r.get("description", ""))

if __name__ == "__main__":
    main()
