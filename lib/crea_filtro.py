# -*- coding: utf-8 -*-
"""Crea filtro da selezione: ordine delle proposte, testi e nome (senza API Revit)."""

# parametri che di solito servono per un filtro, in ordine di importanza
_PREFERITI = [
    ((u"tipo", u"type"), 50),
    ((u"livello", u"level"), 40),
    ((u"comment",), 35),
    ((u"contrassegno", u"mark"), 30),
    ((u"funzione", u"function", u"fase", u"phase"), 25),
]

# caratteri che Revit non accetta nel nome di un filtro
_VIETATI = u'{}[]:\\|;<>?`~'


def punteggio(nome_parametro, identico):
    """Piu' alto = proposta migliore. Un valore uguale per tutti vale piu' di tutto."""
    s = 100 if identico else 0
    basso = (nome_parametro or u"").lower()
    for parole, punti in _PREFERITI:
        if any(p in basso for p in parole):
            s += punti
            break
    return s


def ordina(proposte):
    """proposte: lista di (nome_parametro, identico, ...). Migliori prima, poi per nome."""
    return sorted(proposte, key=lambda p: (-punteggio(p[0], p[1]), p[0].lower()))


def descrivi_valori(valori, massimo=3):
    """'Muro esterno' oppure 'Muro A, Muro B o Muro C' oppure '5 valori: A, B, C...'."""
    valori = sorted(set(v for v in valori if v))
    if len(valori) == 1:
        return valori[0]
    if len(valori) <= massimo:
        return u", ".join(valori[:-1]) + u" o " + valori[-1]
    return u"%d valori: %s..." % (len(valori), u", ".join(valori[:massimo]))


def nome_filtro(categorie, valori):
    """'Muri - Muro esterno 30' (una categoria) o 'Muri e Pavimenti - ...'; senza caratteri vietati."""
    cat = categorie[0] if len(categorie) == 1 else u" e ".join(categorie[:2]) + (u"..." if len(categorie) > 2 else u"")
    valori = sorted(set(v for v in valori if v))
    val = valori[0] if len(valori) == 1 else u"%d valori" % len(valori)
    nome = u"%s - %s" % (cat, val) if val else cat
    nome = u"".join(c for c in nome if c not in _VIETATI)
    return u" ".join(nome.split())[:80]


def nome_libero(nome, esistenti):
    """Il nome, con (2), (3)... se c'e' gia' un filtro con quel nome."""
    if nome not in esistenti:
        return nome
    i = 2
    while u"%s (%d)" % (nome, i) in esistenti:
        i += 1
    return u"%s (%d)" % (nome, i)
