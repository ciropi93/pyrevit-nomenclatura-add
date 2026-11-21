# -*- coding: utf-8 -*-
"""Crea un filtro di vista dagli elementi selezionati.

Propone le regole gia' pronte ("Tipo = Muro esterno 30") ordinate dalla piu' adatta;
se ne sceglie una, il nome si scrive da solo. Il filtro va nella vista attiva o, se la
vista usa un modello, nel modello (la finestra dice quale e quante viste lo usano).
Colore e visibilita' in "Opzioni avanzate" (Maiusc+clic le apre subito).
"""
import os
import clr

clr.AddReference('System')
clr.AddReference('PresentationFramework')

from System.Collections.Generic import List
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, DB, UI, forms, EXEC_PARAMS
import stile_finestre as SF
import memoria_finestre as MF
import avviso_wpf as AVW
import elenco_wpf as EW
import crea_filtro as CF

# ultime scelte della finestra (vedi lib/memoria_finestre.py)
_MEMORIA = u"crea_filtro"
_CONTROLLI = [u"chkAddToActiveView", u"chkApplyColor", u"cmbColor", u"chkSolidFill", u"chkHalftone", u"chkVisibility"]


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
# REGOLE
# ==============================================================================

def nome_parametro(elemento, pid):
    pid_val = get_id_val(pid)
    if pid_val is not None and pid_val < 0:
        try:
            return DB.LabelUtils.GetLabelFor(DB.BuiltInParameter(pid_val))
        except Exception:
            pass
    p = find_element_parameter(elemento, pid)
    return p.Definition.Name if (p and p.Definition) else u"%s" % pid_val


def proposte(doc, elementi, id_categorie):
    """[(nome, identico, pid, valori_testo, valori_raw)] per i parametri che hanno un valore
    in tutti gli elementi selezionati."""
    try:
        filtrabili = DB.ParameterFilterUtilities.GetFilterableParametersInCommon(doc, id_categorie)
    except Exception:
        filtrabili = []
    out = []
    for pid in filtrabili:
        testi, grezzi = [], []
        for el in elementi:
            raw, disp = get_param_raw_and_display_value(el, pid)
            if disp is None or not disp.strip():
                break
            testi.append(disp.strip())
            grezzi.append(raw)
        else:
            if testi:
                distinti = sorted(set(testi))
                out.append((nome_parametro(elementi[0], pid), len(distinti) == 1, pid, distinti, grezzi))
    return CF.ordina(out)


def regola(pid, valore_testo, esempio_raw):
    """Regola "uguale a" con il tipo giusto (elemento, intero, numero, testo)."""
    F = DB.ParameterFilterRuleFactory
    if isinstance(esempio_raw, DB.ElementId):
        return F.CreateEqualsRule(pid, esempio_raw)
    if isinstance(esempio_raw, bool) or isinstance(esempio_raw, int):
        return F.CreateEqualsRule(pid, int(esempio_raw))
    if isinstance(esempio_raw, float):
        return F.CreateEqualsRule(pid, esempio_raw, 1e-4)
    return F.CreateEqualsRule(pid, valore_testo)


def filtro_elementi(doc, elementi, proposta):
    """ElementFilter della proposta: uguale al valore, o a uno dei valori (O)."""
    _nome, _identico, pid, testi, _grezzi = proposta
    sotto = List[DB.ElementFilter]()
    for t in testi:
        # valore grezzo di un elemento che ha proprio quel testo
        esempio = None
        for el in elementi:
            raw, disp = get_param_raw_and_display_value(el, pid)
            if disp is not None and disp.strip() == t:
                esempio = raw
                break
        r = regola(pid, t, esempio)
        if r is not None:
            sotto.Add(DB.ElementParameterFilter(r))
    if sotto.Count == 0:
        return None
    if sotto.Count == 1:
        return sotto[0]
    return DB.LogicalOrFilter(sotto)


def grafica(doc, opz):
    ogs = DB.OverrideGraphicSettings()
    if opz["mezzitoni"]:
        ogs.SetHalftone(True)
    rgb = COLOR_PALETTE.get(opz["colore"]) if opz["colora"] else None
    if rgb:
        c = DB.Color(*rgb)
        ogs.SetProjectionLineColor(c)
        ogs.SetCutLineColor(c)
        if opz["pieno"]:
            pieni = [f for f in DB.FilteredElementCollector(doc).OfClass(DB.FillPatternElement)
                     if f.GetFillPattern().IsSolidFill]
            if pieni:
                ogs.SetSurfaceForegroundPatternId(pieni[0].Id)
                ogs.SetSurfaceForegroundPatternColor(c)
                ogs.SetCutForegroundPatternId(pieni[0].Id)
                ogs.SetCutForegroundPatternColor(c)
    return ogs


# ==============================================================================
# FINESTRA
# ==============================================================================

