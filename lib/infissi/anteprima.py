# -*- coding: utf-8 -*-
"""Cosa disegnare nell'anteprima del configuratore (senza API Revit).

- pezzi_prospetto: i pezzi visibili in prospetto a un livello di dettaglio (anta chiusa);
- quote: le quote sempre visibili sul prospetto (misure esterne e misure delle zone);
- pianta: la pianta tagliata a meta' altezza, con i simboli di apertura in pianta;
- profili_per_gruppo: i profili che contano per lo schema, divisi in gruppi.

Coordinate in mm. Prospetto: x a destra, y in alto, origine nello spigolo esterno in basso a
sinistra (come geometria.py). Pianta: x come nel prospetto, y = profondita' dall'asse del
muro, sempre positiva verso l'interno (in Revit l'interno e' dal lato di G.INTERNO).
"""
from infissi import geometria as G
from infissi import parametri as PA
from infissi import schema as S

# gruppi dei profili al passo "Dettagli": (titolo, chiavi di S.PROFILI)
GRUPPI_PROFILI = (
    (u"Telaio", (u"telaio", u"telaio_prof", u"soglia", u"terra", u"montante")),
    (u"Ante", (u"anta", u"anta_prof", u"anta_spost", u"zoccolo")),
    (u"Vetro", (u"vetro",)),
    (u"Maniglie", (u"maniglia_l", u"maniglia_sporg", u"maniglia_porta")),
    (u"Frecce degli scorrevoli", (u"freccia_l", u"freccia_a")),
)

# stile delle linee in pianta (vedi G: ris["pianta"][..]["stile"])
TRATTEGGIATE = (u"finestra_tratteggio",)
MURO_AI_LATI = 250.0       # mm di muro disegnati ai lati del foro in pianta
# elementi del contorno visti dall'esterno (prospetto)
VISTI_DA_FUORI = (u"mazzetta", u"mostra_est", u"dav_est", u"soglia_pietra")


def contorno_prospetto(ris):
    """Rettangoli (x0, y0, x1, y1, tipo) del contorno visti da fuori: mostra esterna,
    davanzale esterno, soglia e la mazzetta (muro che copre il bordo del telaio)."""
    if not ris.get(u"piani"):
        return []
    px = dict((q[u"id"], q[u"pos"]) for q in ris[u"piani"])
    out = []
    for e in ris[u"contorno"]:
        if e[u"chiave"] in VISTI_DA_FUORI:
            x0, x1 = sorted(px[k] for k in e[u"x"])
            z0, z1 = sorted(px[k] for k in e[u"z"])
            out.append((x0, z0, x1, z1, u"muro" if e[u"tipo"] == u"mazzetta" else e[u"tipo"]))
    return out


def _ha_dettaglio(pz, dettaglio):
    return dettaglio is None or dettaglio in pz.get(u"dettaglio", G.TUTTI)


def pezzi_prospetto(ris, dettaglio=G.ALTO):
    """Pezzi visibili in prospetto con l'anta chiusa al livello di dettaglio dato."""
    return [pz for pz in ris[u"pezzi"]
            if pz.get(u"stato") != u"aperta" and _ha_dettaglio(pz, dettaglio)]


# --- quote --------------------------------------------------------------------------------
def quote(schema, ris):
    """Quote del prospetto: [{chiave, lato, corsia, a, b, valore}].

    lato: "basso"/"sinistra" (misure esterne) o "alto"/"destra" (misure delle zone: colonne
    in alto, righe a destra). a, b: estremi lungo x (basso/alto) o lungo y (sinistra/destra).
    corsia: 0 = la piu' vicina al disegno; ogni divisione ha la sua, cosi' non si accavallano.
    chiave: la stessa del campo che la cambia (vedi G.evidenzia).
    """
    if not ris.get(u"piani"):
        return []
    L, H = float(schema[u"larghezza"]), float(schema[u"altezza"])
    out = [{u"chiave": (u"larghezza",), u"lato": u"basso", u"corsia": 0, u"a": 0.0, u"b": L, u"valore": L},
           {u"chiave": (u"altezza",), u"lato": u"sinistra", u"corsia": 0, u"a": 0.0, u"b": H, u"valore": H}]
    corsie = {u"alto": [], u"destra": []}
    for m in ris[u"misure"]:
        chiave = (u"misura", tuple(m[u"divisione"]), m[u"indice"])
        try:
            q = G.evidenzia(ris, schema, chiave)[u"quota"]
        except (IndexError, KeyError, TypeError):
            q = None
        if q is None:
            continue
        lato = u"alto" if m[u"verso"] == u"v" else u"destra"
        divisione = tuple(m[u"divisione"])
        if divisione not in corsie[lato]:
            corsie[lato].append(divisione)
        a, b = (q[0], q[2]) if lato == u"alto" else (q[1], q[3])
        out.append({u"chiave": chiave, u"lato": lato, u"corsia": corsie[lato].index(divisione),
                    u"a": a, u"b": b, u"valore": m[u"valore"]})
    return out


