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

Pianta e 3D (y = profondita' dall'asse del muro, verso l'interno se INTERNO = 1):
- piani_y: piani paralleli al muro, dal piano "centro" del modello famiglia;
- pianta: simboli di apertura in pianta (anta aperta a 90 gradi e arco), quotabili come i
  simboli del prospetto ma con la y su un piano_y;
- pezzi_aperti: le ante a battente aperte a 90 gradi verso l'interno (si vedono con il
  parametro di istanza "Aperta in 3D"); gli scorrevoli aperti stanno in `pezzi` (spostati).
Ogni pezzo ha `dettaglio` (livelli Basso/Medio/Alto in cui si vede) e `stato`
(None = sempre, "chiusa" = solo con l'anta chiusa, "aperta" = solo con l'anta aperta).
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
# maniglie: placca sul profilo dell'anta, collo, leva; "int"/"est" = lato interno/esterno dell'anta
PARTI_MANIGLIA = ((u"placca", u"placca"), (u"collo", u"collo"), (u"leva", u"leva"))
for _lato, _nome in ((u"int", u"interna"), (u"est", u"esterna")):
    for _parte, _np in PARTI_MANIGLIA:
        PROFONDITA[u"man_%s_%s" % (_parte, _lato)] = (u"Maniglia %s %s inizio" % (_np, _nome),
                                                      u"Maniglia %s %s fine" % (_np, _nome))
# maniglione antipanico: due supporti e la barra, sul lato da cui si spinge (opposto all'apertura)
PROFONDITA[u"panico_supporto"] = (u"Antipanico supporti inizio", u"Antipanico supporti fine")
PROFONDITA[u"panico_barra"] = (u"Antipanico barra inizio", u"Antipanico barra fine")

# lato interno della profondita' (+1 = verso "Anta fine"): ci vanno maniglie, archi e ante
# aperte. Se nel modello famiglia di Revit l'interno e' dall'altra parte, si cambia qui.
INTERNO = -1
# Le profondita' dei pezzi (formule "... inizio/fine") sono offset lungo la normale del piano di
# schizzo dell'asse del telaio, che nei modelli (piano Centro Fronte/Retro) e' -Y: li' l'interno
# va col segno INTERNO_PROF. revit_famiglia tiene la normale dell'asse sempre cosi'.
ASSE_SCHIZZO = -1
INTERNO_PROF = INTERNO * ASSE_SCHIZZO

# livelli di dettaglio di Revit (Basso/Medio/Alto)
BASSO, MEDIO, ALTO = u"basso", u"medio", u"alto"
TUTTI = (BASSO, MEDIO, ALTO)
MEDIO_ALTO = (MEDIO, ALTO)
SOLO_ALTO = (ALTO,)
SOLO_BASSO = (BASSO,)

# stato dell'anta nel 3D (parametri di istanza Si'/No)
APERTA = u"Aperta in 3D"
CHIUSA = u"Chiusa in 3D"
FILO_ANTA = u"Filo anta interno"
ASSE_TELAIO = u"Asse telaio dal filo"     # dal filo del muro all'asse del telaio
MEZZO_TELAIO = u"Mezzo telaio"           # meta' profondita' del telaio: asse -> facce
MURO = u"Spessore muro (anteprima)"

