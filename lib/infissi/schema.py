# -*- coding: utf-8 -*-
"""Schema di un infisso, senza API Revit.

Lo schema e' un dizionario (si salva cosi' com'e' in JSON):

    {"versione": 1, "nome": u"2 ante", "categoria": "finestre" | "porte",
     "larghezza": 1200, "altezza": 1500,            # mm, esterno telaio
     "profili": {"telaio": 70, ...},                # mm, vedi PROFILI
     "radice": nodo}

     "soglia": True,       # traverso in basso; False = telaio a U (porte: non si inciampa)
     "maniglie": True,     # maniglie sulle ante apribili
     "simbolo_pianta": "tratteggio",   # finestre in pianta: nessuno | tratteggio | continuo

Un nodo e' una cella o una divisione:

    {"tipo": "cella", "anta": "battente_sx", "riempimento": "vetro" | "zoccolo" | "pannello"}
    {"tipo": "divisione", "verso": "v" | "o", "montante": True,
     "misure": [600], "figli": [nodo, nodo]}

- verso "v": figli affiancati (colonne, da sinistra); "o": sovrapposti (righe, dal basso).
- misure: n-1 misure in mm, ognuna dal bordo esterno o dall'asse precedente all'asse
  seguente; l'ultimo figlio prende il resto.
- montante False = battuta: due ante che si chiudono una sull'altra, senza montante fisso.

I versi sx/dx delle ante si leggono in prospetto dall'esterno: "battente_sx" ha le cerniere a
sinistra; il simbolo e' un triangolo con la punta sul lato delle cerniere (UNI/DIN).
"""
import copy
import json

VERSIONE = 1

FINESTRE = u"finestre"
PORTE = u"porte"
CATEGORIE = ((FINESTRE, u"Finestre"), (PORTE, u"Porte"))

# (chiave, etichetta)
ANTE = (
    (u"fisso", u"Fisso"),
    (u"battente_sx", u"Battente, cerniere a sinistra"),
    (u"battente_dx", u"Battente, cerniere a destra"),
    (u"vasistas", u"Vasistas (a ribalta)"),
    (u"anta_ribalta_sx", u"Anta-ribalta, cerniere a sinistra"),
    (u"anta_ribalta_dx", u"Anta-ribalta, cerniere a destra"),
    (u"scorrevole_sx", u"Scorrevole verso sinistra"),
    (u"scorrevole_dx", u"Scorrevole verso destra"),
    (u"porta_sx", u"Porta, cerniere a sinistra"),
    (u"porta_dx", u"Porta, cerniere a destra"),
)
NOMI_ANTE = dict(ANTE)
FISSO = u"fisso"


def apribile(anta):
    return anta != FISSO


def scorrevole(anta):
    return anta.startswith(u"scorrevole")


def porta(anta):
    return anta.startswith(u"porta")


# chiusura della zona: tutta vetro, vetro con pannello in basso (solo ante-porta), cieca
VETRO = u"vetro"
ZOCCOLO = u"zoccolo"
PANNELLO = u"pannello"
RIEMPIMENTI = ((VETRO, u"Vetrata"), (ZOCCOLO, u"Vetrata con zoccolo"), (PANNELLO, u"Cieca"))
NOMI_RIEMPIMENTI = dict(RIEMPIMENTI)

# simbolo di apertura in pianta delle finestre (le porte hanno sempre l'arco continuo)
SIMBOLI_PIANTA = ((u"nessuno", u"Nessuno"), (u"tratteggio", u"Arco tratteggiato"),
                  (u"continuo", u"Arco come le porte"))
NOMI_SIMBOLI_PIANTA = dict(SIMBOLI_PIANTA)


def ruota(anta):
    """Ante che si aprono ruotando su cerniere verticali: in pianta arco, in 3D aperte a 90 gradi."""
    return anta.startswith(u"battente") or anta.startswith(u"anta_ribalta") or porta(anta)


def riempimento_valido(anta, riempimento):
    """Lo zoccolo ha senso solo sulle ante-porta: altrove diventa vetro."""
    if riempimento == ZOCCOLO and not porta(anta):
        return VETRO
    return riempimento if riempimento in NOMI_RIEMPIMENTI else VETRO


