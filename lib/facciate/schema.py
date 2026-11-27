# -*- coding: utf-8 -*-
"""Schema di una facciata continua, senza API Revit (si salva cosi' com'e' in JSON).

    {"versione": 1, "nome": u"A-B alternato",
     "colonne": regola, "righe": regola,          # vedi ritmo.py
     "linee": {"colonne": ["montante", "lesena"], # classe della linea che chiude ogni posizione
               "righe": ["traverso"]},
     "celle": {"1,*": "cieco"},                   # posizione colonna, posizione riga -> classe pannello
     "pannello": "vetro",                         # classe delle celle non indicate
     "unioni": [{"colonne": [0, 2], "righe": [0, 0]}],   # celle del motivo da unire
     "classi": {"pannelli": {"vetro": u"<tipo Revit>"}, "montanti": {"montante": u""}}}

Le classi sono nomi liberi; "classi" dice quale tipo di Revit usa ognuna ("" = quello del tipo
di facciata). In "celle" e "unioni" le posizioni sono quelle nel motivo (0 = primo modulo).
"""
import copy
import json
import re

from facciate import ritmo as R

VERSIONE = 1

NESSUNO = u"(nessuno)"     # tipo di una classe di montanti: niente montante su quelle linee
CLASSI_PANNELLI = (R.VETRO, u"cieco", u"apribile", u"vuoto")
CLASSI_MONTANTI = (R.MONTANTE, R.TRAVERSO, R.MARCAPIANO, u"lesena")   # i bordi restano del tipo


class SchemaErrore(ValueError):
    pass


# --- sequenza scritta a mano --------------------------------------------------------
def leggi_sequenza(testo, ids=None):
    """"A A B", "A,A,B", "A-A-B" -> [A, A, B]; "AAB" si divide in lettere se i moduli sono
    lettere singole (ids: gli id dei moduli, per capirlo)."""
    parti = [p for p in re.split(u"[\\s,;\\-]+", testo or u"") if p]
    if len(parti) == 1 and len(parti[0]) > 1 and ids is not None and parti[0] not in ids \
            and all(ch in ids for ch in parti[0]):
        return list(parti[0])
    return parti


def scrivi_sequenza(sequenza):
    return u" ".join(sequenza)


# --- costruzione --------------------------------------------------------------------
def modulo(mid, misura, bloccato=False):
    return {u"id": mid, u"misura": float(misura), u"bloccato": bool(bloccato)}


def regola(moduli, sequenza, modo=R.MIGLIORE, finisci_con=None, ripetizioni=1,
           origine=R.INIZIO, scarto=0.0, resto=None, resto_minimo=0.0, livelli=None):
    r = {u"moduli": list(moduli), u"sequenza": list(sequenza), u"modo": modo,
         u"finisci_con": finisci_con, u"ripetizioni": int(ripetizioni),
         u"origine": origine, u"scarto": float(scarto), u"resto": resto,
         u"resto_minimo": float(resto_minimo)}
    if livelli is not None:
        r[u"livelli"] = livelli
    return r


def livelli(attivo=True, offset=0.0, classe=R.MARCAPIANO):
    return {u"attivo": bool(attivo), u"offset": float(offset), u"classe": classe}


def nuovo(colonne, righe, nome=u"", linee=None, celle=None, pannello=R.VETRO, unioni=None,
          classi=None):
    s = {u"versione": VERSIONE, u"nome": nome, u"colonne": colonne, u"righe": righe,
         u"linee": {u"colonne": list((linee or {}).get(u"colonne") or []),
                    u"righe": list((linee or {}).get(u"righe") or [])},
         u"celle": dict(celle or {}), u"pannello": pannello, u"unioni": list(unioni or [])}
    s[u"classi"] = _classi(classi, s)
    return s


def copia(schema):
    return copy.deepcopy(schema)


def classi_usate(schema):
    """(pannelli, montanti): le classi che lo schema usa, in ordine."""
    pan = [schema.get(u"pannello") or R.VETRO]
    pan += list(schema.get(u"celle", {}).values())
    pan += [schema[k].get(u"resto") for k in (u"colonne", u"righe") if schema[k].get(u"resto")]
    mon = [R.MONTANTE, R.TRAVERSO]
    mon += list(schema[u"linee"].get(u"colonne") or []) + list(schema[u"linee"].get(u"righe") or [])
    liv = schema[u"righe"].get(u"livelli") or {}
    if liv.get(u"attivo"):
        mon.append(liv.get(u"classe") or R.MARCAPIANO)

    def unici(v):
        out = []
        for x in v:
            if x and x not in out:
                out.append(x)
        return out
    return unici(pan), unici(mon)


