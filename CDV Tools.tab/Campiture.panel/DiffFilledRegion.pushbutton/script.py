# -*- coding: utf-8 -*-
"""Differenza tra campiture: selezionate le campiture dello stato di fatto e quelle dello stato di
progetto, crea le campiture del TOLTO (fatto meno progetto) e dell'AGGIUNTO (progetto meno fatto).
Le campiture di partenza restano. Shift+clic: impostazioni (tipi campitura per tolto e aggiunto)."""

from System.Collections.Generic import List
from pyrevit import revit, DB, UI, forms, script, EXEC_PARAMS
import campiture_taglio as CT
import poligoni_2d

VOCI = (("tolto", u"Tipo campitura per il TOLTO (demolito)"),
        ("aggiunto", u"Tipo campitura per l'AGGIUNTO (nuovo)"))


class SoloCampiture(UI.Selection.ISelectionFilter):
    def AllowElement(self, e):
        return isinstance(e, DB.FilledRegion)

    def AllowReference(self, ref, punto):
        return False


def impostazioni(doc, cfg):
    """Chiede i due tipi campitura e li salva. Ritorna False se annullato."""
    nomi = sorted(CT.tipi_campitura(doc))
    for chiave, titolo in VOCI:
        scelto = forms.SelectFromList.show(nomi, title=titolo, button_name=u"Usa")
        if not scelto:
            return False
        setattr(cfg, chiave, scelto)
    script.save_config()
    return True


def scegli_campiture(doc, uidoc, cosa, usa_selezione):
    if usa_selezione:
        sel = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
        if sel and all(isinstance(e, DB.FilledRegion) for e in sel):
            return sel
    try:
        refs = uidoc.Selection.PickObjects(UI.Selection.ObjectType.Element, SoloCampiture(),
                                           u"Seleziona le campiture dello {} e premi Fine".format(cosa))
    except Exception:  # Esc
        return []
    return [doc.GetElement(r) for r in refs]


def in_uv(regioni, o, x, y):
    """Campiture -> facce 2D. shortcut: gli archi diventano spezzate (Tessellate), basta per il disegno."""
    return [[[((p - o).DotProduct(x), (p - o).DotProduct(y)) for c in loop for p in list(c.Tessellate())[:-1]]
             for loop in r.GetBoundaries()] for r in regioni]


def in_loops(facce, o, x, y):
    pt = lambda q: o + x * q[0] + y * q[1]
    return [[DB.CurveLoop.Create(List[DB.Curve]([DB.Line.CreateBound(pt(a[i - 1]), pt(a[i])) for i in range(len(a))]))
             for a in f] for f in facce]


def main():
    doc, uidoc, view = revit.doc, revit.uidoc, revit.active_view
    cfg = script.get_config()
    tipi = CT.tipi_campitura(doc)
    mancante = any(tipi.get(cfg.get_option(k, None)) is None for k, _ in VOCI)
    if EXEC_PARAMS.config_mode or mancante:
        if not impostazioni(doc, cfg) or EXEC_PARAMS.config_mode:
            return

    fatto = scegli_campiture(doc, uidoc, u"STATO DI FATTO", True)
    if not fatto:
        return
    progetto = scegli_campiture(doc, uidoc, u"STATO DI PROGETTO", False)
    if not progetto:
        return

    o = list(fatto[0].GetBoundaries()[0])[0].GetEndPoint(0)  # un punto sul piano delle campiture
    x, y = view.RightDirection, view.UpDirection
    f_fatto, f_progetto = in_uv(fatto, o, x, y), in_uv(progetto, o, x, y)
    tolto = in_loops(poligoni_2d.differenza(f_fatto, f_progetto), o, x, y)
    aggiunto = in_loops(poligoni_2d.differenza(f_progetto, f_fatto), o, x, y)

    with revit.Transaction(u"Differenza campiture"):
        create = (CT.crea(doc, view, tipi[cfg.tolto].Id, tolto)
                  + CT.crea(doc, view, tipi[cfg.aggiunto].Id, aggiunto))
    if not create:
        forms.alert(u"Nessuna differenza: le campiture coincidono.")
        return
    uidoc.Selection.SetElementIds(List[DB.ElementId]([r.Id for r in create]))


if __name__ == "__main__":
    main()