# --- pianta -------------------------------------------------------------------------------
def _profondita(ris):
    """{nome profondita' del pezzo: (inizio, fine)} in mm dall'asse del muro."""
    valori = ris[u"valori"]
    out = {}
    for chiave, (n_inizio, n_fine) in G.PROFONDITA.items():
        try:
            out[chiave] = (PA.valuta(PA.FORMULE_PROFONDITA[n_inizio], valori),
                           PA.valuta(PA.FORMULE_PROFONDITA[n_fine], valori))
        except (KeyError, PA.FormulaErrore):
            pass
    return out


def _tagli_x(ris, pz, quota):
    """Tratti in x del pezzo tagliato all'altezza 'quota' ([] se il taglio non lo prende)."""
    x0, y0, x1, y1 = G.rettangolo(ris, pz[u"esterni"])
    if not (y0 <= quota <= y1):
        return []
    if pz.get(u"interni"):
        ix0, iy0, ix1, iy1 = G.rettangolo(ris, pz[u"interni"])
        if iy0 < quota < iy1:
            return [t for t in ((x0, ix0), (ix1, x1)) if t[1] - t[0] > 1e-6]
    return [(x0, x1)]


def pianta(schema, ris, dettaglio=G.ALTO, quota_taglio=None):
    """Pianta dell'infisso chiuso, tagliato a 'quota_taglio' mm (di base a meta' altezza).

    Ritorna {"rettangoli": [(x0, y0, x1, y1, tipo)], "linee": [(p0, p1, tratteggio)],
    "archi": [(p0, p1, centro, tratteggio)], "y": (ymin, ymax)}. I simboli in pianta ci sono
    solo se lo schema li prevede (porte sempre, finestre secondo "In pianta").
    """
    out = {u"rettangoli": [], u"linee": [], u"archi": [], u"y": (0.0, 0.0)}
    if not ris.get(u"piani"):
        return out
    quota = float(schema[u"altezza"]) / 2.0 if quota_taglio is None else quota_taglio
    prof = _profondita(ris)
    s = G.INTERNO           # y di Revit -> y con l'interno positivo

    def p(pt):
        return (pt[0], pt[1] * s)

    ys = [0.0]
    # muro ai lati del foro (con la mazzetta il foro e' piu' stretto sul lato esterno)
    py = dict((q[u"id"], q[u"pos"] * s) for q in ris[u"piani_y"])
    meta = ris[u"valori"][G.MURO] / 2.0
    L = float(schema[u"larghezza"])
    for x0, x1 in ((-MURO_AI_LATI, 0.0), (L, L + MURO_AI_LATI)):
        out[u"rettangoli"].append((x0, -meta, x1, meta, u"muro"))
    ys.extend((-meta, meta))
    px = dict((q[u"id"], q[u"pos"]) for q in ris[u"piani"])
    asse = ris.get(u"asse_y", 0.0)        # il telaio sta qui (le profondita' sono dal suo asse)
    for pz in pezzi_prospetto(ris, dettaglio):
        if pz[u"profondita"] not in prof:
            continue
        a, b = ((v + asse) * s for v in prof[pz[u"profondita"]])
        for x0, x1 in _tagli_x(ris, pz, quota):
            out[u"rettangoli"].append((x0, min(a, b), x1, max(a, b), pz[u"tipo"]))
            ys.extend((a, b))
    # contorno: quello tagliato dalla pianta, e davanzali e soglia che si vedono sotto
    for e in ris[u"contorno"]:
        z0, z1 = sorted(px[k] for k in e[u"z"])
        if not (z0 <= quota <= z1) and e[u"tipo"] not in (u"davanzale", u"soglia"):
            continue
        x0, x1 = sorted(px[k] for k in e[u"x"])
        ya, yb = sorted(py[k] for k in e[u"y"])
        out[u"rettangoli"].append((x0, ya, x1, yb, u"muro" if e[u"tipo"] == u"mazzetta" else e[u"tipo"]))
        ys.extend((ya, yb))
    for simb in ris[u"pianta"]:
        tratteggio = simb[u"stile"] in TRATTEGGIATE
        for seg in simb[u"segmenti"]:
            ys.extend((seg[u"p0"][1] * s, seg[u"p1"][1] * s))
            if seg[u"tipo"] == u"arco":
                out[u"archi"].append((p(seg[u"p0"]), p(seg[u"p1"]), p(seg[u"centro"]), tratteggio))
            else:
                out[u"linee"].append((p(seg[u"p0"]), p(seg[u"p1"]), tratteggio))
    out[u"y"] = (min(ys), max(ys))
    return out


# --- profili -----------------------------------------------------------------------------
def profili_per_gruppo(schema, ris=None):
    """[(titolo, [chiavi])]: solo i profili che finiscono nella famiglia di questo schema
    (es. le maniglie solo se ci sono). Se lo schema ha errori li mostra tutti, cosi' si
    possono correggere."""
    try:
        usati = set(p[u"nome"] for p in PA.elenco(schema, ris))
        etichette = dict((k, e) for k, e, _v, _m in S.PROFILI)
        tenere = lambda k: etichette[k] in usati  # noqa: E731
    except Exception:
        tenere = lambda k: True  # noqa: E731
    out = []
    for titolo, chiavi in GRUPPI_PROFILI:
        scelte = [k for k in chiavi if tenere(k)]
        if scelte:
            out.append((titolo, scelte))
    return out
