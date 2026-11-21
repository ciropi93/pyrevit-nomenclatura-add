# -*- coding: utf-8 -*-
"""Inserisce in una legenda i componenti dei tipi degli elementi selezionati.

Si selezionano gli elementi (porte, finestre, muri, arredi...) e si sceglie la legenda:
i componenti vengono messi in ordine (in colonna, con il nome del tipo accanto).
Disposizione, distanza, vista del componente e testo in "Opzioni avanzate".
Revit vuole almeno un componente legenda gia' presente nel file: se manca, il comando
apre la legenda e avvia lo strumento di Revit per metterne uno.
"""
import os
import clr

clr.AddReference('System')
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

import System
from Autodesk.Revit.DB import (
    BuiltInParameter,
    CopyPasteOptions,
    ElementId,
    ElementTransformUtils,
    FailureProcessingResult,
    FailureSeverity,
    FilteredElementCollector,
    IFailuresPreprocessor,
    TextNote,
    TextNoteType,
    Transaction,
    Transform,
    View,
    ViewType,
    XYZ,
)
from Autodesk.Revit.UI import PostableCommand, RevitCommandId
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, forms, EXEC_PARAMS
import stile_finestre as SF
import memoria_finestre as MF
import avviso as AV
import avviso_wpf as AVW
import elenco_wpf as EW

# ultime scelte della finestra (vedi lib/memoria_finestre.py)
_MEMORIA = u"componenti_legenda"
_CONTROLLI = [u"rbVertical", u"rbHorizontal", u"txtSpacing", u"cmbViewDirection", u"chkAddTextNote",
              u"cmbTextType", u"cmbTextFormat"]

VISTE_COMPONENTE = [(u"Pianta", -8), (u"Prospetto anteriore", -7), (u"Prospetto posteriore", -6),
                    (u"Come il componente campione", None)]
FORMATI_TESTO = [u"Nome del tipo", u"Famiglia - Tipo", u"Categoria: Tipo"]


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


class Tipo(object):
    def __init__(self, tipo, categoria, famiglia, nome):
        self.id = tipo.Id
        self.categoria = categoria
        self.famiglia = famiglia
        self.nome = nome


def tipi_da_elementi(doc, elementi):
    visti = {}
    for el in elementi:
        tid = el.GetTypeId()
        if tid == ElementId.InvalidElementId or tid in visti:
            continue
        t = doc.GetElement(tid)
        if t is None:
            continue
        fam = getattr(t, "FamilyName", None)
        if not fam:
            pf = t.get_Parameter(BuiltInParameter.ALL_MODEL_FAMILY_NAME)
            fam = pf.AsString() if pf and pf.AsString() else u""
        pn = t.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
        nome = pn.AsString() if pn and pn.AsString() else getattr(t, "Name", u"Tipo")
        visti[tid] = Tipo(t, el.Category.Name if el.Category else u"Altro", fam, nome)
    return sorted(visti.values(), key=lambda x: (x.categoria, x.famiglia, x.nome))


def campione(doc, legenda, legende):
    """Un componente legenda gia' presente: prima nella legenda scelta, poi nelle altre."""
    for lg in [legenda] + [l for l in legende if l.Id != legenda.Id]:
        for el in FilteredElementCollector(doc, lg.Id):
            if el.get_Parameter(BuiltInParameter.LEGEND_COMPONENT):
                return el, lg
    return None, None


