# -*- coding: utf-8 -*-
"""Copia la grafica di una categoria (o di un elemento) dalla vista attiva ad altre viste.

Si seleziona un elemento (o, con Esc, si sceglie la categoria) e si spuntano le viste.
Copia linee, retini, colori, trasparenza, mezzitoni e visibilita'. Le viste con un
modello di vista vengono saltate, a meno di chiedere di scollegarlo (opzioni avanzate).

Legende: lanciato da una legenda copia la grafica dei componenti (quelli selezionati,
o tutti) sui componenti delle legende di destinazione che disegnano la stessa cosa
(stesso tipo e stessa vista del componente).
"""

from pyrevit import revit, DB, UI, forms, EXEC_PARAMS
from Autodesk.Revit.Exceptions import OperationCanceledException

import abbina_legende as AL
import avviso_wpf as AVW
import scelta_wpf as SCW

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
# MAIN
# ==============================================================================

VISTE_GRAFICHE = (
    DB.ViewType.FloorPlan, DB.ViewType.CeilingPlan, DB.ViewType.EngineeringPlan, DB.ViewType.AreaPlan,
    DB.ViewType.Elevation, DB.ViewType.Section, DB.ViewType.Detail, DB.ViewType.ThreeD,
)
NOMI_TIPI = {
    DB.ViewType.FloorPlan: u"Pianta", DB.ViewType.CeilingPlan: u"Controsoffitto",
    DB.ViewType.EngineeringPlan: u"Pianta strutturale", DB.ViewType.AreaPlan: u"Pianta aree",
    DB.ViewType.Elevation: u"Prospetto", DB.ViewType.Section: u"Sezione",
    DB.ViewType.Detail: u"Dettaglio", DB.ViewType.ThreeD: u"3D",
}
OPZIONI = [
    (u"chkCopyCategoryOverrides", u"Grafica della categoria (linee, retini, colori, trasparenza)", True),
    (u"chkCopyVisibility", u"Visibilità della categoria (mostra o nascondi)", True),
    (u"chkCopyElementOverrides", u"Grafica del singolo elemento selezionato, se ne ha", True),
    (u"chkScollega", u"Scollega il modello dalle viste che ne hanno uno (altrimenti vengono saltate)", False),
]


def _modello(doc, v):
    if v.ViewTemplateId == DB.ElementId.InvalidElementId:
        return None
    return doc.GetElement(v.ViewTemplateId)


def copia_legende(doc, src, componenti):
    legende = sorted([v for v in DB.FilteredElementCollector(doc).OfClass(DB.View)
                      if not v.IsTemplate and v.ViewType == DB.ViewType.Legend and v.Id != src.Id],
                     key=lambda v: v.Name)
    if not legende:
        AVW.errore(u"Non ci sono altre legende su cui copiare la grafica")
        return
    ris = SCW.scegli(
        titolo=u"Copia grafica legenda",
        sottotitolo=u"da %s \u00b7 %d componenti" % (src.Name, len(componenti)),
        voci=[(v, v.Name, u"") for v in legende],
        pulsante=(u"Copia su 1 legenda", u"Copia su %d legende", u"Scegli le legende"),
        nota=u"La grafica va sui componenti uguali (stesso tipo e stessa vista del componente).")
    if not ris:
        return
    scelte = ris[0]
    sorgenti = [(legend_key(c), c.Id) for c in componenti]
    ogs_per_id = dict((get_id_val(c.Id), src.GetElementOverrides(c.Id)) for c in componenti)
    aggiornati, senza_pari, legende_fatte = 0, 0, 0
    with revit.Transaction(u"Copia grafica legende"):
        for v in scelte:
            destinazioni = [(legend_key(c), c.Id) for c in legend_components(doc, v)]
            coppie, mancanti = AL.abbina(sorgenti, destinazioni)
            senza_pari += mancanti
            qui = 0
            for id_src, id_dst in coppie:
                try:
                    v.SetElementOverrides(id_dst, ogs_per_id[get_id_val(id_src)])
                    qui += 1
                except Exception:
                    pass
            aggiornati += qui
            legende_fatte += 1 if qui else 0
    msg = u"Grafica copiata su %d componenti in %d legende" % (aggiornati, legende_fatte)
    if senza_pari:
        AVW.attenzione(msg + u" \u00b7 %d senza corrispondente" % senza_pari)
    else:
        AVW.mostra(msg)


