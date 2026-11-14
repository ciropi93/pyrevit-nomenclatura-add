# -*- coding: utf-8 -*-
"""Copia Ritaglio di Vista tra Viste (Crop Region / Crop Box)

Sincronizza le impostazioni di ritaglio da una vista sorgente ad altre viste selezionate:
- Estensione e limiti del riquadro di taglio (Crop Box BoundingBox)
- Sagomatura personalizzata / poligonale (Custom Crop Shape CurveLoop)
- Visibilità del contorno di ritaglio (Crop Region Visible)
- Ritaglio delle annotazioni (Annotation Crop) e relativi offset
- Gestione automatica e scollegamento opzionale del Riquadro di Definizione (Scope Box)
"""

import os
import sys
import clr

clr.AddReference('System')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

import System
from System.Windows.Media import BrushConverter
from System.Collections.ObjectModel import ObservableCollection
from System.ComponentModel import INotifyPropertyChanged, PropertyChangedEventArgs

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

from pyrevit import revit, DB, UI, forms, script

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
# WPF VIEW ITEM MODEL
# ==============================================================================

class ObservableObject(INotifyPropertyChanged):
    def __init__(self):
        self._property_changed_handlers = []

    def add_PropertyChanged(self, handler):
        self._property_changed_handlers.append(handler)

    def remove_PropertyChanged(self, handler):
        if handler in self._property_changed_handlers:
            self._property_changed_handlers.remove(handler)

    def OnPropertyChanged(self, prop_name):
        args = PropertyChangedEventArgs(prop_name)
        for handler in self._property_changed_handlers:
            handler(self, args)


class TargetViewItem(ObservableObject):
    def __init__(self, view, doc, is_compatible=True):
        super(TargetViewItem, self).__init__()
        self.view = view
        self.doc = doc
        self.ViewName = view.Name
        self.ViewType = view.ViewType
        self.ViewTypeName = VIEW_TYPE_NAMES.get(view.ViewType, str(view.ViewType))
        self.IsCompatible = is_compatible

        # Livello
        if hasattr(view, 'GenLevel') and view.GenLevel:
            self.LevelName = view.GenLevel.Name
        else:
            self.LevelName = u"-"

        # Scope Box
        scope_p = view.get_Parameter(BuiltInParameter.VIEWER_VOLUME_OF_INTEREST_CROP)
        self.HasScopeBox = (scope_p and scope_p.AsElementId() != ElementId.InvalidElementId)
        if self.HasScopeBox:
            scope_el = doc.GetElement(scope_p.AsElementId())
            self.ScopeBoxName = scope_el.Name if scope_el else u"Riquadro Assegnato"
        else:
            self.ScopeBoxName = u""

        # Stato ritaglio
        mgr = view.GetCropRegionShapeManager()
        if not view.CropBoxActive:
            self.StatusText = u"Disattivato"
            self.StatusBgColor = "#F1F5F9"  # slate 100
            self.StatusFgColor = "#64748B"  # slate 500
        elif mgr.CanHaveShape and mgr.ShapeSet:
            self.StatusText = u"Attivo [Sagomato]"
            self.StatusBgColor = "#FEF3C7"  # amber 100
            self.StatusFgColor = "#B45309"  # amber 700
        else:
            self.StatusText = u"Attivo [Rettangolare]"
            self.StatusBgColor = "#E0F2FE"  # sky 100
            self.StatusFgColor = "#0369A1"  # sky 700

        if self.HasScopeBox:
            self.StatusText += u" ⚠ Scope Box: " + self.ScopeBoxName

        self._is_selected = False

    @property
    def IsSelected(self):
        return self._is_selected

    @IsSelected.setter
    def IsSelected(self, val):
        if self._is_selected != val:
            self._is_selected = val
            self.OnPropertyChanged("IsSelected")


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
# FINESTRA PRINCIPALE WPF
# ==============================================================================

