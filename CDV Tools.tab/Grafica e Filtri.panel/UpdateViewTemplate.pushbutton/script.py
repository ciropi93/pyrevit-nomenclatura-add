# -*- coding: utf-8 -*-
"""Aggiorna Modello di Vista da Vista (Update View Template from View)

Consente di aggiornare le impostazioni grafiche e i filtri di un Modello di Vista esistente
(o di crearne uno nuovo) a partire dalle impostazioni di visualizzazione della vista corrente.

Flusso operativo ideale:
1. Sgancia il modello di vista dalla vista per fare prove e revisioni grafiche (es. tramite copia grafica o filtri).
2. Quando il risultato nella vista è soddisfacente, avvia questo comando.
3. Seleziona il modello di vista da aggiornare: tutte le sue impostazioni verranno sincronizzate con la vista.
4. Facoltativamente, riaggancia subito la vista corrente al modello di vista aggiornato!
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
from System.Windows import Visibility

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *

from pyrevit import revit, DB, UI, forms, script

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
    ViewType.Schedule: u"Abaco / Quantità",
}

VALID_GRAPHICAL_VIEW_TYPES = [
    ViewType.FloorPlan,
    ViewType.CeilingPlan,
    ViewType.EngineeringPlan,
    ViewType.AreaPlan,
    ViewType.Section,
    ViewType.Elevation,
    ViewType.Detail,
    ViewType.ThreeD,
    ViewType.DraftingView,
]


class WarningSwallower(IFailuresPreprocessor):
    """Elimina silenziosamente avvisi non critici durante l'aggiornamento."""
    def PreprocessFailures(self, failuresAccessor):
        failures = failuresAccessor.GetFailureMessages()
        for f in failures:
            if f.GetSeverity() == FailureSeverity.Warning:
                failuresAccessor.DeleteWarning(f)
        return FailureProcessingResult.Continue


def count_category_overrides(doc, view):
    """Conta quante categorie hanno sovrascritture grafiche esplicite nella vista."""
    count = 0
    for cat in doc.Settings.Categories:
        if cat:
            ogs = view.GetCategoryOverrides(cat.Id)
            if ogs and (ogs.ProjectionLineColor.IsValid or ogs.CutLineColor.IsValid or
                        ogs.Transparency > 0 or ogs.Halftone or
                        ogs.SurfaceForegroundPatternId != ElementId.InvalidElementId or
                        ogs.CutForegroundPatternId != ElementId.InvalidElementId):
                count += 1
            if view.CanCategoryBeHidden(cat.Id) and view.GetCategoryHidden(cat.Id):
                count += 1
    return count


# ==============================================================================
# FINESTRA PRINCIPALE WPF
# ==============================================================================

