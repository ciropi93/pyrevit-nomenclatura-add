# -*- coding: utf-8 -*-
"""Cambia il livello di una pianta (quella attiva o selezionata).

Una sola domanda: a quale livello. La pianta passa al nuovo livello con grafica, modello
di vista, intervallo di visualizzazione, ritaglio, riquadro di definizione, annotazioni
2D e posto in tavola. Maiusc+clic apre subito le opzioni (duplica, nome, cosa portare).
"""

import clr

clr.AddReference('System')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from System.Collections.Generic import List

from Autodesk.Revit.DB import (
    BuiltInParameter,
    BoundingBoxXYZ,
    CopyPasteOptions,
    CurveLoop,
    ElementId,
    ElementTransformUtils,
    FailureProcessingResult,
    FailureSeverity,
    FilteredElementCollector,
    IFailuresPreprocessor,
    Level,
    OverrideGraphicSettings,
    PlanViewPlane,
    StorageType,
    Transform,
    Transaction,
    View,
    ViewPlan,
    Viewport,
    ViewType,
    XYZ,
)

from pyrevit import revit, forms, script, EXEC_PARAMS
import stile_finestre as SF
import memoria_finestre as MF
import avviso_wpf as AVW
import elenco_wpf as EW
import cambia_livello as CL

# ultime scelte della finestra (vedi lib/memoria_finestre.py); il nome non si ricorda
_MEMORIA = u"cambia_livello"
_CONTROLLI = [u"rbReplaceView", u"rbDuplicateView", u"chkCopy2D", u"chkCopyHidden"]


PLAN_VIEW_TYPES = [
    ViewType.FloorPlan,
    ViewType.CeilingPlan,
    ViewType.EngineeringPlan,
    ViewType.AreaPlan,
]

INTERNAL_SKIP_CATEGORIES = (-2000055, -2009609, -2000279)
INTERNAL_SKIP_CLASSES = ("SketchPlane", "SunAndShadowSettings")


def eid_val(eid):
    if eid is None:
        return -1
    return eid.Value if hasattr(eid, "Value") else eid.IntegerValue


class SmartFailureResolver(IFailuresPreprocessor):
    """Sopprime i warning e risolve/rimuove eventuali annotazioni orfane sul nuovo livello."""
    def PreprocessFailures(self, failuresAccessor):
        has_resolved_error = False
        for f in failuresAccessor.GetFailureMessages():
            sev = f.GetSeverity()
            if sev == FailureSeverity.Warning:
                failuresAccessor.DeleteWarning(f)
            elif sev == FailureSeverity.Error:
                if failuresAccessor.IsElementsDeletionPermitted():
                    del_ids = List[ElementId]()
                    for eid in f.GetFailingElementIds():
                        del_ids.Add(eid)
                    for eid in f.GetAdditionalElementIds():
                        del_ids.Add(eid)
                    if del_ids.Count > 0:
                        failuresAccessor.DeleteElements(del_ids)
                        has_resolved_error = True
                        continue
                if f.HasResolutions():
                    failuresAccessor.ResolveFailure(f)
                    has_resolved_error = True
                else:
                    return FailureProcessingResult.ProceedWithRollBack
        if has_resolved_error:
            return FailureProcessingResult.ProceedWithCommit
        return FailureProcessingResult.Continue


def get_unique_view_name(doc, desired_name, ignore_view_id=None):
    existing = set()
    for v in FilteredElementCollector(doc).OfClass(View):
        if ignore_view_id and v.Id == ignore_view_id:
            continue
        existing.add(v.Name)
    if desired_name not in existing:
        return desired_name
    idx = 1
    while True:
        candidate = u"{} ({})".format(desired_name, idx)
        if candidate not in existing:
            return candidate
        idx += 1