# (chiave, etichetta, valore predefinito mm, minimo mm)
PROFILI = (
    (u"telaio", u"Telaio sezione", 70.0, 20.0),
    (u"soglia", u"Soglia sezione", 70.0, 10.0),
    (u"terra", u"Luce a terra", 10.0, 1.0),       # sotto l'anta, senza soglia
    (u"montante", u"Montante sezione", 80.0, 20.0),
    (u"anta", u"Anta sezione", 80.0, 20.0),
    (u"telaio_prof", u"Telaio profondità", 70.0, 20.0),
    (u"anta_prof", u"Anta profondità", 68.0, 20.0),
    (u"anta_spost", u"Anta spostamento", 0.0, None),
    (u"vetro", u"Vetro spessore", 28.0, 4.0),
    (u"zoccolo", u"Zoccolo altezza", 200.0, 0.0),
    (u"freccia_l", u"Freccia lunghezza", 120.0, 10.0),
    (u"freccia_a", u"Freccia apertura", 50.0, 5.0),
    (u"maniglia_l", u"Maniglia lunghezza", 130.0, 20.0),
    (u"maniglia_sporg", u"Maniglia sporgenza", 60.0, 5.0),
    (u"maniglia_porta", u"Maniglia porte da terra", 1050.0, 100.0),
)
PROFILI_PREDEFINITI = dict((k, v) for k, _e, v, _m in PROFILI)

# --- contorno: come l'infisso sta nel muro (passo 5 del Configuratore) --------------------
# schema["contorno"] = {"posizione": ..., "mazzetta": bool, ..., "misure": {chiave: mm}}
POSIZIONI = ((u"centro", u"In mezzo al muro"), (u"filo_esterno", u"Dal filo esterno"),
             (u"filo_interno", u"Dal filo interno"))
NOMI_POSIZIONI = dict(POSIZIONI)
# elementi che si accendono (nella famiglia: parametro Si'/No, tranne la mazzetta che taglia il muro)
ELEMENTI_CONTORNO = (
    (u"mazzetta", u"Mazzetta esterna"),
    (u"mostra_est", u"Mostra esterna"),
    (u"mostra_int", u"Mostra interna"),
    (u"dav_est", u"Davanzale esterno"),
    (u"dav_int", u"Davanzale interno"),
    (u"soglia_pietra", u"Soglia in pietra"),
    (u"imbotte", u"Imbotte"),
)
NOMI_ELEMENTI_CONTORNO = dict(ELEMENTI_CONTORNO)
# (chiave, nome del parametro, mm, minimo)
MISURE_CONTORNO = (
    (u"posizione", u"Posizione telaio", 50.0, 0.0),     # dal filo scelto alla faccia del telaio
    (u"mazzetta", u"Mazzetta", 40.0, 5.0),
    (u"mostra_l", u"Mostra larghezza", 70.0, 5.0),
    (u"mostra_sp", u"Mostra spessore", 20.0, 2.0),
    (u"dav_est_sp", u"Davanzale est. spessore", 30.0, 5.0),
    (u"dav_est_sporg", u"Davanzale est. sporgenza", 40.0, 1.0),
    (u"dav_est_ris", u"Davanzale est. risvolto", 30.0, 1.0),
    (u"dav_int_sp", u"Davanzale int. spessore", 30.0, 5.0),
    (u"dav_int_sporg", u"Davanzale int. sporgenza", 30.0, 1.0),
    (u"dav_int_ris", u"Davanzale int. risvolto", 30.0, 1.0),
    (u"soglia_sp", u"Soglia pietra spessore", 30.0, 5.0),
    (u"soglia_sporg", u"Soglia pietra sporgenza", 20.0, 1.0),
    (u"imbotte_sp", u"Imbotte spessore", 20.0, 2.0),
    (u"muro", u"Spessore muro (anteprima)", 300.0, 50.0),   # solo per disegno e controlli
)
MISURE_CONTORNO_PREDEFINITE = dict((k, v) for k, _e, v, _m in MISURE_CONTORNO)
# quali misure servono a ogni elemento (per mostrarle solo quando l'elemento e' acceso)
MISURE_DI = {
    u"mazzetta": (u"mazzetta",),
    u"mostra_est": (u"mostra_l", u"mostra_sp"), u"mostra_int": (u"mostra_l", u"mostra_sp"),
    u"dav_est": (u"dav_est_sp", u"dav_est_sporg", u"dav_est_ris"),
    u"dav_int": (u"dav_int_sp", u"dav_int_sporg", u"dav_int_ris"),
    u"soglia_pietra": (u"soglia_sp", u"soglia_sporg"),
    u"imbotte": (u"imbotte_sp",),
}