class Finestra(forms.WPFWindow):
    def __init__(self, xaml_file, doc, tipi, n_elementi, legende, apri_opzioni):
        forms.WPFWindow.__init__(self, SF.xaml(xaml_file), literal_string=True)
        self.confermato = False
        n = len(tipi)
        self.lblTipi.Text = u"%d %s da %d elementi" % (n, u"tipo" if n == 1 else u"tipi", n_elementi)

        self.cmbViewDirection.ItemsSource = [v[0] for v in VISTE_COMPONENTE]
        self.cmbViewDirection.SelectedIndex = 0
        self.cmbTextFormat.ItemsSource = FORMATI_TESTO
        self.cmbTextFormat.SelectedIndex = 0
        self.tipi_testo = list(FilteredElementCollector(doc).OfClass(TextNoteType))
        nomi = []
        for tt in self.tipi_testo:
            pn = tt.get_Parameter(BuiltInParameter.SYMBOL_NAME_PARAM)
            nomi.append(pn.AsString() if pn and pn.AsString() else tt.Name)
        self.cmbTextType.ItemsSource = nomi
        if nomi:
            self.cmbTextType.SelectedIndex = 0
        MF.ripristina(self, _MEMORIA, _CONTROLLI)
        self.expOpzioni.IsExpanded = bool(apri_opzioni)

        self.lstLegende.ItemsSource = [EW.Voce(l, l.Name, u"1:%d" % l.Scale) for l in legende]
        attiva = doc.ActiveView
        ultima = MF.valore(_MEMORIA, u"legenda")
        scelta = 0
        for i, l in enumerate(legende):
            if attiva is not None and l.Id == attiva.Id:
                scelta = i
                break
            if l.Name == ultima:
                scelta = i
        self.lstLegende.SelectedIndex = scelta
        self.lstLegende.ScrollIntoView(self.lstLegende.SelectedItem)

        for c in (self.rbVertical, self.rbHorizontal, self.chkAddTextNote):
            c.Checked += lambda s, e: self.aggiorna()
            c.Unchecked += lambda s, e: self.aggiorna()
        self.txtSpacing.TextChanged += lambda s, e: self.aggiorna()
        self.cmbTextFormat.SelectionChanged += lambda s, e: self.aggiorna()
        self.lstLegende.MouseDoubleClick += self.on_apply
        self.btnCancel.Click += lambda s, e: self.Close()
        self.btnApply.Click += self.on_apply
        self.aggiorna()

    def aggiorna(self):
        disp = u"In colonna" if self.rbVertical.IsChecked else u"In riga"
        testo = (u", con %s accanto" % (u"%s" % self.cmbTextFormat.SelectedItem).lower()
                 if self.chkAddTextNote.IsChecked else u", senza testo")
        self.lblRiepilogo.Text = u"%s, ogni %s%s." % (disp, self.txtSpacing.Text.strip(), testo)
        self.btnApply.IsEnabled = self.lstLegende.SelectedItem is not None

    def on_apply(self, sender, args):
        voce = self.lstLegende.SelectedItem
        if voce is None:
            return
        MF.salva(self, _MEMORIA, _CONTROLLI)
        MF.imposta_valore(_MEMORIA, u"legenda", voce.oggetto.Name)
        i_tt = self.cmbTextType.SelectedIndex
        self.legenda = voce.oggetto
        self.opz = {
            "verticale": bool(self.rbVertical.IsChecked),
            "passo": parse_spacing(self.txtSpacing.Text),
            "vista": VISTE_COMPONENTE[max(0, self.cmbViewDirection.SelectedIndex)][1],
            "testo": bool(self.chkAddTextNote.IsChecked) and i_tt >= 0,
            "tipo_testo": self.tipi_testo[i_tt] if i_tt >= 0 else None,
            "formato": max(0, self.cmbTextFormat.SelectedIndex),
        }
        self.confermato = True
        self.Close()


