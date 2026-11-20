# -*- coding: utf-8 -*-
"""Genera le icone PNG dei pulsanti della ribbon (stesso stile delle icone della palette).

Le icone sono disegnate qui in SVG su una griglia 32x32, con la stessa tavolozza di
lib/palette.py: blu = oggetto, arancio = azione, scuro = riferimenti, azzurro = riempimenti.
Uso (serve Node con Playwright, gia' presente in questo ambiente):

    python tools/genera_icone.py            # scrive tutti i icon.png (96x96)
    python tools/genera_icone.py --anteprima ANTEPRIMA.png   # solo un foglio di prova

Questo e' uno strumento di sviluppo: pyRevit usa solo i PNG generati.
"""
import json
import math
import os
import re
import subprocess
import sys
import tempfile

RADICE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TAB = os.path.join(RADICE, "CDV Tools.tab")

BLU = "#1F6FB2"
AZZURRO = "#CFE3F4"
ARANCIO = "#E5862A"
SCURO = "#3C4650"
GRIGIO = "#AAB4BC"
BIANCO = "#FFFFFF"
MARRONE = "#8A6A4F"
CHIARO = "#FCE3C4"

DEFS = (
    '<defs>'
    '<pattern id="h" width="4" height="4" patternUnits="userSpaceOnUse" '
    'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="4" stroke="%s" '
    'stroke-width="1.1"/></pattern>'
    '<pattern id="hg" width="4" height="4" patternUnits="userSpaceOnUse" '
    'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="4" stroke="%s" '
    'stroke-width="1.1"/></pattern>'
    '</defs>' % (BLU, GRIGIO)
)


def _n(v):
    return ("%.2f" % v).rstrip("0").rstrip(".")


def R(x, y, w, h, fill="none", stroke=None, sw=1.6, dash=None, rx=0, op=None):
    if dash and stroke:
        return R(x, y, w, h, fill, None, op=op) + rett_tratti(x, y, w, h, stroke, sw)
    a = 'x="%s" y="%s" width="%s" height="%s" fill="%s"' % (_n(x), _n(y), _n(w), _n(h), fill)
    if rx:
        a += ' rx="%s"' % _n(rx)
    if stroke:
        a += ' stroke="%s" stroke-width="%s" stroke-linejoin="round"' % (stroke, _n(sw))
    if dash:
        a += ' stroke-dasharray="%s"' % dash
    if op is not None:
        a += ' opacity="%s"' % op
    return "<rect %s/>" % a


_SEG = re.compile(r"M\s*([-\d.]+)[, ]\s*([-\d.]+)\s*([HVL])\s*([-\d.]+)(?:[, ]\s*([-\d.]+))?")


def tratti(x1, y1, x2, y2, col, sw=1.6, d=3.4, g=2.2):
    """Linea tratteggiata che inizia e finisce con un trattino intero e passo regolare."""
    lung = math.hypot(x2 - x1, y2 - y1)
    n = max(2, int(round((lung + g) / (d + g))))
    g2 = (lung - n * d) / (n - 1)
    while g2 < 1.3 and n > 2:
        n -= 1
        g2 = (lung - n * d) / (n - 1)
    return ('<path d="M%s,%s L%s,%s" fill="none" stroke="%s" stroke-width="%s" '
            'stroke-dasharray="%s %s" stroke-linecap="butt"/>'
            % (_n(x1), _n(y1), _n(x2), _n(y2), col, _n(sw), _n(d), _n(g2)))


def L(d, stroke, sw=1.6, dash=None, cap="butt"):
    if dash:
        # tratteggio regolare: solo per segmenti rettilinei "Mx,y Hx" / "Vy" / "Lx,y"
        out = ""
        for m in _SEG.finditer(d):
            x1, y1, t, a, b = float(m.group(1)), float(m.group(2)), m.group(3), float(m.group(4)), m.group(5)
            x2, y2 = (a, y1) if t == "H" else ((x1, a) if t == "V" else (a, float(b)))
            out += tratti(x1, y1, x2, y2, stroke, sw)
        return out
    return '<path d="%s" fill="none" stroke="%s" stroke-width="%s" stroke-linecap="%s" stroke-linejoin="round"/>' % (
        d, stroke, _n(sw), cap)