class CopyCropWindow(forms.WPFWindow):
    def __init__(self, xaml_file, doc, initial_source_view):
        forms.WPFWindow.__init__(self, xaml_file)
        self.doc = doc
        self.current_source_view = initial_source_view
        self.all_views = []
        self.filtered_target_items = ObservableCollection[TargetViewItem]()
        self.lstTargetViews.ItemsSource = self.filtered_target_items

        self.load_all_views()
        self.setup_source_combobox()
        self.setup_filters_combobox()
        self.refresh_ui_for_source_view()

        # Collega eventi UI
        self.cmbSourceView.SelectionChanged += self.on_source_view_changed
        self.txtSearch.TextChanged += self.on_filter_changed
        self.cmbViewTypeFilter.SelectionChanged += self.on_filter_changed

        self.btnSelectAll.Click += self.on_select_all
        self.btnDeselectAll.Click += self.on_deselect_all
        self.btnSelectSameType.Click += self.on_select_same_type
        self.btnSelectSameLevel.Click += self.on_select_same_level

        self.btnCancel.Click += self.on_cancel
        self.btnApply.Click += self.on_apply

    def load_all_views(self):
        collector = FilteredElementCollector(self.doc).OfClass(View).ToElements()
        self.all_views = [
            v for v in collector
            if not v.IsTemplate and v.ViewType in VALID_VIEW_TYPES
        ]
        self.all_views.sort(key=lambda x: (str(x.ViewType), x.Name))

    def setup_source_combobox(self):
        self.cmbSourceView.Items.Clear()
        selected_idx = 0
        for i, v in enumerate(self.all_views):
            type_label = VIEW_TYPE_NAMES.get(v.ViewType, str(v.ViewType))
            item_text = u"[{}] {}".format(type_label, v.Name)
            self.cmbSourceView.Items.Add(item_text)
            if v.Id == self.current_source_view.Id:
                selected_idx = i

        if self.cmbSourceView.Items.Count > 0:
            self.cmbSourceView.SelectedIndex = selected_idx

    def setup_filters_combobox(self):
        self.cmbViewTypeFilter.Items.Clear()
        self.cmbViewTypeFilter.Items.Add(u"Tutti i tipi compatibili")
        self.cmbViewTypeFilter.Items.Add(u"Tutte le viste del modello")
        for vt in VALID_VIEW_TYPES:
            name = VIEW_TYPE_NAMES.get(vt, str(vt))
            self.cmbViewTypeFilter.Items.Add(name)
        self.cmbViewTypeFilter.SelectedIndex = 0

    def refresh_ui_for_source_view(self):
        v = self.current_source_view
        if not v:
            return

        # Aggiorna badge sorgente
        mgr = v.GetCropRegionShapeManager()
        if not v.CropBoxActive:
            self.lblSourceCropStatus.Text = u"Ritaglio Disattivato"
            self.lblSourceCropStatus.Foreground = System.Windows.Media.BrushConverter().ConvertFromString("#DC2626")
            self.bdrSourceCropStatus.Background = System.Windows.Media.BrushConverter().ConvertFromString("#FEE2E2")
        elif mgr.CanHaveShape and mgr.ShapeSet:
            self.lblSourceCropStatus.Text = u"Ritaglio Attivo [Sagomato/Poligonale]"
            self.lblSourceCropStatus.Foreground = System.Windows.Media.BrushConverter().ConvertFromString("#B45309")
            self.bdrSourceCropStatus.Background = System.Windows.Media.BrushConverter().ConvertFromString("#FEF3C7")
        else:
            self.lblSourceCropStatus.Text = u"Ritaglio Attivo [Rettangolare]"
            self.lblSourceCropStatus.Foreground = System.Windows.Media.BrushConverter().ConvertFromString("#0369A1")
            self.bdrSourceCropStatus.Background = System.Windows.Media.BrushConverter().ConvertFromString("#E0F2FE")

        # Ritaglio annotazioni
        anno_p = v.get_Parameter(BuiltInParameter.VIEWER_ANNOTATION_CROP_ACTIVE)
        if anno_p and anno_p.AsInteger() == 1:
            self.lblSourceAnnoStatus.Text = u"Ritaglio Annotazioni: Attivo"
        else:
            self.lblSourceAnnoStatus.Text = u"Ritaglio Annotazioni: Disattivato"

        # Livello
        if hasattr(v, 'GenLevel') and v.GenLevel:
            self.lblSourceLevelStatus.Text = u"Livello: " + v.GenLevel.Name
        else:
            self.lblSourceLevelStatus.Text = u"Livello: -"

        # Ricostruisce elenco viste destinazione
        self.apply_target_filter()

    def apply_target_filter(self):
        query = self.txtSearch.Text.lower().strip() if self.txtSearch.Text else ""
        type_filter_idx = self.cmbViewTypeFilter.SelectedIndex

        self.filtered_target_items.Clear()

        for v in self.all_views:
            if v.Id == self.current_source_view.Id:
                continue

            is_compat = are_views_compatible(self.current_source_view, v)

            # Filtro compatibilità / tipo
            if type_filter_idx == 0:  # Tutti i compatibili
                if not is_compat:
                    continue
            elif type_filter_idx == 1:  # Tutte le viste del modello
                pass
            else:  # Uno specifico tipo selezionato
                filter_name = str(self.cmbViewTypeFilter.SelectedItem)
                v_name_type = VIEW_TYPE_NAMES.get(v.ViewType, str(v.ViewType))
                if filter_name != v_name_type:
                    continue

            # Filtro testo ricerca
            if query:
                level_str = v.GenLevel.Name.lower() if hasattr(v, 'GenLevel') and v.GenLevel else ""
                if query not in v.Name.lower() and query not in level_str:
                    continue

            item = TargetViewItem(v, self.doc, is_compatible=is_compat)
            item.add_PropertyChanged(self.on_item_property_changed)
            self.filtered_target_items.Add(item)

        self.update_selection_summary()

    def update_selection_summary(self):
        total = len(self.filtered_target_items)
        selected = sum(1 for it in self.filtered_target_items if it.IsSelected)
        self.lblSelectionSummary.Text = u"{} viste selezionate su {} disponibili".format(selected, total)

    def on_source_view_changed(self, sender, args):
        idx = self.cmbSourceView.SelectedIndex
        if 0 <= idx < len(self.all_views):
            self.current_source_view = self.all_views[idx]
            self.refresh_ui_for_source_view()

    def on_filter_changed(self, sender, args):
        self.apply_target_filter()

    def on_item_property_changed(self, sender, args):
        if args.PropertyName == "IsSelected":
            self.update_selection_summary()

    def on_select_all(self, sender, args):
        for item in self.filtered_target_items:
            item.IsSelected = True

    def on_deselect_all(self, sender, args):
        for item in self.filtered_target_items:
            item.IsSelected = False

    def on_select_same_type(self, sender, args):
        for item in self.filtered_target_items:
            item.IsSelected = (item.view.ViewType == self.current_source_view.ViewType)

    def on_select_same_level(self, sender, args):
        src_level = self.current_source_view.GenLevel if hasattr(self.current_source_view, 'GenLevel') else None
        if not src_level:
            forms.alert(u"La vista sorgente non ha un livello di riferimento.", title=u"CDV Tools")
            return
        for item in self.filtered_target_items:
            item_level = item.view.GenLevel if hasattr(item.view, 'GenLevel') else None
            item.IsSelected = (item_level and item_level.Id == src_level.Id)

    def on_cancel(self, sender, args):
        self.Close()

    def on_apply(self, sender, args):
        selected_items = [it for it in self.filtered_target_items if it.IsSelected]
        if not selected_items:
            forms.alert(u"Seleziona almeno una vista di destinazione.", title=u"CDV Tools")
            return

        copy_vis = bool(self.chkCopyVisibility.IsChecked)
        copy_anno = bool(self.chkCopyAnnotation.IsChecked)
        remove_scope = bool(self.chkRemoveScopeBox.IsChecked)

        tx_title = u"Copia Ritaglio di Vista"
        t = Transaction(self.doc, tx_title)
        opts = t.GetFailureHandlingOptions()
        opts.SetFailuresPreprocessor(WarningSwallower())
        t.SetFailureHandlingOptions(opts)

        success_count = 0
        errors = []

        t.Start()
        try:
            for it in selected_items:
                try:
                    copy_crop_to_view(
                        self.doc,
                        self.current_source_view,
                        it.view,
                        copy_visibility=copy_vis,
                        copy_annotation=copy_anno,
                        remove_scope_box=remove_scope
                    )
                    success_count += 1
                except Exception as ex:
                    errors.append(u"{}: {}".format(it.ViewName, ex))

            t.Commit()
        except Exception as ex:
            t.RollBack()
            forms.alert(u"Errore durante l'applicazione del ritaglio:\n{}".format(ex), title=u"CDV Tools")
            return

        self.Close()

        if success_count > 0:
            msg = u"Ritaglio copiato con successo su {} viste!".format(success_count) if success_count > 1 else u"Ritaglio copiato con successo su 1 vista!"
            if errors:
                forms.alert(msg + u"\n\nErrori su {} viste:\n{}".format(len(errors), u"\n".join(errors[:5])), title=u"CDV Tools")
            else:
                forms.toast(msg, title=u"CDV Tools")
        elif errors:
            forms.alert(u"Impossibile applicare il ritaglio:\n" + u"\n".join(errors[:5]), title=u"CDV Tools")


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    doc = revit.doc
    if not doc:
        forms.alert(u"Nessun documento attivo in Revit.", title=u"CDV Tools")
        return

    active_view = doc.ActiveView
    if not active_view or active_view.IsTemplate:
        forms.alert(u"La vista attiva corrente non è valida o è un modello di vista.", title=u"CDV Tools")
        return

    if active_view.ViewType not in VALID_VIEW_TYPES:
        forms.alert(
            u"La vista attiva corrente ({}) non supporta le regioni di taglio.".format(active_view.Name),
            title=u"CDV Tools"
        )
        return

    xaml_path = os.path.join(os.path.dirname(__file__), "ui.xaml")
    win = CopyCropWindow(xaml_path, doc, active_view)
    win.ShowDialog()


if __name__ == "__main__":
    main()
