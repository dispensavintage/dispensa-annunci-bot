#!/usr/bin/env python3
# Dispensa Vintage - bot annunci: legge le email di submission "Vendi un oggetto"
# e crea il prodotto-annuncio in BOZZA. Stdlib only.
import os, re, ssl, json, html, imaplib, email, urllib.request
from email.header import decode_header

STORE = "f64efc-d9.myshopify.com"
API = "2025-01"
ANNUNCI_COLLECTION = "gid://shopify/Collection/520816099596"
SUBJECT_MATCH = "Vendi un oggetto"
LABELS = ["Nome","Email","Immagine 1","Immagine 2","Immagine 3","Titolo",
          "Descrivi il tuo articolo","Categoria","Condizioni","Prezzo","Città","Citta"]
STOPS = ("Visualizza invii","Gestisci notifiche","Shopify |","© Shopify","151 O'Connor")

def env(k):
    v = os.environ.get(k);
    if not v: raise SystemExit("Manca il secret/variabile: "+k)
    return v

# ---------- Shopify ----------
def get_token():
    data = urllib.parse.urlencode({"grant_type":"client_credentials",
        "client_id":env("SHOPIFY_CLIENT_ID"),"client_secret":env("SHOPIFY_CLIENT_SECRET")}).encode()
    req = urllib.request.Request(f"https://{STORE}/admin/oauth/access_token", data=data)
    with urllib.request.urlopen(req) as r: return json.load(r)["access_token"]

def gql(token, query, variables=None):
    body = json.dumps({"query":query,"variables":variables or {}}).encode()
    req = urllib.request.Request(f"https://{STORE}/admin/api/{API}/graphql.json", data=body,
        headers={"X-Shopify-Access-Token":token,"Content-Type":"application/json"})
    with urllib.request.urlopen(req) as r: return json.load(r)

def resolve_images(token, gids):
    if not gids: return []
    d = gql(token, "query($ids:[ID!]!){nodes(ids:$ids){... on MediaImage{image{url} preview{image{url}}}}}", {"ids":gids})
    urls=[]
    for n in d.get("data",{}).get("nodes",[]):
        if not n: continue
        u = (n.get("image") or {}).get("url") or (n.get("preview") or {}).get("image",{}).get("url")
        if u: urls.append(u)
    return urls

def gen_seo(title, citta, desc):
    st = (title + " | Dispensa Vintage")[:70]
    base = f"{title}. {desc}".strip()
    if citta: base = f"{title}. Si trova a {citta}. {desc}".strip()
    sd = (base[:152].rstrip()+"…") if len(base)>153 else base
    return st, sd

