# -*- coding: utf-8 -*-
"""Copia Proprieta Grafiche Categoria / Elemento tra Viste

Copia le impostazioni di visibilita e grafica (linee, retini, colori, trasparenza,
mezzitoni e visibilita) di una categoria o elemento da una vista/modello sorgente
ad una o piu viste di destinazione.
Se le viste di destinazione hanno modelli di vista assegnati, avvisa l'utente
e consente di scollegarli in sicurezza per applicare le sovrascritture.

Legende: lanciato da una legenda copia la grafica dei componenti (quelli selezionati,
o tutti) sui componenti delle legende di destinazione che disegnano la stessa cosa
(stesso tipo e stessa vista del componente).
"""

import os
import sys
import clr

clr.AddReference('System')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System.Collections.ObjectModel import ObservableCollection
from System.ComponentModel import INotifyPropertyChanged, PropertyChangedEventArgs

from pyrevit import revit, DB, UI, forms, script
import stile_finestre as SF
import memoria_finestre as MF

# ultime scelte della finestra (vedi lib/memoria_finestre.py)
_MEMORIA = u"copia_grafica_viste"
_CONTROLLI = [u"chkCopyCategoryOverrides", u"chkCopyVisibility", u"chkCopyElementOverrides"]
from Autodesk.Revit.Exceptions import OperationCanceledException

import abbina_legende as AL

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


def legend_key(el):
    """(id del tipo, vista del componente) di un componente legenda, None per altri elementi."""
    try:
        p_tipo = el.get_Parameter(DB.BuiltInParameter.LEGEND_COMPONENT)
        p_vista = el.get_Parameter(DB.BuiltInParameter.LEGEND_COMPONENT_VIEW)
    except Exception:
        return None
    if p_tipo is None or p_vista is None:
        return None
    return (get_id_val(p_tipo.AsElementId()), p_vista.AsInteger())


def legend_components(doc, view):
    """Componenti legenda presenti nella vista."""
    return list(DB.FilteredElementCollector(doc, view.Id)
                .OfCategory(DB.BuiltInCategory.OST_LegendComponents)
                .WhereElementIsNotElementType()
                .ToElements())


def extract_element_categories(doc, element):
    """
    Estrae tutte le categorie e sottocategorie associate ad un elemento Revit
    (inclusi stili di linea per curve e confini catastali).
    """
    categories = []
    seen_ids = set()

    def add_cat(c):
        if c is not None:
            cid = get_id_val(c.Id)
            if cid is not None and cid not in seen_ids:
                seen_ids.add(cid)
                categories.append(c)

    if element and element.Category:
        cat = element.Category
        add_cat(cat)
        if cat.Parent:
            add_cat(cat.Parent)

    # Verifica stili di linea (CurveElement, DetailLine, ModelLine)
    if hasattr(element, "LineStyle") and element.LineStyle:
        try:
            ls_cat = element.LineStyle.GraphicsStyleCategory
            if ls_cat:
                add_cat(ls_cat)
                if ls_cat.Parent:
                    add_cat(ls_cat.Parent)
        except Exception:
            pass

    # Gestione speciale per Confini Catastali (Property Lines)
    if element and element.Category:
        cat_id_val = get_id_val(element.Category.Id)
        prop_line_bics = [
            int(DB.BuiltInCategory.OST_SitePropertyLineSegment),
            int(DB.BuiltInCategory.OST_SiteProperty)
        ]
        if cat_id_val in prop_line_bics:
            for bic in [DB.BuiltInCategory.OST_SiteProperty, DB.BuiltInCategory.OST_SitePropertyLineSegment, DB.BuiltInCategory.OST_Site]:
                try:
                    c = DB.Category.GetCategory(doc, bic)
                    if c:
                        add_cat(c)
                except Exception:
                    pass

    return categories


def get_effective_category_settings(doc, view, cat_id):
    """
    Legge le impostazioni effettive (sovrascritture e visibilita) per una categoria.
    Se la vista ha un modello di vista assegnato, legge dal modello di vista.
    """
    ogs = None
    is_hidden = False
    source_desc = view.Name

    if view.ViewTemplateId != DB.ElementId.InvalidElementId:
        template = doc.GetElement(view.ViewTemplateId)
        if template:
            try:
                ogs = template.GetCategoryOverrides(cat_id)
                if template.CanCategoryBeHidden(cat_id):
                    is_hidden = template.GetCategoryHidden(cat_id)
                source_desc = u"Modello: " + template.Name
            except Exception:
                pass

    if ogs is None:
        try:
            ogs = view.GetCategoryOverrides(cat_id)
            if view.CanCategoryBeHidden(cat_id):
                is_hidden = view.GetCategoryHidden(cat_id)
        except Exception:
            ogs = DB.OverrideGraphicSettings()

    return ogs, is_hidden, source_desc