def scegli_categorie(doc, uidoc, selezione):
    """(elemento, categorie) dalla selezione; altrimenti si clicca un elemento o, con Esc,
    si sceglie la categoria dall'elenco."""
    if selezione:
        el = selezione[0]
        return el, extract_element_categories(doc, el)
    try:
        ref = uidoc.Selection.PickObject(
            UI.Selection.ObjectType.Element,
            u"Clicca l'elemento di cui copiare la grafica (Esc: scegli la categoria da un elenco)")
        el = doc.GetElement(ref)
        return el, extract_element_categories(doc, el)
    except OperationCanceledException:
        pass
    tutte = get_all_project_categories(doc)
    nome = forms.SelectFromList.show([n for n, _ in tutte], title=u"Categoria da copiare",
                                     button_name=u"Scegli", multiselect=False)
    if not nome:
        return None, []
    cat = dict(tutte)[nome]
    return None, [cat] + ([cat.Parent] if cat.Parent else [])


def main():
    doc = revit.doc
    uidoc = revit.uidoc
    src = revit.active_view
    if src is None:
        return
    selezione = list(revit.get_selection() or [])

    if src.ViewType == DB.ViewType.Legend:
        componenti = [e for e in selezione if legend_key(e) is not None] or \
            [e for e in legend_components(doc, src) if legend_key(e) is not None]
        if not componenti:
            AVW.errore(u"In questa legenda non ci sono componenti di cui copiare la grafica")
            return
        copia_legende(doc, src, componenti)
        return

    elemento, categorie = scegli_categorie(doc, uidoc, selezione)
    if not categorie:
        return

    destinazioni = []
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View):
        if v.IsTemplate or v.ViewType not in VISTE_GRAFICHE or v.Id == src.Id:
            continue
        tpl = _modello(doc, v)
        destinazioni.append((v, v.Name, (u"modello: " + tpl.Name) if tpl else NOMI_TIPI.get(v.ViewType, u"")))
    destinazioni.sort(key=lambda x: (x[2].startswith(u"modello"), x[2], x[1]))
    if not destinazioni:
        AVW.errore(u"Non ci sono altre viste su cui copiare la grafica")
        return

    ris = SCW.scegli(
        titolo=u"Copia grafica tra viste",
        sottotitolo=u"%s \u00b7 da %s" % (categorie[0].Name, src.Name),
        voci=destinazioni,
        pulsante=(u"Copia su 1 vista", u"Copia su %d viste", u"Scegli le viste"),
        opzioni=OPZIONI, memoria=u"copia_grafica_viste", apri_opzioni=EXEC_PARAMS.config_mode)
    if not ris:
        return
    viste, opz = ris

    impostazioni = []
    for c in categorie:
        ogs, nascosta, _ = get_effective_category_settings(doc, src, c.Id)
        impostazioni.append((c, ogs, nascosta))
    ogs_elemento = None
    if opz[u"chkCopyElementOverrides"] and elemento is not None:
        try:
            ogs_elemento = src.GetElementOverrides(elemento.Id)
        except Exception:
            ogs_elemento = None

    fatte, saltate, scollegate = 0, 0, 0
    with revit.Transaction(u"Copia grafica tra viste"):
        for v in viste:
            if _modello(doc, v) is not None:
                if not opz[u"chkScollega"]:
                    saltate += 1
                    continue
                v.ViewTemplateId = DB.ElementId.InvalidElementId
                scollegate += 1
            for c, ogs, nascosta in impostazioni:
                if opz[u"chkCopyCategoryOverrides"] and ogs is not None and v.IsCategoryOverridable(c.Id):
                    try:
                        v.SetCategoryOverrides(c.Id, ogs)
                    except Exception:
                        pass
                if opz[u"chkCopyVisibility"] and v.CanCategoryBeHidden(c.Id):
                    try:
                        v.SetCategoryHidden(c.Id, nascosta)
                    except Exception:
                        pass
            if ogs_elemento is not None:
                try:
                    v.SetElementOverrides(elemento.Id, ogs_elemento)
                except Exception:
                    pass
            fatte += 1

    msg = u"Grafica di %s copiata su %d viste" % (categorie[0].Name, fatte)
    if scollegate:
        msg += u" \u00b7 %d modelli scollegati" % scollegate
    if saltate:
        AVW.attenzione(msg + u" \u00b7 %d saltate perché hanno un modello" % saltate)
    elif fatte:
        AVW.mostra(msg)
    else:
        AVW.errore(u"Nessuna vista aggiornata")


if __name__ == "__main__":
    main()
