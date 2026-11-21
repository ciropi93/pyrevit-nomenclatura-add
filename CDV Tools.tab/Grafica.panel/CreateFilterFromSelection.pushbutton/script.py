# -*- coding: utf-8 -*-
"""Crea Filtro di Vista da Selezione

Analizza gli elementi selezionati nel progetto, individua i parametri comuni
(sia di tipo che di istanza), suggerisce le regole di filtraggio piu pertinenti
e permette di configurare e creare direttamente il Filtro di Vista in Revit.
"""

import os
import sys
import clr

clr.AddReference('System')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List
from System.ComponentModel import INotifyPropertyChanged, PropertyChangedEventArgs

from pyrevit import revit, DB, UI, forms, script
import stile_finestre as SF
import memoria_finestre as MF

# ultime scelte della finestra (vedi lib/memoria_finestre.py)
_MEMORIA = u"crea_filtro"
_CONTROLLI = [u"rbAnd", u"rbOr", u"chkAddToActiveView", u"chkApplyColor", u"cmbColor", u"chkSolidFill", u"chkHalftone", u"chkVisibility"]
from Autodesk.Revit.Exceptions import OperationCanceledException

# ==============================================================================
# UTILITY FUNCTIONS
# ==============================================================================

def get_id_val(elem_id):
    """Restituisce il valore intero dell'ElementId in modo compatibile (Revit 2019-2026+)."""
    if elem_id is None:
        return None
    if hasattr(elem_id, 'Value'):
        return elem_id.Value
    elif hasattr(elem_id, 'IntegerValue'):
        return elem_id.IntegerValue
    try:
        return int(elem_id)
    except Exception:
        return None


def find_element_parameter(elem, param_id):
    """Trova il parametro su un elemento (istanza o tipo)."""
    if not elem:
        return None
    pid_val = get_id_val(param_id)
    if pid_val is not None and pid_val < 0:
        try:
            p = elem.get_Parameter(DB.BuiltInParameter(pid_val))
            if p:
                return p
        except Exception:
            pass
    for p in elem.Parameters:
        if get_id_val(p.Id) == pid_val:
            return p

    type_id = elem.GetTypeId() if hasattr(elem, "GetTypeId") else None
    if type_id and type_id != DB.ElementId.InvalidElementId:
        elem_type = elem.Document.GetElement(type_id)
        if elem_type:
            if pid_val is not None and pid_val < 0:
                try:
                    p = elem_type.get_Parameter(DB.BuiltInParameter(pid_val))
                    if p:
                        return p
                except Exception:
                    pass
            for p in elem_type.Parameters:
                if get_id_val(p.Id) == pid_val:
                    return p
    return None


def get_param_raw_and_display_value(elem, param_id):
    """Restituisce (valore_raw, valore_stringa_display) per un parametro di un elemento."""
    p = find_element_parameter(elem, param_id)
    if not p or not p.HasValue:
        return None, None

    st = p.StorageType
    if st == DB.StorageType.String:
        val = p.AsString()
        return val, val
    elif st == DB.StorageType.ElementId:
        eid = p.AsElementId()
        if eid and eid != DB.ElementId.InvalidElementId:
            target = elem.Document.GetElement(eid)
            name = target.Name if target else str(get_id_val(eid))
            return eid, name
        return None, None
    elif st == DB.StorageType.Integer:
        ival = p.AsInteger()
        sval = p.AsValueString() or str(ival)
        return ival, sval
    elif st == DB.StorageType.Double:
        dval = p.AsDouble()
        sval = p.AsValueString() or str(round(dval, 4))
        return dval, sval
    return None, None


# Palette di colori predefiniti
COLOR_PALETTE = {
    "Rosso": (239, 68, 68),
    "Verde": (34, 197, 94),
    "Blu": (59, 130, 246),
    "Arancione": (249, 115, 22),
    "Giallo": (234, 179, 8),
    "Viola": (168, 85, 247),
    "Ciano": (6, 182, 212),
    "Magenta": (236, 72, 153),
    "Grigio Scuro": (100, 116, 139)
}


# ==============================================================================
# WPF VIEW MODELS
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


