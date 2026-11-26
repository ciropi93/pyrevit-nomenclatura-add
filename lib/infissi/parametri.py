# -*- coding: utf-8 -*-
"""Parametri della famiglia di un infisso: nomi, valori, formule (senza API Revit).

Tutti parametri di tipo. Larghezza e Altezza sono quelli del modello famiglia di Revit
(`integrato`); nelle formule si scrivono "Larghezza"/"Altezza" e revit_famiglia li
rinomina con i nomi veri della famiglia (es. "Width"/"Height" su Revit in inglese).
"""
import re

from infissi import geometria as G
from infissi import schema as S

LUNGHEZZA = u"lunghezza"
TESTO = u"testo"
MATERIALE = u"materiale"
SINO = u"si_no"

# gruppi (revit_famiglia li traduce nei gruppi di Revit)
DIMENSIONI = u"dimensioni"
COSTRUZIONE = u"costruzione"
GRAFICA = u"grafica"
MATERIALI = u"materiali"
DATI = u"dati"

MATERIALE_TELAIO = u"Materiale telaio"
MATERIALE_VETRO = u"Materiale vetro"
MATERIALE_PANNELLO = u"Materiale pannello"

# lato interno: lo decide geometria.py (maniglie, archi in pianta e ante aperte insieme)
INTERNO = G.INTERNO
APERTURA = u"Apertura"
SCHEMA = u"Schema CDV"

P = G.profilo
FORMULE_PROFONDITA = {
    u"Telaio inizio": u"-%s / 2" % P(u"telaio_prof"),
    u"Telaio fine": u"%s / 2" % P(u"telaio_prof"),
    u"Anta inizio": u"%s - %s / 2" % (P(u"anta_spost"), P(u"anta_prof")),
    u"Anta fine": u"%s + %s / 2" % (P(u"anta_spost"), P(u"anta_prof")),
    u"Anta A inizio": u"%s - %s" % (P(u"anta_spost"), P(u"anta_prof")),
    u"Anta A fine": u"%s" % P(u"anta_spost"),
    u"Anta B inizio": u"%s" % P(u"anta_spost"),
    u"Anta B fine": u"%s + %s" % (P(u"anta_spost"), P(u"anta_prof")),
    u"Vetro inizio": u"-%s / 2" % P(u"vetro"),
    u"Vetro fine": u"%s / 2" % P(u"vetro"),
    u"Vetro anta inizio": u"%s - %s / 2" % (P(u"anta_spost"), P(u"vetro")),
    u"Vetro anta fine": u"%s + %s / 2" % (P(u"anta_spost"), P(u"vetro")),
    u"Vetro A inizio": u"%s - %s / 2 - %s / 2" % (P(u"anta_spost"), P(u"anta_prof"), P(u"vetro")),
    u"Vetro A fine": u"%s - %s / 2 + %s / 2" % (P(u"anta_spost"), P(u"anta_prof"), P(u"vetro")),
    u"Vetro B inizio": u"%s + %s / 2 - %s / 2" % (P(u"anta_spost"), P(u"anta_prof"), P(u"vetro")),
    u"Vetro B fine": u"%s + %s / 2 + %s / 2" % (P(u"anta_spost"), P(u"anta_prof"), P(u"vetro")),
}
if INTERNO > 0:
    FORMULE_PROFONDITA[u"Maniglia inizio"] = u"%s + %s / 2" % (P(u"anta_spost"), P(u"anta_prof"))
    FORMULE_PROFONDITA[u"Maniglia fine"] = u"%s + %s / 2 + %s" % (
        P(u"anta_spost"), P(u"anta_prof"), P(u"maniglia_sporg"))
else:
    FORMULE_PROFONDITA[u"Maniglia inizio"] = u"%s - %s / 2 - %s" % (
        P(u"anta_spost"), P(u"anta_prof"), P(u"maniglia_sporg"))
    FORMULE_PROFONDITA[u"Maniglia fine"] = u"%s - %s / 2" % (P(u"anta_spost"), P(u"anta_prof"))
FORMULA_MONTANTE_MEZZO = u"%s / 2" % P(u"montante")