def create_listing(token, f, img_urls):
    title = f.get("Titolo") or f.get("Descrivi il tuo articolo") or "Annuncio vintage"
    desc = f.get("Descrivi il tuo articolo","")
    citta = f.get("Città") or f.get("Citta") or ""
    cat = f.get("Categoria","")
    cond = f.get("Condizioni","")
    price = re.sub(r"[^0-9.,]","",f.get("Prezzo","0")).replace(",",".") or "0"
    st, sd = gen_seo(title, citta, desc)
    body = f"<p>{html.escape(desc)}</p>"
    if citta: body += f"<p>Si trova a {html.escape(citta)}.</p>"
    mf = [{"namespace":"custom","key":"seller_name","type":"single_line_text_field","value":f.get("Nome","")},
          {"namespace":"custom","key":"seller_email","type":"single_line_text_field","value":f.get("Email","")}]
    if cond: mf.append({"namespace":"custom","key":"condizione","type":"single_line_text_field","value":cond})
    if citta: mf.append({"namespace":"custom","key":"citta","type":"single_line_text_field","value":citta})
    mf = [m for m in mf if m["value"]]
    pin = {"title":title,"descriptionHtml":body,"productType":cat,"vendor":"Annuncio privato",
           "tags":["annunci"]+([cat] if cat else []),"status":"DRAFT","templateSuffix":"annuncio",
           "seo":{"title":st,"description":sd},"metafields":mf}
    r = gql(token,"""mutation C($i:ProductInput!){productCreate(input:$i){product{id variants(first:1){nodes{id}}} userErrors{field message}}}""",{"i":pin})
    res = r["data"]["productCreate"]
    if res["userErrors"]: raise RuntimeError("productCreate: "+str(res["userErrors"]))
    pid = res["product"]["id"]; vid = res["product"]["variants"]["nodes"][0]["id"]; num = pid.split("/")[-1]
    gql(token,"""mutation P($p:ID!,$v:[ProductVariantsBulkInput!]!){productVariantsBulkUpdate(productId:$p,variants:$v){userErrors{message}}}""",{"p":pid,"v":[{"id":vid,"price":price}]})
    gql(token,"""mutation S($mf:[MetafieldsSetInput!]!){metafieldsSet(metafields:$mf){userErrors{message}}}""",{"mf":[{"ownerId":pid,"namespace":"custom","key":"listing_ref","type":"single_line_text_field","value":"DV-A-"+num[-6:]}]})
    if img_urls:
        gql(token,"""mutation M($p:ID!,$m:[CreateMediaInput!]!){productCreateMedia(productId:$p,media:$m){mediaUserErrors{message}}}""",
            {"p":pid,"m":[{"originalSource":u,"mediaContentType":"IMAGE","alt":title} for u in img_urls]})
    gql(token,"""mutation A($id:ID!,$p:[ID!]!){collectionAddProducts(id:$id,productIds:$p){userErrors{message}}}""",{"id":ANNUNCI_COLLECTION,"p":[pid]})
    ua = gql(token,'{collections(first:1,query:"title:Ultimi Arrivi"){nodes{id}}}')["data"]["collections"]["nodes"]
    if ua: gql(token,"""mutation R($id:ID!,$p:[ID!]!){collectionRemoveProducts(id:$id,productIds:$p){userErrors{message}}}""",{"id":ua[0]["id"],"p":[pid]})
    return num, title

# ---------- Email ----------
def get_text(msg):
    html_part = plain = None
    for part in msg.walk():
        ct = part.get_content_type()
        if ct == "text/plain" and plain is None:
            plain = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8","replace")
        elif ct == "text/html" and html_part is None:
            html_part = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8","replace")
    if html_part:
        t = re.sub(r"<(script|style)[^>]*>.*?</\1>","",html_part,flags=re.S|re.I)
        t = re.sub(r"<[^>]+>","\n",t)
        return html.unescape(t)
    return plain or ""

def parse_fields(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    f = {}
    for i,l in enumerate(lines):
        if l in LABELS:
            vals=[]
            for j in range(i+1,len(lines)):
                if lines[j] in LABELS: break
                if any(lines[j].startswith(s) for s in STOPS): break
                vals.append(lines[j])
            if vals: f[l] = " ".join(vals).strip()
    gids = re.findall(r"gid://shopify/MediaImage/\d+", text)
    # dedup preserve order
    seen=set(); gids=[g for g in gids if not (g in seen or seen.add(g))]
    return f, gids

def main():
    token = get_token()
    M = imaplib.IMAP4_SSL(env("IMAP_HOST"))
    M.login(env("IMAP_USER"), env("IMAP_PASSWORD"))
    M.select("INBOX")
    typ, dat = M.search(None, 'UNSEEN', 'SUBJECT', '"%s"' % SUBJECT_MATCH)
    ids = dat[0].split()
    print(f"Trovate {len(ids)} nuove submission.")
    for mid in ids:
        typ, d = M.fetch(mid, "(RFC822)")
        msg = email.message_from_bytes(d[0][1])
        text = get_text(msg)
        f, gids = parse_fields(text)
        if not f.get("Titolo") and not f.get("Descrivi il tuo articolo"):
            print(f"  email {mid.decode()}: non sembra una submission valida, salto."); continue
        try:
            urls = resolve_images(token, gids)
            num, title = create_listing(token, f, urls)
            print(f"  ✅ creato annuncio bozza: '{title}' (id {num}, {len(urls)} foto)")
            M.store(mid, '+FLAGS', '\\Seen')  # segna come letta solo se OK
        except Exception as e:
            print(f"  ❌ errore su email {mid.decode()}: {e} (lasciata non letta, riprovo al prossimo giro)")
    M.logout()

if __name__ == "__main__":
    main()
