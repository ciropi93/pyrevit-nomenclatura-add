# -*- coding: utf-8 -*-
"""Cambia livello di una pianta: scelte proposte e nomi (senza API Revit)."""

PIEDI_IN_METRI = 0.3048


def quota_testo(quota_piedi):
    """Quota di un livello come la scrive un architetto: +3.40 m, -3.20 m, 0.00 m."""
    m = quota_piedi * PIEDI_IN_METRI
    if abs(m) < 0.005:
        return u"0.00 m"
    return u"%+.2f m" % m


def livello_proposto(quote, indice_attuale):
    """Indice del livello da proporre: quello subito sopra l'attuale, altrimenti quello sotto.

    quote: quote dei livelli in ordine crescente; indice_attuale: livello della pianta
    (None se non si sa). Ritorna None se non c'e' un altro livello.
    """
    n = len(quote)
    if n == 0:
        return None
    if indice_attuale is None:
        return 0
    if indice_attuale + 1 < n:
        return indice_attuale + 1
    if indice_attuale - 1 >= 0:
        return indice_attuale - 1
    return None


def nome_nuova_vista(nome, livello_vecchio, livello_nuovo, duplica):
    """Nome per la pianta sul nuovo livello.

    Se il nome contiene il livello vecchio lo sostituisce ("Pianta Piano Terra" ->
    "Pianta Piano Primo"). Altrimenti: spostando tiene il nome; duplicando aggiunge il
    livello in coda, cosi' le due viste non si confondono.
    """
    if livello_vecchio and livello_vecchio in nome:
        return nome.replace(livello_vecchio, livello_nuovo)
    if duplica:
        return u"%s - %s" % (nome, livello_nuovo)
    return nome


def testo_pulsante(nome_livello, duplica):
    if not nome_livello:
        return u"Scegli un livello"
    return (u"Duplica su %s" if duplica else u"Sposta su %s") % nome_livello
