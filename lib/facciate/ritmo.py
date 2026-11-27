# -*- coding: utf-8 -*-
"""Ritmi di facciata: dove cadono montanti e traversi, che classe ha ogni cella (senza API Revit).

Una *regola* dice come dividere una direzione (colonne lungo il muro, righe in altezza):

    {"moduli": [{"id": "A", "misura": 1500, "bloccato": False},
                {"id": "B", "misura": 600, "bloccato": True}],
     "sequenza": ["A", "A", "B"],          # il motivo che si ripete
     "modo": "migliore" | "fisso" | "ripetizioni",
     "finisci_con": 0,                      # migliore: posizione del motivo con cui finire (None = ultima)
     "ripetizioni": 4,                      # ripetizioni: quante volte il motivo
     "origine": "inizio" | "centro" | "fine", "scarto": 0,   # fisso: dove parte il motivo
     "resto_minimo": 0,                     # fisso: i ritagli piu' corti si uniscono al vicino
     "livelli": {"attivo": True, "offset": 0}}               # solo righe: traversi sui livelli

Modi (come in Archicad):
- migliore: il motivo si ripete e finisce esatto sul bordo; i moduli non bloccati si allungano
  o si accorciano tutti dello stesso fattore, scegliendo il numero di ripetizioni che li tiene
  piu' vicini alla misura voluta;
- fisso: il motivo si ripete con le misure vere e si taglia ai bordi (i ritagli sono "resto");
- ripetizioni: il motivo si ripete n volte, i moduli non bloccati si adattano.

Un *tratto* e' un pezzo della direzione: {"da", "a", "modulo", "pos" (posizione nel motivo),
"giro" (quale ripetizione del motivo), "piano" (righe: fascia fra due livelli), "resto"}.
Misure in mm; colonne dall'inizio del muro, righe dal basso.
"""
import math

MIGLIORE = u"migliore"
FISSO = u"fisso"
RIPETIZIONI = u"ripetizioni"
MODI = ((MIGLIORE, u"Divisione migliore"), (FISSO, u"Misura fissa"),
        (RIPETIZIONI, u"Numero di ripetizioni"))
NOMI_MODI = dict(MODI)

INIZIO = u"inizio"
CENTRO = u"centro"
FINE = u"fine"
ORIGINI = ((INIZIO, u"Dall'inizio"), (CENTRO, u"Centrato"), (FINE, u"Dalla fine"))
NOMI_ORIGINI = dict(ORIGINI)

TOLLERANZA = 0.5          # mm: pezzi piu' corti non esistono
MONTANTE = u"montante"     # classe predefinita delle linee verticali
TRAVERSO = u"traverso"     # classe predefinita delle linee orizzontali
MARCAPIANO = u"marcapiano"  # traversi sui livelli
VETRO = u"vetro"           # classe predefinita dei pannelli


class RitmoErrore(ValueError):
    pass


# --- una direzione ----------------------------------------------------------------------
def motivo(regola):
    """[(pos, id, misura, bloccato)] del motivo; errore se un modulo manca o non ha misura."""
    moduli = dict((m[u"id"], m) for m in regola.get(u"moduli") or [])
    out = []
    for pos, mid in enumerate(regola.get(u"sequenza") or []):
        m = moduli.get(mid)
        if m is None:
            raise RitmoErrore(u"Il modulo %s della sequenza non esiste." % mid)
        misura = float(m.get(u"misura") or 0)
        if misura <= TOLLERANZA:
            raise RitmoErrore(u"Il modulo %s non ha una misura." % mid)
        out.append((pos, mid, misura, bool(m.get(u"bloccato"))))
    if not out:
        raise RitmoErrore(u"La sequenza è vuota.")
    return out


def _tratto(da, a, mid, pos, giro, resto=False):
    return {u"da": da, u"a": a, u"modulo": mid, u"pos": pos, u"giro": giro, u"resto": resto}