class CategoryItem(ObservableObject):
    def __init__(self, cat, count, on_toggle_callback):
        super(CategoryItem, self).__init__()
        self.category = cat
        self.id = cat.Id
        self.count = count
        self.DisplayName = u"{} ({} elem.)".format(cat.Name, count)
        self._is_included = True
        self.on_toggle_callback = on_toggle_callback

    @property
    def IsIncluded(self):
        return self._is_included

    @IsIncluded.setter
    def IsIncluded(self, val):
        if self._is_included != val:
            self._is_included = val
            self.OnPropertyChanged("IsIncluded")
            if self.on_toggle_callback:
                self.on_toggle_callback()


class ParameterRuleItem(ObservableObject):
    def __init__(self, param_id, param_name, is_type, is_identical, raw_values, display_values, on_change_callback):
        super(ParameterRuleItem, self).__init__()
        self.param_id = param_id
        self.ParamName = param_name
        self.IsType = is_type
        self.ScopeText = u"Parametro di Tipo" if is_type else u"Parametro di Istanza"
        self.IsIdentical = is_identical
        self.RawValues = raw_values
        self.DisplayValues = display_values
        self.on_change_callback = on_change_callback

        if is_identical:
            self.MatchText = u"✓ Identico (100%)"
            self.MatchBgColor = "#ECFDF5"  # green
            self.MatchFgColor = "#065F46"
            self.RuleValue = display_values[0] if display_values else u""
        else:
            self.MatchText = u"≠ Multiplo ({} val.)".format(len(display_values))
            self.MatchBgColor = "#FEF3C7"  # amber
            self.MatchFgColor = "#92400E"
            self.RuleValue = u", ".join(display_values[:5])

        self.AvailableOperators = [
            u"uguale a",
            u"non uguale a",
            u"contiene",
            u"inizia con",
            u"finisce con",
            u"è maggiore di",
            u"è minore di"
        ]
        self._selected_operator = self.AvailableOperators[0]
        self._is_selected = False

    @property
    def IsSelected(self):
        return self._is_selected

    @IsSelected.setter
    def IsSelected(self, val):
        if self._is_selected != val:
            self._is_selected = val
            self.OnPropertyChanged("IsSelected")
            if self.on_change_callback:
                self.on_change_callback()

    @property
    def SelectedOperator(self):
        return self._selected_operator

    @SelectedOperator.setter
    def SelectedOperator(self, val):
        if self._selected_operator != val:
            self._selected_operator = val
            self.OnPropertyChanged("SelectedOperator")
            if self.on_change_callback:
                self.on_change_callback()


# ==============================================================================
# WPF MAIN WINDOW
# ==============================================================================