class UpdateViewTemplateWindow(forms.WPFWindow):
    def __init__(self, xaml_file, doc, initial_view):
        forms.WPFWindow.__init__(self, xaml_file)
        self.doc = doc
        self.current_source_view = initial_view
        self.all_views = []
        self.all_templates = []
        self.filtered_templates = []
        self.template_usage_map = {}

        self.load_data()
        self.setup_source_combobox()
        self.setup_type_filter_combobox()
        self.refresh_source_info()

        # Eventi UI
        self.cmbSourceView.SelectionChanged += self.on_source_view_changed
        self.rbUpdateExisting.Checked += self.on_mode_changed
        self.rbCreateNew.Checked += self.on_mode_changed

        self.txtSearchTemplate.TextChanged += self.on_filter_changed
        self.cmbTypeFilter.SelectionChanged += self.on_filter_changed
        self.cmbTargetTemplate.SelectionChanged += self.on_target_template_changed

        self.btnCancel.Click += self.on_cancel
        self.btnApply.Click += self.on_apply

    def load_data(self):
        # Tutte le viste grafiche (non template)
        view_collector = FilteredElementCollector(self.doc).OfClass(View).ToElements()
        self.all_views = [
            v for v in view_collector
            if not v.IsTemplate and v.ViewType in VALID_GRAPHICAL_VIEW_TYPES
        ]
        self.all_views.sort(key=lambda x: (str(x.ViewType), x.Name))

        # Tutti i modelli di vista
        self.all_templates = [
            v for v in view_collector
            if v.IsTemplate
        ]
        self.all_templates.sort(key=lambda x: x.Name)

        # Mappa di utilizzo dei modelli di vista nel progetto
        self.template_usage_map = {}
        for v in self.all_views:
            if v.ViewTemplateId != ElementId.InvalidElementId:
                tid = v.ViewTemplateId.Value
                self.template_usage_map[tid] = self.template_usage_map.get(tid, 0) + 1

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

    def setup_type_filter_combobox(self):
        self.cmbTypeFilter.Items.Clear()
        self.cmbTypeFilter.Items.Add(u"Tipi compatibili con la vista")
        self.cmbTypeFilter.Items.Add(u"Tutti i modelli di vista")
        types_set = set(t.ViewType for t in self.all_templates)
        for vt in types_set:
            self.cmbTypeFilter.Items.Add(VIEW_TYPE_NAMES.get(vt, str(vt)))
        self.cmbTypeFilter.SelectedIndex = 0

    def refresh_source_info(self):
        v = self.current_source_view
        if not v:
            return

        # Badge Tipo
        type_str = VIEW_TYPE_NAMES.get(v.ViewType, str(v.ViewType))
        self.lblSourceType.Text = u"Tipo: " + type_str

        # Badge Modello Assegnato
        if v.ViewTemplateId != ElementId.InvalidElementId:
            tpl = self.doc.GetElement(v.ViewTemplateId)
            self.lblSourceTemplate.Text = u"Modello: " + (tpl.Name if tpl else u"Sconosciuto")
            self.lblSourceTemplate.Foreground = System.Windows.Media.BrushConverter().ConvertFromString("#065F46")
            self.bdrSourceTemplate.Background = System.Windows.Media.BrushConverter().ConvertFromString("#D1FAE5")
        else:
            self.lblSourceTemplate.Text = u"Modello: Nessuno (Sganciato per prove)"
            self.lblSourceTemplate.Foreground = System.Windows.Media.BrushConverter().ConvertFromString("#B45309")
            self.bdrSourceTemplate.Background = System.Windows.Media.BrushConverter().ConvertFromString("#FEF3C7")

        # Conteggio sovrascritture categorie
        cat_overrides = count_category_overrides(self.doc, v)
        if cat_overrides > 0:
            self.lblSourceOverrides.Text = u"Sovrascritture: {} categorie modificate".format(cat_overrides)
        else:
            self.lblSourceOverrides.Text = u"Sovrascritture: Categorie standard"

        # Conteggio filtri
        filters_count = v.GetFilters().Count
        self.lblSourceFilters.Text = u"Filtri applicati: {}".format(filters_count)

        # Suggerimento nome nuovo template
        self.txtNewTemplateName.Text = v.Name + u" - Modello"

        # Ricostruisce elenco modelli compatibili
        self.apply_template_filter()

    def apply_template_filter(self):
        v = self.current_source_view
        if not v:
            return

        query = self.txtSearchTemplate.Text.lower().strip() if self.txtSearchTemplate.Text else ""
        type_filter_idx = self.cmbTypeFilter.SelectedIndex

        self.filtered_templates = []
        for t in self.all_templates:
            # Compatibilità
            if type_filter_idx == 0:  # Compatibili
                if not v.IsValidViewTemplate(t.Id) and t.ViewType != v.ViewType:
                    continue
            elif type_filter_idx == 1:  # Tutti
                pass
            else:  # Specifico tipo
                filter_name = str(self.cmbTypeFilter.SelectedItem)
                t_name_type = VIEW_TYPE_NAMES.get(t.ViewType, str(t.ViewType))
                if filter_name != t_name_type:
                    continue

            # Filtro testo
            if query and query not in t.Name.lower():
                continue

            self.filtered_templates.Add(t)

        self.cmbTargetTemplate.Items.Clear()
        selected_idx = 0
        for i, t in enumerate(self.filtered_templates):
            usage = self.template_usage_map.get(t.Id.Value, 0)
            item_text = u"{} (usato in {} viste)".format(t.Name, usage) if usage > 0 else t.Name
            self.cmbTargetTemplate.Items.Add(item_text)

            # Se la vista ha un modello assegnato che corrisponde a questo, preselezionalo
            if v.ViewTemplateId != ElementId.InvalidElementId and t.Id == v.ViewTemplateId:
                selected_idx = i

        if self.cmbTargetTemplate.Items.Count > 0:
            self.cmbTargetTemplate.SelectedIndex = selected_idx
        else:
            self.update_usage_label(None)

    def update_usage_label(self, template):
        if not template:
            self.lblTemplateUsage.Text = u"Nessun modello di vista selezionato."
            self.lblTemplateWarning.Text = u""
            return

        usage = self.template_usage_map.get(template.Id.Value, 0)
        if usage == 0:
            self.lblTemplateUsage.Text = u"Il modello '{}' non è attualmente assegnato ad alcuna vista.".format(template.Name)
            self.lblTemplateWarning.Text = u"L'aggiornamento modificherà le impostazioni salvate del modello."
        elif usage == 1:
            self.lblTemplateUsage.Text = u"Il modello '{}' è assegnato a 1 vista nel progetto.".format(template.Name)
            self.lblTemplateWarning.Text = u"Quella vista erediterà all'istante le nuove impostazioni grafiche."
        else:
            self.lblTemplateUsage.Text = u"Attenzione: il modello '{}' è attualmente assegnato a {} viste nel progetto.".format(template.Name, usage)
            self.lblTemplateWarning.Text = u"Tutte le {} viste collegate verranno aggiornate all'istante con le nuove impostazioni!".format(usage)

    def on_source_view_changed(self, sender, args):
        idx = self.cmbSourceView.SelectedIndex
        if 0 <= idx < len(self.all_views):
            self.current_source_view = self.all_views[idx]
            self.refresh_source_info()

    def on_mode_changed(self, sender, args):
        if self.rbUpdateExisting.IsChecked:
            self.pnlUpdateExisting.Visibility = Visibility.Visible
            self.pnlCreateNew.Visibility = Visibility.Collapsed
            self.on_target_template_changed(None, None)
        else:
            self.pnlUpdateExisting.Visibility = Visibility.Collapsed
            self.pnlCreateNew.Visibility = Visibility.Visible
            self.lblTemplateUsage.Text = u"Verrà creato un nuovo Modello di Vista basato su questa vista."
            self.lblTemplateWarning.Text = u"Nessun'altra vista esistente verrà modificata."

    def on_filter_changed(self, sender, args):
        self.apply_template_filter()

    def on_target_template_changed(self, sender, args):
        idx = self.cmbTargetTemplate.SelectedIndex
        if 0 <= idx < len(self.filtered_templates):
            self.update_usage_label(self.filtered_templates[idx])
        else:
            self.update_usage_label(None)

    def on_cancel(self, sender, args):
        self.Close()

    def on_apply(self, sender, args):
        v = self.current_source_view
        is_create_new = bool(self.rbCreateNew.IsChecked)
        reassign = bool(self.chkReassign.IsChecked)

        tx_title = u"Aggiorna Modello di Vista"
        t = Transaction(self.doc, tx_title)
        opts = t.GetFailureHandlingOptions()
        opts.SetFailuresPreprocessor(WarningSwallower())
        t.SetFailureHandlingOptions(opts)

        t.Start()
        try:
            if is_create_new:
                # Creazione nuovo modello
                new_name = self.txtNewTemplateName.Text.strip()
                if not new_name:
                    forms.alert(u"Inserisci un nome valido per il nuovo modello di vista.", title=u"CDV Tools")
                    t.RollBack()
                    return

                new_tpl = v.CreateViewTemplate()
                new_tpl.Name = new_name
                template_result = new_tpl
                target_name = new_name
            else:
                # Aggiornamento modello esistente
                idx = self.cmbTargetTemplate.SelectedIndex
                if idx < 0 or idx >= len(self.filtered_templates):
                    forms.alert(u"Seleziona un modello di vista valido da aggiornare.", title=u"CDV Tools")
                    t.RollBack()
                    return

                target_tpl = self.filtered_templates[idx]
                target_tpl.ApplyViewTemplateParameters(v)
                template_result = target_tpl
                target_name = target_tpl.Name

            # Riaggancia la vista al modello se richiesto
            if reassign and template_result:
                v.ViewTemplateId = template_result.Id

            t.Commit()
        except Exception as ex:
            t.RollBack()
            forms.alert(u"Errore durante l'aggiornamento del modello di vista:\n{}".format(ex), title=u"CDV Tools")
            return

        self.Close()

        msg = u"Modello di vista '{}' aggiornato con successo!".format(target_name)
        if reassign:
            msg += u"\n(Riassegnato alla vista '{}')".format(v.Name)
        AVW.mostra(msg)


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    doc = revit.doc
    if not doc:
        AVW.errore(u"Nessun documento attivo in Revit.")
        return

    active_view = doc.ActiveView
    initial_view = active_view

    # Se la vista attiva è una tavola o un abaco, cerca una vista grafica valida
    if not active_view or active_view.IsTemplate or active_view.ViewType not in VALID_GRAPHICAL_VIEW_TYPES:
        views = [
            v for v in FilteredElementCollector(doc).OfClass(View).ToElements()
            if not v.IsTemplate and v.ViewType in VALID_GRAPHICAL_VIEW_TYPES
        ]
        if not views:
            AVW.errore(u"Nessuna vista grafica valida trovata nel progetto.")
            return
        initial_view = views[0]

    xaml_path = os.path.join(os.path.dirname(__file__), "ui.xaml")
    win = UpdateViewTemplateWindow(xaml_path, doc, initial_view)
    win.ShowDialog()


if __name__ == "__main__":
    main()