def _fattore(lunghezza, corsa):
    """Fattore dei moduli non bloccati perche' la corsa misuri lunghezza; None se non si puo'."""
    fissi = sum(m for _p, _i, m, b, _g in corsa if b)
    liberi = sum(m for _p, _i, m, b, _g in corsa if not b)
    if liberi <= TOLLERANZA:
        return 1.0 if abs(lunghezza - fissi) <= TOLLERANZA else None
    s = (lunghezza - fissi) / liberi
    return s if s * min(m for _p, _i, m, b, _g in corsa if not b) > TOLLERANZA else None


def _corsa(mot, giri, fine=None):
    """Il motivo ripetuto giri volte, piu' l'inizio del motivo fino alla posizione fine compresa."""
    out = []
    for g in range(giri):
        out.extend((p, i, m, b, g) for p, i, m, b in mot)
    if fine is not None:
        out.extend((p, i, m, b, giri) for p, i, m, b in mot[:fine + 1])
    return out


def _stendi(lunghezza, corsa, s):
    out = []
    x = 0.0
    for p, i, m, b, g in corsa:
        a = x + (m if b else m * s)
        out.append(_tratto(x, a, i, p, g))
        x = a
    out[-1][u"a"] = float(lunghezza)
    return out


def _migliore(lunghezza, mot, regola):
    n = len(mot)
    fine = regola.get(u"finisci_con")
    fine = n - 1 if fine is None or not 0 <= int(fine) < n else int(fine)
    passo = sum(m for _p, _i, m, _b in mot)
    migliore = None
    for giri in range(int(lunghezza / passo) + 3):
        # finire sull'ultima posizione = giri interi: la corsa e' sempre giri + inizio fino a fine
        corsa = _corsa(mot, giri, fine)
        s = _fattore(lunghezza, corsa)
        if s is None:
            continue
        scarto = abs(s - 1.0)
        if migliore is None or scarto < migliore[0] - 1e-9:
            migliore = (scarto, corsa, s)
    if migliore is None:
        if all(b for _p, _i, _m, b in mot):
            raise RitmoErrore(u"Con Divisione migliore almeno un modulo deve restare libero.")
        raise RitmoErrore(u"I moduli bloccati non ci stanno in %d mm." % round(lunghezza))
    return _stendi(lunghezza, migliore[1], migliore[2])


def _ripetizioni(lunghezza, mot, regola):
    giri = max(1, int(regola.get(u"ripetizioni") or 1))
    corsa = _corsa(mot, giri)
    s = _fattore(lunghezza, corsa)
    if s is None:
        raise RitmoErrore(u"%d ripetizioni non ci stanno in %d mm con i moduli bloccati."
                          % (giri, round(lunghezza)))
    return _stendi(lunghezza, corsa, s)


def _fisso(lunghezza, mot, regola):
    passo = sum(m for _p, _i, m, _b in mot)
    scarto = float(regola.get(u"scarto") or 0)
    origine = regola.get(u"origine") or INIZIO
    if origine == FINE:
        x0 = lunghezza - scarto - passo
    elif origine == CENTRO:
        interi = max(1, int(math.floor((lunghezza + TOLLERANZA) / passo)))
        x0 = (lunghezza - interi * passo) / 2.0 + scarto
    else:
        x0 = scarto
    x = x0 - passo * math.ceil((x0 - TOLLERANZA) / passo)     # primo giro che parte a x <= 0
    out = []
    giro = 0
    while x < lunghezza - TOLLERANZA:
        for p, i, m, _b in mot:
            da, a = max(x, 0.0), min(x + m, float(lunghezza))
            if a - da > TOLLERANZA:
                taglio = da > x + TOLLERANZA or a < x + m - TOLLERANZA
                out.append(_tratto(da, a, i, p, giro, taglio))
            x += m
        if out:
            giro += 1
    return _unisci_ritagli(out, float(regola.get(u"resto_minimo") or 0))


def _unisci_ritagli(tratti, minimo):
    """I ritagli ai bordi piu' corti di minimo si uniscono al tratto vicino (niente listelli)."""
    if minimo <= TOLLERANZA or len(tratti) < 2:
        return tratti
    if tratti[0][u"resto"] and tratti[0][u"a"] - tratti[0][u"da"] < minimo:
        tratti[1][u"da"] = tratti[0][u"da"]
        tratti[1][u"resto"] = True
        tratti = tratti[1:]
    if len(tratti) > 1 and tratti[-1][u"resto"] and tratti[-1][u"a"] - tratti[-1][u"da"] < minimo:
        tratti[-2][u"a"] = tratti[-1][u"a"]
        tratti[-2][u"resto"] = True
        tratti = tratti[:-1]
    return tratti