def rett_tratti(x, y, w, h, stroke, sw=1.6):
    """Rettangolo a tratti: ogni lato inizia e finisce con un trattino (angoli pieni)."""
    return (tratti(x, y, x + w, y, stroke, sw) + tratti(x + w, y, x + w, y + h, stroke, sw)
            + tratti(x + w, y + h, x, y + h, stroke, sw) + tratti(x, y + h, x, y, stroke, sw))


def poligono_tratti(pt, stroke, sw=1.6):
    out = ""
    for i in range(len(pt)):
        a, b = pt[i], pt[(i + 1) % len(pt)]
        out += tratti(a[0], a[1], b[0], b[1], stroke, sw, 3, 2)
    return out


def P(d, fill, stroke=None, sw=1.4, dash=None):
    a = 'd="%s" fill="%s"' % (d, fill)
    if stroke:
        a += ' stroke="%s" stroke-width="%s" stroke-linejoin="round"' % (stroke, _n(sw))
    if dash:
        a += ' stroke-dasharray="%s"' % dash
    return "<path %s/>" % a


def C(cx, cy, r, fill="none", stroke=None, sw=1.4):
    a = 'cx="%s" cy="%s" r="%s" fill="%s"' % (_n(cx), _n(cy), _n(r), fill)
    if stroke:
        a += ' stroke="%s" stroke-width="%s"' % (stroke, _n(sw))
    return "<circle %s/>" % a


def testa(x, y, ang, col=ARANCIO, s=4.6, sw=None):
    """Punta piena con la punta in (x, y), rivolta verso 'ang' gradi (lunga s, larga 1.3 s)."""
    return ('<path d="M0,0 L%s,%s L%s,0 L%s,%s Z" fill="%s" stroke="%s" stroke-width="0.4" '
            'stroke-linejoin="round" transform="translate(%s %s) rotate(%s)"/>'
            % (_n(-s), _n(-s * 0.65), _n(-s * 0.82), _n(-s), _n(s * 0.65), col, col,
               _n(x), _n(y), _n(ang)))


def freccia(x1, y1, x2, y2, col=ARANCIO, sw=2, doppia=False, s=4.6):
    """Freccia da (x1,y1) a (x2,y2): l'asta si ferma dentro la punta, mai sopra."""
    ang = math.degrees(math.atan2(y2 - y1, x2 - x1))
    lung = math.hypot(x2 - x1, y2 - y1)
    ux, uy = (x2 - x1) / lung, (y2 - y1) / lung
    rit = s * 0.75
    a0 = rit if doppia else 0
    out = L("M%s,%s L%s,%s" % (_n(x1 + ux * a0), _n(y1 + uy * a0),
                               _n(x2 - ux * rit), _n(y2 - uy * rit)), col, sw)
    out += testa(x2, y2, ang, col, s)
    if doppia:
        out += testa(x1, y1, ang + 180, col, s)
    return out


def arco(cx, cy, r, a0, a1, col=ARANCIO, sw=2.2, testa_fine=True, s=4.8):
    """Arco da a0 a a1 gradi (y verso il basso: angoli crescenti = senso orario)."""
    def pt(a):
        return cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))
    x0, y0 = pt(a0)
    x1, y1 = pt(a1)
    corr = math.degrees(s * 0.7 / r) * (1 if a1 > a0 else -1) if testa_fine else 0
    xe, ye = pt(a1 - corr)
    sweep = 1 if a1 > a0 else 0
    grande = 1 if abs(a1 - a0) > 180 else 0
    out = L("M%s,%s A%s,%s 0 %d %d %s,%s" % (_n(x0), _n(y0), _n(r), _n(r), grande, sweep,
                                           _n(xe), _n(ye)), col, sw)
    if testa_fine:
        # la punta segue la corda dell'ultimo tratto: cosi' resta appoggiata sull'arco
        xm, ym = pt(a1 - corr * 1.6)
        out += testa(x1, y1, math.degrees(math.atan2(y1 - ym, x1 - xm)), col, s)
    return out