def copy_crop_and_scope(doc, src_view, tgt_view):
    scope_p = src_view.get_Parameter(BuiltInParameter.VIEWER_VOLUME_OF_INTEREST_CROP)
    scope_id = scope_p.AsElementId() if scope_p else ElementId.InvalidElementId

    if scope_id and scope_id != ElementId.InvalidElementId:
        tgt_scope_p = tgt_view.get_Parameter(BuiltInParameter.VIEWER_VOLUME_OF_INTEREST_CROP)
        if tgt_scope_p and not tgt_scope_p.IsReadOnly:
            tgt_scope_p.Set(scope_id)
            doc.Regenerate()
    else:
        north_p = src_view.get_Parameter(BuiltInParameter.PLAN_VIEW_NORTH)
        tgt_north_p = tgt_view.get_Parameter(BuiltInParameter.PLAN_VIEW_NORTH)
        if north_p and tgt_north_p and not tgt_north_p.IsReadOnly:
            try:
                tgt_north_p.Set(north_p.AsInteger())
            except Exception:
                pass

        src_mgr = src_view.GetCropRegionShapeManager()
        tgt_mgr = tgt_view.GetCropRegionShapeManager()
        tgt_view.CropBoxActive = True
        doc.Regenerate()

        if src_mgr.CanHaveShape and src_mgr.ShapeSet:
            shapes = src_mgr.GetCropShape()
            if shapes and shapes.Count > 0:
                src_loop = shapes[0]
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
            src_box = src_view.CropBox
            tgt_box = tgt_view.CropBox
            new_box = BoundingBoxXYZ()
            new_box.Transform = tgt_box.Transform
            new_box.Min = XYZ(src_box.Min.X, src_box.Min.Y, tgt_box.Min.Z)
            new_box.Max = XYZ(src_box.Max.X, src_box.Max.Y, tgt_box.Max.Z)
            tgt_view.CropBox = new_box
            doc.Regenerate()

    tgt_view.CropBoxActive = src_view.CropBoxActive
    tgt_view.CropBoxVisible = src_view.CropBoxVisible

    src_anno = src_view.get_Parameter(BuiltInParameter.VIEWER_ANNOTATION_CROP_ACTIVE)
    tgt_anno = tgt_view.get_Parameter(BuiltInParameter.VIEWER_ANNOTATION_CROP_ACTIVE)
    if src_anno and tgt_anno and not tgt_anno.IsReadOnly:
        try:
            tgt_anno.Set(src_anno.AsInteger())
            src_mgr = src_view.GetCropRegionShapeManager()
            tgt_mgr = tgt_view.GetCropRegionShapeManager()
            if src_anno.AsInteger() == 1 and src_mgr.CanHaveAnnotationCrop and tgt_mgr.CanHaveAnnotationCrop:
                tgt_mgr.LeftAnnotationCropOffset = src_mgr.LeftAnnotationCropOffset
                tgt_mgr.RightAnnotationCropOffset = src_mgr.RightAnnotationCropOffset
                tgt_mgr.TopAnnotationCropOffset = src_mgr.TopAnnotationCropOffset
                tgt_mgr.BottomAnnotationCropOffset = src_mgr.BottomAnnotationCropOffset
        except Exception:
            pass


def transfer_element_overrides(doc, src_view, tgt_view):
    default_ogs = OverrideGraphicSettings()
    for el in FilteredElementCollector(doc, src_view.Id).WhereElementIsNotElementType():
        eid = el.Id
        try:
            ogs = src_view.GetElementOverrides(eid)
            if ogs and (
                ogs.ProjectionLineWeight != default_ogs.ProjectionLineWeight
                or ogs.CutLineWeight != default_ogs.CutLineWeight
                or ogs.Transparency != default_ogs.Transparency
                or ogs.Halftone != default_ogs.Halftone
                or ogs.ProjectionLineColor.IsValid
                or ogs.CutLineColor.IsValid
                or ogs.SurfaceForegroundPatternColor.IsValid
                or ogs.CutForegroundPatternColor.IsValid
                or ogs.SurfaceForegroundPatternId != ElementId.InvalidElementId
                or ogs.CutForegroundPatternId != ElementId.InvalidElementId
            ):
                tgt_view.SetElementOverrides(eid, ogs)
        except Exception:
            pass


def transfer_hidden_elements(doc, src_view, tgt_view):
    hide_ids = List[ElementId]()
    for el in FilteredElementCollector(doc).WhereElementIsNotElementType():
        if el.Category is None:
            continue
        try:
            if el.IsHidden(src_view) and el.CanBeHidden(tgt_view):
                hide_ids.Add(el.Id)
        except Exception:
            pass

    if hide_ids.Count > 0:
        try:
            tgt_view.HideElements(hide_ids)
        except Exception:
            pass


