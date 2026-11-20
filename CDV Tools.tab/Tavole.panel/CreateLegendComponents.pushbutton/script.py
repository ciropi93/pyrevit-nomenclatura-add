# -*- coding: utf-8 -*-
"""Inserisci Componenti in Legenda (Create Legend Components)

Dato un insieme di elementi selezionati nel modello (porte, finestre, muri, arredi,
attrezzature, ecc.):
1. Estrae i rispettivi Tipi/Simboli unici.
2. Chiede in quale vista Legenda del progetto inserirli (con possibilità di duplicare/creare una legenda).
3. Genera e posiziona automaticamente i Componenti Legenda in modo ordinato (in colonna o in riga).
4. Imposta la vista del componente (Pianta / Prospetto Anteriore / Prospetto Posteriore).
5. Aggiunge facoltativamente una nota di testo descrittiva con il nome della famiglia e del tipo.
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
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, DB, UI, forms, script
import memoria_finestre as MF

# ultime scelte della finestra (vedi lib/memoria_finestre.py)
_MEMORIA = u"componenti_legenda"
_CONTROLLI = [u"rbVertical", u"rbHorizontal", u"txtSpacing", u"cmbViewDirection", u"chkAddTextNote", u"cmbTextType", u"cmbTextFormat"]

import avviso as AV
import avviso_wpf as AVW

# ==============================================================================
# UTILITY
# ==============================================================================

class WarningSwallower(IFailuresPreprocessor):
    """Elimina silenziosamente avvisi non critici."""
    def PreprocessFailures(self, failuresAccessor):
        failures = failuresAccessor.GetFailureMessages()
        for f in failures:
            if f.GetSeverity() == FailureSeverity.Warning:
                failuresAccessor.DeleteWarning(f)
        return FailureProcessingResult.Continue


def parse_spacing(text):
    """Converte un testo con unità (es. 1500 mm, 150 cm, 1.5 m) in piedi interni Revit."""
    try:
        t = text.lower().replace(" ", "").strip()
        if t.endswith("mm"):
            return float(t[:-2]) / 304.8
        elif t.endswith("cm"):
            return float(t[:-2]) / 30.48
        elif t.endswith("m"):
            return float(t[:-1]) / 0.3048
        else:
            val = float(t)
            return val / 304.8 if val > 20 else val
    except Exception:
        return 1500.0 / 304.8


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


class ComponentTypeItem(ObservableObject):
    def __init__(self, type_element, category_name, family_name, type_name, instance_count=1):
        super(ComponentTypeItem, self).__init__()
        self.type_element = type_element
        self.type_id = type_element.Id
        self.CategoryName = category_name
        self.FamilyName = family_name
        self.TypeName = type_name
        self.InstanceCount = instance_count
        self.InstanceCountStr = u"x{} istanze".format(instance_count) if instance_count > 1 else u"x1 istanza"
        self._is_selected = True

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

class LegendComponentsWindow(forms.WPFWindow):
    def __init__(self, xaml_file, doc, uidoc, type_items):
        forms.WPFWindow.__init__(self, xaml_file)
        self.doc = doc
        self.uidoc = uidoc
        self.all_type_items = type_items
        self.legends_list = []
        self.text_types_list = []

        self.observable_types = ObservableCollection[ComponentTypeItem]()
        for it in type_items:
            it.add_PropertyChanged(self.on_item_property_changed)
            self.observable_types.Add(it)
        self.lstComponentTypes.ItemsSource = self.observable_types

        self.setup_legends_combobox()
        self.setup_options_comboboxes()
        self.update_legend_info()
        self.update_selection_summary()

        # Eventi
        self.cmbTargetLegend.SelectionChanged += self.on_legend_changed
        self.btnDuplicateLegend.Click += self.on_duplicate_legend
        self.btnSelectAll.Click += self.on_select_all
        self.btnDeselectAll.Click += self.on_deselect_all
        self.btnCancel.Click += self.on_cancel
        self.btnApply.Click += self.on_apply

    def setup_legends_combobox(self):
        legends = [
            v for v in FilteredElementCollector(self.doc).OfClass(View).ToElements()
            if v.ViewType == ViewType.Legend and not v.IsTemplate
        ]
        legends.sort(key=lambda x: x.Name)
        self.legends_list = legends

        self.cmbTargetLegend.Items.Clear()
        for lg in legends:
            self.cmbTargetLegend.Items.Add(lg.Name)

        if self.cmbTargetLegend.Items.Count > 0:
            # Se la vista attiva è una legenda, preselezionala
            active_view = self.doc.ActiveView
            sel_idx = 0
            if active_view and active_view.ViewType == ViewType.Legend:
                for i, lg in enumerate(legends):
                    if lg.Id == active_view.Id:
                        sel_idx = i
                        break
            self.cmbTargetLegend.SelectedIndex = sel_idx

    def setup_options_comboboxes(self):
        # Viste del componente
        self.cmbViewDirection.Items.Clear()
        self.cmbViewDirection.Items.Add(u"Pianta (Floor Plan)")
        self.cmbViewDirection.Items.Add(u"Prospetto Anteriore")
        self.cmbViewDirection.Items.Add(u"Prospetto Posteriore")
        self.cmbViewDirection.Items.Add(u"Come da Campione")
        self.cmbViewDirection.SelectedIndex = 0

        # Tipi di testo
        tt_collector = FilteredElementCollector(self.doc).OfClass(TextNoteType).ToElements()
        self.text_types_list = list(tt_collector)
        self.cmbTextType.Items.Clear()
        for tt in self.text_types_list:
            p_name = tt.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            tt_name = p_name.AsString() if p_name else tt.Name
            self.cmbTextType.Items.Add(tt_name)
        if self.cmbTextType.Items.Count > 0:
            self.cmbTextType.SelectedIndex = 0

        # Formato testo
        self.cmbTextFormat.Items.Clear()
        self.cmbTextFormat.Items.Add(u"Nome del Tipo")
        self.cmbTextFormat.Items.Add(u"Famiglia - Tipo")
        self.cmbTextFormat.Items.Add(u"Categoria: Tipo")
        self.cmbTextFormat.SelectedIndex = 0

    def find_sample_legend_component(self, target_legend):
        """Cerca un componente legenda campione nella legenda o nel progetto."""
        # 1. Cerca nella legenda di destinazione
        for el in FilteredElementCollector(self.doc, target_legend.Id).ToElements():
            if el.get_Parameter(BuiltInParameter.LEGEND_COMPONENT):
                return el, target_legend

        # 2. Cerca in qualunque altra legenda del progetto
        for lg in self.legends_list:
            if lg.Id != target_legend.Id:
                for el in FilteredElementCollector(self.doc, lg.Id).ToElements():
                    if el.get_Parameter(BuiltInParameter.LEGEND_COMPONENT):
                        return el, lg

        return None, None

    def update_legend_info(self):
        idx = self.cmbTargetLegend.SelectedIndex
        if idx < 0 or idx >= len(self.legends_list):
            return

        lg = self.legends_list[idx]
        self.lblLegendScale.Text = u"Scala: 1:{}".format(lg.Scale)

        elem_count = FilteredElementCollector(self.doc, lg.Id).GetElementCount()
        self.lblLegendElementsCount.Text = u"Elementi presenti: {}".format(elem_count)

        sample, sample_view = self.find_sample_legend_component(lg)
        if sample:
            if sample_view.Id == lg.Id:
                self.lblTemplateStatus.Text = u"✓ Componente campione trovato nella legenda"
                self.lblTemplateStatus.Foreground = System.Windows.Media.BrushConverter().ConvertFromString("#065F46")
                self.bdrTemplateStatus.Background = System.Windows.Media.BrushConverter().ConvertFromString("#D1FAE5")
            else:
                self.lblTemplateStatus.Text = u"✓ Campione trovato in '{}' (verrà importato)".format(sample_view.Name)
                self.lblTemplateStatus.Foreground = System.Windows.Media.BrushConverter().ConvertFromString("#0284C7")
                self.bdrTemplateStatus.Background = System.Windows.Media.BrushConverter().ConvertFromString("#E0F2FE")
        else:
            self.lblTemplateStatus.Text = u"⚠ Nessun componente legenda campione trovato nel file"
            self.lblTemplateStatus.Foreground = System.Windows.Media.BrushConverter().ConvertFromString("#B45309")
            self.bdrTemplateStatus.Background = System.Windows.Media.BrushConverter().ConvertFromString("#FEF3C7")

    def update_selection_summary(self):
        total = len(self.observable_types)
        selected = sum(1 for it in self.observable_types if it.IsSelected)
        self.lblSelectionSummary.Text = u"{} tipi selezionati su {}".format(selected, total)
        self.lblTypesCount.Text = u"({} tipi unici)".format(total)

    def on_legend_changed(self, sender, args):
        self.update_legend_info()

    def on_duplicate_legend(self, sender, args):
        idx = self.cmbTargetLegend.SelectedIndex
        if idx < 0 or idx >= len(self.legends_list):
            return

        src_lg = self.legends_list[idx]
        with revit.Transaction("Duplica Legenda"):
            new_id = src_lg.Duplicate(ViewDuplicateOption.Duplicate)
            new_lg = self.doc.GetElement(new_id)
            # Rinomina
            base_name = src_lg.Name + " - Copia"
            test_name = base_name
            counter = 1
            while True:
                existing = [l for l in self.legends_list if l.Name.lower() == test_name.lower()]
                if not existing:
                    break
                counter += 1
                test_name = u"{} ({})".format(base_name, counter)
            new_lg.Name = test_name

        self.setup_legends_combobox()
        # Seleziona la nuova legenda
        for i, lg in enumerate(self.legends_list):
            if lg.Id == new_id:
                self.cmbTargetLegend.SelectedIndex = i
                break
        AVW.mostra(u"Legenda duplicata con successo!")

    def on_item_property_changed(self, sender, args):
        if args.PropertyName == "IsSelected":
            self.update_selection_summary()

    def on_select_all(self, sender, args):
        for item in self.observable_types:
            item.IsSelected = True

    def on_deselect_all(self, sender, args):
        for item in self.observable_types:
            item.IsSelected = False

    def on_cancel(self, sender, args):
        self.Close()

    def on_apply(self, sender, args):
        MF.salva(self, _MEMORIA, _CONTROLLI)
        selected_types = [it for it in self.observable_types if it.IsSelected]
        if not selected_types:
            forms.alert(u"Seleziona almeno un tipo di elemento da inserire.", title=u"CDV Tools")
            return

        idx = self.cmbTargetLegend.SelectedIndex
        if idx < 0 or idx >= len(self.legends_list):
            forms.alert(u"Nessuna legenda valida selezionata.", title=u"CDV Tools")
            return
        target_legend = self.legends_list[idx]

        # Verifica presenza di un componente legenda campione
        sample_comp, sample_view = self.find_sample_legend_component(target_legend)

        if not sample_comp:
            # Mostra avviso guidato: come creare il primo componente campione
            msg = (
                u"Nel progetto non è ancora presente alcun Componente Legenda campione inserito in una legenda.\n\n"
                u"Autodesk Revit richiede la presenza di almeno un componente campione nel file per poter duplicare "
                u"e assegnare automaticamente i tipi scelti.\n\n"
                u"Vuoi aprire ora la legenda '{}' e avviare il comando nativo di Revit per posizionare il primo componente?"
            ).format(target_legend.Name)
            if forms.alert(msg, title=u"CDV Tools - Componente Campione Richiesto", yes=True, no=True):
                self.Close()
                self.uidoc.ActiveView = target_legend
                try:
                    cmd_id = RevitCommandId.LookupPostableCommandId(PostableCommand.LegendComponent)
                    if cmd_id and self.uidoc.CanPostCommand(cmd_id):
                        self.uidoc.PostRequestForTool(cmd_id)
                except Exception:
                    pass
            return

        # Parametri di posizionamento
        spacing_feet = parse_spacing(self.txtSpacing.Text)
        is_vertical = bool(self.rbVertical.IsChecked)

        # Mappatura vista
        view_dir_idx = self.cmbViewDirection.SelectedIndex
        view_dir_val = None
        if view_dir_idx == 0:    # Pianta
            view_dir_val = -8
        elif view_dir_idx == 1:  # Prospetto anteriore
            view_dir_val = -7
        elif view_dir_idx == 2:  # Prospetto posteriore
            view_dir_val = -6

        # Opzioni testo
        add_text = bool(self.chkAddTextNote.IsChecked)
        text_type = None
        if add_text and self.text_types_list and self.cmbTextType.SelectedIndex >= 0:
            text_type = self.text_types_list[self.cmbTextType.SelectedIndex]
        text_format_idx = self.cmbTextFormat.SelectedIndex

        # Calcolo punto iniziale nella legenda
        # Determina il BoundingBox degli elementi esistenti per non sovrapporsi
        base_x = 0.0
        base_y = 0.0
        existing_elements = FilteredElementCollector(self.doc, target_legend.Id).ToElements()
        if existing_elements:
            max_x = -999999.0
            min_y = 999999.0
            has_geom = False
            for el in existing_elements:
                bbox = el.get_BoundingBox(target_legend)
                if bbox:
                    has_geom = True
                    if bbox.Max.X > max_x:
                        max_x = bbox.Max.X
                    if bbox.Min.Y < min_y:
                        min_y = bbox.Min.Y

            if has_geom:
                if is_vertical:
                    base_y = min_y - spacing_feet
                else:
                    base_x = max_x + spacing_feet

        # Esecuzione transazione
        tx_title = u"Inserisci Componenti in Legenda"
        t = Transaction(self.doc, tx_title)
        opts = t.GetFailureHandlingOptions()
        opts.SetFailuresPreprocessor(WarningSwallower())
        t.SetFailureHandlingOptions(opts)

        success_count = 0
        errors = []

        t.Start()
        try:
            # Se il campione è in un'altra legenda, copialo prima nella legenda di destinazione
            active_sample_comp = sample_comp
            if sample_view.Id != target_legend.Id:
                copy_opts = CopyPasteOptions()
                new_ids = ElementTransformUtils.CopyElements(
                    sample_view,
                    System.Array[ElementId]([sample_comp.Id]),
                    target_legend,
                    Transform.Identity,
                    copy_opts
                )
                active_sample_comp = self.doc.GetElement(list(new_ids)[0])

            # Posiziona ciascun tipo selezionato
            for i, it in enumerate(selected_types):
                try:
                    if is_vertical:
                        offset = XYZ(0, -i * spacing_feet, 0)
                        pos = XYZ(base_x, base_y - (i * spacing_feet), 0)
                    else:
                        offset = XYZ(i * spacing_feet, 0, 0)
                        pos = XYZ(base_x + (i * spacing_feet), base_y, 0)

                    # Duplica il componente
                    copy_ids = ElementTransformUtils.CopyElement(self.doc, active_sample_comp.Id, offset)
                    new_comp = self.doc.GetElement(copy_ids[0])

                    # Imposta il tipo
                    p_type = new_comp.get_Parameter(BuiltInParameter.LEGEND_COMPONENT)
                    if p_type and not p_type.IsReadOnly:
                        p_type.Set(it.type_id)

                    # Imposta l'orientamento di vista se richiesto
                    if view_dir_val is not None:
                        p_view = new_comp.get_Parameter(BuiltInParameter.LEGEND_COMPONENT_VIEW)
                        if p_view and not p_view.IsReadOnly:
                            try:
                                p_view.Set(view_dir_val)
                            except Exception:
                                pass

                    # Aggiungi nota di testo descrittiva
                    if add_text and text_type:
                        if text_format_idx == 0:
                            label_str = it.TypeName
                        elif text_format_idx == 1:
                            label_str = u"{} - {}".format(it.FamilyName, it.TypeName)
                        else:
                            label_str = u"{}: {}".format(it.CategoryName, it.TypeName)

                        # Offset testo: a destra del componente
                        text_pos = pos + XYZ(spacing_feet * 0.4, 0, 0)
                        TextNote.Create(self.doc, target_legend.Id, text_pos, label_str, text_type.Id)

                    success_count += 1
                except Exception as ex:
                    errors.append(u"{}: {}".format(it.TypeName, ex))

            t.Commit()
        except Exception as ex:
            t.RollBack()
            forms.alert(u"Errore durante l'inserimento dei componenti in legenda:\n{}".format(ex), title=u"CDV Tools")
            return

        self.Close()

        # Attiva la legenda per mostrare subito il risultato
        try:
            self.uidoc.ActiveView = target_legend
        except Exception:
            pass

        if success_count > 0:
            msg = u"Inseriti con successo {} componenti nella legenda '{}'!".format(success_count, target_legend.Name)
            if errors:
                AVW.attenzione(AV.con_errori(msg, errors))
            else:
                AVW.mostra(msg)
        elif errors:
            AVW.errore(AV.con_errori(u"Impossibile inserire i componenti selezionati", errors))


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    doc = revit.doc
    uidoc = revit.uidoc

    if not doc or not uidoc:
        AVW.errore(u"Nessun documento attivo in Revit.")
        return

    # 1. Recupera gli elementi selezionati
    sel_ids = uidoc.Selection.GetElementIds()
    selected_elements = [doc.GetElement(eid) for eid in sel_ids if doc.GetElement(eid)]

    # Se non c'è pre-selezione, chiedi all'utente di selezionare gli elementi
    if not selected_elements:
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element,
                "Seleziona gli elementi del modello da inserire in legenda (Esc per annullare)"
            )
            selected_elements = [doc.GetElement(r.ElementId) for r in refs if doc.GetElement(r.ElementId)]
        except OperationCanceledException:
            return
        except Exception as ex:
            forms.alert(u"Errore durante la selezione: {}".format(ex), title=u"CDV Tools")
            return

    if not selected_elements:
        return

    # 2. Estrai i Tipi unici dagli elementi selezionati
    types_map = {}  # type_id -> (type_el, cat_name, fam_name, type_name, count)

    for el in selected_elements:
        type_id = el.GetTypeId()
        if type_id == ElementId.InvalidElementId:
            continue

        if type_id in types_map:
            t_el, c_name, f_name, t_name, count = types_map[type_id]
            types_map[type_id] = (t_el, c_name, f_name, t_name, count + 1)
        else:
            type_el = doc.GetElement(type_id)
            if not type_el:
                continue

            cat_name = el.Category.Name if el.Category else u"Altro"

            # Nome Famiglia
            if hasattr(type_el, 'FamilyName') and type_el.FamilyName:
                fam_name = type_el.FamilyName
            else:
                p_fam = type_el.get_Parameter(BuiltInParameter.ALL_MODEL_FAMILY_NAME)
                fam_name = p_fam.AsString() if p_fam and p_fam.AsString() else getattr(type_el, 'Name', u"Famiglia")

            # Nome Tipo
            p_tname = type_el.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            if p_tname and p_tname.AsString():
                type_name = p_tname.AsString()
            else:
                type_name = getattr(type_el, 'Name', u"Tipo")

            types_map[type_id] = (type_el, cat_name, fam_name, type_name, 1)

    if not types_map:
        AVW.errore(u"Nessun tipo valido o componente ricavabile dagli elementi selezionati.")
        return

    type_items = []
    for type_id, (t_el, c_name, f_name, t_name, count) in types_map.items():
        type_items.append(ComponentTypeItem(t_el, c_name, f_name, t_name, count))

    type_items.sort(key=lambda x: (x.CategoryName, x.FamilyName, x.TypeName))

    xaml_path = os.path.join(os.path.dirname(__file__), "ui.xaml")
    win = LegendComponentsWindow(xaml_path, doc, uidoc, type_items)
    MF.ripristina(win, _MEMORIA, _CONTROLLI)
    win.ShowDialog()


if __name__ == "__main__":
    main()