def vista(x, y, w, h):
    return R(x, y, w, h, AZZURRO, BLU, 1.6)


def titolo(x, y, w, col=SCURO):
    """Titolo di vista: etichetta piena e linea."""
    return R(x, y - 3.6, min(7, w * 0.4), 2.6, BLU) + L("M%s,%s H%s" % (_n(x), _n(y), _n(x + w)), col, 1.8)


# ==============================================================================
# ICONE (nome -> contenuto SVG su griglia 32x32)
# ==============================================================================
I = {}

# due livelli (linea + testa a destra): la pianta passa dal livello basso a quello alto
I["ChangePlanLevel"] = (
    L("M2,25 H24", GRIGIO, 2) + P("M24,25 L27.5,21.5 L31,25 L27.5,28.5 Z", GRIGIO)
    + L("M2,7 H24", BLU, 2.4) + P("M24,7 L27.5,3.5 L31,7 L27.5,10.5 Z", BLU)
    + R(3, 12, 10, 9, AZZURRO, BLU, 1.4) + L("M8,12 V21 M3,16.5 H13", BLU, 0.8)
    + freccia(19, 22.5, 19, 9.5, sw=2.4, s=5.4))

# linea di sezione; sotto la profondita' della vista e, oltre, lo sfondo a mezzitoni
I["SectionDepth"] = (
    R(3, 7.5, 26, 7.5, AZZURRO, None)
    + R(3, 15, 26, 13, BIANCO, None) + R(3, 15, 26, 13, "url(#hg)")
    + rett_tratti(3, 15, 26, 13, GRIGIO, 1.2) + L("M3,15 H29", BLU, 1.8)
    + L("M6,4.5 H26", SCURO, 2.2) + C(4, 4.5, 2.8, BIANCO, SCURO, 1.8) + C(28, 4.5, 2.8, BIANCO, SCURO, 1.8)
    + freccia(16, 16.5, 16, 27.5, sw=2.4, s=5))

I["CreateFilterFromSelection"] = (
    P("M3,4.5 H29 L19.2,16.5 V27 L12.8,23.6 V16.5 Z", AZZURRO, BLU, 1.8)
    + C(9.5, 8.6, 1.7, BLU) + C(16, 8, 1.7, BLU) + C(22.5, 8.6, 1.7, BLU)
    + L("M21,23 L24.2,26.2 L30,19.5", ARANCIO, 2.4, cap="round"))

# stessa forma di ritaglio: piena nella vista sorgente, a tratti in quella di destinazione
I["CopyCropRegion"] = (
    P("M1,6 H10 V15 H13 V26 H1 Z", AZZURRO, BLU, 1.8)
    + P("M19,6 H28 V15 H31 V26 H19 Z", BIANCO)
    + poligono_tratti([(19, 6), (28, 6), (28, 15), (31, 15), (31, 26), (19, 26)], BLU, 1.8)
    + freccia(6, 10.5, 24, 10.5, sw=2.4, s=5))

# pennello della palette (copia_grafica): dalla categoria tratteggiata a quella vuota
I["CopyCatProps"] = (
    R(2, 2, 11, 11, AZZURRO, BLU) + R(2, 2, 11, 11, "url(#h)")
    + R(19, 19, 11, 11, BIANCO, BLU, 1.6)
    + '<g transform="scale(1.7) translate(2.6 2.6)">'
    + L("M14.6,1.4 L9,7", MARRONE, 2.2)
    + P("M7.4,6.6 L9.4,8.6 L8.4,9.6 L6.4,7.6 Z", SCURO)
    + P("M6.4,7.6 L8.4,9.6 C7.8,12.6 5.2,14.6 1.4,14.6 C1.8,11.8 3.4,8.8 6.4,7.6 Z", ARANCIO)
    + "</g>")

