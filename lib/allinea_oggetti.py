# -*- coding: utf-8 -*-
"""Allinea e distribuisci oggetti nella vista attiva (pianta, sezione, prospetto, dettaglio).

Le funzioni pure lavorano sugli ingombri degli oggetti nel piano della vista:
(id, u_min, v_min, u_max, v_max), con u verso destra e v verso l'alto della vista.
  - Sinistra / Destra / Alto / Basso: riferimento = l'oggetto piu' esterno;
  - Centro X / Centro Y: riferimento = il centro dell'ingombro di tutto il gruppo;
  - Distribuisci: stessa distanza tra gli oggetti, i due estremi restano fermi.
esegui() fa gli spostamenti in Revit in un'unica transazione (annullabile).
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


# ==============================================================================
# REVIT
# ==============================================================================

def _ingombro(el, vista, destra, alto):
    from Autodesk.Revit import DB
    bb = el.get_BoundingBox(vista)
    if bb is None:
        return None
    us, vs = [], []
    for x in (bb.Min.X, bb.Max.X):
        for y in (bb.Min.Y, bb.Max.Y):
            for z in (bb.Min.Z, bb.Max.Z):
                p = bb.Transform.OfPoint(DB.XYZ(x, y, z))
                us.append(p.DotProduct(destra))
                vs.append(p.DotProduct(alto))
    return min(us), min(vs), max(us), max(vs)


def esegui(uidoc, comando):
    """Allinea/distribuisce gli oggetti selezionati nella vista attiva; ritorna il messaggio."""
    from Autodesk.Revit import DB
    doc = uidoc.Document
    vista = doc.ActiveView
    destra, alto = vista.RightDirection, vista.UpDirection
    boxes, saltati = [], 0
    for eid in uidoc.Selection.GetElementIds():
        el = doc.GetElement(eid)
        if el is None:
            continue
        if el.Pinned or el.GroupId != DB.ElementId.InvalidElementId:
            saltati += 1
            continue
        box = _ingombro(el, vista, destra, alto)
        if box is not None:
            boxes.append((eid,) + box)
    mosse = spostamenti(boxes, comando)
    if mosse:
        t = DB.Transaction(doc, u"Palette: allinea oggetti")
        t.Start()
        try:
            for eid, (du, dv) in mosse.items():
                DB.ElementTransformUtils.MoveElement(
                    doc, eid, destra.Multiply(du).Add(alto.Multiply(dv)))
            t.Commit()
        except Exception:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            raise
    msg = u"%d oggetti spostati." % len(mosse) if mosse else u"Gli oggetti erano già allineati."
    if saltati:
        msg += u"\n(%d bloccati o in gruppi: saltati)" % saltati
    return msg