def inserisci(doc, legenda, sample, sample_view, tipi, opz):
    passo = opz["passo"]
    base_x, base_y = 0.0, 0.0
    max_x, min_y, c_geo = -1e9, 1e9, False
    for el in FilteredElementCollector(doc, legenda.Id):
        bb = el.get_BoundingBox(legenda)
        if bb:
            c_geo = True
            max_x = max(max_x, bb.Max.X)
            min_y = min(min_y, bb.Min.Y)
    if c_geo:
        if opz["verticale"]:
            base_y = min_y - passo
        else:
            base_x = max_x + passo

    t = Transaction(doc, u"Componenti in legenda")
    o = t.GetFailureHandlingOptions()
    o.SetFailuresPreprocessor(WarningSwallower())
    t.SetFailureHandlingOptions(o)
    fatti, errori = 0, []
    t.Start()
    try:
        comp = sample
        if sample_view.Id != legenda.Id:
            ids = ElementTransformUtils.CopyElements(sample_view, System.Array[ElementId]([sample.Id]),
                                                     legenda, Transform.Identity, CopyPasteOptions())
            comp = doc.GetElement(list(ids)[0])
        for i, tp in enumerate(tipi):
            try:
                if opz["verticale"]:
                    spost = XYZ(0, -i * passo, 0)
                    pos = XYZ(base_x, base_y - i * passo, 0)
                else:
                    spost = XYZ(i * passo, 0, 0)
                    pos = XYZ(base_x + i * passo, base_y, 0)
                nuovo = doc.GetElement(ElementTransformUtils.CopyElement(doc, comp.Id, spost)[0])
                pt = nuovo.get_Parameter(BuiltInParameter.LEGEND_COMPONENT)
                if pt and not pt.IsReadOnly:
                    pt.Set(tp.id)
                if opz["vista"] is not None:
                    pv = nuovo.get_Parameter(BuiltInParameter.LEGEND_COMPONENT_VIEW)
                    if pv and not pv.IsReadOnly:
                        try:
                            pv.Set(opz["vista"])
                        except Exception:
                            pass
                if opz["testo"] and opz["tipo_testo"] is not None:
                    testo = [tp.nome, u"%s - %s" % (tp.famiglia, tp.nome), u"%s: %s" % (tp.categoria, tp.nome)][opz["formato"]]
                    TextNote.Create(doc, legenda.Id, pos + XYZ(passo * 0.4, 0, 0), testo, opz["tipo_testo"].Id)
                fatti += 1
            except Exception as ex:
                errori.append(u"%s: %s" % (tp.nome, ex))
        t.Commit()
    except Exception as ex:
        t.RollBack()
        AVW.errore(u"Componenti non inseriti: %s" % ex)
        return
    msg = u"%d componenti inseriti in %s" % (fatti, legenda.Name)
    if fatti and errori:
        AVW.attenzione(AV.con_errori(msg, errori))
    elif fatti:
        AVW.mostra(msg)
    else:
        AVW.errore(AV.con_errori(u"Nessun componente inserito", errori))


def main():
    doc = revit.doc
    uidoc = revit.uidoc
    elementi = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    elementi = [e for e in elementi if e is not None and e.Category is not None]
    if not elementi:
        try:
            refs = uidoc.Selection.PickObjects(ObjectType.Element,
                                               u"Seleziona gli elementi da mettere in legenda, poi Fine")
            elementi = [doc.GetElement(r.ElementId) for r in refs]
        except OperationCanceledException:
            return
    tipi = tipi_da_elementi(doc, [e for e in elementi if e is not None])
    if not tipi:
        AVW.errore(u"Dagli elementi selezionati non si ricava nessun tipo")
        return
    legende = sorted([v for v in FilteredElementCollector(doc).OfClass(View)
                      if v.ViewType == ViewType.Legend and not v.IsTemplate], key=lambda v: v.Name)
    if not legende:
        AVW.errore(u"Nel progetto non c'è nessuna legenda: creane una e rilancia")
        return

    xaml = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui.xaml")
    win = Finestra(xaml, doc, tipi, len(elementi), legende, EXEC_PARAMS.config_mode)
    win.ShowDialog()
    if not win.confermato:
        return

    sample, sample_view = campione(doc, win.legenda, legende)
    if sample is None:
        # Revit vuole un primo componente legenda: lo si fa mettere con lo strumento di Revit
        try:
            uidoc.ActiveView = win.legenda
            cmd = RevitCommandId.LookupPostableCommandId(PostableCommand.LegendComponent)
            if cmd and uidoc.Application.CanPostCommand(cmd):
                uidoc.Application.PostCommand(cmd)
        except Exception:
            pass
        AVW.attenzione(u"Metti un primo componente legenda, poi rilancia il comando")
        return

    inserisci(doc, win.legenda, sample, sample_view, tipi, win.opz)
    try:
        uidoc.ActiveView = win.legenda
    except Exception:
        pass


if __name__ == "__main__":
    main()
