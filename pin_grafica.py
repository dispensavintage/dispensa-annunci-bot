# -*- coding: utf-8 -*-
"""Compone un pin verticale 1000x1500 da un'immagine orizzontale di articolo.

Pinterest mostra i pin in 2:3: un'immagine 1600x900 viene schiacciata in una
striscia e non la guarda nessuno. Qui l'immagine riempie i due terzi alti e il
titolo sta su un pannello bordeaux, leggibile anche in miniatura.

Dipende da Pillow e dai due Arvo (lo stesso carattere dei titoli del sito).
"""
import io, urllib.request
from PIL import Image, ImageDraw, ImageFont

L, A = 1000, 1500          # larghezza, altezza del pin
H_FOTO_MAX = 952           # quanto puo' occupare la foto al massimo
H_FOTO_MIN = 520
INGRANDIMENTO_MAX = 1.10   # oltre questo la foto diventa sgranata
RIGA = 10                  # filetto ambra
BORDEAUX = (109, 41, 50)
AMBRA = (255, 199, 0)
BIANCO = (255, 255, 255)

def _scarica(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return Image.open(io.BytesIO(urllib.request.urlopen(req, timeout=timeout).read()))

def _riempi(im, l, a):
    """Ritaglia al centro riempiendo il riquadro, senza deformare."""
    im = im.convert("RGB")
    sl, sa = im.size
    s = max(l / sl, a / sa)
    im = im.resize((max(1, round(sl * s)), max(1, round(sa * s))), Image.LANCZOS)
    nl, na = im.size
    return im.crop(((nl - l) // 2, (na - a) // 3, (nl - l) // 2 + l, (na - a) // 3 + a))

def _righe(testo, font, disegno, largh):
    parole, righe, cur = testo.split(), [], ""
    for p in parole:
        prova = (cur + " " + p).strip()
        if disegno.textlength(prova, font=font) <= largh:
            cur = prova
        else:
            if cur: righe.append(cur)
            cur = p
    if cur: righe.append(cur)
    return righe

def altezza_foto(l, a):
    """Quanto alta puo' essere la foto senza ingrandirla oltre il consentito.
    Le copertine 1000x555 del blog non reggono il riquadro pieno: il pin
    diventa una foto sgranata. Meglio foto piu' bassa e titolo piu' grande."""
    scala = max(l and L / l or 1, INGRANDIMENTO_MAX)
    return max(H_FOTO_MIN, min(H_FOTO_MAX, int(a * scala)))


def componi(url_immagine, titolo, occhiello, percorso_font, dominio="dispensavintage.it"):
    sorgente = _scarica(url_immagine)
    h_foto = altezza_foto(*sorgente.size)
    foto = _riempi(sorgente, L, h_foto)
    pin = Image.new("RGB", (L, A), BORDEAUX)
    pin.paste(foto, (0, 0))
    d = ImageDraw.Draw(pin)
    d.rectangle([0, h_foto, L, h_foto + RIGA], fill=AMBRA)

    margine = 64
    largh = L - 2 * margine
    alto_pannello = A - (h_foto + RIGA)
    alt_occhiello = 52 if occhiello else 0
    spazio = alto_pannello - alt_occhiello - 150   # 150 = aria sopra/sotto + dominio

    for corpo in range(84, 33, -3):
        f = ImageFont.truetype(f"{percorso_font}/Arvo-Bold.ttf", corpo)
        righe = _righe(titolo, f, d, largh)
        interlinea = round(corpo * 1.26)
        if len(righe) * interlinea <= spazio and len(righe) <= 5:
            break

    # il blocco occhiello+titolo sta al centro del pannello: senza questo, sui
    # titoli corti restava mezzo riquadro bordeaux vuoto.
    blocco = alt_occhiello + len(righe) * interlinea
    y = h_foto + RIGA + max(46, (alto_pannello - 70 - blocco) // 2)

    if occhiello:
        f_occ = ImageFont.truetype(f"{percorso_font}/Arvo-Regular.ttf", 28)
        d.text((margine, y), occhiello.upper(), font=f_occ, fill=AMBRA)
        y += alt_occhiello

    for r in righe:
        d.text((margine, y), r, font=f, fill=BIANCO)
        y += interlinea

    f_dom = ImageFont.truetype(f"{percorso_font}/Arvo-Regular.ttf", 27)
    d.text((margine, A - 68), dominio, font=f_dom, fill=(255, 255, 255, 180))
    return pin