def _classi(dati, schema):
    """Ogni classe usata ha il suo tipo di Revit ("" = quello del tipo di facciata)."""
    dati = dati or {}
    pan, mon = classi_usate(schema)
    out = {u"pannelli": dict(dati.get(u"pannelli") or {}), u"montanti": dict(dati.get(u"montanti") or {})}
    for k in pan:
        out[u"pannelli"].setdefault(k, u"")
    for k in mon:
        out[u"montanti"].setdefault(k, u"")
    return out


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
        raise SchemaErrore(u"Schema di facciata non leggibile (JSON rovinato).")
    return normalizza(dati)


def _regola(d, con_livelli=False):
    if not isinstance(d, dict):
        raise SchemaErrore(u"Schema di facciata senza regola delle colonne o delle righe.")
    moduli = [modulo(m[u"id"], m.get(u"misura") or 0, m.get(u"bloccato")) for m in d.get(u"moduli") or []]
    liv = None
    if con_livelli:
        l = d.get(u"livelli") or {}
        liv = livelli(l.get(u"attivo", False), l.get(u"offset") or 0, l.get(u"classe") or R.MARCAPIANO)
    modo = d.get(u"modo") if d.get(u"modo") in R.NOMI_MODI else R.MIGLIORE
    origine = d.get(u"origine") if d.get(u"origine") in R.NOMI_ORIGINI else R.INIZIO
    return regola(moduli, d.get(u"sequenza") or [], modo, d.get(u"finisci_con"),
                  d.get(u"ripetizioni") or 1, origine, d.get(u"scarto") or 0, d.get(u"resto"),
                  d.get(u"resto_minimo") or 0, liv)


def normalizza(dati):
    """Schema completo dai dati letti; errore se la forma e' sbagliata."""
    if not isinstance(dati, dict):
        raise SchemaErrore(u"Schema di facciata vuoto.")
    unioni = []
    for u in dati.get(u"unioni") or []:
        try:
            unioni.append({u"colonne": [int(v) for v in u[u"colonne"]][:2],
                           u"righe": [int(v) for v in u[u"righe"]][:2]})
        except Exception:
            continue
    return nuovo(_regola(dati.get(u"colonne")), _regola(dati.get(u"righe"), True),
                 dati.get(u"nome") or u"", dati.get(u"linee"), dati.get(u"celle"),
                 dati.get(u"pannello") or R.VETRO, unioni, dati.get(u"classi"))


# --- controlli ----------------------------------------------------------------------
def errori(schema, lunghezza=None, altezza=None, quote_livelli=()):
    """Frasi che spiegano cosa non va; vuoto se lo schema si puo' applicare.
    Con lunghezza e altezza prova anche il calcolo sulla facciata vera."""
    err = []
    for chiave, nome in ((u"colonne", u"Colonne"), (u"righe", u"Righe")):
        r = schema[chiave]
        ids = [m[u"id"] for m in r[u"moduli"]]
        if len(set(ids)) != len(ids):
            err.append(u"%s: due moduli con lo stesso nome." % nome)
        try:
            R.motivo(r)
        except R.RitmoErrore as ex:
            err.append(u"%s: %s" % (nome, ex))
    for u in schema.get(u"unioni") or []:
        if len(u[u"colonne"]) != 2 or len(u[u"righe"]) != 2:
            err.append(u"Unione di celle incompleta.")
    if err or lunghezza is None or altezza is None:
        return err
    try:
        R.calcola(schema, lunghezza, altezza, quote_livelli)
    except R.RitmoErrore as ex:
        err.append(u"%s" % ex)
    return err


def descrizione(schema):
    """Riga breve: "Colonne A A B (migliore) · righe P V sui livelli"."""
    c, r = schema[u"colonne"], schema[u"righe"]
    testo = u"Colonne %s (%s) · righe %s (%s)" % (
        scrivi_sequenza(c[u"sequenza"]), R.NOMI_MODI.get(c[u"modo"], c[u"modo"]).lower(),
        scrivi_sequenza(r[u"sequenza"]), R.NOMI_MODI.get(r[u"modo"], r[u"modo"]).lower())
    if (r.get(u"livelli") or {}).get(u"attivo"):
        testo += u" sui livelli"
    return testo


# --- modifiche dalla finestra ----------------------------------------------------------
LETTERE = u"ABCDEFGHIJKLMNOPQRSTUVWXYZ"
CELLA = u"cella"
COLONNA = u"colonna"
RIGA = u"riga"


