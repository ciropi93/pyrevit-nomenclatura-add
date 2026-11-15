# -*- coding: utf-8 -*-
"""Allinea e distribuisci oggetti nella vista attiva (pianta, sezione, prospetto, dettaglio).

Le funzioni pure lavorano sugli ingombri degli oggetti nel piano della vista:
(id, u_min, v_min, u_max, v_max), con u verso destra e v verso l'alto della vista.
  - Sinistra / Destra / Alto / Basso: riferimento = l'oggetto piu' esterno;
  - Centro X / Centro Y: riferimento = il centro dell'ingombro di tutto il gruppo;
  - Distribuisci: stessa distanza tra gli oggetti, i due estremi restano fermi.
Vale in pianta, sezione, prospetto, dettaglio e legenda, non nelle viste 3D.
Gli spostamenti in Revit li fa palette_azioni.allinea_oggetti (una transazione).
"""
import allinea_in_tavola as AIT

COMANDI_ALLINEA = [u"ogg_sinistra", u"ogg_centro_x", u"ogg_destra",
                   u"ogg_alto", u"ogg_centro_y", u"ogg_basso"]
COMANDI_DISTRIBUISCI = [u"ogg_distribuisci_x", u"ogg_distribuisci_y"]
COMANDI = COMANDI_ALLINEA + COMANDI_DISTRIBUISCI


def spostamenti(boxes, comando):
    """{id: (du, dv)} per gli oggetti da spostare (quelli gia' a posto non compaiono)."""
    if not boxes:
        return {}
    out = {}
    if comando in COMANDI_DISTRIBUISCI:
        asse = u"x" if comando == u"ogg_distribuisci_x" else u"y"
        for k, d in AIT.calcola_distribuzione(boxes, asse).items():
            if abs(d) > 1e-9:
                out[k] = (d, 0.0) if asse == u"x" else (0.0, d)
        return out
    u_min = min(b[1] for b in boxes)
    v_min = min(b[2] for b in boxes)
    u_max = max(b[3] for b in boxes)
    v_max = max(b[4] for b in boxes)
    for k, a, b, c, d in boxes:
        if comando == u"ogg_sinistra":
            mossa = (u_min - a, 0.0)
        elif comando == u"ogg_destra":
            mossa = (u_max - c, 0.0)
        elif comando == u"ogg_centro_x":
            mossa = ((u_min + u_max) / 2.0 - (a + c) / 2.0, 0.0)
        elif comando == u"ogg_alto":
            mossa = (0.0, v_max - d)
        elif comando == u"ogg_basso":
            mossa = (0.0, v_min - b)
        elif comando == u"ogg_centro_y":
            mossa = (0.0, (v_min + v_max) / 2.0 - (b + d) / 2.0)
        else:
            raise ValueError(u"Comando sconosciuto: %s" % comando)
        if abs(mossa[0]) > 1e-9 or abs(mossa[1]) > 1e-9:
            out[k] = mossa
    return out


# Per ogni comando: asse (0 = orizzontale, 1 = verticale) e lato dell'ingombro che conta
_RIFERIMENTO = {
    u"ogg_sinistra": (0, u"min"), u"ogg_centro_x": (0, u"centro"), u"ogg_destra": (0, u"max"),
    u"ogg_basso": (1, u"min"), u"ogg_centro_y": (1, u"centro"), u"ogg_alto": (1, u"max"),
    u"ogg_distribuisci_x": (0, u"min"), u"ogg_distribuisci_y": (1, u"min"),
}


def _quota(box, asse, lato):
    minimo, massimo = box[1 + asse], box[3 + asse]
    if lato == u"min":
        return minimo
    if lato == u"max":
        return massimo
    return (minimo + massimo) / 2.0


def bersagli(boxes, comando):
    """{id: quota} dove deve finire, lungo l'asse del comando, il lato che conta di OGNI
    oggetto: il bordo destro per "Destra", il centro per i "Centro", il sinistro per
    "Sinistra" e "Distribuisci"... Anche di quelli che restano fermi: se un altro li
    trascina vanno rimessi a posto."""
    asse, lato = _RIFERIMENTO[comando]
    mosse = spostamenti(boxes, comando)
    out = {}
    for b in boxes:
        out[b[0]] = _quota(b, asse, lato) + mosse.get(b[0], (0.0, 0.0))[asse]
    return out


def residui(boxes, obiettivi, comando, tolleranza=1e-6):
    """{id: (du, dv)} che manca a ogni oggetto per arrivare al suo bersaglio.

    Serve dopo il primo giro di spostamenti: un oggetto ne trascina altri (il muro la
    sua porta, l'elemento la sua etichetta) e quelli vanno corretti sulla posizione
    nuova, non su quella di partenza. Si guarda solo l'asse del comando e il lato che
    conta, cosi' un ingombro che cambia un po' forma non rovina l'allineamento.
    """
    asse, lato = _RIFERIMENTO[comando]
    out = {}
    for b in boxes:
        if b[0] not in obiettivi:
            continue
        d = obiettivi[b[0]] - _quota(b, asse, lato)
        if abs(d) > tolleranza:
            out[b[0]] = (d, 0.0) if asse == 0 else (0.0, d)
    return out


# Viste dove destra/alto della vista sono direzioni sensate per spostare gli oggetti
# (nomi di Autodesk.Revit.DB.ViewType). Nelle viste 3D "alto" e' obliquo: niente.
VISTE_AMMESSE = frozenset([u"FloorPlan", u"CeilingPlan", u"EngineeringPlan", u"AreaPlan",
                           u"Section", u"Elevation", u"Detail", u"DraftingView", u"Legend"])


def vista_ammessa(tipo_vista):
    return tipo_vista in VISTE_AMMESSE
