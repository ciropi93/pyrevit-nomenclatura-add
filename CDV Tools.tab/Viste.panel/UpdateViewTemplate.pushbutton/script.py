# -*- coding: utf-8 -*-
"""Aggiorna un modello di vista con la grafica della vista attiva.

Il giro di lavoro (vedi lib/aggiorna_modello.py):
1. la vista usa un modello: "Sgancia per modificare" (la grafica resta, il modello si ricorda);
2. si cambia la grafica della vista;
3. si rilancia: il modello di prima e' gia' proposto, "Aggiorna" e la vista si riaggancia.
Se la vista non ha un modello si puo' anche crearne uno nuovo.
"""
import clr

clr.AddReference('RevitAPI')
clr.AddReference('PresentationFramework')

from System.Windows import Visibility
from Autodesk.Revit.DB import (
    ElementId,
    FailureProcessingResult,
    FailureSeverity,
    FilteredElementCollector,
    IFailuresPreprocessor,
    Transaction,
    View,
    Viewport,
    ViewType,
)

from pyrevit import revit, forms, script
import stile_finestre as SF
import memoria_finestre as MF
import avviso_wpf as AVW
import elenco_wpf as EW
import aggiorna_modello as AM

# ultime scelte della finestra (vedi lib/memoria_finestre.py)
_MEMORIA = u"aggiorna_modello"
_CONTROLLI = [u"chkReassign"]

VISTE_GRAFICHE = (
    ViewType.FloorPlan, ViewType.CeilingPlan, ViewType.EngineeringPlan, ViewType.AreaPlan,
    ViewType.Section, ViewType.Elevation, ViewType.Detail, ViewType.ThreeD, ViewType.DraftingView,
)


def _val(eid):
    return eid.Value if hasattr(eid, "Value") else eid.IntegerValue


class WarningSwallower(IFailuresPreprocessor):
    """Elimina silenziosamente gli avvisi non critici durante l'aggiornamento."""
    def PreprocessFailures(self, failuresAccessor):
        for f in failuresAccessor.GetFailureMessages():
            if f.GetSeverity() == FailureSeverity.Warning:
                failuresAccessor.DeleteWarning(f)
        return FailureProcessingResult.Continue


def viste_per_modello(doc):
    """{id modello: numero di viste che lo usano}."""
    conti = {}
    for v in FilteredElementCollector(doc).OfClass(View):
        if not v.IsTemplate and v.ViewTemplateId != ElementId.InvalidElementId:
            k = _val(v.ViewTemplateId)
            conti[k] = conti.get(k, 0) + 1
    return conti


class Finestra(forms.WPFWindow):
    def __init__(self, xaml_file, doc, vista):
        forms.WPFWindow.__init__(self, SF.xaml(xaml_file), literal_string=True)
        self.doc = doc
        self.vista = vista
        self.azione = None          # u"sgancia" | u"aggiorna" | u"crea"
        self.modello = None
        self.nome = None
        self.riaggancia = True

        self.lblVista.Text = vista.Name
        self.conti = viste_per_modello(doc)
        tutti = [t for t in FilteredElementCollector(doc).OfClass(View) if t.IsTemplate]
        self.modelli = sorted([t for t in tutti if vista.IsValidViewTemplate(t.Id)], key=lambda t: t.Name.lower())
        self.txtNewTemplateName.Text = AM.nome_nuovo_modello(vista.Name, [t.Name for t in tutti])
        MF.ripristina(self, _MEMORIA, _CONTROLLI)

        self.btnSgancia.Click += self.on_sgancia
        self.btnAltro.Click += lambda s, e: self.mostra_scelta()
        self.btnCancel1.Click += lambda s, e: self.Close()
        self.btnCancel.Click += lambda s, e: self.Close()
        self.btnApply.Click += self.on_apply
        self.txtSearch.TextChanged += lambda s, e: self.riempi()
        self.lstModelli.SelectionChanged += lambda s, e: self.aggiorna()
        self.lstModelli.MouseDoubleClick += self.on_apply

        if vista.ViewTemplateId != ElementId.InvalidElementId:
            tpl = doc.GetElement(vista.ViewTemplateId)
            self.lblModelloAttuale.Text = tpl.Name if tpl else u"-"
        else:
            self.mostra_scelta()

    # --- caso 2: scegliere il modello -------------------------------------------------
    def mostra_scelta(self):
        self.pnlSgancia.Visibility = Visibility.Collapsed
        self.pnlScegli.Visibility = Visibility.Visible
        self.riempi()
        ricordato = MF.valore(AM.COMANDO_SGANCIATI, self.vista.UniqueId)
        chiavi = [v.oggetto.UniqueId if v.oggetto is not None else None for v in self.lstModelli.ItemsSource]
        i = AM.indice_proposto(chiavi, ricordato)
        if i is not None:
            self.lstModelli.SelectedIndex = i
            self.lstModelli.ScrollIntoView(self.lstModelli.SelectedItem)
        self.aggiorna()

    def riempi(self):
        cerca = (self.txtSearch.Text or u"").strip().lower()
        prima = self.lstModelli.SelectedItem
        scelto = prima.oggetto if prima is not None else None
        voci = [EW.Voce(None, u"+ Nuovo modello da questa vista", u"")]
        for t in self.modelli:
            if cerca and cerca not in t.Name.lower():
                continue
            voci.append(EW.Voce(t, t.Name, AM.testo_viste(self.conti.get(_val(t.Id), 0))))
        self.lstModelli.ItemsSource = voci
        for i, v in enumerate(voci):
            if prima is not None and v.oggetto is not None and scelto is not None and v.oggetto.Id == scelto.Id:
                self.lstModelli.SelectedIndex = i
        self.aggiorna()

    def aggiorna(self):
        voce = self.lstModelli.SelectedItem
        nuovo = voce is not None and voce.oggetto is None
        self.pnlNome.Visibility = Visibility.Visible if nuovo else Visibility.Collapsed
        if voce is None:
            self.btnApply.Content = AM.testo_pulsante(None, False)
            self.btnApply.IsEnabled = False
            self.lblNota.Text = u"Scegli il modello da aggiornare con la grafica di questa vista."
            return
        self.btnApply.IsEnabled = True
        if nuovo:
            self.btnApply.Content = AM.testo_pulsante(None, True)
            self.lblNota.Text = u"Il nuovo modello prende la grafica di questa vista."
        else:
            self.btnApply.Content = AM.testo_pulsante(voce.oggetto.Name, False)
            self.lblNota.Text = AM.nota_impatto(self.conti.get(_val(voce.oggetto.Id), 0))

    def on_apply(self, sender, args):
        voce = self.lstModelli.SelectedItem
        if voce is None:
            return
        MF.salva(self, _MEMORIA, _CONTROLLI)
        self.riaggancia = bool(self.chkReassign.IsChecked)
        if voce.oggetto is None:
            self.azione = u"crea"
            self.nome = self.txtNewTemplateName.Text.strip()
        else:
            self.azione = u"aggiorna"
            self.modello = voce.oggetto
        self.Close()

    # --- caso 1: sganciare ------------------------------------------------------------
    def on_sgancia(self, sender, args):
        self.azione = u"sgancia"
        self.modello = self.doc.GetElement(self.vista.ViewTemplateId)
        self.Close()


