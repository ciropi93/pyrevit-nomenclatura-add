# -*- coding: utf-8 -*-
"""Aggiorna modello di vista: testi e scelte proposte (senza API Revit).

Il giro di lavoro e':
  1. la vista usa un modello -> "Sgancia per modificare" (si ricorda quale era);
  2. si cambia la grafica della vista;
  3. si rilancia: il modello di prima e' gia' proposto -> "Aggiorna" e la vista si riaggancia.
"""

COMANDO_SGANCIATI = u"aggiorna_modello_sganciati"   # chiave in memoria_finestre


def testo_viste(n):
    if n <= 0:
        return u"nessuna vista"
    return u"1 vista" if n == 1 else u"%d viste" % n


def nota_impatto(n_altre):
    """Cosa succede alle altre viste che usano il modello."""
    if n_altre <= 0:
        return u"Nessun'altra vista usa questo modello."
    return u"Cambiano subito anche le altre %s che lo usano." % testo_viste(n_altre)


def testo_pulsante(nome_modello, nuovo):
    if nuovo:
        return u"Crea modello"
    if not nome_modello:
        return u"Scegli un modello"
    return u"Aggiorna %s" % nome_modello


def nome_nuovo_modello(nome_vista, esistenti):
    """'<vista> - Modello', con (2), (3)... se il nome c'e' gia'."""
    base = u"%s - Modello" % nome_vista
    if base not in esistenti:
        return base
    i = 2
    while u"%s (%d)" % (base, i) in esistenti:
        i += 1
    return u"%s (%d)" % (base, i)


def indice_proposto(chiavi_modelli, chiave_ricordata):
    """Posizione del modello da cui la vista era stata sganciata; None se non si sa.

    Senza un ricordo non si propone nulla: aggiornare il modello sbagliato cambierebbe
    tutte le sue viste.
    """
    if chiave_ricordata and chiave_ricordata in chiavi_modelli:
        return list(chiavi_modelli).index(chiave_ricordata)
    return None
