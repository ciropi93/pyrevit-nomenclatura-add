# -*- coding: utf-8 -*-
"""Crea una campitura sulla parte sezionata degli elementi selezionati (pianta o sezione).
Shift+clic: impostazioni (campiture singole o unica, tipo campitura)."""

from System.Collections.Generic import List
from pyrevit import revit, DB, UI, forms, script, EXEC_PARAMS

SINGOLE = u"Campiture singole (una per elemento)"
UNICA = u"Campitura unica (tutti gli elementi uniti)"


def piano_di_taglio(doc, view):
    """Piano di taglio della vista: in pianta il piano di taglio dell'intervallo di vista, in sezione il piano della vista."""
    if isinstance(view, DB.ViewPlan):
        vr = view.GetViewRange()
        livello = doc.GetElement(vr.GetLevelId(DB.PlanViewPlane.CutPlane))
        z = livello.ProjectElevation + vr.GetOffset(DB.PlanViewPlane.CutPlane)
        return DB.Plane.CreateByNormalAndOrigin(DB.XYZ.BasisZ, DB.XYZ(0, 0, z))
    return DB.Plane.CreateByNormalAndOrigin(view.ViewDirection, view.Origin)


def solidi(elem, transform=None):
    """Solidi con volume dell'elemento, in coordinate del modello host."""
    opts = DB.Options()
    opts.DetailLevel = DB.ViewDetailLevel.Fine
    out = []
    pila = list(elem.get_Geometry(opts) or [])
    while pila:
        g = pila.pop()
        if isinstance(g, DB.GeometryInstance):
            pila.extend(g.GetInstanceGeometry() or [])
        elif isinstance(g, DB.Solid) and g.Volume > 1e-6:
            out.append(DB.SolidUtils.CreateTransformed(g, transform) if transform else g)
    return out


def unisci(lista):
    """Unisce i solidi dove Revit ci riesce; quelli che falliscono restano separati."""
    uniti = []
    for s in lista:
        for i, u in enumerate(uniti):
            try:
                uniti[i] = DB.BooleanOperationsUtils.ExecuteBooleanOperation(u, s, DB.BooleanOperationsType.Union)
                break
            except Exception:
                pass
        else:
            uniti.append(s)
    return uniti


def facce_di_taglio(lista, piano):
    """Per ogni faccia sul piano di taglio: lista di CurveLoop (contorno + fori)."""
    n, o = piano.Normal, piano.Origin
    facce = []
    for s in unisci(lista):
        try:
            tagliato = DB.BooleanOperationsUtils.CutWithHalfSpace(s, piano)
        except Exception:
            continue
        if tagliato is None:
            continue
        for f in tagliato.Faces:
            if (isinstance(f, DB.PlanarFace) and abs(f.FaceNormal.DotProduct(n)) > 0.999
                    and abs((f.Origin - o).DotProduct(n)) < 1e-3):
                facce.append(list(f.GetEdgesAsCurveLoops()))
    return facce


def crea(doc, view, tipo_id, facce):
    """Una campitura con tutte le facce; se Revit la rifiuta (facce sovrapposte), una per faccia."""
    if not facce:
        return []
    try:
        loops = List[DB.CurveLoop]([l for f in facce for l in f])
        return [DB.FilledRegion.Create(doc, tipo_id, view.Id, loops)]
    except Exception as ex:
        if len(facce) == 1:
            script.get_logger().warning(u"Faccia scartata: {}".format(ex))
            return []
        return [r for f in facce for r in crea(doc, view, tipo_id, [f])]


def campiture(doc, view, tipo_id, gruppi, unica):
    """gruppi: lista di liste di solidi (una per elemento). Ritorna le campiture create."""
    piano = piano_di_taglio(doc, view)
    if unica:
        gruppi = [[s for g in gruppi for s in g]]
    return [r for g in gruppi for r in crea(doc, view, tipo_id, facce_di_taglio(g, piano))]


def tipi_campitura(doc):
    tipi = DB.FilteredElementCollector(doc).OfClass(DB.FilledRegionType)
    return dict((DB.Element.Name.GetValue(t), t) for t in tipi)


def impostazioni(doc, cfg):
    """Chiede modo e tipo campitura e li salva. Ritorna False se annullato."""
    modo = forms.CommandSwitchWindow.show([SINGOLE, UNICA], message=u"Come creare le campiture?")
    if not modo:
        return False
    tipo = forms.SelectFromList.show(sorted(tipi_campitura(doc)), title=u"Tipo campitura", button_name=u"Usa")
    if not tipo:
        return False
    cfg.unica = modo == UNICA
    cfg.tipo = tipo
    script.save_config()
    return True


def scegli_elementi(doc, uidoc):
    """Lista di (elemento, transform): selezione corrente, altrimenti scelta a video (modello o link)."""
    modello = lambda e: e is not None and e.Category is not None and e.Category.CategoryType == DB.CategoryType.Model
    scelti = [(e, None) for e in (doc.GetElement(i) for i in uidoc.Selection.GetElementIds()) if modello(e)]
    if scelti:
        return scelti
    dove = forms.CommandSwitchWindow.show([u"Elementi del modello", u"Elementi in link RVT"], message=u"Cosa selezioni?")
    if not dove:
        return []
    try:
        if dove == u"Elementi del modello":
            refs = uidoc.Selection.PickObjects(UI.Selection.ObjectType.Element, u"Seleziona gli elementi e premi Fine")
            return [(doc.GetElement(r), None) for r in refs if modello(doc.GetElement(r))]
        refs = uidoc.Selection.PickObjects(UI.Selection.ObjectType.LinkedElement, u"Seleziona gli elementi nel link e premi Fine")
    except Exception:  # Esc
        return []
    out = []
    for r in refs:
        link = doc.GetElement(r.ElementId)
        e = link.GetLinkDocument().GetElement(r.LinkedElementId)
        if modello(e):
            out.append((e, link.GetTotalTransform()))
    return out


def main():
    doc, uidoc, view = revit.doc, revit.uidoc, revit.active_view
    if not isinstance(view, (DB.ViewPlan, DB.ViewSection)):
        forms.alert(u"Apri una pianta, una sezione o un prospetto.", exitscript=True)
    cfg = script.get_config()
    if EXEC_PARAMS.config_mode or cfg.get_option("tipo", None) is None:
        if not impostazioni(doc, cfg) or EXEC_PARAMS.config_mode:
            return
    tipo = tipi_campitura(doc).get(cfg.tipo)
    if tipo is None:
        forms.alert(u"Tipo campitura '{}' non trovato: scegline un altro.".format(cfg.tipo))
        if not impostazioni(doc, cfg):
            return
        tipo = tipi_campitura(doc)[cfg.tipo]

    elementi = scegli_elementi(doc, uidoc)
    if not elementi:
        return
    gruppi = [solidi(e, t) for e, t in elementi]
    with revit.Transaction(u"Campitura sezionato"):
        create = campiture(doc, view, tipo.Id, gruppi, cfg.unica)
    if not create:
        forms.alert(u"Nessuna parte sezionata trovata: gli elementi sono tagliati dal piano della vista?")
        return
    uidoc.Selection.SetElementIds(List[DB.ElementId]([r.Id for r in create]))


if __name__ == "__main__":
    main()