I["UpdateViewTemplate"] = (
    R(3, 3, 18, 23, BIANCO, SCURO, 1.5, rx=1.5)
    + R(6, 7, 4, 4, AZZURRO, BLU, 1) + L("M12.5,9 H18", SCURO, 1.6)
    + R(6, 13.5, 4, 4, AZZURRO, BLU, 1) + L("M12.5,15.5 H18", SCURO, 1.6)
    + R(6, 20, 4, 4, AZZURRO, BLU, 1) + L("M12.5,22 H16", SCURO, 1.6)
    + C(22.5, 22.5, 8.6, BIANCO)
    + arco(22.5, 22.5, 6.2, 200, 330, sw=2.2) + arco(22.5, 22.5, 6.2, 20, 150, sw=2.2))

# --- Campiture ---------------------------------------------------------------
I["CutFilledRegion"] = (
    R(4, 7, 24, 18, AZZURRO, BLU, 1.8) + R(4, 7, 24, 18, "url(#h)")
    + L("M3,16 H29", ARANCIO, 2, "4.4 2")
    + L("M1.5,12 V20 M30.5,12 V20", ARANCIO, 2.2))

I["OffsetFilledRegion"] = (
    P("M3,27 V8 H29 V16 H11 V27 Z", AZZURRO) + P("M3,27 V8 H29 V16 H11 V27 Z", "url(#h)")
    + L("M3,27 V8 H29", BLU, 2.6)
    + freccia(23, 9.5, 23, 15, sw=1.6, s=3.2) + L("M11,16 H29 M11,16 V27", ARANCIO, 1.6))

I["DiffFilledRegion"] = (
    R(12, 12, 18, 18, AZZURRO, BLU, 1.8) + R(12, 12, 18, 18, "url(#h)")
    + R(2, 2, 18, 18, BIANCO, GRIGIO, 1.8, "3 2")
    + L("M22,6 H29.5", ARANCIO, 2.8))

I["SectionFilledRegion"] = (
    R(2, 5, 28, 5, BLU, BLU, 1)
    + P("M2,17 C8,13.5 14,19 20,15.5 S28,17 30,14.5 V29.5 H2 Z", AZZURRO)
    + P("M2,17 C8,13.5 14,19 20,15.5 S28,17 30,14.5 V29.5 H2 Z", "url(#h)")
    + L("M2,17 C8,13.5 14,19 20,15.5 S28,17 30,14.5", ARANCIO, 2.4))

# --- Modellazione ------------------------------------------------------------
_PANNELLO_ON = (
    R(2, 12, 28, 17, BIANCO, SCURO, 1.6, rx=3)
    + R(5.5, 16, 5.5, 9, BLU) + R(13.2, 16, 5.5, 9, AZZURRO, BLU, 1.2) + R(20.9, 16, 5.5, 9, ARANCIO))
_PANNELLO_OFF = (
    R(2, 12, 28, 17, BIANCO, GRIGIO, 1.6, rx=3)
    + R(5.5, 16, 5.5, 9, GRIGIO) + R(13.2, 16, 5.5, 9, "#E6EAED", GRIGIO, 1.2)
    + R(20.9, 16, 5.5, 9, GRIGIO, None, op=0.6))


def _accensione(col):
    return (C(24, 8.5, 7.6, col)
            + L("M24,4.6 V9", BIANCO, 2, cap="round")
            + arco(24, 9.6, 4.6, -55, -125 + 360, BIANCO, 1.9, testa_fine=False))


I["PaletteOnOff"] = _PANNELLO_ON + _accensione(BLU)
I["PaletteOnOff_on"] = I["PaletteOnOff"]
I["PaletteOnOff_off"] = _PANNELLO_OFF + _accensione(GRIGIO)