def describe_overrides(ogs, is_hidden):
    """Genera una descrizione leggibile delle sovrascritture rilevate."""
    parts = []
    if is_hidden:
        parts.append(u"Visibilità: Nascosto")
    else:
        parts.append(u"Visibilità: Visibile")

    if ogs:
        if ogs.Halftone:
            parts.append(u"Mezzitoni: Attivo")
        if ogs.Transparency > 0:
            parts.append(u"Trasparenza: {}%".format(ogs.Transparency))

        # Linee di proiezione
        if ogs.ProjectionLineColor.IsValid:
            c = ogs.ProjectionLineColor
            parts.append(u"Linea Proiez.: RGB({},{},{})".format(c.Red, c.Green, c.Blue))
        if ogs.ProjectionLineWeight > 0:
            parts.append(u"Spessore Proiez.: {}".format(ogs.ProjectionLineWeight))

        # Linee di taglio
        if ogs.CutLineColor.IsValid:
            c = ogs.CutLineColor
            parts.append(u"Linea Sez.: RGB({},{},{})".format(c.Red, c.Green, c.Blue))
        if ogs.CutLineWeight > 0:
            parts.append(u"Spessore Sez.: {}".format(ogs.CutLineWeight))

        # Retino superficie
        if ogs.SurfaceForegroundPatternColor.IsValid:
            c = ogs.SurfaceForegroundPatternColor
            parts.append(u"Retino Sup.: RGB({},{},{})".format(c.Red, c.Green, c.Blue))

        # Retino sezione
        if ogs.CutForegroundPatternColor.IsValid:
            c = ogs.CutForegroundPatternColor
            parts.append(u"Retino Sez.: RGB({},{},{})".format(c.Red, c.Green, c.Blue))

    if len(parts) <= 1 and not is_hidden:
        return u"Nessuna sovrascrittura personalizzata (grafica predefinita standard)"

    return u" | ".join(parts)


def get_all_project_categories(doc):
    """Raccoglie tutte le categorie e sottocategorie del modello per la selezione manuale."""
    category_list = []
    for cat in doc.Settings.Categories:
        if cat and cat.Name:
            category_list.append((cat.Name, cat))
            if cat.SubCategories:
                for scat in cat.SubCategories:
                    if scat and scat.Name:
                        category_list.append((u"{} -> {}".format(cat.Name, scat.Name), scat))
    category_list.sort(key=lambda x: x[0])
    return category_list


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


class ViewItem(ObservableObject):
    def __init__(self, view, doc):
        super(ViewItem, self).__init__()
        self.view = view
        self.ViewName = view.Name
        self.ViewType = str(view.ViewType)
        has_tpl = view.ViewTemplateId != DB.ElementId.InvalidElementId
        self.HasTemplate = has_tpl
        if has_tpl:
            tpl = doc.GetElement(view.ViewTemplateId)
            self.TemplateName = tpl.Name if tpl else "Modello Sconosciuto"
            self.TemplateText = u"⚠ Modello: " + self.TemplateName
            self.TemplateBgColor = "#FEF3C7"  # light amber
            self.TemplateFgColor = "#92400E"  # dark amber
        else:
            self.TemplateName = ""
            self.TemplateText = u"Nessun Modello"
            self.TemplateBgColor = "#ECFDF5"  # light green
            self.TemplateFgColor = "#065F46"  # dark green
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
# WPF MAIN DIALOG WINDOW
# ==============================================================================

