# -*- coding: utf-8 -*-
"""Schemi pronti, schemi salvati dall'utente e impostazioni del configuratore (senza API Revit).

Gli schemi dell'utente stanno in %APPDATA%\\pyRevit\\CDVTools\\infissi\\schemi\\*.json,
le impostazioni (modelli famiglia, cartella di salvataggio) in ...\\infissi\\impostazioni.json.
"""
import io
import json
import os
import re

from infissi import schema as S

c = S.cella
dv = lambda figli, misure, montante=True: S.divisione(u"v", figli, misure, montante)  # noqa: E731
do = lambda figli, misure, montante=True: S.divisione(u"o", figli, misure, montante)  # noqa: E731

_PORTA = {u"soglia": 30.0, u"zoccolo": 200.0}


def _due_ante(sx=u"battente_sx", dx=u"anta_ribalta_dx", meta=600):
    return dv([c(sx), c(dx)], [meta], montante=False)


def preimpostati():
    """Schemi pronti (come quelli dei cataloghi dei serramentisti)."""
    N = S.nuovo
    return [
        N(c(u"anta_ribalta_dx"), 800, 1400, u"1 anta"),
        N(_due_ante(), 1200, 1500, u"2 ante"),
        N(dv([c(u"battente_sx"), c(u"fisso"), c(u"anta_ribalta_dx")], [600, 600]),
          1800, 1500, u"3 ante (centrale fissa)"),
        N(dv([c(u"fisso"), c(u"anta_ribalta_dx")], [600]), 1200, 1500, u"Fisso + anta"),
        N(do([_due_ante(), c(u"fisso")], [1500]), 1200, 2000, u"2 ante + sopraluce"),
        N(do([dv([c(u"battente_sx"), c(u"fisso"), c(u"anta_ribalta_dx")], [600, 600]),
              dv([c(u"fisso"), c(u"fisso"), c(u"fisso")], [600, 600])], [1500]),
          1800, 2000, u"3 ante + sopraluce diviso"),
        N(c(u"vasistas"), 800, 600, u"Vasistas"),
        N(do([c(u"fisso"), c(u"vasistas")], [1000]), 800, 1500, u"Fisso + vasistas sopra"),
        N(c(u"porta_sx"), 900, 2400, u"Portafinestra 1 anta", profili=_PORTA),
        N(_due_ante(u"porta_sx", u"porta_dx", 700), 1400, 2400, u"Portafinestra 2 ante",
          profili=_PORTA),
        N(do([_due_ante(u"porta_sx", u"porta_dx", 700), c(u"fisso")], [2200]), 1400, 2800,
          u"Portafinestra 2 ante + sopraluce", profili=_PORTA),
        N(dv([c(u"fisso"), c(u"porta_dx")], [500]), 1400, 2400, u"Portafinestra + laterale fisso",
          profili=_PORTA),
        N(dv([c(u"scorrevole_dx"), c(u"scorrevole_sx")], [900], montante=False), 1800, 2400,
          u"Scorrevole 2 ante", profili={u"soglia": 30.0}),
        N(dv([c(u"scorrevole_dx"), c(u"fisso")], [1000]), 2000, 2400, u"Scorrevole + fisso",
          profili={u"soglia": 30.0}),
        N(dv([c(u"porta_sx"), c(u"fisso")], [1000]), 1500, 2400, u"Porta + laterale fisso",
          categoria=S.PORTE, profili=_PORTA),
    ]


# --- percorsi -------------------------------------------------------------------------
def cartella_base():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "pyRevit", "CDVTools", "infissi")


def cartella_schemi(base=None):
    return os.path.join(base or cartella_base(), "schemi")


def nome_file(nome):
    """Nome di file sicuro da un nome di schema."""
    pulito = re.sub(u"[^0-9A-Za-zÀ-ÿ _+-]", u"_", nome or u"").strip()
    return (pulito or u"schema") + u".json"


def _scrivi(percorso, dati):
    cartella = os.path.dirname(percorso)
    if cartella and not os.path.isdir(cartella):
        os.makedirs(cartella)
    testo = json.dumps(dati, indent=2, ensure_ascii=False, sort_keys=True)
    if not isinstance(testo, type(u"")):
        testo = testo.decode("utf-8")
    with io.open(percorso, "w", encoding="utf-8") as f:
        f.write(testo + u"\n")


def _leggi(percorso):
    with io.open(percorso, "r", encoding="utf-8-sig") as f:
        return json.load(f)


# --- schemi dell'utente ----------------------------------------------------------------
def salva_schema(schema, base=None):
    percorso = os.path.join(cartella_schemi(base), nome_file(schema.get(u"nome")))
    _scrivi(percorso, schema)
    return percorso


def schemi_utente(base=None):
    """[(percorso, schema)] ordinati per nome; i file rovinati si saltano."""
    cartella = cartella_schemi(base)
    if not os.path.isdir(cartella):
        return []
    out = []
    for nome in sorted(os.listdir(cartella)):
        if not nome.lower().endswith(".json"):
            continue
        percorso = os.path.join(cartella, nome)
        try:
            out.append((percorso, S.normalizza(_leggi(percorso))))
        except Exception:
            continue
    return out


def elimina_schema(percorso):
    if os.path.exists(percorso):
        os.remove(percorso)


# --- impostazioni ----------------------------------------------------------------------
IMPOSTAZIONI_PREDEFINITE = {u"modello_finestre": u"", u"modello_porte": u"", u"cartella": u""}

# nomi dei modelli famiglia di Revit, dal piu' probabile
MODELLI = {
    S.FINESTRE: (u"Finestra metrica.rft", u"Metric Window.rft", u"Finestra.rft", u"Window.rft"),
    S.PORTE: (u"Porta metrica.rft", u"Metric Door.rft", u"Porta.rft", u"Door.rft"),
}


def percorso_impostazioni(base=None):
    return os.path.join(base or cartella_base(), "impostazioni.json")


def carica_impostazioni(base=None):
    imp = dict(IMPOSTAZIONI_PREDEFINITE)
    percorso = percorso_impostazioni(base)
    if os.path.exists(percorso):
        try:
            dati = _leggi(percorso)
            if isinstance(dati, dict):
                imp.update(dict((k, v) for k, v in dati.items() if k in imp))
        except Exception:
            pass
    return imp


def salva_impostazioni(imp, base=None):
    _scrivi(percorso_impostazioni(base), imp)


def trova_modello(categoria, cartelle, imp=None):
    """Percorso del modello famiglia: prima quello delle impostazioni, poi per nome nelle cartelle."""
    imp = imp or {}
    scelto = imp.get(u"modello_" + categoria)
    if scelto and os.path.exists(scelto):
        return scelto
    nomi = [n.lower() for n in MODELLI[categoria]]
    trovati = {}
    for cartella in cartelle:
        if not cartella or not os.path.isdir(cartella):
            continue
        for radice, _dirs, files in os.walk(cartella):
            for f in files:
                if f.lower() in nomi and f.lower() not in trovati:
                    trovati[f.lower()] = os.path.join(radice, f)
    for n in nomi:
        if n in trovati:
            return trovati[n]
    return None
