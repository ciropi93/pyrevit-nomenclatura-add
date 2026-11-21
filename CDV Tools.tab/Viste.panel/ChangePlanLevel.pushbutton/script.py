# -*- coding: utf-8 -*-
"""Cambia il livello associato di una vista di pianta trasferendo grafica, modello di vista, intervallo di visualizzazione, ritaglio, riquadro di definizione, annotazioni 2D e posizionamento su tavola."""

import os
import clr

clr.AddReference('System')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

import System
from System.Collections.Generic import List
from System.Windows.Media import BrushConverter

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

from pyrevit import revit, forms, script
import stile_finestre as SF
import memoria_finestre as MF

# ultime scelte della finestra (vedi lib/memoria_finestre.py)
_MEMORIA = u"cambia_livello"
_CONTROLLI = [u"rbReplaceView", u"rbDuplicateView", u"chkCopy2D", u"chkCopyHidden"]


PLAN_VIEW_TYPES = [
    ViewType.FloorPlan,
    ViewType.CeilingPlan,
    ViewType.EngineeringPlan,
    ViewType.AreaPlan,
]

VIEW_TYPE_LABELS = {
    ViewType.FloorPlan: u"Pianta di Pavimento",
    ViewType.CeilingPlan: u"Pianta dei Controsoffitti",
    ViewType.EngineeringPlan: u"Pianta Strutturale",
    ViewType.AreaPlan: u"Pianta delle Aree",
}

INTERNAL_SKIP_CATEGORIES = (-2000055, -2009609, -2000279)
INTERNAL_SKIP_CLASSES = ("SketchPlane", "SunAndShadowSettings")


def eid_val(eid):
    if eid is None:
        return -1
    return eid.Value if hasattr(eid, "Value") else eid.IntegerValue


