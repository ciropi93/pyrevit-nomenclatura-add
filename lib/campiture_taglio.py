# -*- coding: utf-8 -*-
"""Geometria comune ai pulsanti delle campiture di sezione:
solidi degli elementi (anche da link), piano di taglio della vista, facce tagliate, campiture."""

from System.Collections.Generic import List
from pyrevit import DB, UI, forms, script

AREA_MIN = 1e-3  # ft2 (~1 cm2): scarta le schegge lasciate dalle operazioni booleane


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
            if (isinstance(f, DB.PlanarFace) and f.Area > AREA_MIN and abs(f.FaceNormal.DotProduct(n)) > 0.999
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


def tipi_campitura(doc):
    tipi = DB.FilteredElementCollector(doc).OfClass(DB.FilledRegionType)
    return dict((DB.Element.Name.__get__(t), t) for t in tipi)


def vista_valida(view):
    if not isinstance(view, (DB.ViewPlan, DB.ViewSection)):
        forms.alert(u"Apri una pianta, una sezione o un prospetto.", exitscript=True)


def _di_modello(e):
    return e is not None and e.Category is not None and e.Category.CategoryType == DB.CategoryType.Model


def scegli_elementi(doc, uidoc, cosa=u"gli elementi", usa_selezione=True):
    """Lista di (elemento, transform): selezione corrente, altrimenti scelta a video (modello o link)."""
    if usa_selezione:
        scelti = [(e, None) for e in (doc.GetElement(i) for i in uidoc.Selection.GetElementIds()) if _di_modello(e)]
        if scelti:
            return scelti
    dove = forms.CommandSwitchWindow.show([u"Elementi del modello", u"Elementi in link RVT"],
                                          message=u"Dove sono {}?".format(cosa))
    if not dove:
        return []
    msg = u"Seleziona {} e premi Fine".format(cosa)
    try:
        if dove == u"Elementi del modello":
            refs = uidoc.Selection.PickObjects(UI.Selection.ObjectType.Element, msg)
            return [(doc.GetElement(r), None) for r in refs if _di_modello(doc.GetElement(r))]
        refs = uidoc.Selection.PickObjects(UI.Selection.ObjectType.LinkedElement, msg)
    except Exception:  # Esc
        return []
    out = []
    for r in refs:
        link = doc.GetElement(r.ElementId)
        e = link.GetLinkDocument().GetElement(r.LinkedElementId)
        if _di_modello(e):
            out.append((e, link.GetTotalTransform()))
    return out
