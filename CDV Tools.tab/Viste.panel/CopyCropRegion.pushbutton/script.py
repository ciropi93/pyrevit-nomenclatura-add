# -*- coding: utf-8 -*-
"""Copia il ritaglio della vista attiva su altre viste dello stesso tipo.

La sorgente e' la vista attiva (in tavola: la vista selezionata). Si spuntano le viste
compatibili e si copia: forma (anche sagomata), estensione, ritaglio delle annotazioni.
Opzioni in "Opzioni avanzate" (Maiusc+clic le apre subito).
"""
import clr

clr.AddReference('RevitAPI')

from Autodesk.Revit.DB import (
    BoundingBoxXYZ,
    BuiltInParameter,
    CurveLoop,
    ElementId,
    FailureProcessingResult,
    FailureSeverity,
    FilteredElementCollector,
    IFailuresPreprocessor,
    Transaction,
    Transform,
    View,
    Viewport,
    ViewType,
    XYZ,
)

from pyrevit import revit, EXEC_PARAMS
import avviso as AV
import avviso_wpf as AVW
import scelta_wpf as SCW

# ==============================================================================
# UTILITY E TIPI DI VISTA
# ==============================================================================

VIEW_TYPE_NAMES = {
    ViewType.FloorPlan: u"Pianta di Pavimento",
    ViewType.CeilingPlan: u"Pianta dei Controsoffitti",
    ViewType.EngineeringPlan: u"Pianta Strutturale",
    ViewType.AreaPlan: u"Pianta delle Aree",
    ViewType.Section: u"Sezione",
    ViewType.Elevation: u"Prospetto",
    ViewType.Detail: u"Dettaglio",
    ViewType.ThreeD: u"Vista 3D",
}

PLAN_TYPES = [
    ViewType.FloorPlan,
    ViewType.CeilingPlan,
    ViewType.EngineeringPlan,
    ViewType.AreaPlan
]

SECTION_TYPES = [
    ViewType.Section,
    ViewType.Detail
]

VALID_VIEW_TYPES = [
    ViewType.FloorPlan,
    ViewType.CeilingPlan,
    ViewType.EngineeringPlan,
    ViewType.AreaPlan,
    ViewType.Section,
    ViewType.Elevation,
    ViewType.Detail,
    ViewType.ThreeD
]


def are_views_compatible(view1, view2):
    """Verifica se due viste sono geometricamente compatibili per la copia del ritaglio."""
    t1 = view1.ViewType
    t2 = view2.ViewType

    # Piante con altre piante (stesso piano orizzontale di proiezione)
    if t1 in PLAN_TYPES and t2 in PLAN_TYPES:
        return True

    # Sezioni e viste di dettaglio (piano verticale)
    if t1 in SECTION_TYPES and t2 in SECTION_TYPES:
        return True

    # Prospetti con prospetti
    if t1 == ViewType.Elevation and t2 == ViewType.Elevation:
        return True

    # Viste 3D con viste 3D
    if t1 == ViewType.ThreeD and t2 == ViewType.ThreeD:
        return True

    return t1 == t2


class WarningSwallower(IFailuresPreprocessor):
    """Elimina silenziosamente gli avvisi non critici durante l'applicazione del ritaglio."""
    def PreprocessFailures(self, failuresAccessor):
        failures = failuresAccessor.GetFailureMessages()
        for f in failures:
            if f.GetSeverity() == FailureSeverity.Warning:
                failuresAccessor.DeleteWarning(f)
        return FailureProcessingResult.Continue


# ==============================================================================
# LOGICA DI COPIA RITAGLIO
# ==============================================================================