def change_plan_level(doc, uidoc, old_view, target_level, desired_name, replace_old=True, copy_2d=True, copy_hidden=True):
    old_level_id = old_view.GenLevel.Id if old_view.GenLevel else ElementId.InvalidElementId
    was_active = (uidoc.ActiveView.Id == old_view.Id)
    old_view_id = old_view.Id

    final_name = get_unique_view_name(
        doc,
        desired_name.strip() or old_view.Name,
        ignore_view_id=old_view_id if replace_old else None
    )

    t = Transaction(doc, "Cambia Livello Pianta")
    fail_opts = t.GetFailureHandlingOptions()
    fail_opts.SetFailuresPreprocessor(SmartFailureResolver())
    fail_opts.SetClearAfterRollback(True)
    t.SetFailureHandlingOptions(fail_opts)
    t.Start()

    if replace_old and old_view.Name == final_name:
        old_view.Name = get_unique_view_name(doc, old_view.Name + "_old_tmp")

    if old_view.ViewType == ViewType.AreaPlan:
        new_view = ViewPlan.CreateAreaPlan(doc, old_view.AreaScheme.Id, target_level.Id)
    else:
        new_view = ViewPlan.Create(doc, old_view.GetTypeId(), target_level.Id)

    new_view.ViewTemplateId = ElementId.InvalidElementId
    new_view.ApplyViewTemplateParameters(old_view)

    # Intervallo di visualizzazione (PlanViewRange)
    try:
        vr = old_view.GetViewRange()
        new_vr = new_view.GetViewRange()
        for plane in (
            PlanViewPlane.TopClipPlane,
            PlanViewPlane.CutPlane,
            PlanViewPlane.BottomClipPlane,
            PlanViewPlane.ViewDepthPlane,
        ):
            lid = vr.GetLevelId(plane)
            if lid == old_level_id:
                new_vr.SetLevelId(plane, target_level.Id)
            else:
                new_vr.SetLevelId(plane, lid)
            new_vr.SetOffset(plane, vr.GetOffset(plane))
        new_view.SetViewRange(new_vr)
    except Exception:
        pass

    # Sottostante (Underlay)
    try:
        ub = old_view.GetUnderlayBaseLevel()
        ut = old_view.GetUnderlayTopLevel()
        if ub != ElementId.InvalidElementId:
            new_view.SetUnderlayRange(ub, ut)
            new_view.SetUnderlayOrientation(old_view.GetUnderlayOrientation())
    except Exception:
        pass

    # Scope Box, Orientamento e Ritaglio
    copy_crop_and_scope(doc, old_view, new_view)

    # Modello di vista
    if old_view.ViewTemplateId != ElementId.InvalidElementId:
        new_view.ViewTemplateId = old_view.ViewTemplateId

    # Parametri scrivibili della vista (es. Titolo sulla tavola, organizzazione browser, fasi)
    skip_bip_vals = (
        int(BuiltInParameter.VIEW_NAME),
        int(BuiltInParameter.VIEW_TEMPLATE),
        int(BuiltInParameter.VIEW_TEMPLATE_FOR_SCHEDULE),
        int(BuiltInParameter.VIEW_FIXED_SKETCH_PLANE),
    )
    for p in old_view.Parameters:
        if not p.IsReadOnly and p.Definition:
            if eid_val(p.Id) in skip_bip_vals:
                continue
            np = new_view.get_Parameter(p.Definition)
            if np and not np.IsReadOnly:
                try:
                    st = p.StorageType
                    if st == StorageType.String and p.AsString() is not None:
                        np.Set(p.AsString())
                    elif st == StorageType.Integer:
                        np.Set(p.AsInteger())
                    elif st == StorageType.Double:
                        np.Set(p.AsDouble())
                    elif st == StorageType.ElementId:
                        np.Set(p.AsElementId())
                except Exception:
                    pass

    doc.Regenerate()

    # Elementi 2D e annotazioni
    copied_2d_count = 0
    if copy_2d:
        owned = list(FilteredElementCollector(doc).OwnedByView(old_view.Id))
        copyable_ids = List[ElementId]()
        for el in owned:
            cls_name = type(el).__name__
            if cls_name not in INTERNAL_SKIP_CLASSES and el.Name != "ExtentElem" and el.Category is not None:
                if eid_val(el.Category.Id) not in INTERNAL_SKIP_CATEGORIES:
                    copyable_ids.Add(el.Id)
        if copyable_ids.Count > 0:
            try:
                copied_ids = ElementTransformUtils.CopyElements(
                    old_view, copyable_ids, new_view, Transform.Identity, CopyPasteOptions()
                )
                copied_2d_count = len(copied_ids)
            except Exception:
                pass

    # Sovrascritture per singolo elemento ed elementi nascosti manualmente
    transfer_element_overrides(doc, old_view, new_view)
    if copy_hidden:
        transfer_hidden_elements(doc, old_view, new_view)

    # Sostituzione su Tavola (Viewport)
    swapped_sheets = []
    if replace_old:
        vps = [vp for vp in FilteredElementCollector(doc).OfClass(Viewport) if vp.ViewId == old_view.Id]
        for vp in vps:
            sheet = doc.GetElement(vp.SheetId)
            sheet_num = sheet.SheetNumber if sheet else "?"
            try:
                vp.ViewId = new_view.Id
                swapped_sheets.append(sheet_num)
            except Exception:
                try:
                    center = vp.GetBoxCenter()
                    vp_type_id = vp.GetTypeId()
                    rot = vp.Rotation
                    lbl_offset = vp.LabelOffset
                    lbl_len = vp.LabelLineLength
                    det_p = vp.get_Parameter(BuiltInParameter.VIEWPORT_DETAIL_NUMBER)
                    det_num = det_p.AsString() if det_p else None
                    doc.Delete(vp.Id)
                    new_vp = Viewport.Create(doc, sheet.Id, new_view.Id, center)
                    new_vp.ChangeTypeId(vp_type_id)
                    new_vp.Rotation = rot
                    new_vp.LabelOffset = lbl_offset
                    new_vp.LabelLineLength = lbl_len
                    if det_num:
                        ndp = new_vp.get_Parameter(BuiltInParameter.VIEWPORT_DETAIL_NUMBER)
                        if ndp and not ndp.IsReadOnly:
                            ndp.Set(det_num)
                    swapped_sheets.append(sheet_num)
                except Exception:
                    pass

    new_view.Name = final_name

    if replace_old and not was_active:
        try:
            doc.Delete(old_view_id)
        except Exception:
            pass

    t.Commit()

    # Attiva la nuova vista ed elimina la vecchia se era la vista attiva
    try:
        uidoc.ActiveView = new_view
    except Exception:
        pass

    if replace_old and was_active:
        t_del = Transaction(doc, "Elimina vista precedente")
        t_del.Start()
        try:
            doc.Delete(old_view_id)
            t_del.Commit()
        except Exception:
            t_del.RollBack()

        try:
            for uiv in uidoc.GetOpenUIViews():
                if uiv.ViewId == old_view_id:
                    uiv.Close()
        except Exception:
            pass

    return new_view, copied_2d_count, swapped_sheets