def contorno_vuoto():
    """Niente contorno: telaio in mezzo al muro, foro semplice (come le famiglie di prima)."""
    c = {u"posizione": u"centro", u"misure": dict(MISURE_CONTORNO_PREDEFINITE)}
    for k, _e in ELEMENTI_CONTORNO:
        c[k] = False
    return c


def normalizza_contorno(dati):
    c = contorno_vuoto()
    if not isinstance(dati, dict):
        return c
    if dati.get(u"posizione") in NOMI_POSIZIONI:
        c[u"posizione"] = dati[u"posizione"]
    for k, _e in ELEMENTI_CONTORNO:
        c[k] = bool(dati.get(k, False))
    for k, v in (dati.get(u"misure") or {}).items():
        if k in MISURE_CONTORNO_PREDEFINITE:
            c[u"misure"][k] = float(v)
    return c


def elementi_ammessi(categoria):
    """Elementi del contorno che hanno senso per la categoria (soglia alle porte, davanzali alle finestre)."""
    no = (u"dav_est", u"dav_int") if categoria == PORTE else (u"soglia_pietra",)
    return [k for k, _e in ELEMENTI_CONTORNO if k not in no]


def contorno_attivo(schema, elemento):
    """True se l'elemento del contorno e' acceso e ha senso per la categoria dello schema."""
    c = schema.get(u"contorno") or {}
    return bool(c.get(elemento)) and elemento in elementi_ammessi(schema.get(u"categoria"))


class SchemaErrore(ValueError):
    pass


# --- costruzione ------------------------------------------------------------------
def cella(anta=FISSO, riempimento=VETRO):
    return {u"tipo": u"cella", u"anta": anta, u"riempimento": riempimento_valido(anta, riempimento)}


def divisione(verso, figli, misure, montante=True):
    return {u"tipo": u"divisione", u"verso": verso, u"montante": bool(montante),
            u"misure": [float(m) for m in misure], u"figli": list(figli)}


def ha_ante_porta(radice):
    return any(porta(c[u"anta"]) for _p, c in celle(radice))


def nuovo(radice, larghezza, altezza, nome=u"", categoria=FINESTRE, profili=None,
          soglia=None, maniglie=True, simbolo_pianta=u"tratteggio", contorno=None):
    """soglia None = senza soglia se ci sono ante-porta (non si inciampa), altrimenti con."""
    p = dict(PROFILI_PREDEFINITI)
    p.update(profili or {})
    if soglia is None:
        soglia = not ha_ante_porta(radice)
    return {u"versione": VERSIONE, u"nome": nome, u"categoria": categoria,
            u"larghezza": float(larghezza), u"altezza": float(altezza),
            u"profili": p, u"radice": radice, u"soglia": bool(soglia), u"maniglie": bool(maniglie),
            u"simbolo_pianta": simbolo_pianta if simbolo_pianta in NOMI_SIMBOLI_PIANTA else u"nessuno",
            u"contorno": normalizza_contorno(contorno)}


def copia(schema):
    return copy.deepcopy(schema)


# --- JSON -------------------------------------------------------------------------
def to_json(schema):
    testo = json.dumps(schema, ensure_ascii=False, sort_keys=True)
    if not isinstance(testo, type(u"")):
        testo = testo.decode("utf-8")
    return testo


def from_json(testo):
    try:
        dati = json.loads(testo)
    except Exception:
        raise SchemaErrore(u"Schema non leggibile (JSON rovinato).")
    return normalizza(dati)


def normalizza(dati):
    """Schema completo dai dati letti (profili mancanti = predefiniti); errore se la forma e' sbagliata."""
    if not isinstance(dati, dict) or not isinstance(dati.get(u"radice"), dict):
        raise SchemaErrore(u"Schema senza radice.")
    profili = dict((k, float(v)) for k, v in (dati.get(u"profili") or {}).items()
                   if k in PROFILI_PREDEFINITI)
    # schemi di prima: con soglia e senza maniglie (la famiglia non cambia finche' non si sceglie)
    s = nuovo(_nodo(dati[u"radice"]), dati.get(u"larghezza", 0), dati.get(u"altezza", 0),
              nome=dati.get(u"nome", u"") or u"",
              categoria=dati.get(u"categoria", FINESTRE), profili=profili,
              soglia=dati.get(u"soglia", True), maniglie=dati.get(u"maniglie", False),
              simbolo_pianta=dati.get(u"simbolo_pianta", u"nessuno"),
              contorno=dati.get(u"contorno"))      # schemi di prima: niente contorno
    # chiusura mancante: come prima, lo zoccolo c'era sulle porte se il profilo era > 0
    zoccolo_prima = profili.get(u"zoccolo", 0.0) > 0
    for _p, c in celle(s[u"radice"]):
        if c.get(u"_riempimento_mancante"):
            del c[u"_riempimento_mancante"]
            c[u"riempimento"] = ZOCCOLO if (porta(c[u"anta"]) and zoccolo_prima) else VETRO
    return s