I["Palette"] = (
    R(3, 3, 26, 26, BIANCO, SCURO, 1.6, rx=3)
    + R(7, 7, 5.5, 5.5, AZZURRO, BLU, 1.2) + L("M8,9.8 L9.6,11.6 L12.2,7.4", ARANCIO, 1.7, cap="round")
    + L("M16,9.8 H25", SCURO, 1.8)
    + R(7, 13.5, 5.5, 5.5, AZZURRO, BLU, 1.2) + L("M8,16.4 L9.6,18.2 L12.2,14", ARANCIO, 1.7, cap="round")
    + L("M16,16.4 H23", SCURO, 1.8)
    + R(7, 20, 5.5, 5.5, BIANCO, BLU, 1.2) + L("M16,22.8 H25", SCURO, 1.8))

I["FlipWallCenter"] = (
    R(2, 10.5, 20, 5.5, BLU, BLU, 1) + R(2, 16, 20, 5.5, AZZURRO, BLU, 1.2)
    + L("M1,16 H24", SCURO, 1.3, "4 2")
    + L("M25.5,5 C32.5,10 32.5,22 25.5,27.5", ARANCIO, 2.2)
    + testa(25.5, 27.5, 140) + testa(25.5, 5, -140))

# --- Tavole: titoli ----------------------------------------------------------
I["TitoloColonna"] = (
    titolo(7, 8, 20) + titolo(7, 16, 13) + titolo(7, 24, 17) + L("M7,3 V29", ARANCIO, 2.2, "4 2"))
I["TitoloRiga"] = (
    L("M1,28 H31", ARANCIO, 2.2, "4 2")
    + vista(2, 5, 8, 12) + vista(12, 9, 8, 8) + vista(22, 3, 8, 14)
    + L("M2,23 H10 M12,23 H20 M22,23 H30", SCURO, 1.8))
I["TitoloBordoSinistro"] = (
    vista(9, 4, 21, 15) + titolo(9, 25, 18)
    + L("M9,1 V30", ARANCIO, 1.6, "3 2") + freccia(2, 25, 8, 25, s=3.6))
I["TitoloDistanzaY"] = (
    vista(2, 2, 12, 12) + vista(18, 6, 12, 8)
    + titolo(2, 24, 12) + titolo(18, 24, 12)
    + freccia(8, 15, 8, 23, doppia=True, sw=1.5, s=3) + freccia(24, 15, 24, 23, doppia=True, sw=1.5, s=3))
I["TitoloLarghezzaVista"] = (
    vista(5, 4, 22, 16) + titolo(5, 25, 22)
    + L("M5,2 V30 M27,2 V30", ARANCIO, 1.5, "3 2"))
I["TitoloLunghezzaRif"] = (
    L("M4,8 H28", BLU, 2.4) + L("M4,5 V11 M28,5 V11", BLU, 1.6)
    + L("M4,23 H15", GRIGIO, 2.4) + L("M4,20 V26", GRIGIO, 1.6)
    + freccia(15, 23, 28, 23) + L("M28,12 V27", ARANCIO, 1.5, "3 2"))

# --- Tavole: viste -----------------------------------------------------------
I["CropImage"] = (
    R(6, 6, 20, 20, AZZURRO, BLU, 1.2)
    + P("M6,26 L13,15.5 L18.5,22 L21.5,18.5 L26,26 Z", BLU)
    + C(20.5, 11, 2.4, BIANCO)
    + L("M1.5,9 V1.5 H9 M23,1.5 H30.5 V9 M30.5,23 V30.5 H23 M9,30.5 H1.5 V23", ARANCIO, 2.6))

I["AllineaAlto"] = R(3, 7, 11, 18, AZZURRO, BLU) + R(18, 7, 11, 11, AZZURRO, BLU) + L("M0,7 H32", ARANCIO, 2.4)
I["AllineaBasso"] = R(3, 7, 11, 18, AZZURRO, BLU) + R(18, 14, 11, 11, AZZURRO, BLU) + L("M0,25 H32", ARANCIO, 2.4)
I["AllineaCentroY"] = (R(3, 6, 11, 20, AZZURRO, BLU) + R(18, 10, 11, 12, AZZURRO, BLU)
                       + L("M1,16 H31", ARANCIO, 2.2, "5 2"))