# spessori delle ante aperte (vedi G.SPESSORI_APERTI): pos/neg = verso il vano a destra/sinistra
FORMULE_APERTE = {
    u"Anta aperta pos": u"%s" % P(u"anta_prof"),
    u"Anta aperta neg": u"-%s" % P(u"anta_prof"),
    u"Vetro aperto inizio pos": u"%s / 2 - %s / 2" % (P(u"anta_prof"), P(u"vetro")),
    u"Vetro aperto fine pos": u"%s / 2 + %s / 2" % (P(u"anta_prof"), P(u"vetro")),
    u"Vetro aperto inizio neg": u"-%s / 2 - %s / 2" % (P(u"anta_prof"), P(u"vetro")),
    u"Vetro aperto fine neg": u"-%s / 2 + %s / 2" % (P(u"anta_prof"), P(u"vetro")),
}
FORMULA_CHIUSA = u"not(%s)" % G.APERTA


class FormulaErrore(ValueError):
    pass


def _parametro(nome, tipo, gruppo, valore=None, formula=None, integrato=False, istanza=False):
    return {u"nome": nome, u"tipo": tipo, u"gruppo": gruppo, u"valore": valore,
            u"formula": formula, u"integrato": integrato, u"istanza": istanza}


# --- formule ---------------------------------------------------------------------------
_NUMERO = re.compile(u"[0-9]+(\\.[0-9]+)?")


def tokenizza(formula, nomi):
    """[(tipo, testo)] con tipo in nome/numero/op; i nomi si riconoscono dal piu' lungo."""
    ordinati = sorted(nomi, key=len, reverse=True)
    out = []
    i = 0
    while i < len(formula):
        ch = formula[i]
        if ch.isspace():
            i += 1
            continue
        if ch in u"+-*/()":
            out.append((u"op", ch))
            i += 1
            continue
        m = _NUMERO.match(formula, i)
        if m:
            out.append((u"numero", m.group(0)))
            i = m.end()
            continue
        for n in ordinati:
            if formula.startswith(n, i):
                out.append((u"nome", n))
                i += len(n)
                break
        else:
            raise FormulaErrore(u"Formula non valida vicino a: %s" % formula[i:])
    return out


def dipendenze(formula, nomi):
    return [t for k, t in tokenizza(formula, nomi) if k == u"nome"]


def valuta(formula, valori):
    """Valore numerico di una formula (solo + - * / e parentesi)."""
    pezzi = []
    for k, t in tokenizza(formula, list(valori.keys())):
        pezzi.append(repr(float(valori[t])) if k == u"nome" else t)
    try:
        return float(eval(u" ".join(pezzi), {"__builtins__": {}}, {}))
    except Exception:
        raise FormulaErrore(u"Formula non calcolabile: %s" % formula)


def rinomina(formula, mappa, nomi):
    """Sostituisce i nomi di parametro secondo `mappa` (gli altri restano)."""
    parti = []
    for k, t in tokenizza(formula, list(nomi) + list(mappa.keys())):
        parti.append(mappa.get(t, t) if k == u"nome" else t)
    testo = u" ".join(parti)
    return testo.replace(u"( ", u"(").replace(u" )", u")")