class FilterCreatorWindow(forms.WPFWindow):
    def __init__(self, xaml_file, doc, active_view, selected_elements):
        forms.WPFWindow.__init__(self, SF.xaml(xaml_file), literal_string=True)
        self.doc = doc
        self.active_view = active_view
        self.elements = selected_elements
        self.all_param_items = []
        self.category_items = []

        self.setup_categories()
        self.setup_parameters()
        self.setup_view_options()
        self.update_rules_count()
        self.regenerate_filter_name()

        # Event Handlers
        self.txtSearchParam.TextChanged += self.on_search_changed
        self.btnRegenName.Click += lambda s, e: self.regenerate_filter_name()
        self.btnCreateFilter.Click += self.on_create_filter
        self.btnCancel.Click += lambda s, e: self.Close()
        self.chkAddToActiveView.Checked += self.on_view_option_toggle
        self.chkAddToActiveView.Unchecked += self.on_view_option_toggle

    def setup_categories(self):
        cat_counts = {}
        for el in self.elements:
            cat = el.Category
            if cat:
                cid = get_id_val(cat.Id)
                if cid not in cat_counts:
                    cat_counts[cid] = [cat, 0]
                cat_counts[cid][1] += 1

        self.category_items = []
        for cid, (cat, count) in cat_counts.items():
            item = CategoryItem(cat, count, self.on_category_toggled)
            self.category_items.append(item)

        self.icCategories.ItemsSource = ObservableCollection[object](self.category_items)
        self.lblSelectionSummary.Text = u"{} elementi selezionati in {} categorie".format(len(self.elements), len(self.category_items))

    def on_category_toggled(self):
        self.setup_parameters()
        self.regenerate_filter_name()

    def setup_parameters(self):
        included_cat_ids = List[DB.ElementId]()
        included_cat_id_set = set()
        for ci in self.category_items:
            if ci.IsIncluded:
                included_cat_ids.Add(ci.id)
                included_cat_id_set.add(get_id_val(ci.id))

        if not included_cat_ids:
            self.lvParameters.ItemsSource = ObservableCollection[object]([])
            return

        # Filtra gli elementi che appartengono alle categorie incluse
        active_elements = [el for el in self.elements if el.Category and get_id_val(el.Category.Id) in included_cat_id_set]
        if not active_elements:
            active_elements = self.elements

        try:
            filterable_ids = DB.ParameterFilterUtilities.GetFilterableParametersInCommon(self.doc, included_cat_ids)
        except Exception:
            filterable_ids = []

        param_items = []
        for pid in filterable_ids:
            raw_vals = []
            disp_vals = []
            val_set = set()
            is_type = False

            for el in active_elements:
                p = find_element_parameter(el, pid)
                if p:
                    # Verifica se è di tipo
                    type_id = el.GetTypeId() if hasattr(el, "GetTypeId") else None
                    if type_id and type_id != DB.ElementId.InvalidElementId:
                        el_type = self.doc.GetElement(type_id)
                        if el_type and el_type.get_Parameter(p.Definition) if hasattr(p, "Definition") and p.Definition else False:
                            is_type = True

                raw_v, disp_v = get_param_raw_and_display_value(el, pid)
                if disp_v is not None and disp_v.strip() != "":
                    raw_vals.append(raw_v)
                    disp_vals.append(disp_v.strip())
                    val_set.add(disp_v.strip())

            # Se tutti gli elementi possiedono un valore valido per questo parametro
            if len(disp_vals) == len(active_elements) and len(val_set) > 0:
                is_identical = len(val_set) == 1
                pid_val = get_id_val(pid)

                # Nome del parametro
                pname = None
                if pid_val < 0:
                    try:
                        pname = DB.LabelUtils.GetLabelFor(DB.BuiltInParameter(pid_val))
                    except Exception:
                        pass
                if not pname:
                    sample_p = find_element_parameter(active_elements[0], pid)
                    pname = sample_p.Definition.Name if (sample_p and sample_p.Definition) else str(pid_val)

                # Priorità parametri più comuni
                item = ParameterRuleItem(
                    param_id=pid,
                    param_name=pname,
                    is_type=is_type,
                    is_identical=is_identical,
                    raw_values=raw_vals,
                    display_values=list(val_set),
                    on_change_callback=self.on_rule_param_changed
                )
                param_items.append(item)

        # Ordina per priorità: Identici prima, poi per nome
        # Priorità extra a parametri architettonici chiave: Tipo, Livello, Commenti, Contrassegno
        def priority_score(item):
            name_low = item.ParamName.lower()
            score = 0
            if item.IsIdentical:
                score += 100
            if "tipo" in name_low or "type" in name_low:
                score += 50
            elif "livello" in name_low or "level" in name_low:
                score += 40
            elif "comment" in name_low:
                score += 35
            elif "contrassegno" in name_low or "mark" in name_low:
                score += 30
            elif "funzione" in name_low or "fase" in name_low:
                score += 25
            return -score

        param_items.sort(key=lambda x: (priority_score(x), x.ParamName))

        # Pre-seleziona il primo parametro identico più rilevante se presente
        if param_items:
            param_items[0].IsSelected = True

        self.all_param_items = param_items
        self.lvParameters.ItemsSource = ObservableCollection[object](param_items)
        self.update_rules_count()

    def on_rule_param_changed(self):
        self.update_rules_count()
        self.regenerate_filter_name()

    def update_rules_count(self):
        selected = [p for p in self.all_param_items if p.IsSelected]
        self.lblRulesCount.Text = u"{} regole selezionate per il filtro".format(len(selected))

    def on_search_changed(self, sender, args):
        query = self.txtSearchParam.Text.strip().lower() if self.txtSearchParam.Text else ""
        if not query:
            self.lvParameters.ItemsSource = ObservableCollection[object](self.all_param_items)
        else:
            filtered = [p for p in self.all_param_items if query in p.ParamName.lower() or query in p.RuleValue.lower()]
            self.lvParameters.ItemsSource = ObservableCollection[object](filtered)

    def setup_view_options(self):
        self.cmbColor.ItemsSource = list(COLOR_PALETTE.keys())
        self.cmbColor.SelectedIndex = 0

    def on_view_option_toggle(self, sender, args):
        is_active = bool(self.chkAddToActiveView.IsChecked)
        self.chkApplyColor.IsEnabled = is_active
        self.cmbColor.IsEnabled = is_active
        self.chkSolidFill.IsEnabled = is_active
        self.chkHalftone.IsEnabled = is_active
        self.chkVisibility.IsEnabled = is_active

    def regenerate_filter_name(self):
        included_cats = [ci.category.Name for ci in self.category_items if ci.IsIncluded]
        cat_str = included_cats[0] if len(included_cats) == 1 else "MultiCat"

        selected_rules = [p for p in self.all_param_items if p.IsSelected]
        if selected_rules:
            first_rule = selected_rules[0]
            val_clean = "".join([c for c in first_rule.RuleValue if c.isalnum() or c in ['_', '-']])[:15]
            pname_clean = "".join([c for c in first_rule.ParamName if c.isalnum()])[:10]
            if val_clean:
                name = u"Filtro_{}_{}_{}".format(cat_str, pname_clean, val_clean)
            else:
                name = u"Filtro_{}_{}".format(cat_str, pname_clean)
        else:
            name = u"Filtro_{}".format(cat_str)

        self.txtFilterName.Text = name

    def create_single_rule_filter(self, rule_item):
        """Crea un ElementFilter a partire dal RuleItem configurato."""
        pid = rule_item.param_id
        op = rule_item.SelectedOperator.lower()
        val_str = rule_item.RuleValue.strip()

        # Determina StorageType dal primo valore o dal parametro
        sample_raw = rule_item.RawValues[0] if rule_item.RawValues else None
        
        # Gestione valori multipli (OR) se sono presenti virgole e l'operatore è "uguale a"
        if u"," in val_str and u"uguale a" in op:
            parts = [v.strip() for v in val_str.split(u",") if v.strip()]
            sub_filters = List[DB.ElementFilter]()
            for sub_val in parts:
                r = self.build_single_rule(pid, op, sub_val, sample_raw)
                if r:
                    sub_filters.Add(DB.ElementParameterFilter(r))
            if sub_filters.Count > 1:
                return DB.LogicalOrFilter(sub_filters)
            elif sub_filters.Count == 1:
                return sub_filters[0]

        rule = self.build_single_rule(pid, op, val_str, sample_raw)
        return DB.ElementParameterFilter(rule) if rule else None

    def build_single_rule(self, param_id, operator_str, value_str, sample_raw):
        """Costruisce una FilterRule nativa di Revit."""
        if isinstance(sample_raw, DB.ElementId):
            # ElementId rule
            eid_val = sample_raw
            if u"non uguale" in operator_str:
                return DB.ParameterFilterRuleFactory.CreateNotEqualsRule(param_id, eid_val)
            return DB.ParameterFilterRuleFactory.CreateEqualsRule(param_id, eid_val)

        elif isinstance(sample_raw, (int, long)):
            # Integer / Boolean rule
            try:
                ival = int(value_str)
                if u"non uguale" in operator_str:
                    return DB.ParameterFilterRuleFactory.CreateNotEqualsRule(param_id, ival)
                elif u"maggiore" in operator_str:
                    return DB.ParameterFilterRuleFactory.CreateGreaterRule(param_id, ival)
                elif u"minore" in operator_str:
                    return DB.ParameterFilterRuleFactory.CreateLessRule(param_id, ival)
                return DB.ParameterFilterRuleFactory.CreateEqualsRule(param_id, ival)
            except Exception:
                pass

        elif isinstance(sample_raw, float):
            # Double rule
            try:
                dval = float(value_str.replace(u",", u"."))
                tol = 1e-4
                if u"non uguale" in operator_str:
                    return DB.ParameterFilterRuleFactory.CreateNotEqualsRule(param_id, dval, tol)
                elif u"maggiore" in operator_str:
                    return DB.ParameterFilterRuleFactory.CreateGreaterRule(param_id, dval, tol)
                elif u"minore" in operator_str:
                    return DB.ParameterFilterRuleFactory.CreateLessRule(param_id, dval, tol)
                return DB.ParameterFilterRuleFactory.CreateEqualsRule(param_id, dval, tol)
            except Exception:
                pass

        # Default: String rule
        if u"non uguale" in operator_str:
            return DB.ParameterFilterRuleFactory.CreateNotEqualsRule(param_id, value_str)
        elif u"contiene" in operator_str:
            return DB.ParameterFilterRuleFactory.CreateContainsRule(param_id, value_str)
        elif u"inizia" in operator_str:
            return DB.ParameterFilterRuleFactory.CreateBeginsWithRule(param_id, value_str)
        elif u"finisce" in operator_str:
            return DB.ParameterFilterRuleFactory.CreateEndsWithRule(param_id, value_str)
        else:
            return DB.ParameterFilterRuleFactory.CreateEqualsRule(param_id, value_str)

    def on_create_filter(self, sender, args):
        MF.salva(self, _MEMORIA, _CONTROLLI)
        filter_name = self.txtFilterName.Text.strip()
        if not filter_name:
            forms.alert(u"Inserisci un nome valido per il filtro.", title="Attenzione")
            return

        selected_rules = [p for p in self.all_param_items if p.IsSelected]
        if not selected_rules:
            forms.alert(u"Seleziona almeno un parametro / regola per creare il filtro.", title="Attenzione")
            return

        included_cat_ids = List[DB.ElementId]()
        for ci in self.category_items:
            if ci.IsIncluded:
                included_cat_ids.Add(ci.id)

        if not included_cat_ids:
            forms.alert(u"Seleziona almeno una categoria da includere nel filtro.", title="Attenzione")
            return

        # Costruzione dell'ElementFilter complessivo
        rule_filters = List[DB.ElementFilter]()
        for r_item in selected_rules:
            rf = self.create_single_rule_filter(r_item)
            if rf:
                rule_filters.Add(rf)

        if rule_filters.Count == 0:
            forms.alert(u"Impossibile generare le regole di filtraggio per i parametri selezionati.", title="Errore")
            return

        if rule_filters.Count == 1:
            combined_filter = rule_filters[0]
        else:
            if self.rbOr.IsChecked:
                combined_filter = DB.LogicalOrFilter(rule_filters)
            else:
                combined_filter = DB.LogicalAndFilter(rule_filters)

        # Gestione View Template della vista attiva se si desidera aggiungere il filtro
        add_to_view = bool(self.chkAddToActiveView.IsChecked)
        target_view = self.active_view
        unlink_template = False

        if add_to_view and self.active_view.ViewTemplateId != DB.ElementId.InvalidElementId:
            tpl = self.doc.GetElement(self.active_view.ViewTemplateId)
            td = UI.TaskDialog("Modello di Vista Assegnato")
            td.MainInstruction = u"La vista attiva ha il Modello di Vista '{}' assegnato.".format(tpl.Name)
            td.MainContent = (
                u"Per visualizzare e modificare le sovrascritture grafiche del filtro, "
                u"scegli come desideri procedere:"
            )
            td.AddCommandLink(UI.TaskDialogCommandLinkId.CommandLink1, u"Aggiungi il filtro direttamente al MODELLO DI VISTA", u"Il filtro verra aggiunto al modello di vista e applicato a tutte le viste collegate.")
            td.AddCommandLink(UI.TaskDialogCommandLinkId.CommandLink2, u"Scollega il Modello di Vista dalla vista attiva", u"Imposta il modello su <Nessuno> e applica il filtro solo a questa vista.")
            td.AddCommandLink(UI.TaskDialogCommandLinkId.CommandLink3, u"Crea solo il filtro nel progetto (senza aggiungerlo alla vista)")
            td.CommonButtons = UI.TaskDialogCommonButtons.Cancel

            res = td.Show()
            if res == UI.TaskDialogResult.CommandLink1:
                target_view = tpl
            elif res == UI.TaskDialogResult.CommandLink2:
                target_view = self.active_view
                unlink_template = True
            elif res == UI.TaskDialogResult.CommandLink3:
                add_to_view = False
            else:
                return

        # Verifica univocita nome filtro
        existing_filters = {f.Name: f for f in DB.FilteredElementCollector(self.doc).OfClass(DB.ParameterFilterElement).ToElements()}
        final_name = filter_name
        if final_name in existing_filters:
            counter = 1
            while u"{}_{}".format(filter_name, counter) in existing_filters:
                counter += 1
            final_name = u"{}_{}".format(filter_name, counter)

        # Esecuzione transazione
        with revit.Transaction("Crea Filtro da Selezione"):
            # 1. Crea il filtro di vista
            pfe = DB.ParameterFilterElement.Create(self.doc, final_name, included_cat_ids, combined_filter)

            # 2. Aggiungi alla vista e imposta sovrascritture se richiesto
            if add_to_view and pfe and target_view:
                if unlink_template:
                    self.active_view.ViewTemplateId = DB.ElementId.InvalidElementId

                target_view.AddFilter(pfe.Id)
                is_visible = bool(self.chkVisibility.IsChecked)
                target_view.SetFilterVisibility(pfe.Id, is_visible)

                ogs = DB.OverrideGraphicSettings()
                
                # Mezzitoni
                if self.chkHalftone.IsChecked:
                    ogs.SetHalftone(True)

                # Sovrascrittura Colore e Retino
                if self.chkApplyColor.IsChecked and self.cmbColor.SelectedItem:
                    col_name = str(self.cmbColor.SelectedItem)
                    if col_name in COLOR_PALETTE:
                        r, g, b = COLOR_PALETTE[col_name]
                        color = DB.Color(r, g, b)
                        ogs.SetProjectionLineColor(color)
                        ogs.SetProjectionLineWeight(2)
                        ogs.SetCutLineColor(color)
                        ogs.SetCutLineWeight(2)

                        if self.chkSolidFill.IsChecked:
                            solid_pats = [p for p in DB.FilteredElementCollector(self.doc).OfClass(DB.FillPatternElement).ToElements() if p.GetFillPattern().IsSolidFill]
                            if solid_pats:
                                sid = solid_pats[0].Id
                                ogs.SetSurfaceForegroundPatternId(sid)
                                ogs.SetSurfaceForegroundPatternColor(color)
                                ogs.SetSurfaceForegroundPatternVisible(True)
                                ogs.SetCutForegroundPatternId(sid)
                                ogs.SetCutForegroundPatternColor(color)
                                ogs.SetCutForegroundPatternVisible(True)

                target_view.SetFilterOverrides(pfe.Id, ogs)

        self.Close()

        feedback = u"Filtro '{}' creato con successo!".format(final_name)
        if add_to_view:
            feedback += u"\nAggiunto a: {}".format(target_view.Name)
        forms.alert(feedback, title="Filtro Creato")


