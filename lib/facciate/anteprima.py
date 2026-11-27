# -*- coding: utf-8 -*-
"""Cosa disegnare nel prospetto della finestra Facciate e cosa c'e' sotto il mouse
(senza API Revit ne' WPF).

Coordinate in mm come ritmo.calcola: x lungo la facciata da sinistra (visto da fuori),
y dal basso. Il disegno usa (sc, ox, oy): pixel = (ox + x*sc, oy - y*sc).
"""
from facciate import ritmo as R

# colori fissi per le classi piu' comuni, poi a giro
COLORI_PANNELLI = {R.VETRO: u"#CFE3F4", u"cieco": u"#B9C3CC", u"apribile": u"#BFE3C6",
                   u"vuoto": u"#FFFFFF"}
GIRO_PANNELLI = (u"#F3D9B1", u"#D9C8EE", u"#F2C4C4", u"#C8E6E0", u"#E8E2B8")
COLORI_MONTANTI = {R.MONTANTE: u"#4A5866", R.TRAVERSO: u"#4A5866", R.MARCAPIANO: u"#185A91",
                   u"lesena": u"#8A6A4F"}
GIRO_MONTANTI = (u"#B5543C", u"#5E7D3A", u"#7A4E9A")
SPESSORI = {R.MONTANTE: 2.0, R.TRAVERSO: 2.0, R.MARCAPIANO: 3.5, u"lesena": 4.0}


def _a_giro(classe, fissi, giro, ordine):
    if classe in fissi:
        return fissi[classe]
    altre = [c for c in ordine if c not in fissi]
    i = altre.index(classe) if classe in altre else len(altre)
    return giro[i % len(giro)]


def colore_pannello(classe, ordine=()):
    """Colore della classe di pannello; ordine: le classi usate, per dare colori diversi."""
    return _a_giro(classe, COLORI_PANNELLI, GIRO_PANNELLI, list(ordine))


def colore_montante(classe, ordine=()):
    return _a_giro(classe, COLORI_MONTANTI, GIRO_MONTANTI, list(ordine))


def spessore_montante(classe):
    return SPESSORI.get(classe, 3.0)


def scala(lunghezza, altezza, w, h, margini=(60.0, 40.0, 30.0, 50.0)):
    """(sc, ox, oy) perche' la facciata stia nel riquadro w x h; margini: sinistra, alto,
    destra, basso in pixel. None se non c'e' posto."""
    sx, alto, dx, basso = margini
    disp_w, disp_h = w - sx - dx, h - alto - basso
    if lunghezza <= 0 or altezza <= 0 or disp_w <= 0 or disp_h <= 0:
        return None
    sc = min(disp_w / lunghezza, disp_h / altezza)
    ox = sx + (disp_w - lunghezza * sc) / 2.0
    oy = alto + (disp_h + altezza * sc) / 2.0
    return sc, ox, oy


def elemento_in_punto(ris, x, y, tolleranza):
    """Cosa c'e' nel punto (mm): ("verticale", linea), ("orizzontale", linea), ("cella", cella)
    o None. Le linee vincono entro la tolleranza (mm)."""
    if not (-tolleranza <= x <= ris[u"lunghezza"] + tolleranza and -tolleranza <= y <= ris[u"altezza"] + tolleranza):
        return None
    vicine = [(abs(l[u"pos"] - x), u"verticale", l) for l in ris[u"linee_v"] if abs(l[u"pos"] - x) <= tolleranza]
    vicine += [(abs(l[u"pos"] - y), u"orizzontale", l) for l in ris[u"linee_o"] if abs(l[u"pos"] - y) <= tolleranza]
    if vicine:
        vicine.sort(key=lambda v: v[0])
        return vicine[0][1], vicine[0][2]
    c = R.trova_cella(ris[u"celle"], ris[u"colonne"], ris[u"righe"], x, y)
    return (u"cella", c) if c is not None else None