def vista_di_partenza(doc, uidoc):
    """La vista attiva; in tavola, la vista selezionata."""
    v = doc.ActiveView
    if v is not None and not v.IsTemplate and v.ViewType in VISTE_GRAFICHE:
        return v
    for eid in uidoc.Selection.GetElementIds():
        el = doc.GetElement(eid)
        if isinstance(el, Viewport):
            sv = doc.GetElement(el.ViewId)
            if sv is not None and sv.ViewType in VISTE_GRAFICHE:
                return sv
    return None


def esegui(doc, win):
    v = win.vista
    t = Transaction(doc, u"Aggiorna modello di vista")
    opts = t.GetFailureHandlingOptions()
    opts.SetFailuresPreprocessor(WarningSwallower())
    t.SetFailureHandlingOptions(opts)
    t.Start()
    try:
        if win.azione == u"sgancia":
            v.ViewTemplateId = ElementId.InvalidElementId
            try:
                v.ApplyViewTemplateParameters(win.modello)   # la grafica resta quella del modello
            except Exception:
                pass
            msg = u"Modello sganciato: modifica la vista e rilancia il comando"
        elif win.azione == u"crea":
            nomi = set(x.Name for x in FilteredElementCollector(doc).OfClass(View) if x.IsTemplate)
            if not win.nome or win.nome in nomi:
                t.RollBack()
                AVW.errore(u"Il nome del modello è vuoto o già usato")
                return
            nuovo = v.CreateViewTemplate()
            nuovo.Name = win.nome
            if win.riaggancia:
                v.ViewTemplateId = nuovo.Id
            msg = u"Modello %s creato" % win.nome
        else:
            win.modello.ApplyViewTemplateParameters(v)
            if win.riaggancia:
                v.ViewTemplateId = win.modello.Id
            n = viste_per_modello(doc).get(_val(win.modello.Id), 0)
            msg = u"Modello %s aggiornato · %s" % (win.modello.Name, AM.testo_viste(n))
        t.Commit()
    except Exception as ex:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        AVW.errore(u"Aggiornamento del modello non riuscito: %s" % ex)
        return

    if win.azione == u"sgancia":
        MF.imposta_valore(AM.COMANDO_SGANCIATI, v.UniqueId, win.modello.UniqueId)
    elif win.riaggancia:
        MF.imposta_valore(AM.COMANDO_SGANCIATI, v.UniqueId, None)
    AVW.mostra(msg)


def main():
    doc = revit.doc
    vista = vista_di_partenza(doc, revit.uidoc)
    if vista is None:
        AVW.errore(u"Apri la vista da cui prendere la grafica (o selezionala in tavola)")
        return
    win = Finestra(script.get_bundle_file("ui.xaml"), doc, vista)
    win.ShowDialog()
    if win.azione:
        esegui(doc, win)


if __name__ == "__main__":
    main()
