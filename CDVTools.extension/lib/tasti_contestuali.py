# -*- coding: utf-8 -*-
"""Quali tasti mostrare nel pannello in sovraimpressione (senza API Revit).

In tavola, cliccando il titolo di una vista si seleziona il suo riquadro (Viewport),
quindi "viste" e "titoli" selezionati sono la stessa cosa: si contano le viste.
Il riquadro di sfondo di una sezione conta come la sua sezione madre.
"""

SEZIONE_APRI = u"sezione_apri"
SEZIONE_SINCRONIZZA = u"sezione_sincronizza"

# (comando, etichetta, suggerimento)
_SEZIONE = [
    (SEZIONE_APRI, u"Profondità sezione", u"Apri Profondità Sezione su questa sezione"),
    (SEZIONE_SINCRONIZZA, u"Sincronizza sfondo",
     u"Riallinea sfondo e tavole alla sezione madre (annullabile)"),
]

_TITOLO_SINGOLO = [
    (u"titolo_bordo_sinistro", u"A filo del ritaglio",
     u"Porta il titolo sul bordo sinistro del ritaglio della vista"),
    (u"titolo_larghezza_vista", u"Linea = larghezza ritaglio",
     u"Linea del titolo lunga quanto il ritaglio della vista"),
]

_TITOLI_MULTI = [
    (u"titolo_colonna", u"Incolonna (X)",
     u"Titoli sulla stessa verticale (riferimento: la vista più a sinistra)"),
    (u"titolo_riga", u"In riga (Y)",
     u"Titoli sulla stessa orizzontale (riferimento: la vista più in basso)"),
    (u"titolo_distanza_y", u"Stessa distanza",
     u"Stessa distanza verticale tra titolo e fondo del ritaglio (riferimento: la vista più in basso)"),
    (u"titolo_lunghezza_rif", u"Stessa linea",
     u"Stessa lunghezza della linea del titolo (riferimento scelto in automatico)"),
]

_VISTE = [
    (u"box_sinistra", u"Sinistra", u"Allinea il bordo sinistro dei ritagli (riferimento: la vista più a sinistra)"),
    (u"box_centro_x", u"Centro X", u"Allinea il centro orizzontale dei ritagli"),
    (u"box_destra", u"Destra", u"Allinea il bordo destro dei ritagli (riferimento: la vista più a destra)"),
    (u"box_modello_x", u"Modello X", u"Allinea le viste sulle stesse coordinate del modello (X)"),
    (u"box_alto", u"Alto", u"Allinea il bordo superiore dei ritagli (riferimento: la vista più in alto)"),
    (u"box_centro_y", u"Centro Y", u"Allinea il centro verticale dei ritagli"),
    (u"box_basso", u"Basso", u"Allinea il bordo inferiore dei ritagli (riferimento: la vista più in basso)"),
    (u"box_modello_y", u"Modello Y", u"Allinea le viste sulle stesse coordinate del modello (Y / quote)"),
]

_DISTRIBUISCI = [
    (u"distribuisci_x", u"Orizzontale", u"Stessa distanza tra le viste in orizzontale (le estreme restano ferme)"),
    (u"distribuisci_y", u"Verticale", u"Stessa distanza tra le viste in verticale (le estreme restano ferme)"),
]


def viste_distinte(id_viste, sfondo_a_madre):
    """Id delle viste selezionate, con lo sfondo sostituito dalla sua madre, senza doppioni."""
    out = []
    for v in id_viste:
        m = sfondo_a_madre.get(v, v)
        if m not in out:
            out.append(m)
    return out


def comandi_per_selezione(n_viste, in_tavola=True, sezione_con_sfondo=False):
    """Gruppi di tasti da mostrare: lista di (titolo_gruppo, [(comando, etichetta, suggerimento)])."""
    gruppi = []
    if sezione_con_sfondo and n_viste == 1:
        gruppi.append((u"Sezione", list(_SEZIONE)))
    if in_tavola and n_viste == 1:
        gruppi.append((u"Titolo", list(_TITOLO_SINGOLO)))
    if in_tavola and n_viste >= 2:
        gruppi.append((u"Titoli", list(_TITOLI_MULTI) + list(_TITOLO_SINGOLO)))
        gruppi.append((u"Allinea viste", list(_VISTE)))
    if in_tavola and n_viste >= 3:
        gruppi.append((u"Distribuisci", list(_DISTRIBUISCI)))
    return gruppi