# --- elenco dei parametri --------------------------------------------------------------
def elenco(schema, ris=None):
    """Parametri della famiglia, in ordine di creazione (prima quelli da cui dipendono gli altri)."""
    ris = ris or G.calcola(schema)
    if ris[u"errori"]:
        raise S.SchemaErrore(u"\n".join(ris[u"errori"]))
    valori = ris[u"valori"]
    out = [_parametro(G.LARGHEZZA, LUNGHEZZA, DIMENSIONI, valori[G.LARGHEZZA], integrato=True),
           _parametro(G.ALTEZZA, LUNGHEZZA, DIMENSIONI, valori[G.ALTEZZA], integrato=True)]
    for m in ris[u"misure"]:
        out.append(_parametro(m[u"nome"], LUNGHEZZA, DIMENSIONI, m[u"valore"]))

    usati = set(p[u"param"] for p in ris[u"piani"] if p[u"param"])
    profondita = set()
    for pz in ris[u"pezzi"]:
        profondita.update(G.PROFONDITA[pz[u"profondita"]])
    usati.update(profondita)
    usati.update(p[u"param"] for p in ris[u"piani_y"] if p[u"param"])
    for s in ris[u"simboli"] + ris[u"pianta"]:
        for seg in s[u"segmenti"]:
            for c in seg[u"coord"]:
                if c[1]:
                    usati.add(c[1])
    for pz in ris[u"pezzi_aperti"]:
        for coppia in G.SPESSORI_APERTI[u"vetro" if pz[u"spessore"] == u"vetro" else u"anta"].values():
            usati.update(n for n in coppia if n)
    derivati = dict((d[u"nome"], d) for d in ris[u"derivati"])
    formule = dict(FORMULE_PROFONDITA)
    formule.update(FORMULE_APERTE)
    formule[G.MONTANTE_MEZZO] = FORMULA_MONTANTE_MEZZO
    for d in ris[u"derivati"]:
        formule[d[u"nome"]] = d[u"formula"]

    # chiusura: anche i parametri da cui dipendono le formule usate
    tutti_nomi = list(valori.keys()) + list(formule.keys())
    da_vedere = list(usati)
    while da_vedere:
        n = da_vedere.pop()
        if n in formule:
            for d in dipendenze(formule[n], tutti_nomi):
                if d not in usati:
                    usati.add(d)
                    da_vedere.append(d)

    for k, etichetta, _v, _m in S.PROFILI:
        if etichetta in usati:
            out.append(_parametro(etichetta, LUNGHEZZA, COSTRUZIONE, valori[etichetta]))
    if G.MONTANTE_MEZZO in usati:
        out.append(_parametro(G.MONTANTE_MEZZO, LUNGHEZZA, COSTRUZIONE,
                              valori[G.MONTANTE_MEZZO], FORMULA_MONTANTE_MEZZO))
    for nome in sorted(FORMULE_PROFONDITA):
        if nome in usati:
            v = valuta(FORMULE_PROFONDITA[nome], valori)
            out.append(_parametro(nome, LUNGHEZZA, COSTRUZIONE, v, FORMULE_PROFONDITA[nome]))
    for nome in sorted(FORMULE_APERTE):
        if nome in usati:
            out.append(_parametro(nome, LUNGHEZZA, COSTRUZIONE, valuta(FORMULE_APERTE[nome], valori),
                                  FORMULE_APERTE[nome]))
    for d in ris[u"derivati"]:
        if d[u"nome"] in usati:
            out.append(_parametro(d[u"nome"], LUNGHEZZA, GRAFICA, derivati[d[u"nome"]][u"valore"],
                                  d[u"formula"]))
    out.append(_parametro(MATERIALE_TELAIO, MATERIALE, MATERIALI))
    out.append(_parametro(MATERIALE_VETRO, MATERIALE, MATERIALI))
    if any(pz[u"tipo"] == u"pannello" for pz in ris[u"pezzi"]):
        out.append(_parametro(MATERIALE_PANNELLO, MATERIALE, MATERIALI))
    if ris[u"pezzi_aperti"] or any(pz[u"stato"] for pz in ris[u"pezzi"]):
        # di istanza: ogni finestra/porta del progetto si mostra aperta o chiusa da sola
        out.append(_parametro(G.APERTA, SINO, GRAFICA, 0, istanza=True))
        out.append(_parametro(G.CHIUSA, SINO, GRAFICA, None, FORMULA_CHIUSA, istanza=True))
    out.append(_parametro(APERTURA, TESTO, DATI, S.descrizione(schema)))
    out.append(_parametro(SCHEMA, TESTO, DATI, S.to_json(schema)))
    return out


def valori_input(parametri):
    """{nome: mm} dei parametri di lunghezza senza formula (quelli da scrivere nel tipo)."""
    return dict((p[u"nome"], p[u"valore"]) for p in parametri
                if p[u"tipo"] == LUNGHEZZA and not p[u"formula"])


def schema_da_valori(schema, valori):
    """Schema con larghezza, altezza, profili e misure presi da {nome parametro: mm}.

    Serve per "Modifica infisso": i valori sono quelli del tipo nel progetto, che l'utente
    puo' aver cambiato in Revit. I nomi mancanti restano come nello schema.
    """
    s = S.copia(schema)
    if G.LARGHEZZA in valori:
        s[u"larghezza"] = float(valori[G.LARGHEZZA])
    if G.ALTEZZA in valori:
        s[u"altezza"] = float(valori[G.ALTEZZA])
    for k, etichetta, _v, _m in S.PROFILI:
        if etichetta in valori:
            s[u"profili"][k] = float(valori[etichetta])
    for percorso, div in S.divisioni(s[u"radice"]):
        for i in range(len(div[u"figli"]) - 1):
            nome = G.nome_misura(div[u"verso"], tuple(percorso) + (i,))
            if nome in valori:
                div[u"misure"][i] = float(valori[nome])
    return s