def posizioni(lunghezza, regola):
    """I tratti in cui la regola divide la lunghezza, da 0 a lunghezza."""
    lunghezza = float(lunghezza)
    if lunghezza <= TOLLERANZA:
        raise RitmoErrore(u"La facciata non ha lunghezza.")
    mot = motivo(regola)
    modo = regola.get(u"modo") or MIGLIORE
    if modo == FISSO:
        return _fisso(lunghezza, mot, regola)
    if modo == RIPETIZIONI:
        return _ripetizioni(lunghezza, mot, regola)
    return _migliore(lunghezza, mot, regola)


# --- righe sui livelli --------------------------------------------------------------------
def fasce(altezza, quote_livelli=(), offset=0.0):
    """Le fasce [(da, a)] tra i livelli: tagli a quota livello + offset, dentro l'altezza.
    quote_livelli: quote dei livelli misurate dalla base della facciata."""
    tagli = sorted(set(round(float(q) + float(offset), 3) for q in quote_livelli))
    tagli = [q for q in tagli if TOLLERANZA < q < altezza - TOLLERANZA]
    bordi = [0.0] + tagli + [float(altezza)]
    return list(zip(bordi[:-1], bordi[1:]))


def righe(altezza, regola, quote_livelli=()):
    """I tratti delle righe; con i livelli accesi il motivo riparte in ogni piano."""
    liv = regola.get(u"livelli") or {}
    if liv.get(u"attivo"):
        bande = fasce(altezza, quote_livelli, liv.get(u"offset") or 0.0)
    else:
        bande = [(0.0, float(altezza))]
    out = []
    for piano, (da, a) in enumerate(bande):
        for t in posizioni(a - da, regola):
            t[u"da"] += da
            t[u"a"] += da
            t[u"piano"] = piano
            out.append(t)
    return out


# --- linee ----------------------------------------------------------------------------
def linee(tratti, classi=(), predefinita=MONTANTE, classe_livello=MARCAPIANO):
    """Le linee interne [{"pos", "classe", "indice"}]: la linea che chiude un tratto prende la
    classe della sua posizione nel motivo; fra due piani la classe del livello."""
    out = []
    for i in range(len(tratti) - 1):
        t, u = tratti[i], tratti[i + 1]
        if t.get(u"piano") != u.get(u"piano"):
            classe = classe_livello
        else:
            classe = classi[t[u"pos"]] if t[u"pos"] < len(classi) and classi[t[u"pos"]] else predefinita
        out.append({u"pos": t[u"a"], u"classe": classe, u"indice": i})
    return out


# --- celle ----------------------------------------------------------------------------
def classe_cella(celle, col, riga, predefinita=VETRO):
    """Classe della cella del motivo: chiave "c,r", poi "c,*", poi "*,r", poi la predefinita."""
    for chiave in (u"%d,%d" % (col, riga), u"%d,*" % col, u"*,%d" % riga):
        if celle.get(chiave):
            return celle[chiave]
    return predefinita


def _gruppi(tratti, da, a):
    """Indici dei tratti consecutivi dello stesso giro (e piano) con posizione in [da, a]."""
    out = []
    corrente = []
    chiave = None
    for i, t in enumerate(tratti):
        k = (t.get(u"piano"), t[u"giro"])
        if da <= t[u"pos"] <= a and (not corrente or (k == chiave and corrente[-1] == i - 1)):
            corrente.append(i)
            chiave = k
            continue
        if corrente:
            out.append(corrente)
        corrente = [i] if da <= t[u"pos"] <= a else []
        chiave = k
    if corrente:
        out.append(corrente)
    return out