class CopyPropsWindow(forms.WPFWindow):
    def __init__(self, xaml_file, doc, source_view, initial_element=None, initial_categories=None,
                 legend_sources=None):
        forms.WPFWindow.__init__(self, SF.xaml(xaml_file), literal_string=True)
        self.doc = doc
        self.source_view = source_view
        self.selected_element = initial_element
        self.categories = initial_categories or []
        # Componenti della legenda sorgente: la loro grafica va sui componenti uguali
        # delle legende di destinazione
        self.legend_sources = legend_sources or []
        self.all_view_items = []
        self.applied = False

        self.setup_source_info()
        self.setup_views_list()
        self.setup_filters()
        self.update_count_label()

        # Connect event handlers
        self.txtSearch.TextChanged += self.on_filter_changed
        self.cmbViewTypeFilter.SelectionChanged += self.on_filter_changed
        self.btnSelectAll.Click += self.on_select_all
        self.btnDeselectAll.Click += self.on_deselect_all
        self.btnSelectNoTemplate.Click += self.on_select_no_template
        self.btnSelectSameType.Click += self.on_select_same_type
        self.btnChangeCategory.Click += self.on_change_category
        self.btnApply.Click += self.on_apply
        self.btnCancel.Click += self.on_cancel
        if self.legend_sources:
            self.on_filter_changed(None, None)  # mostra subito solo le legende

    def setup_source_info(self):
        # Vista sorgente
        src_tpl = self.doc.GetElement(self.source_view.ViewTemplateId) if self.source_view.ViewTemplateId != DB.ElementId.InvalidElementId else None
        if src_tpl:
            self.lblSourceView.Text = u"Vista Sorgente: {} [Modello: {}]".format(self.source_view.Name, src_tpl.Name)
        else:
            self.lblSourceView.Text = u"Vista Sorgente: {} (Senza modello)".format(self.source_view.Name)

        if self.legend_sources:
            self.lblSourceElement.Text = u"Componenti legenda da copiare: {}".format(len(self.legend_sources))
            self.lblSourceCategory.Text = u"Legende: la grafica va sui componenti uguali (stesso tipo e stessa vista)."
            self.lblSourceOverrides.Text = u"Spunta le legende di destinazione (filtro 'Legende')."
            return

        # Elemento
        if self.selected_element:
            elem_name = self.selected_element.Name if hasattr(self.selected_element, "Name") else self.selected_element.GetType().Name
            elem_id = get_id_val(self.selected_element.Id)
            self.lblSourceElement.Text = u"Elemento: {} (ID: {})".format(elem_name, elem_id)
        else:
            self.lblSourceElement.Text = u"Elemento: Nessun elemento specifico (Selezione da categoria)"

        # Categorie e anteprima sovrascritture
        if self.categories:
            cat_names = [c.Name for c in self.categories]
            self.lblSourceCategory.Text = u"Categorie Rilevate: {}".format(u", ".join(cat_names))

            # Dettagli sovrascritture della prima categoria o di quella con modifiche
            desc_list = []
            for c in self.categories:
                ogs, hidden, src_desc = get_effective_category_settings(self.doc, self.source_view, c.Id)
                d = describe_overrides(ogs, hidden)
                if u"Nessuna sovrascrittura" not in d or len(self.categories) == 1:
                    desc_list.append(u"• {}: {}".format(c.Name, d))

            if desc_list:
                self.lblSourceOverrides.Text = u"\n".join(desc_list)
            else:
                self.lblSourceOverrides.Text = u"Grafica predefinita (nessuna sovrascrittura attiva sulla categoria sorgente)."
        else:
            self.lblSourceCategory.Text = u"Nessuna categoria selezionata."
            self.lblSourceOverrides.Text = u"Seleziona una categoria con il pulsante 'Cambia Categoria...'."

    def setup_views_list(self):
        valid_view_types = [
            DB.ViewType.FloorPlan,
            DB.ViewType.CeilingPlan,
            DB.ViewType.Elevation,
            DB.ViewType.Section,
            DB.ViewType.ThreeD,
            DB.ViewType.Detail,
            DB.ViewType.EngineeringPlan,
            DB.ViewType.AreaPlan,
            DB.ViewType.Legend
        ]

        self.all_view_items = []
        for v in DB.FilteredElementCollector(self.doc).OfClass(DB.View).ToElements():
            if not v.IsTemplate and v.ViewType in valid_view_types and v.Id != self.source_view.Id:
                item = ViewItem(v, self.doc)
                item.add_PropertyChanged(self.on_item_property_changed)
                self.all_view_items.append(item)

        # Ordina alfabeticamente per nome
        self.all_view_items.sort(key=lambda x: x.ViewName)
        self.lvViews.ItemsSource = ObservableCollection[object](self.all_view_items)

    def setup_filters(self):
        filter_options = [
            "Tutte le Viste",
            "Piante (Pavimento / Controsoffitto / Aree)",
            "Prospetti e Sezioni",
            "Viste 3D",
            "Legende",
            "Solo Senza Modello di Vista"
        ]
        self.cmbViewTypeFilter.ItemsSource = filter_options
        self.cmbViewTypeFilter.SelectedIndex = 4 if self.legend_sources else 0

    def on_item_property_changed(self, sender, args):
        if args.PropertyName == "IsSelected":
            self.update_count_label()

    def update_count_label(self):
        selected = [item for item in self.all_view_items if item.IsSelected]
        with_tpl = [item for item in selected if item.HasTemplate]
        if with_tpl:
            self.lblSelectionCount.Text = u"Selezionate: {} viste (di cui {} con Modello di Vista ⚠)".format(len(selected), len(with_tpl))
        else:
            self.lblSelectionCount.Text = u"Selezionate: {} viste".format(len(selected))

    def on_filter_changed(self, sender, args):
        query = self.txtSearch.Text.strip().lower() if self.txtSearch.Text else ""
        selected_type = str(self.cmbViewTypeFilter.SelectedItem) if self.cmbViewTypeFilter.SelectedItem else "Tutte le Viste"

        filtered = []
        for item in self.all_view_items:
            type_match = True
            vt = item.view.ViewType
            if "Piante" in selected_type:
                type_match = vt in [DB.ViewType.FloorPlan, DB.ViewType.CeilingPlan, DB.ViewType.AreaPlan, DB.ViewType.EngineeringPlan]
            elif "Prospetti" in selected_type:
                type_match = vt in [DB.ViewType.Elevation, DB.ViewType.Section, DB.ViewType.Detail]
            elif "3D" in selected_type:
                type_match = vt == DB.ViewType.ThreeD
            elif "Legende" in selected_type:
                type_match = vt == DB.ViewType.Legend
            elif "Solo Senza" in selected_type:
                type_match = not item.HasTemplate

            name_match = (query == "") or (query in item.ViewName.lower()) or (query in item.TemplateName.lower())

            if type_match and name_match:
                filtered.append(item)

        self.lvViews.ItemsSource = ObservableCollection[object](filtered)

    def on_select_all(self, sender, args):
        current_items = list(self.lvViews.ItemsSource) if self.lvViews.ItemsSource else []
        for item in current_items:
            item.IsSelected = True
        self.update_count_label()

    def on_deselect_all(self, sender, args):
        for item in self.all_view_items:
            item.IsSelected = False
        self.update_count_label()

    def on_select_no_template(self, sender, args):
        current_items = list(self.lvViews.ItemsSource) if self.lvViews.ItemsSource else []
        for item in current_items:
            item.IsSelected = not item.HasTemplate
        self.update_count_label()

    def on_select_same_type(self, sender, args):
        src_type = self.source_view.ViewType
        current_items = list(self.lvViews.ItemsSource) if self.lvViews.ItemsSource else []
        for item in current_items:
            item.IsSelected = (item.view.ViewType == src_type)
        self.update_count_label()

    def on_change_category(self, sender, args):
        all_cats = get_all_project_categories(self.doc)
        names = [x[0] for x in all_cats]
        selected_name = forms.SelectFromList.show(
            names,
            title="Seleziona Categoria da Copiare",
            button_name="Scegli Categoria",
            multiselect=False
        )
        if selected_name:
            for name, cat in all_cats:
                if name == selected_name:
                    self.categories = [cat]
                    if cat.Parent:
                        self.categories.append(cat.Parent)
                    self.selected_element = None
                    self.setup_source_info()
                    break

    def on_cancel(self, sender, args):
        self.Close()

    def apply_legends(self, selected_items):
        """Grafica dei componenti della legenda sorgente sui componenti uguali delle legende scelte."""
        legends = [item.view for item in selected_items if item.view.ViewType == DB.ViewType.Legend]
        if not legends:
            forms.alert(u"Tra le viste spuntate non c'è nessuna legenda.", title="Attenzione")
            return

        src = self.source_view
        sources = [(legend_key(c), c.Id) for c in self.legend_sources]
        ogs_by_id = dict((get_id_val(c.Id), src.GetElementOverrides(c.Id)) for c in self.legend_sources)

        updated, unmatched, legends_done = 0, 0, 0
        with revit.Transaction("Copia grafica legende"):
            for v in legends:
                targets = [(legend_key(c), c.Id) for c in legend_components(self.doc, v)]
                pairs, missing = AL.abbina(sources, targets)
                unmatched += missing
                done_here = 0
                for src_id, dst_id in pairs:
                    try:
                        v.SetElementOverrides(dst_id, ogs_by_id[get_id_val(src_id)])
                        done_here += 1
                    except Exception as ex:
                        print(u"Errore nella legenda {}: {}".format(v.Name, ex))
                updated += done_here
                if done_here:
                    legends_done += 1

        self.applied = True
        self.Close()

        msg = u"Grafica copiata su {} componenti in {} legende.".format(updated, legends_done)
        if unmatched:
            msg += u"\n{} componenti non hanno un corrispondente nella legenda sorgente e sono rimasti com'erano.".format(unmatched)
        forms.alert(msg, title="Completato")

    def on_apply(self, sender, args):
        MF.salva(self, _MEMORIA, _CONTROLLI)
        selected_items = [item for item in self.all_view_items if item.IsSelected]
        if not selected_items:
            forms.alert(u"Nessuna vista di destinazione selezionata.\nSeleziona almeno una vista con la casella di controllo.", title="Attenzione")
            return

        if self.legend_sources:
            self.apply_legends(selected_items)
            return

        if not self.categories:
            forms.alert(u"Nessuna categoria selezionata da copiare.", title="Attenzione")
            return

        # Controllo dei Modelli di Vista assegnati alle viste di destinazione
        views_with_template = [item for item in selected_items if item.HasTemplate]
        unlink_templates = False

        if views_with_template:
            # Creazione popup / TaskDialog di conferma
            td = UI.TaskDialog("Verifica Modelli di Vista Assegnati")
            td.MainInstruction = u"{} viste selezionate hanno un Modello di Vista assegnato.".format(len(views_with_template))
            td.MainContent = (
                u"Per poter applicare le sovrascritture di visualizzazione personalizzate, "
                u"il modello di vista deve essere scollegato da queste viste (impostato su <Nessuno>).\n\n"
                u"Come desideri procedere?"
            )
            
            names_summary = u"\n".join([u"• {} (Modello: {})".format(item.ViewName, item.TemplateName) for item in views_with_template[:10]])
            if len(views_with_template) > 10:
                names_summary += u"\n... e altre {} viste".format(len(views_with_template) - 10)
            td.ExpandedContent = u"Viste con modello:\n" + names_summary

            td.AddCommandLink(UI.TaskDialogCommandLinkId.CommandLink1, u"Sì, scollega i Modelli di Vista e applica", u"Rimuove il modello di vista da queste viste e applica le sovrascritture.")
            td.AddCommandLink(UI.TaskDialogCommandLinkId.CommandLink2, u"Applica SOLO alle viste SENZA Modello di Vista", u"Mantiene inalterate le viste con modello e aggiorna solo le viste libere.")
            td.CommonButtons = UI.TaskDialogCommonButtons.Cancel

            res = td.Show()

            if res == UI.TaskDialogResult.CommandLink1:
                unlink_templates = True
            elif res == UI.TaskDialogResult.CommandLink2:
                unlink_templates = False
                # Escludi le viste con modello
                selected_items = [item for item in selected_items if not item.HasTemplate]
                if not selected_items:
                    forms.alert(u"Nessuna vista senza modello selezionata. Operazione annullata.", title="Info")
                    return
            else:
                # Annullato dall'utente
                return

        # Prepara le impostazioni da copiare
        copy_cat_overrides = bool(self.chkCopyCategoryOverrides.IsChecked)
        copy_visibility = bool(self.chkCopyVisibility.IsChecked)
        copy_elem_overrides = bool(self.chkCopyElementOverrides.IsChecked)

        cat_settings_map = {}
        for c in self.categories:
            ogs, is_hidden, _ = get_effective_category_settings(self.doc, self.source_view, c.Id)
            cat_settings_map[get_id_val(c.Id)] = (c, ogs, is_hidden)

        elem_ogs = None
        if copy_elem_overrides and self.selected_element:
            try:
                elem_ogs = self.source_view.GetElementOverrides(self.selected_element.Id)
            except Exception:
                elem_ogs = None

        # Esecuzione transazione
        updated_count = 0
        unlinked_count = 0

        with revit.Transaction("Copia Proprietà Grafiche Categoria"):
            for item in selected_items:
                v = item.view
                try:
                    # Scollegamento modello di vista se confermato
                    if item.HasTemplate and unlink_templates:
                        v.ViewTemplateId = DB.ElementId.InvalidElementId
                        unlinked_count += 1

                    # Applicazione sovrascritture di categoria
                    for cid_val, (cat, ogs, is_hidden) in cat_settings_map.items():
                        cid = cat.Id
                        if copy_cat_overrides and v.IsCategoryOverridable(cid) and ogs is not None:
                            try:
                                v.SetCategoryOverrides(cid, ogs)
                            except Exception:
                                pass

                        if copy_visibility and v.CanCategoryBeHidden(cid):
                            try:
                                v.SetCategoryHidden(cid, is_hidden)
                            except Exception:
                                pass

                    # Applicazione sovrascritture elemento
                    if copy_elem_overrides and elem_ogs and self.selected_element:
                        try:
                            v.SetElementOverrides(self.selected_element.Id, elem_ogs)
                        except Exception:
                            pass

                    updated_count += 1
                except Exception as ex:
                    print("Errore sulla vista {}: {}".format(v.Name, ex))

        self.applied = True
        self.Close()

        # Resoconto finale
        msg = u"Proprietà grafiche applicate con successo a {} viste!".format(updated_count)
        if unlinked_count > 0:
            msg += u"\n({} modelli di vista scollegati)".format(unlinked_count)
        forms.alert(msg, title="Completato")


