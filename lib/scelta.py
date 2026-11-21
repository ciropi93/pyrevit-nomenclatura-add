# -*- coding: utf-8 -*-
"""Finestra "scegli da un elenco": testi e filtro (senza API Revit ne' WPF).

La finestra (scelta_wpf.py + scelta.xaml) mostra una sorgente gia' nota, un elenco
da spuntare con ricerca e un pulsante che dice quante voci verranno toccate.
"""


def testo_pulsante(n, singolare, plurale, vuoto=None):
    """'Copia su 1 vista' / 'Copia su 3 viste' (plurale con %d); vuoto se n == 0."""
    if n <= 0:
        return vuoto or plurale.replace(u"%d", u"0")
    if n == 1:
        return singolare
    return plurale % n


def corrisponde(testo_cercato, *campi):
    """True se tutte le parole cercate compaiono in almeno uno dei campi (senza maiuscole)."""
    parole = (testo_cercato or u"").lower().split()
    if not parole:
        return True
    unito = u" ".join((c or u"") for c in campi).lower()
    return all(p in unito for p in parole)


def testo_tutte(spuntate_visibili, visibili):
    """Etichetta del pulsante che spunta/toglie tutte le voci visibili."""
    if visibili and spuntate_visibili == visibili:
        return u"Deseleziona tutte"
    return u"Seleziona tutte"
