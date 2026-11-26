# -*- coding: utf-8 -*-
"""Geometria di un infisso in prospetto, senza API Revit.

Da uno schema (schema.py) calcola, in mm con origine nello spigolo esterno in basso a
sinistra del telaio (x a destra, y in alto):

- piani: i piani di riferimento della famiglia. Ognuno, tranne i quattro di bordo
  (sx, dx, basso, alto: quelli del modello famiglia di Revit), nasce da un piano base + o -
  un parametro: e' la quota etichettata che lo rende parametrico.
- pezzi: le estrusioni (telaio, montanti, ante, vetri, zoccoli), ognuna con i piani a cui
  vanno bloccate le sue facce e i parametri di profondita'.
- celle: le zone foglia con luce, vetro e anta.
- simboli: i segmenti dei simboli di apertura in prospetto; ogni coordinata di ogni estremo
  e' (piano, parametro, segno), cosi' in Revit la si quota e la si etichetta.
- derivati: parametri con formula usati dai simboli (meta' luce, punte delle frecce).
- errori: misure che non stanno.
"""
from infissi import schema as S

LARGHEZZA = u"Larghezza"
ALTEZZA = u"Altezza"
MONTANTE_MEZZO = u"Montante mezzo"
NOMI_PROFILI = dict((k, e) for k, e, _v, _m in S.PROFILI)

# profondita': (parametro inizio, parametro fine) misurati dall'asse del muro
PROFONDITA = {
    u"telaio": (u"Telaio inizio", u"Telaio fine"),
    u"anta": (u"Anta inizio", u"Anta fine"),
    u"anta_a": (u"Anta A inizio", u"Anta A fine"),
    u"anta_b": (u"Anta B inizio", u"Anta B fine"),
    u"vetro": (u"Vetro inizio", u"Vetro fine"),
    u"vetro_anta": (u"Vetro anta inizio", u"Vetro anta fine"),
    u"vetro_a": (u"Vetro A inizio", u"Vetro A fine"),
    u"vetro_b": (u"Vetro B inizio", u"Vetro B fine"),
}

LUCE_MIN_FISSO = 50.0       # mm di vetro libero minimo in una cella fissa
LUCE_MIN_ANTA = 50.0        # mm di vetro libero minimo dentro un'anta
RADICI = (u"sx", u"dx", u"basso", u"alto")
_EPS = 1e-6


def profilo(nome_chiave):
    return NOMI_PROFILI[nome_chiave]


def nome_zona(percorso):
    return S.nome_percorso(percorso) or u"1"


def nome_misura(verso, percorso_figlio):
    """Parametro della misura di un figlio: u"L zona 2" (colonne) o u"H zona 2.1" (righe)."""
    return (u"L zona %s" if verso == u"v" else u"H zona %s") % S.nome_percorso(percorso_figlio)


def nome_mezza_altezza(percorso):
    return u"Mezza altezza %s" % nome_zona(percorso)


def nome_mezza_larghezza(percorso):
    return u"Mezza larghezza %s" % nome_zona(percorso)


def nome_freccia(percorso, alto):
    return (u"Freccia alto %s" if alto else u"Freccia basso %s") % nome_zona(percorso)


class _Piani(object):
    def __init__(self, larghezza, altezza):
        self.lista = []
        self._per_chiave = {}
        self.per_id = {}
        for pid, verso, pos in ((u"sx", u"v", 0.0), (u"dx", u"v", larghezza),
                                (u"basso", u"o", 0.0), (u"alto", u"o", altezza)):
            self._registra({u"id": pid, u"verso": verso, u"pos": float(pos),
                            u"base": None, u"param": None, u"segno": 0})

    def _registra(self, p):
        self.lista.append(p)
        self.per_id[p[u"id"]] = p
        return p[u"id"]

    def aggiungi(self, base, param, segno, valore):
        """Piano a distanza `valore` (parametro `param`) dal piano base, verso `segno`."""
        chiave = (base, param, segno)
        if chiave in self._per_chiave:
            return self._per_chiave[chiave]
        b = self.per_id[base]
        pid = u"P%d" % (len(self.lista) - 3)
        self._registra({u"id": pid, u"verso": b[u"verso"], u"pos": b[u"pos"] + segno * valore,
                        u"base": base, u"param": param, u"segno": segno})
        self._per_chiave[chiave] = pid
        return pid

    def pos(self, pid):
        return self.per_id[pid][u"pos"]


def formula_posizione(piani_per_id, pid):
    """Posizione di un piano come formula Revit (u"" = zero)."""
    p = piani_per_id[pid]
    if p[u"base"] is None:
        return {u"sx": u"", u"basso": u"", u"dx": LARGHEZZA, u"alto": ALTEZZA}[pid]
    base = formula_posizione(piani_per_id, p[u"base"])
    op = u" + " if p[u"segno"] > 0 else u" - "
    if not base:
        return p[u"param"] if p[u"segno"] > 0 else u"-" + p[u"param"]
    return base + op + p[u"param"]