def _nodo(d):
    if not isinstance(d, dict):
        raise SchemaErrore(u"Nodo non valido.")
    if d.get(u"tipo") == u"cella":
        c = cella(d.get(u"anta", FISSO), d.get(u"riempimento") or VETRO)
        if u"riempimento" not in d:
            c[u"_riempimento_mancante"] = True
        return c
    if d.get(u"tipo") == u"divisione":
        return divisione(d.get(u"verso"), [_nodo(f) for f in d.get(u"figli") or []],
                         d.get(u"misure") or [], d.get(u"montante", True))
    raise SchemaErrore(u"Nodo di tipo sconosciuto: %s" % d.get(u"tipo"))


# --- percorsi ---------------------------------------------------------------------
def nome_percorso(percorso):
    """(1, 0) -> u"2.1"; la radice -> u"" (numeri da 1, come si leggono)."""
    return u".".join(u"%d" % (i + 1) for i in percorso)


def nodo_in(radice, percorso):
    n = radice
    for i in percorso:
        n = n[u"figli"][i]
    return n


def celle(radice, percorso=()):
    """[(percorso, cella)] in ordine (colonne da sinistra, righe dal basso)."""
    if radice[u"tipo"] == u"cella":
        return [(tuple(percorso), radice)]
    out = []
    for i, f in enumerate(radice[u"figli"]):
        out.extend(celle(f, tuple(percorso) + (i,)))
    return out


def divisioni(radice, percorso=()):
    """[(percorso, divisione)] in ordine di visita."""
    if radice[u"tipo"] == u"cella":
        return []
    out = [(tuple(percorso), radice)]
    for i, f in enumerate(radice[u"figli"]):
        out.extend(divisioni(f, tuple(percorso) + (i,)))
    return out


def _sostituisci(radice, percorso, nuovo_nodo):
    if not percorso:
        return nuovo_nodo
    r = copy.deepcopy(radice)
    padre = nodo_in(r, percorso[:-1])
    padre[u"figli"][percorso[-1]] = nuovo_nodo
    return r


# --- modifiche (ritornano uno schema nuovo) ---------------------------------------------
def imposta_anta(schema, percorso, anta):
    if anta not in NOMI_ANTE:
        raise SchemaErrore(u"Anta sconosciuta: %s" % anta)
    s = copia(schema)
    vecchia = nodo_in(s[u"radice"], tuple(percorso))
    s[u"radice"] = _sostituisci(s[u"radice"], tuple(percorso),
                                cella(anta, vecchia.get(u"riempimento", VETRO)))
    return s


def imposta_riempimento(schema, percorso, riempimento):
    if riempimento not in NOMI_RIEMPIMENTI:
        raise SchemaErrore(u"Chiusura sconosciuta: %s" % riempimento)
    s = copia(schema)
    c = nodo_in(s[u"radice"], tuple(percorso))
    c[u"riempimento"] = riempimento_valido(c[u"anta"], riempimento)
    return s


def dividi(schema, percorso, verso, misura, montante=True):
    """La cella al percorso diventa una divisione in due celle uguali a lei."""
    s = copia(schema)
    vecchia = nodo_in(s[u"radice"], percorso)
    if vecchia[u"tipo"] != u"cella":
        raise SchemaErrore(u"Si divide solo una cella.")
    r = vecchia.get(u"riempimento", VETRO)
    nuovo_nodo = divisione(verso, [cella(vecchia[u"anta"], r), cella(vecchia[u"anta"], r)],
                           [misura], montante)
    s[u"radice"] = _sostituisci(s[u"radice"], tuple(percorso), nuovo_nodo)
    return s


def togli_divisione(schema, percorso_cella):
    """La divisione che contiene la cella torna una cella sola (con l'anta della cella)."""
    percorso_cella = tuple(percorso_cella)
    if not percorso_cella:
        raise SchemaErrore(u"Non c'e' nessuna divisione da togliere.")
    s = copia(schema)
    vecchia = nodo_in(s[u"radice"], percorso_cella)
    s[u"radice"] = _sostituisci(s[u"radice"], percorso_cella[:-1],
                                cella(vecchia.get(u"anta", FISSO), vecchia.get(u"riempimento", VETRO)))
    return s