# ==============================================================================
# MAIN SCRIPT EXECUTION
# ==============================================================================

def main():
    doc = revit.doc
    uidoc = revit.uidoc
    active_view = revit.active_view

    if not active_view:
        forms.alert(u"Nessuna vista attiva nel progetto.", exitscript=True)

    # 1. Rileva elemento preselezionato o chiedi di selezionarne uno
    selection = revit.get_selection()
    target_element = None
    categories = []
    legend_sources = []

    if active_view.ViewType == DB.ViewType.Legend:
        # In legenda: componenti selezionati, altrimenti tutti quelli della legenda
        legend_sources = [e for e in (selection or []) if legend_key(e) is not None]
        if not legend_sources:
            legend_sources = [e for e in legend_components(doc, active_view) if legend_key(e) is not None]
        if not legend_sources:
            forms.alert(u"In questa legenda non ci sono componenti legenda da copiare.", exitscript=True)
    elif selection and len(selection) > 0:
        target_element = selection[0]
        categories = extract_element_categories(doc, target_element)
    else:
        try:
            ref = uidoc.Selection.PickObject(
                UI.Selection.ObjectType.Element,
                u"Seleziona un elemento con le proprietà grafiche da copiare (oppure premi ESC per scegliere la categoria dall'elenco)"
            )
            if ref:
                target_element = doc.GetElement(ref)
                categories = extract_element_categories(doc, target_element)
        except OperationCanceledException:
            # Utente ha premuto ESC: mostra elenco categorie
            all_cats = get_all_project_categories(doc)
            names = [x[0] for x in all_cats]
            selected_name = forms.SelectFromList.show(
                names,
                title="Seleziona Categoria da Copiare",
                button_name="Scegli Categoria",
                multiselect=False
            )
            if selected_name:
                for name, cat in all_cats:
                    if name == selected_name:
                        categories = [cat]
                        if cat.Parent:
                            categories.append(cat.Parent)
                        break
            else:
                forms.alert(u"Nessuna categoria o elemento selezionato.", exitscript=True)
        except Exception:
            pass

    if not categories and not target_element and not legend_sources:
        forms.alert(u"Nessun elemento o categoria valido selezionato.", exitscript=True)

    # 2. Percorso file XAML
    xaml_path = os.path.join(os.path.dirname(__file__), "ui.xaml")
    if not os.path.exists(xaml_path):
        forms.alert(u"File UI non trovato: {}".format(xaml_path), exitscript=True)

    # 3. Mostra la finestra WPF
    window = CopyPropsWindow(
        xaml_file=xaml_path,
        doc=doc,
        source_view=active_view,
        initial_element=target_element,
        initial_categories=categories,
        legend_sources=legend_sources
    )
    MF.ripristina(window, _MEMORIA, _CONTROLLI)
    window.ShowDialog()


if __name__ == "__main__":
    main()