def _differenza(fa, fb):
    """Formula di fa - fb."""
    if not fb:
        return fa or u"0"
    return u"%s - (%s)" % (fa or u"0", fb)


def calcola(schema):
    L = float(schema[u"larghezza"])
    H = float(schema[u"altezza"])
    prof = schema[u"profili"]
    valori = {LARGHEZZA: L, ALTEZZA: H, MONTANTE_MEZZO: prof[u"montante"] / 2.0}
    for k, nome in NOMI_PROFILI.items():
        valori[nome] = float(prof[k])

    ris = {u"piani": None, u"pezzi": [], u"celle": [], u"simboli": [], u"derivati": [],
           u"errori": [], u"misure": [], u"valori": valori}
    err = ris[u"errori"]
    if L <= 0 or H <= 0:
        err.append(u"Larghezza e altezza devono essere maggiori di zero.")
    for k, etichetta, _v, minimo in S.PROFILI:
        if minimo is not None and prof[k] < minimo:
            err.append(u"%s: almeno %g mm." % (etichetta, minimo))
    err.extend(S.errori_struttura(schema))
    if L <= 0 or H <= 0:
        ris[u"piani"] = []
        return ris
    try:
        _costruisci(schema, L, H, valori, ris)
    except (IndexError, KeyError, TypeError):
        # struttura rotta (es. misure mancanti): gli errori lo dicono gia'
        if not err:
            raise
        ris[u"piani"], ris[u"pezzi"], ris[u"celle"], ris[u"simboli"] = [], [], [], []
    return ris


def _costruisci(schema, L, H, valori, ris):
    err = ris[u"errori"]
    piani = _Piani(L, H)
    ris[u"piani"] = piani.lista

    # telaio perimetrale (cornice)
    t, s = valori[profilo(u"telaio")], valori[profilo(u"soglia")]
    est = (u"sx", u"dx", u"basso", u"alto")
    inn = (piani.aggiungi(u"sx", profilo(u"telaio"), 1, t),
           piani.aggiungi(u"dx", profilo(u"telaio"), -1, t),
           piani.aggiungi(u"basso", profilo(u"soglia"), 1, s),
           piani.aggiungi(u"alto", profilo(u"telaio"), -1, t))
    ris[u"pezzi"].append(_pezzo(u"telaio", est, inn, u"telaio", None))

    stato = {u"scorrevoli": 0}
    bordi = {u"sx": (u"sx", u"telaio"), u"dx": (u"dx", u"telaio"),
             u"basso": (u"basso", u"soglia"), u"alto": (u"alto", u"telaio")}
    _visita(schema[u"radice"], (), bordi, piani, valori, ris, stato)

    for c in ris[u"celle"]:
        _controlla_cella(c, piani, valori, err)


def _pezzo(tipo, esterni, interni, profondita, percorso):
    return {u"tipo": tipo, u"esterni": tuple(esterni),
            u"interni": tuple(interni) if interni else None,
            u"profondita": profondita, u"cella": percorso}


_DENTRO = {u"sx": 1, u"basso": 1, u"dx": -1, u"alto": -1}


def _faccia(bordo, lato, piani, valori):
    """Piano della faccia interna di un bordo di zona."""
    pid, tipo = bordo
    if tipo == u"battuta":
        return pid
    nome = {u"telaio": profilo(u"telaio"), u"soglia": profilo(u"soglia"),
            u"montante": MONTANTE_MEZZO}[tipo]
    return piani.aggiungi(pid, nome, _DENTRO[lato], valori[nome])