def linea_esiste(ris, verso, linea):
    """False se la linea non si crea (coperta per intero da celle unite)."""
    chiave = u"verticali" if verso == u"verticale" else u"orizzontali"
    return linea[u"indice"] not in ris[u"senza_linea"][chiave]


def segmenti(ris, verso, linea):
    """I tratti (da, a) in mm della linea che restano dopo le celle unite."""
    if verso == u"verticale":
        trasv, tolti = ris[u"righe"], ris[u"tolti"][u"verticali"].get(linea[u"indice"], [])
    else:
        trasv, tolti = ris[u"colonne"], ris[u"tolti"][u"orizzontali"].get(linea[u"indice"], [])
    out = []
    for j, t in enumerate(trasv):
        if j in tolti:
            continue
        if out and abs(out[-1][1] - t[u"da"]) < 1e-6:
            out[-1] = (out[-1][0], t[u"a"])
        else:
            out.append((t[u"da"], t[u"a"]))
    return out


def posizioni_cella(ris, cella):
    """Posizioni nel motivo (colonna, riga) della cella (della sua prima parte se unita)."""
    return ris[u"colonne"][cella[u"col"][0]][u"pos"], ris[u"righe"][cella[u"riga"][0]][u"pos"]


def descrizione_cella(ris, cella):
    tc, tr = ris[u"colonne"][cella[u"col"][0]], ris[u"righe"][cella[u"riga"][0]]
    testo = u"Colonna %s (posto %d del motivo) · riga %s (posto %d)" % (
        tc[u"modulo"], tc[u"pos"] + 1, tr[u"modulo"], tr[u"pos"] + 1)
    if cella[u"col"][0] != cella[u"col"][1] or cella[u"riga"][0] != cella[u"riga"][1]:
        testo += u" · celle unite"
    if tc[u"resto"] or tr[u"resto"]:
        testo += u" · ritaglio"
    return testo


def descrizione_linea(ris, verso, linea):
    tratti = ris[u"colonne"] if verso == u"verticale" else ris[u"righe"]
    t = tratti[linea[u"indice"]]
    nome = u"Montante" if verso == u"verticale" else u"Traverso"
    if t.get(u"piano") != tratti[linea[u"indice"] + 1].get(u"piano"):
        return u"%s sul livello a %d mm" % (nome, round(linea[u"pos"]))
    return u"%s dopo %s (posto %d del motivo) a %d mm" % (nome, t[u"modulo"], t[u"pos"] + 1, round(linea[u"pos"]))


def sul_livello(ris, linea):
    """True se il traverso sta fra due piani (la sua classe e' quella dei livelli)."""
    t = ris[u"righe"]
    return t[linea[u"indice"]].get(u"piano") != t[linea[u"indice"] + 1].get(u"piano")


def riquadro_selezione(ris, celle):
    """Posizioni del motivo (c0, c1), (r0, r1) che coprono le celle scelte (per Unisci);
    None se le celle non stanno nello stesso giro del motivo (e piano)."""
    if not celle:
        return None
    col = [ris[u"colonne"][i] for c in celle for i in range(c[u"col"][0], c[u"col"][1] + 1)]
    rig = [ris[u"righe"][j] for c in celle for j in range(c[u"riga"][0], c[u"riga"][1] + 1)]
    if len(set(t[u"giro"] for t in col)) > 1 or len(set((t.get(u"piano"), t[u"giro"]) for t in rig)) > 1:
        return None
    pc = [t[u"pos"] for t in col]
    pr = [t[u"pos"] for t in rig]
    return (min(pc), max(pc)), (min(pr), max(pr))


def quote(tratti, sc, minimo_px=34.0):
    """[(da, a, testo)] delle misure dei tratti abbastanza larghi da scriverle."""
    return [(t[u"da"], t[u"a"], u"%d" % round(t[u"a"] - t[u"da"])) for t in tratti
            if (t[u"a"] - t[u"da"]) * sc >= minimo_px]
