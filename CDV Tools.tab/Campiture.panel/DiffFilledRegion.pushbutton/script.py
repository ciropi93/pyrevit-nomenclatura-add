# -*- coding: utf-8 -*-
"""Differenza tra stato di fatto e stato di progetto: selezionati gli elementi del fatto e quelli del
progetto (anche da link), taglia entrambi col piano della vista e crea le campiture del TOLTO
(fatto meno progetto) e dell'AGGIUNTO (progetto meno fatto). Shift+clic: tipi campitura."""

from System.Collections.Generic import List
from pyrevit import revit, DB, forms, script, EXEC_PARAMS
import avviso_wpf as AVW
import campiture_taglio as CT
import poligoni_2d

VOCI = (("tolto", u"Tipo campitura per il TOLTO (demolito)"),
        ("aggiunto", u"Tipo campitura per l'AGGIUNTO (nuovo)"))


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


def sezioni(elementi, piano):
    """Facce tagliate dal piano, elemento per elemento (l'unione la fa poligoni_2d, piu' leggera)."""
    return [f for e, t in elementi for f in CT.facce_di_taglio(CT.solidi(e, t), piano)]


def in_uv(facce, o, x, y):
    """Facce (liste di CurveLoop) -> facce 2D. shortcut: gli archi diventano spezzate (Tessellate), basta per il disegno."""
    return [[[((p - o).DotProduct(x), (p - o).DotProduct(y)) for c in loop for p in list(c.Tessellate())[:-1]]
             for loop in f] for f in facce]


def in_loops(facce, o, x, y):
    pt = lambda q: o + x * q[0] + y * q[1]
    return [[DB.CurveLoop.Create(List[DB.Curve]([DB.Line.CreateBound(pt(a[i - 1]), pt(a[i])) for i in range(len(a))]))
             for a in f] for f in facce]


def main():
    doc, uidoc, view = revit.doc, revit.uidoc, revit.active_view
    CT.vista_valida(view)
    cfg = script.get_config()
    tipi = CT.tipi_campitura(doc)
    mancante = any(tipi.get(cfg.get_option(k, None)) is None for k, _ in VOCI)
    if EXEC_PARAMS.config_mode or mancante:
        if not impostazioni(doc, cfg) or EXEC_PARAMS.config_mode:
            return

    fatto = CT.scegli_elementi(doc, uidoc, u"gli elementi dello STATO DI FATTO")
    if not fatto:
        return
    progetto = CT.scegli_elementi(doc, uidoc, u"gli elementi dello STATO DI PROGETTO", False)
    if not progetto:
        return

    piano = CT.piano_di_taglio(doc, view)
    o, x, y = piano.Origin, view.RightDirection, view.UpDirection
    f_fatto, f_progetto = in_uv(sezioni(fatto, piano), o, x, y), in_uv(sezioni(progetto, piano), o, x, y)
    if not f_fatto and not f_progetto:
        AVW.errore(u"Nessuna parte tagliata: gli elementi sono tagliati dal piano della vista?")
        return
    tolto = in_loops(poligoni_2d.differenza(f_fatto, f_progetto), o, x, y)
    aggiunto = in_loops(poligoni_2d.differenza(f_progetto, f_fatto), o, x, y)

    with revit.Transaction(u"Differenza fatto-progetto"):
        create = (CT.crea(doc, view, tipi[cfg.tolto].Id, tolto)
                  + CT.crea(doc, view, tipi[cfg.aggiunto].Id, aggiunto))
    if not create:
        AVW.attenzione(u"Nessuna differenza: fatto e progetto coincidono")
        return
    uidoc.Selection.SetElementIds(List[DB.ElementId]([r.Id for r in create]))
    AVW.mostra(u"Campiture della differenza create: %d" % len(create))


if __name__ == "__main__":
    main()