def nuovo_id(regola):
    usati = set(m[u"id"] for m in regola[u"moduli"])
    for ch in LETTERE:
        if ch not in usati:
            return ch
    n = 1
    while u"M%d" % n in usati:
        n += 1
    return u"M%d" % n


def aggiungi_modulo(regola, misura=None):
    """Nuovo modulo (con la misura dell'ultimo) in fondo alla sequenza; ritorna il suo id."""
    mid = nuovo_id(regola)
    if misura is None:
        misura = regola[u"moduli"][-1][u"misura"] if regola[u"moduli"] else 1000.0
    regola[u"moduli"].append(modulo(mid, misura))
    regola[u"sequenza"].append(mid)
    return mid


def togli_modulo(regola, mid):
    """Toglie il modulo e i suoi posti nella sequenza (l'ultimo modulo resta)."""
    if len(regola[u"moduli"]) <= 1:
        raise SchemaErrore(u"Serve almeno un modulo.")
    regola[u"moduli"] = [m for m in regola[u"moduli"] if m[u"id"] != mid]
    regola[u"sequenza"] = [i for i in regola[u"sequenza"] if i != mid] or [regola[u"moduli"][0][u"id"]]
    fine = regola.get(u"finisci_con")
    if fine is not None and fine >= len(regola[u"sequenza"]):
        regola[u"finisci_con"] = None


def imposta_sequenza(regola, testo):
    """Sequenza dal testo scritto ("A A B" o "AAB"); i moduli mancanti li segnala errori()."""
    regola[u"sequenza"] = leggi_sequenza(testo, [m[u"id"] for m in regola[u"moduli"]])
    fine = regola.get(u"finisci_con")
    if fine is not None and fine >= len(regola[u"sequenza"]):
        regola[u"finisci_con"] = None


def imposta_classe_cella(schema, c, r, classe, ambito=CELLA):
    """Classe di una cella del motivo (posizioni c, r), di tutta la sua colonna o riga.
    Per colonna e riga si tolgono le scelte piu' strette che la coprirebbero."""
    celle = schema[u"celle"]
    if ambito == COLONNA:
        for k in [k for k in celle if k.split(u",")[0] == u"%d" % c]:
            del celle[k]
        celle[u"%d,*" % c] = classe
    elif ambito == RIGA:
        for k in [k for k in celle if k.split(u",")[1] == u"%d" % r]:
            del celle[k]
        celle[u"*,%d" % r] = classe
        # "c,*" vale piu' di "*,r": sugli incroci con le colonne gia' scelte vince la riga
        for k in [k for k in celle if k.endswith(u",*") and not k.startswith(u"*")]:
            celle[u"%s,%d" % (k.split(u",")[0], r)] = classe
    else:
        celle[u"%d,%d" % (c, r)] = classe
    aggiorna_classi(schema)


def imposta_classe_linea(schema, direzione, pos, classe):
    """Classe della linea che chiude la posizione pos del motivo (direzione: colonne o righe)."""
    linee = schema[u"linee"][direzione]
    predefinita = R.MONTANTE if direzione == u"colonne" else R.TRAVERSO
    while len(linee) <= pos:
        linee.append(predefinita)
    linee[pos] = classe
    aggiorna_classi(schema)


def unisci(schema, colonne, righe):
    """Unisce le celle del motivo nelle posizioni colonne=(c0, c1), righe=(r0, r1); le unioni
    che si sovrappongono si tolgono."""
    c0, c1 = sorted(colonne)
    r0, r1 = sorted(righe)
    tieni = []
    for u in schema[u"unioni"]:
        a0, a1 = sorted(u[u"colonne"])
        b0, b1 = sorted(u[u"righe"])
        if a1 < c0 or a0 > c1 or b1 < r0 or b0 > r1:
            tieni.append(u)
    tieni.append({u"colonne": [c0, c1], u"righe": [r0, r1]})
    schema[u"unioni"] = tieni


def separa(schema, c, r):
    """Toglie le unioni che contengono la cella del motivo (c, r)."""
    schema[u"unioni"] = [u for u in schema[u"unioni"]
                         if not (min(u[u"colonne"]) <= c <= max(u[u"colonne"])
                                 and min(u[u"righe"]) <= r <= max(u[u"righe"]))]


def aggiorna_classi(schema):
    """Le classi in uso, ognuna col tipo gia' scelto; quelle non piu' usate si tolgono."""
    pan, mon = classi_usate(schema)
    vecchie = schema.get(u"classi") or {}
    schema[u"classi"] = {
        u"pannelli": dict((k, (vecchie.get(u"pannelli") or {}).get(k, u"")) for k in pan),
        u"montanti": dict((k, (vecchie.get(u"montanti") or {}).get(k, u"")) for k in mon)}