# spessore delle ante aperte (estrusioni sul piano delle cerniere, verso il vano):
# {verso: (parametro inizio, parametro fine)}; None = 0
SPESSORI_APERTI = {
    u"anta": {1: (None, u"Anta aperta pos"), -1: (None, u"Anta aperta neg")},
    u"vetro": {1: (u"Vetro aperto inizio pos", u"Vetro aperto fine pos"),
               -1: (u"Vetro aperto inizio neg", u"Vetro aperto fine neg")},
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


def nome_quota_maniglia(percorso):
    return u"Maniglia quota %s" % nome_zona(percorso)


def nome_larghezza_anta(percorso):
    return u"Larghezza anta %s" % nome_zona(percorso)


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


class _PianiY(_Piani):
    """Piani paralleli al muro (normale y). Radici: "centro" (l'asse del muro) e le due facce
    del muro "esterno"/"interno" (nel modello famiglia sono i piani Esterno/Interno, legati
    al muro: seguono il suo spessore)."""
    def __init__(self, spessore_muro=0.0):
        self.lista = []
        self._per_chiave = {}
        self.per_id = {}
        self._n = 0
        meta = float(spessore_muro) / 2.0
        for pid, pos in ((u"centro", 0.0), (u"esterno", -INTERNO * meta), (u"interno", INTERNO * meta)):
            self._registra({u"id": pid, u"verso": u"y", u"pos": pos,
                            u"base": None, u"param": None, u"segno": 0})

    def aggiungi(self, base, param, segno, valore):
        chiave = (base, param, segno)
        if chiave in self._per_chiave:
            return self._per_chiave[chiave]
        b = self.per_id[base]
        self._n += 1
        pid = u"Y%d" % self._n
        self._registra({u"id": pid, u"verso": u"y", u"pos": b[u"pos"] + segno * valore,
                        u"base": base, u"param": param, u"segno": segno})
        self._per_chiave[chiave] = pid
        return pid


def formula_posizione(piani_per_id, pid):
    """Posizione di un piano come formula Revit (u"" = zero)."""
    p = piani_per_id[pid]
    if p[u"base"] is None:
        return {u"sx": u"", u"basso": u"", u"dx": LARGHEZZA, u"alto": ALTEZZA, u"centro": u""}[pid]
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


def calcola(schema, spessore_muro=None):
    """spessore_muro: quello del muro del modello famiglia (in Revit); di base quello
    dell'anteprima scelto nel passo 5."""
    L = float(schema[u"larghezza"])
    H = float(schema[u"altezza"])
    prof = schema[u"profili"]
    valori = {LARGHEZZA: L, ALTEZZA: H, MONTANTE_MEZZO: prof[u"montante"] / 2.0}
    for k, nome in NOMI_PROFILI.items():
        valori[nome] = float(prof[k])
    contorno = schema.get(u"contorno") or S.contorno_vuoto()
    for k, nome, _v, _m in S.MISURE_CONTORNO:
        valori[nome] = float(contorno[u"misure"].get(k, S.MISURE_CONTORNO_PREDEFINITE[k]))
    if spessore_muro is not None:
        valori[MURO] = float(spessore_muro)

    ris = {u"piani": None, u"pezzi": [], u"celle": [], u"simboli": [], u"derivati": [],
           u"errori": [], u"misure": [], u"valori": valori,
           u"piani_y": [], u"pianta": [], u"pezzi_aperti": [], u"contorno": [],
           u"asse": u"centro", u"asse_y": 0.0}
    err = ris[u"errori"]
    if L <= 0 or H <= 0:
        err.append(u"Larghezza e altezza devono essere maggiori di zero.")
    for k, etichetta, _v, minimo in S.PROFILI:
        if minimo is not None and prof[k] < minimo:
            err.append(u"%s: almeno %g mm." % (etichetta, minimo))
    for k, etichetta, _v, minimo in S.MISURE_CONTORNO:
        if valori[etichetta] < minimo and _misura_in_uso(schema, k):
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
        ris[u"piani_y"], ris[u"pianta"], ris[u"pezzi_aperti"], ris[u"contorno"] = [], [], [], []
    return ris


def _misura_in_uso(schema, chiave):
    """La misura del contorno conta per lo schema (se no il suo minimo non si controlla)."""
    if chiave == u"muro":
        return True
    c = schema.get(u"contorno") or {}
    if chiave == u"posizione":
        return c.get(u"posizione", u"centro") != u"centro"
    return any(chiave in S.MISURE_DI[e] for e in S.elementi_ammessi(schema.get(u"categoria"))
               if S.contorno_attivo(schema, e))


def _costruisci(schema, L, H, valori, ris):
    err = ris[u"errori"]
    piani = _Piani(L, H)
    ris[u"piani"] = piani.lista

    # telaio perimetrale: cornice con la soglia, a U senza (si passa senza inciampare)
    t, s = valori[profilo(u"telaio")], valori[profilo(u"soglia")]
    if schema.get(u"soglia", True):
        est = (u"sx", u"dx", u"basso", u"alto")
        inn = (piani.aggiungi(u"sx", profilo(u"telaio"), 1, t),
               piani.aggiungi(u"dx", profilo(u"telaio"), -1, t),
               piani.aggiungi(u"basso", profilo(u"soglia"), 1, s),
               piani.aggiungi(u"alto", profilo(u"telaio"), -1, t))
        ris[u"pezzi"].append(_pezzo(u"telaio", est, inn, u"telaio", None))
        bordo_basso = (u"basso", u"soglia")
    else:
        i_sx = piani.aggiungi(u"sx", profilo(u"telaio"), 1, t)
        i_dx = piani.aggiungi(u"dx", profilo(u"telaio"), -1, t)
        i_alto = piani.aggiungi(u"alto", profilo(u"telaio"), -1, t)
        for esterni in ((u"sx", i_sx, u"basso", u"alto"), (i_dx, u"dx", u"basso", u"alto"),
                        (i_sx, i_dx, i_alto, u"alto")):
            ris[u"pezzi"].append(_pezzo(u"telaio", esterni, None, u"telaio", None))
        bordo_basso = (u"basso", u"terra")        # ante e vetri arrivano quasi a terra

    # piani paralleli al muro: asse del telaio (dove sta nel muro), poi filo interno dell'anta,
    # da cui partono archi in pianta e ante aperte
    piani_y = _PianiY(valori[MURO])
    ris[u"piani_y"] = piani_y.lista
    asse = _asse_telaio(schema, piani_y, valori, ris)
    ris[u"asse"] = asse
    ris[u"asse_y"] = piani_y.pos(asse)
    spost, prof_a = valori[profilo(u"anta_spost")], valori[profilo(u"anta_prof")]
    # faccia interna dell'anta: in profondita' e' spost + prof/2 dal lato INTERNO_PROF; il piano
    # y sta a quella distanza dall'asse verso INTERNO
    if INTERNO_PROF > 0:
        filo, f_filo = spost + prof_a / 2.0, u"%s + %s / 2" % (profilo(u"anta_spost"), profilo(u"anta_prof"))
    else:
        filo, f_filo = prof_a / 2.0 - spost, u"%s / 2 - %s" % (profilo(u"anta_prof"), profilo(u"anta_spost"))
    valori[FILO_ANTA] = filo
    stato = {u"scorrevoli": 0, u"categoria": schema.get(u"categoria", S.FINESTRE),
             u"piani_y": piani_y, u"f_filo": f_filo, u"filo": None, u"asse": asse,
             u"simbolo_finestre": schema.get(u"simbolo_pianta", u"nessuno")}
    bordi = {u"sx": (u"sx", u"telaio"), u"dx": (u"dx", u"telaio"),
             u"basso": bordo_basso, u"alto": (u"alto", u"telaio")}
    _visita(schema[u"radice"], (), bordi, piani, valori, ris, stato)

    # livello Basso: un vetro solo dentro il telaio, al posto di montanti, ante e vetri
    unico = tuple(_faccia(bordi[lato], lato, piani, valori) for lato in RADICI)
    ris[u"pezzi"].append(_pezzo(u"vetro", unico, None, u"vetro", None, dettaglio=SOLO_BASSO))

    for c in ris[u"celle"]:
        _controlla_cella(c, piani, valori, err)
    _contorno(schema, piani, piani_y, asse, valori, ris)


def _pezzo(tipo, esterni, interni, profondita, percorso, dettaglio=TUTTI, stato=None):
    return {u"tipo": tipo, u"esterni": tuple(esterni),
            u"interni": tuple(interni) if interni else None,
            u"profondita": profondita, u"cella": percorso,
            u"dettaglio": tuple(dettaglio), u"stato": stato}


_DENTRO = {u"sx": 1, u"basso": 1, u"dx": -1, u"alto": -1}


def _faccia(bordo, lato, piani, valori):
    """Piano della faccia interna di un bordo di zona."""
    pid, tipo = bordo
    if tipo == u"battuta":
        return pid
    nome = {u"telaio": profilo(u"telaio"), u"soglia": profilo(u"soglia"),
            u"terra": profilo(u"terra"), u"montante": MONTANTE_MEZZO}[tipo]
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
                ris[u"pezzi"].append(_pezzo(u"montante", esterni, None, u"telaio", p_figlio,
                                            dettaglio=MEDIO_ALTO))
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
    riemp = S.riempimento_valido(anta, nodo.get(u"riempimento", S.VETRO))
    c = {u"percorso": percorso, u"anta": anta, u"regione": regione, u"luce": luce,
         u"anta_interna": None, u"vetro": luce, u"zoccolo": None, u"livello": u"",
         u"riempimento": riemp, u"maniglia": S.maniglia_di(nodo, stato[u"categoria"])}
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
        if riemp == S.ZOCCOLO and z > 0:
            cima = piani.aggiungi(interna[2], profilo(u"zoccolo"), 1, z)
            c[u"zoccolo"] = (interna[0], interna[1], interna[2], cima)
            c[u"vetro"] = (interna[0], interna[1], cima, interna[3])
            ris[u"pezzi"].append(_pezzo(u"zoccolo", c[u"zoccolo"], None, prof_anta, percorso))
        if riemp == S.PANNELLO:
            ris[u"pezzi"].append(_pezzo(u"pannello", c[u"vetro"], None, prof_anta, percorso))
        else:
            ris[u"pezzi"].append(_pezzo(u"vetro", c[u"vetro"], None, prof_vetro, percorso))
    elif riemp == S.PANNELLO:
        ris[u"pezzi"].append(_pezzo(u"pannello", luce, None, u"telaio", percorso))
    else:
        ris[u"pezzi"].append(_pezzo(u"vetro", luce, None, u"vetro", percorso))
    ris[u"celle"].append(c)
    if S.apribile(anta):
        _simbolo(c, piani, valori, ris)
        if c[u"maniglia"] != S.NESSUNA:
            _maniglia(c, piani, valori, ris)
    # i pezzi della cella si vedono da Medio in su (a Basso c'e' il vetro unico), la maniglia ad Alto
    propri = [pz for pz in ris[u"pezzi"] if pz[u"cella"] == percorso and pz[u"tipo"] != u"montante"]
    for pz in propri:
        pz[u"dettaglio"] = SOLO_ALTO if pz[u"tipo"] == u"maniglia" else MEDIO_ALTO
    aperta = False
    if S.ruota(anta):
        aperta = _aperta_ruota(c, piani, valori, ris, stato)
    elif S.scorrevole(anta):
        aperta = _aperta_scorre(c, propri, piani, valori, ris)
    if aperta:
        for pz in propri:
            pz[u"stato"] = u"chiusa"


# --- simboli di apertura -------------------------------------------------------------
def _su_piano(piani, pid):
    """Coordinata che sta su un piano, espressa come (piano base, parametro, segno)."""
    p = piani.per_id[pid]
    return (p[u"base"], p[u"param"], p[u"segno"])


def _derivato(ris, _piani, nome, formula, valore):
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


# --- ante aperte e simboli in pianta -----------------------------------------------------
def _su_piano_y(piani_y, pid):
    p = piani_y.per_id[pid]
    return (p[u"base"], p[u"param"], p[u"segno"])


def _larghezza_anta(c, piani, valori, ris):
    sx, dx = c[u"luce"][0], c[u"luce"][1]
    nome = nome_larghezza_anta(c[u"percorso"])
    w = piani.pos(dx) - piani.pos(sx)
    fp = lambda pid: formula_posizione(piani.per_id, pid)  # noqa: E731
    _derivato(ris, piani, nome, _differenza(fp(dx), fp(sx)), w)
    valori[nome] = w
    return nome, w


def _filo(stato, valori, ris):
    """Piano y del filo interno dell'anta (creato una volta sola)."""
    if stato[u"filo"] is None:
        _derivato(ris, None, FILO_ANTA, stato[u"f_filo"], valori[FILO_ANTA])
        stato[u"filo"] = stato[u"piani_y"].aggiungi(stato[u"asse"], FILO_ANTA, INTERNO, valori[FILO_ANTA])
    return stato[u"filo"]


def _aperta_ruota(c, piani, valori, ris, stato):
    """Anta a battente aperta a 90 gradi verso l'interno + anta e arco in pianta."""
    per = c[u"percorso"]
    py = stato[u"piani_y"]
    sx, dx, basso, alto = c[u"luce"]
    isx, idx, ib, ia = c[u"anta_interna"]
    cerniere_sx = c[u"anta"].endswith(u"_sx")
    x_h, x_l = (sx, dx) if cerniere_sx else (dx, sx)
    verso = 1 if cerniere_sx else -1            # lo spessore dell'anta aperta va verso il vano
    nome_w, w = _larghezza_anta(c, piani, valori, ris)
    a = valori[profilo(u"anta")]
    yf = _filo(stato, valori, ris)
    yw = py.aggiungi(yf, nome_w, INTERNO, w)
    yi0 = py.aggiungi(yf, profilo(u"anta"), INTERNO, a)
    yi1 = py.aggiungi(yw, profilo(u"anta"), -INTERNO, a)

    def pezzo(tipo, y, z, y_int=None, z_int=None, spessore=u"anta"):
        ris[u"pezzi_aperti"].append({
            u"tipo": tipo, u"cella": per, u"piano_x": x_h, u"verso": verso,
            u"y": y, u"z": z, u"y_int": y_int, u"z_int": z_int, u"spessore": spessore,
            u"dettaglio": MEDIO_ALTO, u"stato": u"aperta"})

    pezzo(u"anta", (yf, yw), (basso, alto), (yi0, yi1), (ib, ia))
    riemp = c[u"riempimento"]
    if c[u"zoccolo"] is not None:
        pezzo(u"zoccolo", (yi0, yi1), (ib, c[u"zoccolo"][3]))
    z_vetro = (c[u"vetro"][2], c[u"vetro"][3])
    if riemp == S.PANNELLO:
        pezzo(u"pannello", (yi0, yi1), z_vetro)
    else:
        pezzo(u"vetro", (yi0, yi1), z_vetro, spessore=u"vetro")

    # pianta: anta aperta e arco (porte sempre; finestre secondo la scelta)
    if S.porta(c[u"anta"]):
        stile = u"porta"
    elif stato[u"simbolo_finestre"] in (u"tratteggio", u"continuo"):
        stile = u"finestra_" + stato[u"simbolo_finestre"]
    else:
        stile = None
    if stile:
        XH, XL = (piani.pos(x_h), _su_piano(piani, x_h)), (piani.pos(x_l), _su_piano(piani, x_l))
        YF, YW = (py.pos(yf), _su_piano_y(py, yf)), (py.pos(yw), _su_piano_y(py, yw))
        ris[u"pianta"].append({u"cella": per, u"stile": stile, u"segmenti": [
            {u"tipo": u"linea", u"p0": (XH[0], YF[0]), u"p1": (XH[0], YW[0]),
             u"coord": (XH[1], YF[1], XH[1], YW[1])},
            {u"tipo": u"arco", u"p0": (XL[0], YF[0]), u"p1": (XH[0], YW[0]),
             u"centro": (XH[0], YF[0]), u"coord": (XL[1], YF[1], XH[1], YW[1])},
        ]})
    return True


def _aperta_scorre(c, propri, piani, valori, ris):
    """Anta scorrevole aperta: gli stessi pezzi spostati di una larghezza verso l'apertura."""
    nome_w, w = _larghezza_anta(c, piani, valori, ris)
    segno = -1 if c[u"anta"].endswith(u"_sx") else 1
    spostati = {}

    def sposta(pid):
        if pid not in spostati:
            spostati[pid] = piani.aggiungi(pid, nome_w, segno, w)
        return spostati[pid]

    for pz in list(propri):
        if pz[u"tipo"] == u"maniglia":
            continue
        e = pz[u"esterni"]
        nuovo = _pezzo(pz[u"tipo"], (sposta(e[0]), sposta(e[1]), e[2], e[3]),
                       (sposta(pz[u"interni"][0]), sposta(pz[u"interni"][1]),
                        pz[u"interni"][2], pz[u"interni"][3]) if pz[u"interni"] else None,
                       pz[u"profondita"], c[u"percorso"], dettaglio=MEDIO_ALTO, stato=u"aperta")
        ris[u"pezzi"].append(nuovo)
    return True


# --- contorno: posizione nel muro, foro, mostre, davanzali, imbotte ------------------------
MC = dict((k, e) for k, e, _v, _m in S.MISURE_CONTORNO)    # chiave -> nome del parametro
MAT_MOSTRE = u"Materiale mostre"
MAT_DAVANZALI = u"Materiale davanzali"
MAT_IMBOTTE = u"Materiale imbotte"
MAT_MAZZETTA = u"Materiale mazzetta"


def _asse_telaio(schema, piani_y, valori, ris):
    """Piano y dell'asse del telaio: l'asse del muro, o a una distanza da una sua faccia."""
    posizione = (schema.get(u"contorno") or {}).get(u"posizione", u"centro")
    if posizione == u"centro":
        return u"centro"
    tp = profilo(u"telaio_prof")
    v = valori[MC[u"posizione"]] + valori[tp] / 2.0
    _derivato(ris, None, ASSE_TELAIO, u"%s + %s / 2" % (MC[u"posizione"], tp), v)
    valori[ASSE_TELAIO] = v
    if posizione == u"filo_esterno":
        return piani_y.aggiungi(u"esterno", ASSE_TELAIO, INTERNO, v)
    return piani_y.aggiungi(u"interno", ASSE_TELAIO, -INTERNO, v)


def _contorno(schema, piani, py, asse, valori, ris):
    """Elementi del contorno in ris["contorno"]: {chiave, nome, tipo, x, z, y, visibile, materiale}.

    x, z: coppie di piani (prospetto); y: coppia di piani paralleli al muro.
    tipo: mazzetta, mostra, davanzale, soglia, imbotte.
    visibile: parametro Si'/No che accende l'elemento nella famiglia.
    """
    err = ris[u"errori"]
    porta = schema.get(u"categoria") == S.PORTE
    T = valori[MURO]
    tp = valori[profilo(u"telaio_prof")]
    if abs(py.pos(asse)) + tp / 2.0 > T / 2.0 + _EPS:
        err.append(u"Il telaio (profondità %g mm) esce dal muro di %g mm: cambia la posizione nel muro "
                   u"o lo spessore del muro." % (tp, T))
    facce = {}

    def faccia(lato):
        """Piano y della faccia del telaio verso l'esterno ("est") o l'interno ("int")."""
        if lato not in facce:
            _derivato(ris, None, MEZZO_TELAIO, u"%s / 2" % profilo(u"telaio_prof"), tp / 2.0)
            valori[MEZZO_TELAIO] = tp / 2.0
            facce[lato] = py.aggiungi(asse, MEZZO_TELAIO, -INTERNO if lato == u"est" else INTERNO, tp / 2.0)
        return facce[lato]

    def spazio(a, b, cosa):
        if abs(py.pos(a) - py.pos(b)) < 1.0:
            err.append(u"%s: tra il telaio e il filo del muro non c'è spazio (cambia la posizione nel muro)."
                       % cosa)

    def el(chiave, nome, tipo, x, z, y, materiale=None):
        ris[u"contorno"].append({
            u"chiave": chiave, u"nome": nome, u"tipo": tipo, u"x": x, u"z": z, u"y": y,
            u"visibile": S.NOMI_ELEMENTI_CONTORNO[chiave], u"materiale": materiale})

    att = lambda e: S.contorno_attivo(schema, e)  # noqa: E731
    sx, dx, basso, alto = u"sx", u"dx", u"basso", u"alto"
    hx0, hx1, hz1 = sx, dx, alto          # bordi del foro sul lato esterno
    if att(u"mazzetta"):
        # riseghe piene nel foro, dal filo esterno del muro alla faccia del telaio: da fuori il
        # foro e' piu' stretto e il telaio sta dietro la battuta. (Un vuoto che taglia il muro
        # ospite le API di Revit non lo permettono nelle famiglie: il foro resta quello del modello.)
        n, m = MC[u"mazzetta"], valori[MC[u"mazzetta"]]
        hx0, hx1, hz1 = piani.aggiungi(sx, n, 1, m), piani.aggiungi(dx, n, -1, m), piani.aggiungi(alto, n, -1, m)
        spazio(u"esterno", faccia(u"est"), u"Mazzetta")
        y = (u"esterno", faccia(u"est"))
        el(u"mazzetta", u"Mazzetta sinistra", u"mazzetta", (sx, hx0), (basso, alto), y, MAT_MAZZETTA)
        el(u"mazzetta", u"Mazzetta destra", u"mazzetta", (hx1, dx), (basso, alto), y, MAT_MAZZETTA)
        el(u"mazzetta", u"Mazzetta sopra", u"mazzetta", (hx0, hx1), (hz1, alto), y, MAT_MAZZETTA)

    for chiave, filo, bordi, davanzale in ((u"mostra_est", u"esterno", (hx0, hx1, hz1), u"dav_est"),
                                           (u"mostra_int", u"interno", (sx, dx, alto), u"dav_int")):
        if not att(chiave):
            continue
        nl, w = MC[u"mostra_l"], valori[MC[u"mostra_l"]]
        fuori = -INTERNO if filo == u"esterno" else INTERNO
        y = (filo, py.aggiungi(filo, MC[u"mostra_sp"], fuori, valori[MC[u"mostra_sp"]]))
        b0, b1, bz = bordi
        m0, m1, mz = piani.aggiungi(b0, nl, -1, w), piani.aggiungi(b1, nl, 1, w), piani.aggiungi(bz, nl, 1, w)
        sotto = not porta and not att(davanzale)     # finestre senza davanzale: cornice chiusa
        z0 = piani.aggiungi(basso, nl, -1, w) if sotto else basso
        nome = S.NOMI_ELEMENTI_CONTORNO[chiave]
        el(chiave, nome + u" sinistra", u"mostra", (m0, b0), (z0, mz), y, MAT_MOSTRE)
        el(chiave, nome + u" destra", u"mostra", (b1, m1), (z0, mz), y, MAT_MOSTRE)
        el(chiave, nome + u" sopra", u"mostra", (b0, b1), (bz, mz), y, MAT_MOSTRE)
        if sotto:
            el(chiave, nome + u" sotto", u"mostra", (b0, b1), (z0, basso), y, MAT_MOSTRE)

    for chiave, filo, lato, b0, b1 in ((u"dav_est", u"esterno", u"est", hx0, hx1),
                                       (u"dav_int", u"interno", u"int", sx, dx)):
        if not att(chiave):
            continue
        suf = u"est" if lato == u"est" else u"int"
        nr, nsp, nsg = MC[u"dav_%s_ris" % suf], MC[u"dav_%s_sp" % suf], MC[u"dav_%s_sporg" % suf]
        fuori = -INTERNO if filo == u"esterno" else INTERNO
        x = (piani.aggiungi(b0, nr, -1, valori[nr]), piani.aggiungi(b1, nr, 1, valori[nr]))
        z = (piani.aggiungi(basso, nsp, -1, valori[nsp]), basso)
        y = (faccia(lato), py.aggiungi(filo, nsg, fuori, valori[nsg]))
        el(chiave, S.NOMI_ELEMENTI_CONTORNO[chiave], u"davanzale", x, z, y, MAT_DAVANZALI)

    if att(u"soglia_pietra"):
        nsp, nsg = MC[u"soglia_sp"], MC[u"soglia_sporg"]
        z = (piani.aggiungi(basso, nsp, -1, valori[nsp]), basso)
        y = (py.aggiungi(u"esterno", nsg, -INTERNO, valori[nsg]), u"interno")
        el(u"soglia_pietra", S.NOMI_ELEMENTI_CONTORNO[u"soglia_pietra"], u"soglia", (sx, dx), z, y, MAT_DAVANZALI)

    if att(u"imbotte"):
        n, t = MC[u"imbotte_sp"], valori[MC[u"imbotte_sp"]]
        i0, i1, iz = piani.aggiungi(sx, n, 1, t), piani.aggiungi(dx, n, -1, t), piani.aggiungi(alto, n, -1, t)
        y = (faccia(u"int"), u"interno")
        spazio(faccia(u"int"), u"interno", u"Imbotte")
        el(u"imbotte", u"Imbotte sinistra", u"imbotte", (sx, i0), (basso, alto), y, MAT_IMBOTTE)
        el(u"imbotte", u"Imbotte destra", u"imbotte", (i1, dx), (basso, alto), y, MAT_IMBOTTE)
        el(u"imbotte", u"Imbotte sopra", u"imbotte", (i0, i1), (iz, alto), y, MAT_IMBOTTE)


# --- maniglie ---------------------------------------------------------------------------
def lato_maniglia(anta):
    """Lato della maniglia: opposto alle cerniere; negli scorrevoli il lato che chiude
    (opposto al verso di apertura); nel vasistas in alto (u"alto")."""
    if anta == u"vasistas":
        return u"alto"
    return u"dx" if anta.endswith(u"_sx") else u"sx"


# misure derivate delle maniglie (formule: seguono anta e maniglia senza altri parametri da toccare)
MEZZA_ANTA = u"Mezza anta"
MAN_SPESSORE = u"Maniglia mezzo spessore"
MAN_PLACCA_L = u"Maniglia mezza placca"
MAN_PLACCA_H = u"Maniglia mezza altezza placca"
PANICO_BARRA = u"Antipanico mezza barra"


def _misura(ris, valori, nome, formula, valore):
    _derivato(ris, None, nome, formula, valore)
    valori[nome] = valore
    return valore


def _maniglia(c, piani, valori, ris):
    """Maniglia stilizzata (placca, collo, leva) o maniglione antipanico; segue le misure.

    Finestre: placca a meta' del profilo dell'anta sul lato maniglia, leva che scende
    (martellina). Porte: a quota da terra, leva orizzontale verso le cerniere. Vasistas: sul
    traverso alto, al centro. Lato interno, o tutti e due (c["maniglia"] == DUE_LATI).
    Antipanico: supporti sui due profili verticali dell'anta e barra in mezzo, sul lato da cui
    si spinge (opposto a quello verso cui apre l'anta).
    """
    per = c[u"percorso"]
    sx, dx, basso, alto = c[u"luce"]
    isx, idx, ib, ia = c[u"anta_interna"]
    fp = lambda pid: formula_posizione(piani.per_id, pid)  # noqa: E731
    pa, pl = profilo(u"anta"), profilo(u"maniglia_l")
    a, lung = valori[pa], valori[pl]
    lato = lato_maniglia(c[u"anta"])
    porta = S.porta(c[u"anta"])
    t = _misura(ris, valori, MAN_SPESSORE, u"%s / 10" % pa, a / 10.0)
    pw = _misura(ris, valori, MAN_PLACCA_L, u"%s / 5" % pa, a / 5.0)
    ph = _misura(ris, valori, MAN_PLACCA_H, u"%s / 3" % pl, lung / 3.0)
    err = []

    def quota_porta():
        """Piano orizzontale all'altezza della maniglia delle porte (da terra)."""
        nome_q = nome_quota_maniglia(per)
        q = valori[profilo(u"maniglia_porta")] - piani.pos(basso)
        _misura(ris, valori, nome_q, _differenza(profilo(u"maniglia_porta"), fp(basso)), q)
        return piani.aggiungi(basso, nome_q, 1, q)

    def pezzo(x, z, prof):
        ris[u"pezzi"].append(_pezzo(u"maniglia", (x[0], x[1], z[0], z[1]), None, prof, per))

    def intorno(pid, nome, v):
        return (piani.aggiungi(pid, nome, -1, v), piani.aggiungi(pid, nome, 1, v))

    if c[u"maniglia"] == S.ANTIPANICO:
        zc = quota_porta()
        tb = _misura(ris, valori, PANICO_BARRA, u"%s / 4" % pa, a / 4.0)
        s0, s1 = intorno(isx, PANICO_BARRA, tb), intorno(idx, PANICO_BARRA, tb)
        zs, zb = intorno(zc, MAN_PLACCA_H, ph), intorno(zc, PANICO_BARRA, tb)
        pezzo(s0, zs, u"panico_supporto")
        pezzo(s1, zs, u"panico_supporto")
        pezzo((s0[1], s1[0]), zb, u"panico_barra")
        if piani.pos(s1[0]) - piani.pos(s0[1]) < 4 * tb:
            err.append(u"il maniglione è più largo dell'anta")
        if piani.pos(zs[0]) < piani.pos(ib) or piani.pos(zs[1]) > piani.pos(ia):
            err.append(u"il maniglione non sta in altezza (cambia la quota da terra)")
    else:
        mezza = _misura(ris, valori, MEZZA_ANTA, u"%s / 2" % pa, a / 2.0)
        if lato == u"alto":
            # vasistas: al centro del traverso alto, leva orizzontale
            ml = (piani.pos(dx) - piani.pos(sx)) / 2.0
            nome_ml = nome_mezza_larghezza(per)
            _misura(ris, valori, nome_ml, u"(%s) / 2" % _differenza(fp(dx), fp(sx)), ml)
            xc = piani.aggiungi(sx, nome_ml, 1, ml)
            zc = piani.aggiungi(alto, MEZZA_ANTA, -1, mezza)
            verso_leva = 1
        else:
            xc = piani.aggiungi(dx, MEZZA_ANTA, -1, mezza) if lato == u"dx" else \
                piani.aggiungi(sx, MEZZA_ANTA, 1, mezza)
            if porta:
                zc = quota_porta()
            else:
                mh = (piani.pos(alto) - piani.pos(basso)) / 2.0
                nome_mh = nome_mezza_altezza(per)
                _misura(ris, valori, nome_mh, u"(%s) / 2" % _differenza(fp(alto), fp(basso)), mh)
                zc = piani.aggiungi(basso, nome_mh, 1, mh)
            verso_leva = (-1 if lato == u"dx" else 1) if porta else 0     # 0 = leva che scende
        if lato == u"alto":     # vasistas: sul traverso la placca sta coricata, come la leva
            placca = (intorno(xc, MAN_PLACCA_H, ph), intorno(zc, MAN_PLACCA_L, pw))
        else:
            placca = (intorno(xc, MAN_PLACCA_L, pw), intorno(zc, MAN_PLACCA_H, ph))
        collo = (intorno(xc, MAN_SPESSORE, t), intorno(zc, MAN_SPESSORE, t))
        if verso_leva == 0:
            leva = (collo[0], (piani.aggiungi(zc, pl, -1, lung), collo[1][1]))
            if piani.pos(leva[1][0]) < piani.pos(basso):
                err.append(u"la leva esce dall'anta in basso")
        elif verso_leva < 0:
            leva = ((piani.aggiungi(xc, pl, -1, lung), collo[0][1]), collo[1])
            if piani.pos(leva[0][0]) < piani.pos(sx):
                err.append(u"la leva esce dall'anta")
        else:
            leva = ((collo[0][0], piani.aggiungi(xc, pl, 1, lung)), collo[1])
            if piani.pos(leva[0][1]) > piani.pos(dx):
                err.append(u"la leva esce dall'anta")
        if piani.pos(placca[1][0]) < piani.pos(basso) or piani.pos(placca[1][1]) > piani.pos(alto):
            err.append(u"la placca esce dall'anta")
        lati = (u"int", u"est") if c[u"maniglia"] == S.DUE_LATI else (u"int",)
        for lato_y in lati:
            pezzo(placca[0], placca[1], u"man_placca_" + lato_y)
            pezzo(collo[0], collo[1], u"man_collo_" + lato_y)
            pezzo(leva[0], leva[1], u"man_leva_" + lato_y)
    if err:
        ris[u"errori"].append(u"Zona %s: %s (cambia le misure della maniglia)." % (nome_zona(per), err[0]))


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


# --- evidenziazione del campo in uso (anteprima del configuratore) ---------------------------
def _strisce(est, inn):
    """Una cornice in quattro rettangoli: sotto, sopra, sinistra, destra."""
    return [(est[0], est[1], est[2], inn[1]), (est[0], inn[3], est[2], est[3]),
            (est[0], inn[1], inn[0], inn[3]), (inn[2], inn[1], est[2], inn[3])]


# profilo -> tipi di pezzo che cambia
_PEZZI_DEL_PROFILO = {
    u"telaio": (u"telaio",), u"telaio_prof": (u"telaio",), u"soglia": (u"telaio",),
    u"montante": (u"montante",), u"anta": (u"anta",), u"anta_prof": (u"anta",),
    u"anta_spost": (u"anta",), u"vetro": (u"vetro",), u"zoccolo": (u"zoccolo",),
    u"maniglia_l": (u"maniglia",),
    u"maniglia_sporg": (u"maniglia",), u"maniglia_porta": (u"maniglia",),
}


def evidenzia(ris, schema, chiave):
    """Cosa illuminare nell'anteprima mentre si scrive in un campo.

    chiave: ("larghezza",) | ("altezza",) | ("misura", percorso_divisione, indice) |
    ("profilo", k). Ritorna {"rettangoli": [(x0, y0, x1, y1)], "quota": (x0, y0, x1, y1) o None}
    in mm; la quota e' orizzontale se y0 == y1.
    """
    out = {u"rettangoli": [], u"quota": None}
    if not chiave or not ris.get(u"piani"):
        return out
    L, H = float(schema[u"larghezza"]), float(schema[u"altezza"])
    tipo = chiave[0]
    if tipo == u"larghezza":
        out[u"rettangoli"].append((0.0, 0.0, L, H))
        out[u"quota"] = (0.0, H, L, H)
    elif tipo == u"altezza":
        out[u"rettangoli"].append((0.0, 0.0, L, H))
        out[u"quota"] = (L, 0.0, L, H)
    elif tipo == u"misura":
        perc, i = tuple(chiave[1]), chiave[2]
        verso = S.nodo_in(schema[u"radice"], perc)[u"verso"]
        dentro = [rettangolo(ris, c[u"regione"]) for c in ris[u"celle"]
                  if tuple(c[u"percorso"][:len(perc) + 1]) == perc + (i,)]
        if dentro:
            r = (min(x[0] for x in dentro), min(x[1] for x in dentro),
                 max(x[2] for x in dentro), max(x[3] for x in dentro))
            out[u"rettangoli"].append(r)
            out[u"quota"] = (r[0], r[3], r[2], r[3]) if verso == u"v" else (r[2], r[1], r[2], r[3])
    elif tipo == u"profilo":
        k = chiave[1]
        if k.startswith(u"freccia"):
            for simb in ris[u"simboli"]:
                c = [x for x in ris[u"celle"] if x[u"percorso"] == simb[u"cella"]]
                if c and S.scorrevole(c[0][u"anta"]):
                    pts = [p for seg in simb[u"segmenti"] for p in (seg[u"p0"], seg[u"p1"])]
                    out[u"rettangoli"].append((min(p[0] for p in pts), min(p[1] for p in pts),
                                              max(p[0] for p in pts), max(p[1] for p in pts)))
            return out
        if k == u"terra":
            if not schema.get(u"soglia", True):
                t = float(schema[u"profili"][u"telaio"])
                out[u"rettangoli"].append((t, 0.0, L - t, float(schema[u"profili"][u"terra"])))
            return out
        tipi = _PEZZI_DEL_PROFILO.get(k, ())
        for pz in ris[u"pezzi"]:
            if pz[u"tipo"] not in tipi:
                continue
            est = rettangolo(ris, pz[u"esterni"])
            if pz[u"interni"]:
                strisce = _strisce(est, rettangolo(ris, pz[u"interni"]))
                if k == u"soglia":
                    strisce = strisce[:1]           # solo il traverso in basso
                elif k == u"telaio" and pz[u"tipo"] == u"telaio" and schema.get(u"soglia", True):
                    strisce = strisce[1:]           # la sezione del telaio, non la soglia
                out[u"rettangoli"].extend(strisce)
            elif k != u"soglia":
                out[u"rettangoli"].append(est)
    return out