# ==============================================================================
# MAIN SCRIPT EXECUTION
# ==============================================================================

def main():
    doc = revit.doc
    uidoc = revit.uidoc
    active_view = revit.active_view

    if not active_view:
        forms.alert(u"Nessuna vista attiva.", exitscript=True)

    # 1. Rileva elementi selezionati o richiedi selezione multipla
    selection = revit.get_selection()
    elements = []

    if selection and len(selection) > 0:
        elements = list(selection)
    else:
        try:
            refs = uidoc.Selection.PickObjects(
                UI.Selection.ObjectType.Element,
                u"Seleziona uno o piu elementi per cui creare il filtro (premi Fine/Finish o ESC)"
            )
            if refs:
                elements = [doc.GetElement(r) for r in refs if doc.GetElement(r)]
        except OperationCanceledException:
            forms.alert(u"Selezione annullata.", exitscript=True)
        except Exception as ex:
            print("Errore selezione: {}".format(ex))

    if not elements:
        forms.alert(u"Nessun elemento selezionato.", exitscript=True)

    # 2. Carica XAML
    xaml_path = os.path.join(os.path.dirname(__file__), "ui.xaml")
    if not os.path.exists(xaml_path):
        forms.alert(u"File UI non trovato: {}".format(xaml_path), exitscript=True)

    # 3. Avvia interfaccia
    window = FilterCreatorWindow(xaml_path, doc, active_view, elements)
    MF.ripristina(window, _MEMORIA, _CONTROLLI)
    window.ShowDialog()


if __name__ == "__main__":
    main()