def _visita(nodo, percorso, bordi, piani, valori, ris, stato):
    if nodo[u"tipo"] == u"cella":
        _cella(nodo, percorso, bordi, piani, valori, ris, stato)
        return
    verso = nodo[u"verso"]
    inizio, fine = (u"sx", u"dx") if verso == u"v" else (u"basso", u"alto")
    trasv = (u"basso", u"alto") if verso == u"v" else (u"sx", u"dx")
    tipo_interno = u"montante" if nodo[u"montante"] else u"battuta"
    n = len(nodo[u"figli"])
    precedente = bordi[inizio]
    for i, figlio in enumerate(nodo[u"figli"]):
        p_figlio = percorso + (i,)
        if i < n - 1:
            nome = nome_misura(verso, p_figlio)
            valori[nome] = float(nodo[u"misure"][i])
            asse = piani.aggiungi(precedente[0], nome, 1, valori[nome])
            ris[u"misure"].append({u"nome": nome, u"valore": valori[nome],
                                   u"divisione": percorso, u"indice": i, u"verso": verso})
            successivo = (asse, tipo_interno)
            if nodo[u"montante"]:
                m = valori[MONTANTE_MEZZO]
                a = piani.aggiungi(asse, MONTANTE_MEZZO, -1, m)
                b = piani.aggiungi(asse, MONTANTE_MEZZO, 1, m)
                t0 = _faccia(bordi[trasv[0]], trasv[0], piani, valori)
                t1 = _faccia(bordi[trasv[1]], trasv[1], piani, valori)
                esterni = (a, b, t0, t1) if verso == u"v" else (t0, t1, a, b)
                ris[u"pezzi"].append(_pezzo(u"montante", esterni, None, u"telaio", p_figlio))
        else:
            successivo = bordi[fine]
        b_figlio = dict(bordi)
        b_figlio[inizio] = precedente
        b_figlio[fine] = successivo
        _visita(figlio, p_figlio, b_figlio, piani, valori, ris, stato)
        precedente = successivo


def _cella(nodo, percorso, bordi, piani, valori, ris, stato):
    anta = nodo[u"anta"]
    luce = tuple(_faccia(bordi[lato], lato, piani, valori) for lato in RADICI)
    regione = tuple(bordi[lato][0] for lato in RADICI)
    c = {u"percorso": percorso, u"anta": anta, u"regione": regione, u"luce": luce,
         u"anta_interna": None, u"vetro": luce, u"zoccolo": None, u"livello": u""}
    if S.apribile(anta):
        a = valori[profilo(u"anta")]
        nome = profilo(u"anta")
        interna = (piani.aggiungi(luce[0], nome, 1, a), piani.aggiungi(luce[1], nome, -1, a),
                   piani.aggiungi(luce[2], nome, 1, a), piani.aggiungi(luce[3], nome, -1, a))
        c[u"anta_interna"] = interna
        c[u"vetro"] = interna
        if S.scorrevole(anta):
            c[u"livello"] = u"a" if stato[u"scorrevoli"] % 2 == 0 else u"b"
            stato[u"scorrevoli"] += 1
        livello = c[u"livello"]
        prof_anta = u"anta_" + livello if livello else u"anta"
        prof_vetro = u"vetro_" + livello if livello else u"vetro_anta"
        ris[u"pezzi"].append(_pezzo(u"anta", luce, interna, prof_anta, percorso))
        z = valori[profilo(u"zoccolo")]
        if S.porta(anta) and z > 0:
            cima = piani.aggiungi(interna[2], profilo(u"zoccolo"), 1, z)
            c[u"zoccolo"] = (interna[0], interna[1], interna[2], cima)
            c[u"vetro"] = (interna[0], interna[1], cima, interna[3])
            ris[u"pezzi"].append(_pezzo(u"zoccolo", c[u"zoccolo"], None, prof_anta, percorso))
        ris[u"pezzi"].append(_pezzo(u"vetro", c[u"vetro"], None, prof_vetro, percorso))
    else:
        ris[u"pezzi"].append(_pezzo(u"vetro", luce, None, u"vetro", percorso))
    ris[u"celle"].append(c)
    if S.apribile(anta):
        _simbolo(c, piani, valori, ris)


# --- simboli di apertura -------------------------------------------------------------
def _su_piano(piani, pid):
    """Coordinata che sta su un piano, espressa come (piano base, parametro, segno)."""
    p = piani.per_id[pid]
    return (p[u"base"], p[u"param"], p[u"segno"])


def _derivato(ris, piani, nome, formula, valore):
    for d in ris[u"derivati"]:
        if d[u"nome"] == nome:
            return
    ris[u"derivati"].append({u"nome": nome, u"formula": formula, u"valore": valore})