I["AllineaModelloY"] = (
    R(2, 7, 10, 17, AZZURRO, BLU) + R(14, 11, 9, 13, AZZURRO, BLU)
    + L("M1,24 H25", ARANCIO, 2.2, "5 2") + P("M24.5,24 L27.5,19.5 L30.5,24 Z", SCURO)
    + L("M27.5,24 V29", SCURO, 1.4))
I["AllineaSinistra"] = R(7, 3, 21, 10, AZZURRO, BLU) + R(7, 19, 12, 10, AZZURRO, BLU) + L("M4.5,0 V32", ARANCIO, 2.4)
I["AllineaDestra"] = R(4, 3, 21, 10, AZZURRO, BLU) + R(13, 19, 12, 10, AZZURRO, BLU) + L("M27.5,0 V32", ARANCIO, 2.4)
I["AllineaCentroX"] = (R(5, 3, 22, 10, AZZURRO, BLU) + R(10, 19, 12, 10, AZZURRO, BLU)
                       + L("M16,1 V31", ARANCIO, 2.2, "5 2"))
I["AllineaModelloX"] = (
    R(3, 9, 16, 8, AZZURRO, BLU) + R(11, 20, 17, 8, AZZURRO, BLU)
    + L("M15,9 V31", ARANCIO, 2.2, "5 2") + C(15, 5, 3.6, BIANCO, SCURO, 1.5))
I["DistribuisciX"] = (
    R(2, 3, 5, 18, AZZURRO, BLU) + R(13.5, 3, 5, 18, AZZURRO, BLU) + R(25, 3, 5, 18, AZZURRO, BLU)
    + L("M4.5,22 V30 M16,22 V30 M27.5,22 V30", ARANCIO, 1.4, cap="round")
    + freccia(4.5, 26, 14.5, 26, doppia=True, sw=1.6, s=3) + freccia(17.5, 26, 27.5, 26, doppia=True, sw=1.6, s=3))
I["DistribuisciY"] = (
    R(3, 2, 18, 5, AZZURRO, BLU) + R(3, 13.5, 18, 5, AZZURRO, BLU) + R(3, 25, 18, 5, AZZURRO, BLU)
    + L("M22,4.5 H30 M22,16 H30 M22,27.5 H30", ARANCIO, 1.4, cap="round")
    + freccia(26, 4.5, 26, 14.5, doppia=True, sw=1.6, s=3) + freccia(26, 17.5, 26, 27.5, doppia=True, sw=1.6, s=3))

I["AlignViewports"] = (
    R(2, 3, 13, 26, BIANCO, SCURO, 1.4, rx=1.5) + R(17, 3, 13, 26, BIANCO, SCURO, 1.4, rx=1.5)
    + R(4, 7, 9, 10, AZZURRO, BLU, 1.4) + R(19, 7, 9, 10, AZZURRO, BLU, 1.4)
    + L("M4,23 H13 M19,23 H28", SCURO, 1.6)
    + L("M1,12 H31", ARANCIO, 1.6, "3 2") + C(8.5, 12, 1.8, ARANCIO) + C(23.5, 12, 1.8, ARANCIO))

I["CreateLegendComponents"] = (
    R(3, 3, 26, 26, BIANCO, SCURO, 1.5, rx=2)
    + R(6, 6.5, 6.5, 6, BLU) + L("M16,9.5 H26", SCURO, 1.7)
    + R(6, 14, 6.5, 6, AZZURRO, BLU, 1.2) + L("M16,17 H26", SCURO, 1.7)
    + C(9.2, 25, 3.2, AZZURRO, BLU, 1.2) + L("M16,25 H19", SCURO, 1.7)
    + C(24.5, 24.5, 6, ARANCIO) + L("M24.5,21 V28 M21,24.5 H28", BIANCO, 2, cap="round"))