def celle(colonne, righe_, schema):
    """Le celle della facciata [{"col": [i0, i1], "riga": [j0, j1], "classe"}], unioni comprese.
    Le celle dei ritagli prendono la classe "resto" della loro direzione, se c'e'."""
    def_celle = schema.get(u"celle") or {}
    resto_c = (schema.get(u"colonne") or {}).get(u"resto")
    resto_r = (schema.get(u"righe") or {}).get(u"resto")
    predefinita = schema.get(u"pannello") or VETRO

    def classe(i, j):
        if colonne[i][u"resto"] and resto_c:
            return resto_c
        if righe_[j][u"resto"] and resto_r:
            return resto_r
        return classe_cella(def_celle, colonne[i][u"pos"], righe_[j][u"pos"], predefinita)

    preso = {}
    out = []
    for u in schema.get(u"unioni") or []:
        c0, c1 = sorted(int(v) for v in u[u"colonne"])
        r0, r1 = sorted(int(v) for v in u[u"righe"])
        for gc in _gruppi(colonne, c0, c1):
            for gr in _gruppi(righe_, r0, r1):
                if len(gc) * len(gr) < 2:
                    continue
                parti = [(i, j) for i in gc for j in gr]
                if any(p in preso for p in parti):
                    continue                      # due unioni sulla stessa cella: vince la prima
                cella = {u"col": [gc[0], gc[-1]], u"riga": [gr[0], gr[-1]],
                         u"classe": classe(gc[0], gr[0])}
                for p in parti:
                    preso[p] = cella
                out.append(cella)
    for i in range(len(colonne)):
        for j in range(len(righe_)):
            if (i, j) not in preso:
                out.append({u"col": [i, i], u"riga": [j, j], u"classe": classe(i, j)})
    out.sort(key=lambda c: (c[u"riga"][0], c[u"col"][0]))
    return out


def segmenti_tolti(celle_):
    """Segmenti delle linee da togliere per le celle unite:
    {"verticali": {linea: [righe]}, "orizzontali": {linea: [colonne]}}, dove la linea k sta
    fra il tratto k e il tratto k+1."""
    vert = {}
    oriz = {}
    for c in celle_:
        (i0, i1), (j0, j1) = c[u"col"], c[u"riga"]
        for k in range(i0, i1):
            vert.setdefault(k, []).extend(range(j0, j1 + 1))
        for k in range(j0, j1):
            oriz.setdefault(k, []).extend(range(i0, i1 + 1))
    return {u"verticali": dict((k, sorted(v)) for k, v in vert.items()),
            u"orizzontali": dict((k, sorted(v)) for k, v in oriz.items())}


def trova_cella(celle_, colonne, righe_, x, y):
    """La cella che contiene il punto (x lungo il muro, y dal basso); None se fuori."""
    for c in celle_:
        if (colonne[c[u"col"][0]][u"da"] - TOLLERANZA <= x <= colonne[c[u"col"][1]][u"a"] + TOLLERANZA
                and righe_[c[u"riga"][0]][u"da"] - TOLLERANZA <= y <= righe_[c[u"riga"][1]][u"a"] + TOLLERANZA):
            return c
    return None


# --- tutto insieme ----------------------------------------------------------------------
def calcola(schema, lunghezza, altezza, quote_livelli=()):
    """Il ritmo di una facciata: tratti, linee interne, celle e segmenti da togliere.
    Le linee coperte per intero da celle unite non si creano (Revit non toglie l'ultimo
    segmento di una linea): stanno in "senza_linea"."""
    col = posizioni(lunghezza, schema[u"colonne"])
    rig = righe(altezza, schema[u"righe"], quote_livelli)
    lin = schema.get(u"linee") or {}
    lv = linee(col, lin.get(u"colonne") or (), MONTANTE)
    lo = linee(rig, lin.get(u"righe") or (), TRAVERSO,
               (schema[u"righe"].get(u"livelli") or {}).get(u"classe") or MARCAPIANO)
    cel = celle(col, rig, schema)
    tolti = segmenti_tolti(cel)
    senza = {u"verticali": [k for k, v in tolti[u"verticali"].items() if len(v) == len(rig)],
             u"orizzontali": [k for k, v in tolti[u"orizzontali"].items() if len(v) == len(col)]}
    return {u"lunghezza": float(lunghezza), u"altezza": float(altezza),
            u"colonne": col, u"righe": rig, u"linee_v": lv, u"linee_o": lo,
            u"celle": cel, u"tolti": tolti, u"senza_linea": senza}