def _simbolo(c, piani, valori, ris):
    sx, dx, basso, alto = c[u"luce"]
    per = c[u"percorso"]
    fp = lambda pid: formula_posizione(piani.per_id, pid)  # noqa: E731
    x0, x1, y0, y1 = piani.pos(sx), piani.pos(dx), piani.pos(basso), piani.pos(alto)

    nome_mh = nome_mezza_altezza(per)
    nome_ml = nome_mezza_larghezza(per)
    mh = (y1 - y0) / 2.0
    ml = (x1 - x0) / 2.0
    f_mh = u"(%s) / 2" % _differenza(fp(alto), fp(basso))
    f_ml = u"(%s) / 2" % _differenza(fp(dx), fp(sx))

    X = {u"sx": (x0, _su_piano(piani, sx)), u"dx": (x1, _su_piano(piani, dx))}
    Y = {u"basso": (y0, _su_piano(piani, basso)), u"alto": (y1, _su_piano(piani, alto))}

    def mezzo_y():
        _derivato(ris, piani, nome_mh, f_mh, mh)
        valori[nome_mh] = mh
        return (y0 + mh, (basso, nome_mh, 1))

    def mezzo_x():
        _derivato(ris, piani, nome_ml, f_ml, ml)
        valori[nome_ml] = ml
        return (x0 + ml, (sx, nome_ml, 1))

    segmenti = []

    def seg(px, py, qx, qy):
        segmenti.append({u"p0": (px[0], py[0]), u"p1": (qx[0], qy[0]),
                         u"coord": (px[1], py[1], qx[1], qy[1])})

    anta = c[u"anta"]
    cerniere = None
    if anta.endswith(u"_sx") and not S.scorrevole(anta):
        cerniere, maniglia = u"sx", u"dx"
    elif anta.endswith(u"_dx") and not S.scorrevole(anta):
        cerniere, maniglia = u"dx", u"sx"
    if cerniere:
        punta = (X[cerniere], mezzo_y())
        seg(X[maniglia], Y[u"alto"], punta[0], punta[1])
        seg(X[maniglia], Y[u"basso"], punta[0], punta[1])
    if anta == u"vasistas" or anta.startswith(u"anta_ribalta"):
        mx = mezzo_x()
        seg(X[u"sx"], Y[u"alto"], mx, Y[u"basso"])
        seg(X[u"dx"], Y[u"alto"], mx, Y[u"basso"])
    if S.scorrevole(anta):
        verso = u"sx" if anta.endswith(u"_sx") else u"dx"
        dentro = _DENTRO[verso]
        fl = valori[profilo(u"freccia_l")]
        fa = valori[profilo(u"freccia_a")]
        my = mezzo_y()
        mx = mezzo_x()
        seg(mx, my, X[verso], my)
        nome_fa, nome_fb = nome_freccia(per, True), nome_freccia(per, False)
        _derivato(ris, piani, nome_fa, u"%s + %s" % (nome_mh, profilo(u"freccia_a")), mh + fa)
        _derivato(ris, piani, nome_fb, u"%s - %s" % (nome_mh, profilo(u"freccia_a")), mh - fa)
        valori[nome_fa] = mh + fa
        valori[nome_fb] = mh - fa
        xb = (X[verso][0] + dentro * fl,
              (dx if verso == u"dx" else sx, profilo(u"freccia_l"), dentro))
        seg(X[verso], my, xb, (y0 + mh + fa, (basso, nome_fa, 1)))
        seg(X[verso], my, xb, (y0 + mh - fa, (basso, nome_fb, 1)))
    ris[u"simboli"].append({u"cella": per, u"segmenti": segmenti})


# --- controlli sulle misure ----------------------------------------------------------
def _controlla_cella(c, piani, valori, err):
    dove = nome_zona(c[u"percorso"])
    r = [piani.pos(p) for p in c[u"regione"]]
    if r[1] - r[0] <= _EPS or r[3] - r[2] <= _EPS:
        err.append(u"Zona %s: le misure delle zone superano lo spazio disponibile." % dove)
        return
    luce = [piani.pos(p) for p in c[u"luce"]]
    if c[u"anta_interna"] is None:
        if luce[1] - luce[0] < LUCE_MIN_FISSO or luce[3] - luce[2] < LUCE_MIN_FISSO:
            err.append(u"Zona %s: troppo stretta per un vetro (luce %d x %d mm)."
                       % (dove, luce[1] - luce[0], luce[3] - luce[2]))
        return
    vetro = [piani.pos(p) for p in c[u"vetro"]]
    if vetro[1] - vetro[0] < LUCE_MIN_ANTA or vetro[3] - vetro[2] < LUCE_MIN_ANTA:
        err.append(u"Zona %s: troppo piccola per un'anta (luce %d x %d mm)."
                   % (dove, luce[1] - luce[0], luce[3] - luce[2]))


# --- aiuti per anteprima e controlli -------------------------------------------------
def rettangolo(ris, piani_ids):
    """(x0, y0, x1, y1) da una quaterna di piani (sx, dx, basso, alto)."""
    per_id = dict((p[u"id"], p) for p in ris[u"piani"])
    sx, dx, b, a = piani_ids
    return (per_id[sx][u"pos"], per_id[b][u"pos"], per_id[dx][u"pos"], per_id[a][u"pos"])


def cella_in_punto(ris, x, y):
    """Percorso della cella la cui zona (tra assi) contiene il punto; None se fuori."""
    for c in ris[u"celle"]:
        x0, y0, x1, y1 = rettangolo(ris, c[u"regione"])
        if x0 - _EPS <= x <= x1 + _EPS and y0 - _EPS <= y <= y1 + _EPS:
            return c[u"percorso"]
    return None