I["AlignTrueNorth"] = (
    '<g transform="rotate(38 16 16)">'
    + poligono_tratti([(16, 3), (20.5, 16), (11.5, 16)], GRIGIO, 1.5)
    + poligono_tratti([(16, 29), (20.5, 16), (11.5, 16)], GRIGIO, 1.5) + "</g>"
    + P("M16,3 L20.5,16 H11.5 Z", BLU) + P("M16,29 L20.5,16 H11.5 Z", AZZURRO, BLU, 1.4)
    + C(16, 16, 1.5, BIANCO)
    + arco(16, 16, 12.5, -48, -84, sw=2.2, s=3.4))

# menu unico "Allinea in tavola": due viste con titolo, allineate a sinistra
I["Allinea"] = (
    vista(7, 2, 20, 9) + L("M7,14.5 H22", SCURO, 1.8)
    + vista(7, 18, 13, 8) + L("M7,29.5 H17", SCURO, 1.8)
    + L("M4,1 V31", ARANCIO, 2.4))

# ------------------------------------------------------------------------------
# DOVE VANNO I FILE
# ------------------------------------------------------------------------------
_ALLINEA = os.path.join("Tavole.panel", "Allinea.pulldown")
_VISTE = "Viste.panel"
_GF = "Grafica.panel"
_PAL = os.path.join("Modellazione.panel", "Palette.stack")

PERCORSI = {
    "ChangePlanLevel": os.path.join(_VISTE, "ChangePlanLevel.pushbutton", "icon.png"),
    "SectionDepth": os.path.join(_VISTE, "SectionDepth.pushbutton", "icon.png"),
    "CreateFilterFromSelection": os.path.join(_GF, "CreateFilterFromSelection.pushbutton", "icon.png"),
    "CopyCropRegion": os.path.join(_VISTE, "CopyCropRegion.pushbutton", "icon.png"),
    "CopyCatProps": os.path.join(_GF, "CopyCatProps.pushbutton", "icon.png"),
    "UpdateViewTemplate": os.path.join(_VISTE, "UpdateViewTemplate.pushbutton", "icon.png"),
    "CutFilledRegion": os.path.join("Campiture.panel", "CutFilledRegion.pushbutton", "icon.png"),
    "OffsetFilledRegion": os.path.join("Campiture.panel", "OffsetFilledRegion.pushbutton", "icon.png"),
    "DiffFilledRegion": os.path.join("Campiture.panel", "DiffFilledRegion.pushbutton", "icon.png"),
    "SectionFilledRegion": os.path.join("Campiture.panel", "SectionFilledRegion.pushbutton", "icon.png"),
    "PaletteOnOff": os.path.join(_PAL, "PaletteOnOff.pushbutton", "icon.png"),
    "PaletteOnOff_on": os.path.join(_PAL, "PaletteOnOff.pushbutton", "on.png"),
    "PaletteOnOff_off": os.path.join(_PAL, "PaletteOnOff.pushbutton", "off.png"),
    "Palette": os.path.join(_PAL, "Palette.pushbutton", "icon.png"),
    "FlipWallCenter": os.path.join("Modellazione.panel", "FlipWallCenter.pushbutton", "icon.png"),
    "Allinea": os.path.join(_ALLINEA, "icon.png"),
    "TitoloColonna": os.path.join(_ALLINEA, "TitoloColonna.pushbutton", "icon.png"),
    "TitoloRiga": os.path.join(_ALLINEA, "TitoloRiga.pushbutton", "icon.png"),
    "TitoloBordoSinistro": os.path.join(_ALLINEA, "TitoloBordoSinistro.pushbutton", "icon.png"),
    "TitoloDistanzaY": os.path.join(_ALLINEA, "TitoloDistanzaY.pushbutton", "icon.png"),
    "TitoloLarghezzaVista": os.path.join(_ALLINEA, "TitoloLarghezzaVista.pushbutton", "icon.png"),
    "TitoloLunghezzaRif": os.path.join(_ALLINEA, "TitoloLunghezzaRif.pushbutton", "icon.png"),
    "CropImage": os.path.join("Tavole.panel", "CropImage.pushbutton", "icon.png"),
    "AllineaAlto": os.path.join(_ALLINEA, "AllineaAlto.pushbutton", "icon.png"),
    "AllineaBasso": os.path.join(_ALLINEA, "AllineaBasso.pushbutton", "icon.png"),
    "AllineaCentroY": os.path.join(_ALLINEA, "AllineaCentroY.pushbutton", "icon.png"),
    "AllineaModelloY": os.path.join(_ALLINEA, "AllineaModelloY.pushbutton", "icon.png"),
    "AllineaSinistra": os.path.join(_ALLINEA, "AllineaSinistra.pushbutton", "icon.png"),
    "AllineaDestra": os.path.join(_ALLINEA, "AllineaDestra.pushbutton", "icon.png"),
    "AllineaCentroX": os.path.join(_ALLINEA, "AllineaCentroX.pushbutton", "icon.png"),
    "AllineaModelloX": os.path.join(_ALLINEA, "AllineaModelloX.pushbutton", "icon.png"),
    "DistribuisciX": os.path.join(_ALLINEA, "DistribuisciX.pushbutton", "icon.png"),
    "DistribuisciY": os.path.join(_ALLINEA, "DistribuisciY.pushbutton", "icon.png"),
    "CreateLegendComponents": os.path.join("Tavole.panel", "CreateLegendComponents.pushbutton", "icon.png"),
    "AlignTrueNorth": os.path.join("Tavole.panel", "AlignTrueNorth.pushbutton", "icon.png"),
    "AlignViewports": os.path.join("Tavole.panel", "AlignViewports.pushbutton", "icon.png"),
}