class Finestra(forms.WPFWindow):
    def __init__(self, xaml_file, doc, vista, elementi, nomi_categorie, lista, apri_opzioni):
        forms.WPFWindow.__init__(self, SF.xaml(xaml_file), literal_string=True)
        self.nomi_categorie = nomi_categorie
        self.confermato = False
        self._nome_auto = u""
        self._nome_toccato = False

        n = len(elementi)
        self.lblSelezione.Text = u"%d %s \u00b7 %s" % (n, u"elemento" if n == 1 else u"elementi",
                                                     u", ".join(nomi_categorie))
        self.cmbColor.ItemsSource = list(COLOR_PALETTE.keys())
        self.cmbColor.SelectedIndex = 0
        MF.ripristina(self, _MEMORIA, _CONTROLLI)
        self.expOpzioni.IsExpanded = bool(apri_opzioni)

        self.tpl = doc.GetElement(vista.ViewTemplateId) if vista.ViewTemplateId != DB.ElementId.InvalidElementId else None
        self.n_viste_tpl = 0
        if self.tpl is not None:
            self.n_viste_tpl = len([v for v in DB.FilteredElementCollector(doc).OfClass(DB.View)
                                    if not v.IsTemplate and v.ViewTemplateId == self.tpl.Id])
        self.vista = vista

        self.lstRegole.ItemsSource = [EW.Voce(p, p[0] + u" =", CF.descrivi_valori(p[3])) for p in lista]
        self.lstRegole.SelectedIndex = 0
        self.lstRegole.SelectionChanged += lambda s, e: self.aggiorna()
        self.txtFilterName.TextChanged += self.on_nome
        self.chkAddToActiveView.Checked += lambda s, e: self.aggiorna()
        self.chkAddToActiveView.Unchecked += lambda s, e: self.aggiorna()
        self.btnCancel.Click += lambda s, e: self.Close()
        self.btnCreateFilter.Click += self.on_crea
        self.aggiorna()

    def on_nome(self, sender, args):
        if self.txtFilterName.Text != self._nome_auto:
            self._nome_toccato = True

    def aggiorna(self):
        voce = self.lstRegole.SelectedItem
        if voce is not None and not self._nome_toccato:
            self._nome_auto = CF.nome_filtro(self.nomi_categorie, voce.oggetto[3])
            self.txtFilterName.Text = self._nome_auto
        self.btnCreateFilter.IsEnabled = voce is not None
        if not self.chkAddToActiveView.IsChecked:
            self.lblDove.Text = u"Il filtro viene solo creato nel progetto."
        elif self.tpl is not None:
            self.lblDove.Text = (u"La vista usa il modello %s: il filtro va nel modello (%d viste)."
                                 % (self.tpl.Name, self.n_viste_tpl))
        else:
            self.lblDove.Text = u"Il filtro va nella vista %s." % self.vista.Name

    def on_crea(self, sender, args):
        voce = self.lstRegole.SelectedItem
        if voce is None:
            return
        MF.salva(self, _MEMORIA, _CONTROLLI)
        self.proposta = voce.oggetto
        self.nome = self.txtFilterName.Text.strip() or self._nome_auto
        self.opz = {
            "aggiungi": bool(self.chkAddToActiveView.IsChecked),
            "colora": bool(self.chkApplyColor.IsChecked),
            "colore": u"%s" % self.cmbColor.SelectedItem,
            "pieno": bool(self.chkSolidFill.IsChecked),
            "mezzitoni": bool(self.chkHalftone.IsChecked),
            "visibile": bool(self.chkVisibility.IsChecked),
        }
        self.confermato = True
        self.Close()


# ==============================================================================
# MAIN
# ==============================================================================

def main():
    doc = revit.doc
    uidoc = revit.uidoc
    vista = revit.active_view
    if vista is None:
        return

    elementi = [e for e in (revit.get_selection() or []) if e.Category is not None]
    if not elementi:
        try:
            refs = uidoc.Selection.PickObjects(
                UI.Selection.ObjectType.Element,
                u"Seleziona gli elementi da filtrare, poi Fine")
            elementi = [doc.GetElement(r) for r in refs]
            elementi = [e for e in elementi if e is not None and e.Category is not None]
        except OperationCanceledException:
            return
    if not elementi:
        AVW.errore(u"Seleziona gli elementi da filtrare")
        return

    categorie = {}
    for el in elementi:
        categorie[get_id_val(el.Category.Id)] = el.Category
    id_categorie = List[DB.ElementId]([c.Id for c in categorie.values()])
    nomi_categorie = sorted(c.Name for c in categorie.values())

    lista = proposte(doc, elementi, id_categorie)
    if not lista:
        AVW.errore(u"Nessun parametro comune a tutti gli elementi da usare per un filtro")
        return

    xaml = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui.xaml")
    win = Finestra(xaml, doc, vista, elementi, nomi_categorie, lista, EXEC_PARAMS.config_mode)
    win.ShowDialog()
    if not win.confermato:
        return

    regole = filtro_elementi(doc, elementi, win.proposta)
    if regole is None:
        AVW.errore(u"Non riesco a costruire la regola per %s" % win.proposta[0])
        return
    esistenti = [f.Name for f in DB.FilteredElementCollector(doc).OfClass(DB.ParameterFilterElement)]
    nome = CF.nome_libero(win.nome, esistenti)
    dove = win.tpl if win.tpl is not None else vista

    try:
        with revit.Transaction(u"Crea filtro da selezione"):
            pfe = DB.ParameterFilterElement.Create(doc, nome, id_categorie, regole)
            if win.opz["aggiungi"]:
                dove.AddFilter(pfe.Id)
                dove.SetFilterVisibility(pfe.Id, win.opz["visibile"])
                dove.SetFilterOverrides(pfe.Id, grafica(doc, win.opz))
    except Exception as ex:
        AVW.errore(u"Filtro non creato: %s" % ex)
        return

    if not win.opz["aggiungi"]:
        AVW.mostra(u"Filtro %s creato" % nome)
    elif win.tpl is not None:
        AVW.mostra(u"Filtro %s aggiunto al modello %s" % (nome, win.tpl.Name))
    else:
        AVW.mostra(u"Filtro %s aggiunto alla vista" % nome)


if __name__ == "__main__":
    main()