def feet_to_m_str(feet_val):
    meters = feet_val * 0.3048
    sign = "+" if meters > 0.0001 else ""
    return u"{}{:.2f} m".format(sign, meters)


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
    def __init__(self, xaml_file, doc, uidoc, initial_view):
        forms.WPFWindow.__init__(self, SF.xaml(xaml_file), literal_string=True)
        self.doc = doc
        self.uidoc = uidoc
        self.current_view = initial_view
        self.plan_views = []
        self.levels = []

        self.load_data()
        self.setup_views_combo()
        self.setup_levels_list()
        self.refresh_source_info()

        self.cmbSourceView.SelectionChanged += self.on_source_view_changed
        self.lstLevels.SelectionChanged += self.on_level_changed
        self.rbReplaceView.Checked += self.on_mode_changed
        self.rbDuplicateView.Checked += self.on_mode_changed
        self.btnSuggestName.Click += self.on_suggest_name
        self.btnCancel.Click += self.on_cancel
        self.btnApply.Click += self.on_apply

    def load_data(self):
        all_views = FilteredElementCollector(self.doc).OfClass(ViewPlan).ToElements()
        self.plan_views = [
            v for v in all_views
            if not v.IsTemplate and v.ViewType in PLAN_VIEW_TYPES and v.GenLevel is not None
        ]
        self.plan_views.sort(key=lambda v: (v.GenLevel.Elevation, v.Name))

        all_levels = FilteredElementCollector(self.doc).OfClass(Level).ToElements()
        self.levels = sorted(all_levels, key=lambda l: l.Elevation)

    def setup_views_combo(self):
        self.cmbSourceView.Items.Clear()
        sel_idx = 0
        for idx, v in enumerate(self.plan_views):
            lvl_name = v.GenLevel.Name if v.GenLevel else "-"
            vt_label = VIEW_TYPE_LABELS.get(v.ViewType, str(v.ViewType))
            self.cmbSourceView.Items.Add(u"{}  [Livello: {} | {}]".format(v.Name, lvl_name, vt_label))
            if self.current_view and v.Id == self.current_view.Id:
                sel_idx = idx
        if self.cmbSourceView.Items.Count > 0:
            self.cmbSourceView.SelectedIndex = sel_idx
            self.current_view = self.plan_views[sel_idx]

    def setup_levels_list(self):
        self.lstLevels.Items.Clear()
        cur_lvl_id = self.current_view.GenLevel.Id if (self.current_view and self.current_view.GenLevel) else None
        first_other_idx = 0
        for idx, lvl in enumerate(self.levels):
            elev_str = feet_to_m_str(lvl.Elevation)
            is_cur = (cur_lvl_id and lvl.Id == cur_lvl_id)
            tag = u"  (LIVELLO ATTUALE)" if is_cur else u""
            self.lstLevels.Items.Add(u"{}   [Quota: {}]{}".format(lvl.Name, elev_str, tag))
            if not is_cur and first_other_idx == 0:
                first_other_idx = idx
        if self.lstLevels.Items.Count > 0:
            self.lstLevels.SelectedIndex = first_other_idx

    def refresh_source_info(self):
        v = self.current_view
        if not v:
            return
        lvl = v.GenLevel
        if lvl:
            self.lblCurrentLevel.Text = u"Livello attuale: {} ({})".format(lvl.Name, feet_to_m_str(lvl.Elevation))
        else:
            self.lblCurrentLevel.Text = u"Livello attuale: -"

        self.lblViewType.Text = u"Tipo: {}".format(VIEW_TYPE_LABELS.get(v.ViewType, str(v.ViewType)))

        vps = [vp for vp in FilteredElementCollector(self.doc).OfClass(Viewport) if vp.ViewId == v.Id]
        if vps:
            sheet = self.doc.GetElement(vps[0].SheetId)
            s_num = sheet.SheetNumber if sheet else "?"
            self.lblSheetStatus.Text = u"Impaginata su tavola: {}".format(s_num)
            self.lblSheetStatus.Foreground = BrushConverter().ConvertFromString("#15803D")
            self.bdrSheetStatus.Background = BrushConverter().ConvertFromString("#DCFCE7")
        else:
            self.lblSheetStatus.Text = u"Non impaginata su tavola"
            self.lblSheetStatus.Foreground = BrushConverter().ConvertFromString("#5B6B78")
            self.bdrSheetStatus.Background = BrushConverter().ConvertFromString("#EEF2F5")

        self.update_name_preview()

    def get_selected_level(self):
        idx = self.lstLevels.SelectedIndex
        if 0 <= idx < len(self.levels):
            return self.levels[idx]
        return None

    def compute_suggested_name(self, force_level_in_name=False):
        v = self.current_view
        tgt_lvl = self.get_selected_level()
        if not v:
            return ""
        base_name = v.Name
        cur_lvl_name = v.GenLevel.Name if v.GenLevel else ""
        tgt_lvl_name = tgt_lvl.Name if tgt_lvl else ""

        is_replace = bool(self.rbReplaceView.IsChecked)
        if is_replace and not force_level_in_name:
            return base_name

        if cur_lvl_name and tgt_lvl_name and cur_lvl_name in base_name:
            return base_name.replace(cur_lvl_name, tgt_lvl_name)
        if tgt_lvl_name:
            return u"{} - {}".format(base_name, tgt_lvl_name)
        return base_name

    def update_name_preview(self):
        self.txtNewViewName.Text = self.compute_suggested_name(force_level_in_name=False)

    def on_source_view_changed(self, sender, args):
        idx = self.cmbSourceView.SelectedIndex
        if 0 <= idx < len(self.plan_views):
            self.current_view = self.plan_views[idx]
            self.setup_levels_list()
            self.refresh_source_info()

    def on_level_changed(self, sender, args):
        if bool(self.rbDuplicateView.IsChecked):
            self.update_name_preview()

    def on_mode_changed(self, sender, args):
        self.update_name_preview()

    def on_suggest_name(self, sender, args):
        self.txtNewViewName.Text = self.compute_suggested_name(force_level_in_name=True)

    def on_cancel(self, sender, args):
        self.Close()

    def on_apply(self, sender, args):
        MF.salva(self, _MEMORIA, _CONTROLLI)
        if not self.current_view:
            forms.alert("Seleziona una vista di pianta valida.")
            return
        tgt_lvl = self.get_selected_level()
        if not tgt_lvl:
            forms.alert("Seleziona un livello di destinazione.")
            return
        if self.current_view.GenLevel and tgt_lvl.Id == self.current_view.GenLevel.Id and bool(self.rbReplaceView.IsChecked):
            forms.alert("La vista è già associata al livello '{}'. Scegli un livello diverso.".format(tgt_lvl.Name))
            return

        desired_name = self.txtNewViewName.Text.strip() or self.current_view.Name
        replace_old = bool(self.rbReplaceView.IsChecked)
        copy_2d = bool(self.chkCopy2D.IsChecked)
        copy_hidden = bool(self.chkCopyHidden.IsChecked)

        self.Close()

        try:
            new_view, copied_2d, swapped_sheets = change_plan_level(
                self.doc,
                self.uidoc,
                self.current_view,
                tgt_lvl,
                desired_name,
                replace_old=replace_old,
                copy_2d=copy_2d,
                copy_hidden=copy_hidden,
            )
            msg = u"Vista '{}' associata con successo al livello '{}'.".format(new_view.Name, tgt_lvl.Name)
            if copy_2d:
                msg += u"\n• Elementi 2D/annotazioni trasferiti: {}".format(copied_2d)
            if swapped_sheets:
                msg += u"\n• Aggiornata su tavola: {}".format(", ".join(swapped_sheets))
            forms.alert(msg, title="Cambia Livello Pianta")
        except Exception as ex:
            forms.alert("Errore durante il cambio di livello:\n{}".format(str(ex)), title="Errore")


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

    plans = [
        v for v in FilteredElementCollector(doc).OfClass(ViewPlan).ToElements()
        if not v.IsTemplate and v.ViewType in PLAN_VIEW_TYPES and v.GenLevel is not None
    ]
    if not plans:
        forms.alert("Nessuna vista di pianta trovata nel progetto.", exitscript=True)

    levels = FilteredElementCollector(doc).OfClass(Level).ToElements()
    if len(levels) < 1:
        forms.alert("Nessun livello trovato nel progetto.", exitscript=True)

    initial_view = resolve_initial_plan_view(doc, uidoc) or plans[0]
    xaml_path = script.get_bundle_file('ui.xaml')
    win = ChangePlanLevelWindow(xaml_path, doc, uidoc, initial_view)
    MF.ripristina(win, _MEMORIA, _CONTROLLI)
    win.ShowDialog()


if __name__ == '__main__':
    main()