_RENDER_JS = r"""
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const lavori = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 96, height: 96 } });
  for (const [out, svg] of Object.entries(lavori)) {
    await p.setContent('<html><body style="margin:0;background:transparent">' + svg + '</body></html>');
    await p.screenshot({ path: out, omitBackground: true, clip: { x: 0, y: 0, width: 96, height: 96 } });
  }
  await b.close();
})();
"""


def svg(contenuto):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 32 32">%s%s</svg>'
            % (DEFS, contenuto))


def render(lavori):
    """lavori: {percorso_png: contenuto svg}."""
    d = tempfile.mkdtemp()
    js = os.path.join(d, "render.js")
    dati = os.path.join(d, "lavori.json")
    with open(js, "w") as f:
        f.write(_RENDER_JS)
    with open(dati, "w") as f:
        json.dump({k: svg(v) for k, v in lavori.items()}, f)
    env = dict(os.environ)
    if not env.get("NODE_PATH"):
        try:
            env["NODE_PATH"] = subprocess.check_output(["npm", "root", "-g"]).decode().strip()
        except Exception:
            pass
    subprocess.check_call(["node", js, dati], env=env)


def main(argv):
    mancanti = [n for n in PERCORSI if n not in I]
    assert not mancanti, mancanti
    if "--anteprima" in argv:
        out = argv[argv.index("--anteprima") + 1]
        d = tempfile.mkdtemp()
        lavori = {os.path.join(d, n + ".png"): I[n] for n in PERCORSI}
        render(lavori)
        from PIL import Image
        nomi = list(PERCORSI)
        col = 8
        righe = (len(nomi) + col - 1) // col
        foglio = Image.new("RGBA", (col * 110, righe * 110 * 2), (255, 255, 255, 255))
        for i, n in enumerate(nomi):
            im = Image.open(os.path.join(d, n + ".png")).convert("RGBA")
            x, y = (i % col) * 110 + 7, (i // col) * 220 + 7
            foglio.alpha_composite(im, (x, y))
            piccola = im.resize((32, 32), Image.LANCZOS)
            foglio.alpha_composite(piccola, (x + 32, y + 100))
            scura = Image.new("RGBA", (40, 40), (43, 43, 43, 255))
            scura.alpha_composite(piccola, (4, 4))
            foglio.alpha_composite(scura, (x + 60, y + 96))
        foglio.save(out)
        return
    render({os.path.join(TAB, PERCORSI[n]): I[n] for n in PERCORSI})
    print("Scritte %d icone" % len(PERCORSI))


if __name__ == "__main__":
    main(sys.argv[1:])
