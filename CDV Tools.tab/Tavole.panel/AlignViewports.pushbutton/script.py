# -*- coding: utf-8 -*-
"""Allinea Viste su Tavole (Align Viewports across Sheets)

Allinea la posizione di una vista posizionata in una tavola su altre tavole del progetto.
Supporta:
- Allineamento delle coordinate del modello (il fabbricato, i pilastri e le griglie cadono
  esattamente allo stesso millimetro sulla tavola anche con ritagli leggermente differenti).
- Allineamento del centro geometrico del riquadro vista (Box Center).
- Sincronizzazione della posizione del titolo della vista (Label Offset).
- Sincronizzazione della lunghezza della riga del titolo (Label Line Length).
- Sincronizzazione dello stile/tipo di Viewport (Famiglia e Tipo del titolo).
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
from System.Collections.ObjectModel import ObservableCollection
from System.ComponentModel import INotifyPropertyChanged, PropertyChangedEventArgs

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

from pyrevit import revit, DB, UI, forms, script
import stile_finestre as SF
import memoria_finestre as MF

# ultime scelte della finestra (vedi lib/memoria_finestre.py)
_MEMORIA = u"allinea_viste_tavole"
_CONTROLLI = [u"rbAlignModel", u"rbAlignBoxCenter", u"chkAlignTitle", u"chkAlignTitleLength", u"chkApplyType"]

import avviso as AV
import avviso_wpf as AVW

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
    ViewType.DraftingView: u"Vista di Disegno",
    ViewType.Legend: u"Legenda",
}


class WarningSwallower(IFailuresPreprocessor):
    """Elimina silenziosamente eventuali avvisi non bloccanti."""
    def PreprocessFailures(self, failuresAccessor):
        failures = failuresAccessor.GetFailureMessages()
        for f in failures:
            if f.GetSeverity() == FailureSeverity.Warning:
                failuresAccessor.DeleteWarning(f)
        return FailureProcessingResult.Continue


# ==============================================================================
# WPF MODEL
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


class TargetViewportItem(ObservableObject):
    def __init__(self, sheet, viewport, view):
        super(TargetViewportItem, self).__init__()
        self.sheet = sheet
        self.viewport = viewport
        self.view = view

        self.SheetDisplay = u"[{}] {}".format(sheet.SheetNumber, sheet.Name)
        self.ViewName = view.Name
        self.ViewType = view.ViewType
        self.ViewTypeName = VIEW_TYPE_NAMES.get(view.ViewType, str(view.ViewType))

        if hasattr(view, 'Scale') and view.Scale > 0:
            self.ScaleStr = u"1:{}".format(view.Scale)
        else:
            self.ScaleStr = u"-"

        center = viewport.GetBoxCenter()
        # In millimetri sul foglio (1 ft = 304.8 mm)
        self.PositionStr = u"X:{:.0f} Y:{:.0f} mm".format(center.X * 304.8, center.Y * 304.8)

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
# FINESTRA PRINCIPALE WPF
# ==============================================================================

class AlignViewportsWindow(forms.WPFWindow):
    def __init__(self, xaml_file, doc, initial_source_vp=None):
        forms.WPFWindow.__init__(self, SF.xaml(xaml_file), literal_string=True)
        self.doc = doc
        self.all_viewport_entries = []
        self.current_source_entry = None
        self.filtered_target_items = ObservableCollection[TargetViewportItem]()
        self.lstTargetViewports.ItemsSource = self.filtered_target_items

        self.load_all_viewports(initial_source_vp)
        self.setup_source_combobox()
        self.setup_filters_combobox()
        self.refresh_source_info()

        # Eventi
        self.cmbSourceViewport.SelectionChanged += self.on_source_vp_changed
        self.txtSearch.TextChanged += self.on_filter_changed
        self.cmbViewTypeFilter.SelectionChanged += self.on_filter_changed

        self.btnSelectAll.Click += self.on_select_all
        self.btnDeselectAll.Click += self.on_deselect_all
        self.btnSelectSameType.Click += self.on_select_same_type

        self.btnCancel.Click += self.on_cancel
        self.btnApply.Click += self.on_apply

    def load_all_viewports(self, initial_source_vp):
        sheets = FilteredElementCollector(self.doc).OfClass(ViewSheet).ToElements()
        self.all_viewport_entries = []

        found_initial = None
        for s in sheets:
            for vpid in s.GetAllViewports():
                vp = self.doc.GetElement(vpid)
                v = self.doc.GetElement(vp.ViewId)
                entry = (s, vp, v)
                self.all_viewport_entries.append(entry)
                if initial_source_vp and vp.Id == initial_source_vp.Id:
                    found_initial = entry

        self.all_viewport_entries.sort(key=lambda x: (x[0].SheetNumber, x[2].Name))

        if found_initial:
            self.current_source_entry = found_initial
        elif self.all_viewport_entries:
            self.current_source_entry = self.all_viewport_entries[0]

    def setup_source_combobox(self):
        self.cmbSourceViewport.Items.Clear()
        selected_idx = 0
        for i, (s, vp, v) in enumerate(self.all_viewport_entries):
            type_label = VIEW_TYPE_NAMES.get(v.ViewType, str(v.ViewType))
            item_text = u"[{}] {} -> {} ({})".format(s.SheetNumber, s.Name, v.Name, type_label)
            self.cmbSourceViewport.Items.Add(item_text)
            if self.current_source_entry and vp.Id == self.current_source_entry[1].Id:
                selected_idx = i

        if self.cmbSourceViewport.Items.Count > 0:
            self.cmbSourceViewport.SelectedIndex = selected_idx

    def setup_filters_combobox(self):
        self.cmbViewTypeFilter.Items.Clear()
        self.cmbViewTypeFilter.Items.Add(u"Tutti i tipi di vista")
        self.cmbViewTypeFilter.Items.Add(u"Stesso tipo della sorgente")
        types_set = set(e[2].ViewType for e in self.all_viewport_entries)
        for vt in types_set:
            name = VIEW_TYPE_NAMES.get(vt, str(vt))
            self.cmbViewTypeFilter.Items.Add(name)
        self.cmbViewTypeFilter.SelectedIndex = 0

    def refresh_source_info(self):
        if not self.current_source_entry:
            return

        s, vp, v = self.current_source_entry
        self.lblSourceSheet.Text = u"Tavola: [{}] {}".format(s.SheetNumber, s.Name)
        self.lblSourceViewType.Text = u"Tipo: " + VIEW_TYPE_NAMES.get(v.ViewType, str(v.ViewType))

        if hasattr(v, 'Scale') and v.Scale > 0:
            self.lblSourceScale.Text = u"Scala: 1:{}".format(v.Scale)
        else:
            self.lblSourceScale.Text = u"Scala: -"

        center = vp.GetBoxCenter()
        self.lblSourcePos.Text = u"Centro: X:{:.0f} Y:{:.0f} mm".format(center.X * 304.8, center.Y * 304.8)

        self.apply_target_filter()

    def apply_target_filter(self):
        if not self.current_source_entry:
            return

        src_s, src_vp, src_v = self.current_source_entry
        query = self.txtSearch.Text.lower().strip() if self.txtSearch.Text else ""
        type_filter_idx = self.cmbViewTypeFilter.SelectedIndex

        self.filtered_target_items.Clear()

        for s, vp, v in self.all_viewport_entries:
            if vp.Id == src_vp.Id:
                continue

            # Filtro tipo
            if type_filter_idx == 1:  # Stesso tipo della sorgente
                if v.ViewType != src_v.ViewType:
                    continue
            elif type_filter_idx > 1:  # Uno specifico tipo
                filter_name = str(self.cmbViewTypeFilter.SelectedItem)
                v_name_type = VIEW_TYPE_NAMES.get(v.ViewType, str(v.ViewType))
                if filter_name != v_name_type:
                    continue

            # Filtro ricerca
            if query:
                search_blob = u"{} {} {}".format(s.SheetNumber, s.Name, v.Name).lower()
                if query not in search_blob:
                    continue

            item = TargetViewportItem(s, vp, v)
            item.add_PropertyChanged(self.on_item_property_changed)
            self.filtered_target_items.Add(item)

        self.update_selection_summary()

    def update_selection_summary(self):
        total = len(self.filtered_target_items)
        selected = sum(1 for it in self.filtered_target_items if it.IsSelected)
        self.lblSelectionSummary.Text = u"{} viste selezionate su {} disponibili".format(selected, total)

    def on_source_vp_changed(self, sender, args):
        idx = self.cmbSourceViewport.SelectedIndex
        if 0 <= idx < len(self.all_viewport_entries):
            self.current_source_entry = self.all_viewport_entries[idx]
            self.refresh_source_info()

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
        src_v = self.current_source_entry[2]
        for item in self.filtered_target_items:
            item.IsSelected = (item.view.ViewType == src_v.ViewType)

    def on_cancel(self, sender, args):
        self.Close()

    def on_apply(self, sender, args):
        MF.salva(self, _MEMORIA, _CONTROLLI)
        selected_items = [it for it in self.filtered_target_items if it.IsSelected]
        if not selected_items:
            forms.alert(u"Seleziona almeno una vista di destinazione da allineare.", title=u"CDV Tools")
            return

        src_s, src_vp, src_v = self.current_source_entry

        align_model = bool(self.rbAlignModel.IsChecked)
        align_title = bool(self.chkAlignTitle.IsChecked)
        align_title_len = bool(self.chkAlignTitleLength.IsChecked)
        apply_type = bool(self.chkApplyType.IsChecked)

        tx_title = u"Allinea Viste su Tavole"
        t = Transaction(self.doc, tx_title)
        opts = t.GetFailureHandlingOptions()
        opts.SetFailuresPreprocessor(WarningSwallower())
        t.SetFailureHandlingOptions(opts)

        success_count = 0
        errors = []

        t.Start()
        try:
            for it in selected_items:
                tgt_vp = it.viewport
                try:
                    # 1. Allineamento posizione vista sul foglio
                    if align_model and src_vp.HasViewportTransforms() and tgt_vp.HasViewportTransforms():
                        # Calcolo differenza di proiezione coordinate modello
                        t_src = src_vp.GetProjectionToSheetTransform()
                        t_tgt = tgt_vp.GetProjectionToSheetTransform()
                        delta = XYZ(t_src.Origin.X - t_tgt.Origin.X, t_src.Origin.Y - t_tgt.Origin.Y, 0.0)
                        new_center = tgt_vp.GetBoxCenter() + delta
                        tgt_vp.SetBoxCenter(new_center)
                    else:
                        # Centro geometrico del riquadro (Box Center)
                        src_center = src_vp.GetBoxCenter()
                        tgt_center = tgt_vp.GetBoxCenter()
                        new_center = XYZ(src_center.X, src_center.Y, tgt_center.Z)
                        tgt_vp.SetBoxCenter(new_center)

                    self.doc.Regenerate()

                    # 2. Posizione del titolo della vista (Label Offset)
                    if align_title and hasattr(src_vp, 'LabelOffset') and hasattr(tgt_vp, 'LabelOffset'):
                        try:
                            tgt_vp.LabelOffset = src_vp.LabelOffset
                        except Exception:
                            pass

                    # 3. Lunghezza riga del titolo (Label Line Length)
                    if align_title_len and hasattr(src_vp, 'LabelLineLength') and hasattr(tgt_vp, 'LabelLineLength'):
                        try:
                            tgt_vp.LabelLineLength = src_vp.LabelLineLength
                        except Exception:
                            pass

                    # 4. Tipo di Viewport (stile/famiglia titolo)
                    if apply_type:
                        try:
                            tgt_vp.ChangeTypeId(src_vp.GetTypeId())
                        except Exception:
                            pass

                    success_count += 1
                except Exception as ex:
                    errors.append(u"[{}] {}: {}".format(it.sheet.SheetNumber, it.ViewName, ex))

            t.Commit()
        except Exception as ex:
            t.RollBack()
            forms.alert(u"Errore durante l'allineamento delle viste:\n{}".format(ex), title=u"CDV Tools")
            return

        self.Close()

        if success_count > 0:
            msg = u"Allineate con successo {} viste!".format(success_count) if success_count > 1 else u"Allineata 1 vista con successo!"
            if errors:
                AVW.attenzione(AV.con_errori(msg, errors))
            else:
                AVW.mostra(msg)
        elif errors:
            AVW.errore(AV.con_errori(u"Impossibile allineare le viste selezionate", errors))


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    doc = revit.doc
    uidoc = revit.uidoc

    if not doc or not uidoc:
        AVW.errore(u"Nessun documento attivo in Revit.")
        return

    # 1. Verifica se ci sono tavole nel progetto
    sheet_collector = FilteredElementCollector(doc).OfClass(ViewSheet).ToElements()
    if not sheet_collector or len(sheet_collector) == 0:
        AVW.errore(u"Il progetto corrente non contiene alcuna tavola.")
        return

    # 2. Rileva eventuale Viewport pre-selezionato
    initial_source_vp = None
    sel_ids = uidoc.Selection.GetElementIds()
    for eid in sel_ids:
        el = doc.GetElement(eid)
        if isinstance(el, Viewport):
            initial_source_vp = el
            break

    # Se non c'è viewport selezionato ma la vista attiva è una tavola, prendi il primo viewport della tavola
    if not initial_source_vp and isinstance(doc.ActiveView, ViewSheet):
        active_sheet = doc.ActiveView
        sheet_vps = active_sheet.GetAllViewports()
        if sheet_vps and sheet_vps.Count > 0:
            initial_source_vp = doc.GetElement(sheet_vps[0])

    xaml_path = os.path.join(os.path.dirname(__file__), "ui.xaml")
    win = AlignViewportsWindow(xaml_path, doc, initial_source_vp)
    MF.ripristina(win, _MEMORIA, _CONTROLLI)
    win.ShowDialog()


if __name__ == "__main__":
    main()