def imposta_montante(schema, percorso_divisione, montante):
    s = copia(schema)
    nodo_in(s[u"radice"], percorso_divisione)[u"montante"] = bool(montante)
    return s


def imposta_misura(schema, percorso_divisione, indice, valore):
    s = copia(schema)
    nodo_in(s[u"radice"], percorso_divisione)[u"misure"][indice] = float(valore)
    return s


# --- controlli di struttura -------------------------------------------------------------
def errori_struttura(schema):
    """Errori che non dipendono dalle misure (le misure le controlla geometria.py)."""
    err = []
    if schema.get(u"categoria") not in (FINESTRE, PORTE):
        err.append(u"Categoria non valida: scegli Finestre o Porte.")
    _controlla(schema[u"radice"], (), err)
    return err


def _controlla(nodo, percorso, err):
    dove = nome_percorso(percorso) or u"intero infisso"
    if nodo[u"tipo"] == u"cella":
        if nodo.get(u"anta") not in NOMI_ANTE:
            err.append(u"Zona %s: tipo di anta sconosciuto." % dove)
        if nodo.get(u"riempimento", VETRO) not in NOMI_RIEMPIMENTI:
            err.append(u"Zona %s: chiusura sconosciuta." % dove)
        return
    figli = nodo[u"figli"]
    if nodo.get(u"verso") not in (u"v", u"o"):
        err.append(u"Zona %s: verso della divisione non valido." % dove)
    if len(figli) < 2:
        err.append(u"Zona %s: una divisione deve avere almeno due parti." % dove)
    if len(nodo[u"misure"]) != len(figli) - 1:
        err.append(u"Zona %s: servono %d misure." % (dove, max(len(figli) - 1, 0)))
    if not nodo[u"montante"]:
        for f in figli:
            if f[u"tipo"] != u"cella" or not apribile(f.get(u"anta", FISSO)):
                err.append(u"Zona %s: senza montante tutte le parti devono essere ante "
                           u"apribili (non fissi, non altre divisioni)." % dove)
                break
        else:
            n_scorr = len([f for f in figli if scorrevole(f[u"anta"])])
            if 0 < n_scorr < len(figli):
                err.append(u"Zona %s: senza montante non si mischiano ante scorrevoli e a "
                           u"battente." % dove)
    for i, f in enumerate(figli):
        _controlla(f, percorso + (i,), err)


# --- descrizioni ---------------------------------------------------------------------
def conta_ante(schema):
    n_apr = n_fissi = 0
    for _p, c in celle(schema[u"radice"]):
        if apribile(c[u"anta"]):
            n_apr += 1
        else:
            n_fissi += 1
    return n_apr, n_fissi


def sigla(schema):
    """Es. u"2A1F" (2 ante apribili, 1 fisso)."""
    n_apr, n_fissi = conta_ante(schema)
    parti = []
    if n_apr:
        parti.append(u"%dA" % n_apr)
    if n_fissi:
        parti.append(u"%dF" % n_fissi)
    return u"".join(parti)


def descrizione(schema):
    """Testo per il parametro Apertura, es. u"2 Battente, cerniere a sinistra; 1 Fisso"."""
    conti = []
    for _p, c in celle(schema[u"radice"]):
        nome = NOMI_ANTE.get(c[u"anta"], c[u"anta"])
        r = c.get(u"riempimento", VETRO)
        if r == PANNELLO:
            nome += u", cieca"
        elif r == ZOCCOLO:
            nome += u", con zoccolo"
        for v in conti:
            if v[0] == nome:
                v[1] += 1
                break
        else:
            conti.append([nome, 1])
    return u"; ".join(u"%d %s" % (n, nome) for nome, n in conti)


def nome_famiglia(schema):
    tipo = u"Porta" if schema.get(u"categoria") == PORTE else u"Finestra"
    return u"CDV_%s_%s" % (tipo, sigla(schema))


def nome_tipo(schema):
    """Es. u"120x150" (cm); se le misure non sono a cm tondi, in mm."""
    l, h = schema[u"larghezza"], schema[u"altezza"]
    if abs(l / 10.0 - round(l / 10.0)) < 1e-6 and abs(h / 10.0 - round(h / 10.0)) < 1e-6:
        return u"%dx%d" % (int(round(l / 10.0)), int(round(h / 10.0)))
    return u"%gx%g mm" % (l, h)