def copy_crop_to_view(doc, src_view, tgt_view, copy_visibility=True, copy_annotation=True, remove_scope_box=True):
    """
    Copia l'estensione e la forma del ritaglio dalla vista sorgente alla vista di destinazione.
    """
    src_mgr = src_view.GetCropRegionShapeManager()
    tgt_mgr = tgt_view.GetCropRegionShapeManager()

    # 1. Gestione Scope Box (Riquadro di Definizione)
    if remove_scope_box:
        scope_p = tgt_view.get_Parameter(BuiltInParameter.VIEWER_VOLUME_OF_INTEREST_CROP)
        if scope_p and not scope_p.IsReadOnly and scope_p.AsElementId() != ElementId.InvalidElementId:
            scope_p.Set(ElementId.InvalidElementId)
            doc.Regenerate()

    # 2. Attiva il CropBox sulla destinazione per consentire modifiche
    tgt_view.CropBoxActive = True
    doc.Regenerate()

    # 3. Geometria del ritaglio
    if src_mgr.CanHaveShape and src_mgr.ShapeSet:
        # Ritaglio personalizzato (poligonale / sagomato)
        shapes = src_mgr.GetCropShape()
        if shapes and shapes.Count > 0:
            src_loop = shapes[0]

            # Traslazione per piani di quota differenti (es. diverse quote nei piani di livello)
            z_src = src_view.CropBox.Transform.Origin.Z
            z_tgt = tgt_view.CropBox.Transform.Origin.Z
            delta_z = z_tgt - z_src

            tgt_loop = CurveLoop()
            trans = Transform.CreateTranslation(XYZ(0, 0, delta_z))
            for c in src_loop:
                tgt_loop.Append(c.CreateTransformed(trans))

            if tgt_mgr.IsCropRegionShapeValid(tgt_loop):
                tgt_mgr.SetCropShape(tgt_loop)
                doc.Regenerate()
    else:
        # Ritaglio standard rettangolare
        if tgt_mgr.CanHaveShape and tgt_mgr.ShapeSet:
            tgt_mgr.RemoveCropRegionShape()
            doc.Regenerate()

        src_box = src_view.CropBox
        tgt_box = tgt_view.CropBox

        new_box = BoundingBoxXYZ()
        new_box.Transform = tgt_box.Transform
        new_box.Min = XYZ(src_box.Min.X, src_box.Min.Y, tgt_box.Min.Z)
        new_box.Max = XYZ(src_box.Max.X, src_box.Max.Y, tgt_box.Max.Z)
        tgt_view.CropBox = new_box
        doc.Regenerate()

    # 4. Stato attivo e visibilità del contorno
    tgt_view.CropBoxActive = src_view.CropBoxActive
    if copy_visibility:
        tgt_view.CropBoxVisible = src_view.CropBoxVisible

    # 5. Ritaglio delle annotazioni (Annotation Crop)
    if copy_annotation:
        src_anno = src_view.get_Parameter(BuiltInParameter.VIEWER_ANNOTATION_CROP_ACTIVE)
        tgt_anno = tgt_view.get_Parameter(BuiltInParameter.VIEWER_ANNOTATION_CROP_ACTIVE)
        if src_anno and tgt_anno and not tgt_anno.IsReadOnly:
            tgt_anno.Set(src_anno.AsInteger())
            doc.Regenerate()

            if src_anno.AsInteger() == 1 and src_mgr.CanHaveAnnotationCrop and tgt_mgr.CanHaveAnnotationCrop:
                try:
                    tgt_mgr.LeftAnnotationCropOffset = src_mgr.LeftAnnotationCropOffset
                    tgt_mgr.RightAnnotationCropOffset = src_mgr.RightAnnotationCropOffset
                    tgt_mgr.TopAnnotationCropOffset = src_mgr.TopAnnotationCropOffset
                    tgt_mgr.BottomAnnotationCropOffset = src_mgr.BottomAnnotationCropOffset
                except Exception:
                    pass


# ==============================================================================
# MAIN
# ==============================================================================

OPZIONI = [
    (u"chkCopyAnnotation", u"Copia anche il ritaglio delle annotazioni", True),
    (u"chkCopyVisibility", u"Copia anche se il contorno del ritaglio è visibile", True),
    (u"chkRemoveScopeBox", u"Scollega il riquadro di definizione, se c'è (altrimenti il ritaglio non si può cambiare)", True),
]


def vista_sorgente(doc, uidoc):
    v = doc.ActiveView
    if v is not None and not v.IsTemplate and v.ViewType in VALID_VIEW_TYPES:
        return v
    for eid in uidoc.Selection.GetElementIds():
        el = doc.GetElement(eid)
        if isinstance(el, Viewport):
            sv = doc.GetElement(el.ViewId)
            if sv is not None and sv.ViewType in VALID_VIEW_TYPES:
                return sv
    return None


def dettaglio(v):
    lvl = getattr(v, "GenLevel", None)
    if lvl is not None:
        return lvl.Name
    return VIEW_TYPE_NAMES.get(v.ViewType, u"")


def main():
    doc = revit.doc
    uidoc = revit.uidoc
    src = vista_sorgente(doc, uidoc)
    if src is None:
        AVW.errore(u"Apri la vista da cui copiare il ritaglio (pianta, sezione, prospetto o 3D)")
        return

    candidate = [
        v for v in FilteredElementCollector(doc).OfClass(View)
        if not v.IsTemplate and v.Id != src.Id and v.ViewType in VALID_VIEW_TYPES
        and are_views_compatible(src, v)
    ]
    if not candidate:
        AVW.errore(u"Nessun'altra vista dello stesso tipo a cui copiare il ritaglio")
        return
    candidate.sort(key=lambda v: (dettaglio(v), v.Name))

    ris = SCW.scegli(
        titolo=u"Copia ritaglio",
        sottotitolo=u"da " + src.Name,
        voci=[(v, v.Name, dettaglio(v)) for v in candidate],
        pulsante=(u"Copia su 1 vista", u"Copia su %d viste", u"Scegli le viste"),
        opzioni=OPZIONI, memoria=u"copia_ritaglio", apri_opzioni=EXEC_PARAMS.config_mode)
    if not ris:
        return
    viste, opz = ris

    t = Transaction(doc, u"Copia ritaglio")
    o = t.GetFailureHandlingOptions()
    o.SetFailuresPreprocessor(WarningSwallower())
    t.SetFailureHandlingOptions(o)
    fatte, errori = 0, []
    t.Start()
    try:
        for v in viste:
            try:
                copy_crop_to_view(doc, src, v,
                                  copy_visibility=opz[u"chkCopyVisibility"],
                                  copy_annotation=opz[u"chkCopyAnnotation"],
                                  remove_scope_box=opz[u"chkRemoveScopeBox"])
                fatte += 1
            except Exception as ex:
                errori.append(u"%s: %s" % (v.Name, ex))
        t.Commit()
    except Exception as ex:
        t.RollBack()
        AVW.errore(u"Copia del ritaglio non riuscita: %s" % ex)
        return

    msg = u"Ritaglio copiato su 1 vista" if fatte == 1 else u"Ritaglio copiato su %d viste" % fatte
    if fatte and errori:
        AVW.attenzione(AV.con_errori(msg, errori))
    elif fatte:
        AVW.mostra(msg)
    else:
        AVW.errore(AV.con_errori(u"Ritaglio non copiato", errori))


if __name__ == "__main__":
    main()