class ChangePlanLevelWindow(forms.WPFWindow):
    """Elenco dei livelli (quello attuale non si sceglie) e opzioni chiuse in "Opzioni"."""

    def __init__(self, xaml_file, doc, vista, opzioni_aperte=False):
        forms.WPFWindow.__init__(self, SF.xaml(xaml_file), literal_string=True)
        self.vista = vista
        self.esegui = False
        self.livello = None
        self._nome_auto = u""
        self._nome_toccato = False

        self.livelli = sorted(FilteredElementCollector(doc).OfClass(Level).ToElements(),
                              key=lambda l: l.Elevation)
        id_attuale = vista.GenLevel.Id if vista.GenLevel else None
        indice_attuale = None
        voci = []
        for i, lvl in enumerate(self.livelli):
            attuale = id_attuale is not None and lvl.Id == id_attuale
            if attuale:
                indice_attuale = i
            voci.append(EW.Voce(lvl, lvl.Name, u"attuale" if attuale else CL.quota_testo(lvl.Elevation),
                                abilitato=not attuale))
        self.lstLevels.ItemsSource = voci
        self.lblVista.Text = vista.Name

        MF.ripristina(self, _MEMORIA, _CONTROLLI)
        self.expOpzioni.IsExpanded = bool(opzioni_aperte)
        proposto = CL.livello_proposto([l.Elevation for l in self.livelli], indice_attuale)
        if proposto is not None:
            self.lstLevels.SelectedIndex = proposto

        self.lstLevels.SelectionChanged += lambda s, e: self.aggiorna()
        self.lstLevels.MouseDoubleClick += lambda s, e: self.on_apply(s, e)
        self.rbReplaceView.Checked += lambda s, e: self.aggiorna()
        self.rbDuplicateView.Checked += lambda s, e: self.aggiorna()
        self.txtNewViewName.TextChanged += self.on_nome_cambiato
        self.btnCancel.Click += lambda s, e: self.Close()
        self.btnApply.Click += self.on_apply
        self.aggiorna()

    def livello_scelto(self):
        voce = self.lstLevels.SelectedItem
        if voce is None or not voce.Abilitato:
            return None
        return voce.oggetto

    def aggiorna(self):
        lvl = self.livello_scelto()
        duplica = bool(self.rbDuplicateView.IsChecked)
        self.btnApply.Content = CL.testo_pulsante(lvl.Name if lvl else None, duplica)
        self.btnApply.IsEnabled = lvl is not None
        if lvl is not None and not self._nome_toccato:
            vecchio = self.vista.GenLevel.Name if self.vista.GenLevel else u""
            self._nome_auto = CL.nome_nuova_vista(self.vista.Name, vecchio, lvl.Name, duplica)
            self.txtNewViewName.Text = self._nome_auto

    def on_nome_cambiato(self, sender, args):
        if self.txtNewViewName.Text != self._nome_auto:
            self._nome_toccato = True

    def on_apply(self, sender, args):
        lvl = self.livello_scelto()
        if lvl is None:
            return
        MF.salva(self, _MEMORIA, _CONTROLLI)
        self.livello = lvl
        self.nome = self.txtNewViewName.Text.strip() or self.vista.Name
        self.duplica = bool(self.rbDuplicateView.IsChecked)
        self.copia_2d = bool(self.chkCopy2D.IsChecked)
        self.copia_nascosti = bool(self.chkCopyHidden.IsChecked)
        self.esegui = True
        self.Close()


def resolve_initial_plan_view(doc, uidoc):
    active = doc.ActiveView
    if active and not active.IsTemplate and active.ViewType in PLAN_VIEW_TYPES:
        return active
    sel_ids = uidoc.Selection.GetElementIds()
    for eid in sel_ids:
        el = doc.GetElement(eid)
        if isinstance(el, Viewport):
            v = doc.GetElement(el.ViewId)
            if v and v.ViewType in PLAN_VIEW_TYPES:
                return v
        elif isinstance(el, ViewPlan) and not el.IsTemplate and el.ViewType in PLAN_VIEW_TYPES:
            return el
    return None


def main():
    doc = revit.doc
    uidoc = revit.uidoc
    vista = resolve_initial_plan_view(doc, uidoc)
    if vista is None or vista.GenLevel is None:
        AVW.errore(u"Apri una pianta (o selezionala nel browser o in tavola) per cambiarne il livello")
        return

    win = ChangePlanLevelWindow(script.get_bundle_file('ui.xaml'), doc, vista, EXEC_PARAMS.config_mode)
    win.ShowDialog()
    if not win.esegui:
        return

    try:
        nuova, _n2d, tavole = change_plan_level(
            doc, uidoc, vista, win.livello, win.nome,
            replace_old=not win.duplica, copy_2d=win.copia_2d, copy_hidden=win.copia_nascosti)
    except Exception as ex:
        AVW.errore(u"Cambio di livello non riuscito: %s" % ex)
        return
    msg = (u"Pianta duplicata su %s" if win.duplica else u"Pianta spostata su %s") % win.livello.Name
    if tavole:
        msg += u" \u00b7 tavola %s" % u", ".join(tavole)
    AVW.mostra(msg)


if __name__ == '__main__':
    main()
