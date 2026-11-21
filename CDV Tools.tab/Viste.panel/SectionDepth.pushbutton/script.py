# -*- coding: utf-8 -*-
"""Profondita' sezione: sfondo grigio oltre la profondita' della sezione.

Crea e tiene sincronizzata una vista di sfondo (grigio/mezzitoni) che parte dove finisce
la sezione (d1) e arriva alla profondita' scelta, allineata anche in tavola.
- clic su una sezione che ha gia' lo sfondo: lo sincronizza subito;
- altrimenti (o Maiusc+clic, o tasto della palette): una sola domanda, fino a che profondita'.
"""

import os
import clr

clr.AddReference('System')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from System.Windows import Visibility
from System.Windows.Media import BrushConverter
from Autodesk.Revit import DB
from pyrevit import revit, forms, EXEC_PARAMS
import stile_finestre as SF
import memoria_finestre as MF

import avviso as AV
import avviso_wpf as AVW

import profondita_sezione as PS


# grafica dello sfondo nuova: si ricordano le ultime scelte (per gli sfondi esistenti
# vale quella salvata sullo sfondo stesso)
_MEMORIA = u"profondita_sezione"
_CONTROLLI = [u"chkHalftone", u"chkGreyColor", u"txtGreyRgb", u"chkHideCutPatterns", u"chkSyncSheet"]
CFG_PREDEFINITA = {"modalita": u"totale", "valore_m": 20.0, "halftone": True, "grigio": True,
                   "grigio_rgb": 140, "nascondi_retini": True}


class WarningSwallower(DB.IFailuresPreprocessor):
    """Elimina silenziosamente gli avvisi non critici durante la sincronizzazione."""
    def PreprocessFailures(self, failuresAccessor):
        for f in failuresAccessor.GetFailureMessages():
            if f.GetSeverity() == DB.FailureSeverity.Warning:
                failuresAccessor.DeleteWarning(f)
        return DB.FailureProcessingResult.Continue


def _parse_float(text, default=None):
    if not text:
        return default
    try:
        return float(text.strip().replace(u",", u"."))
    except Exception:
        return default


def _rileva_madre_iniziale(doc, uidoc, source_views, sfondo_to_madre):
    """La sezione da selezione (linea in pianta, vista in tavola) o vista attiva; None se non c'e'."""
    by_id = dict((PS._id_val(v.Id), v) for v in source_views)
    by_name = dict((v.Name, v) for v in source_views)

    # 1. Controlla selezione corrente (Viewport in tavola o linea di sezione in pianta)
    for eid in uidoc.Selection.GetElementIds():
        el = doc.GetElement(eid)
        if isinstance(el, DB.Viewport):
            vid = PS._id_val(el.ViewId)
            if vid in sfondo_to_madre:
                madre = sfondo_to_madre[vid]
                if PS._id_val(madre.Id) in by_id:
                    return madre
            if vid in by_id:
                return by_id[vid]
        elif el is not None and el.Category and PS._id_val(el.Category.Id) == int(DB.BuiltInCategory.OST_Viewers):
            if el.Name in by_name:
                return by_name[el.Name]
            if el.Name.endswith(PS.SUFFISSO_SFONDO):
                base = el.Name[:-len(PS.SUFFISSO_SFONDO)]
                if base in by_name:
                    return by_name[base]

    # 2. Controlla vista attiva
    av = doc.ActiveView
    if av is not None:
        avid = PS._id_val(av.Id)
        if avid in sfondo_to_madre:
            madre = sfondo_to_madre[avid]
            if PS._id_val(madre.Id) in by_id:
                return madre
        if avid in by_id:
            return by_id[avid]

    return None


class SectionDepthWindow(forms.WPFWindow):
    def __init__(self, xaml_file, madre, d1_m, sfondo, n_sfondi, apri_opzioni):
        forms.WPFWindow.__init__(self, SF.xaml(xaml_file), literal_string=True)
        self.d1 = d1_m
        self.azione = None          # u"una" | u"tutte"
        self.cfg = None
        self._pennelli = BrushConverter()

        self.lblVista.Text = madre.Name
        cfg = PS.leggi_config_sfondo(sfondo) if sfondo is not None else None
        if cfg:
            self.chkHalftone.IsChecked = bool(cfg.get("halftone", True))
            self.chkGreyColor.IsChecked = bool(cfg.get("grigio", True))
            self.txtGreyRgb.Text = u"%d" % int(cfg.get("grigio_rgb", 140))
            self.chkHideCutPatterns.IsChecked = bool(cfg.get("nascondi_retini", True))
        else:
            MF.ripristina(self, _MEMORIA, _CONTROLLI)
        if sfondo is not None:
            self.chkSyncSheet.IsChecked = bool(MF.valore(_MEMORIA, u"chkSyncSheet", True))
        self.txtDepthValue.Text = u"%.2f" % PS.totale_da_config(d1_m, cfg)
        self.btnApply.Content = u"Aggiorna sfondo" if sfondo is not None else u"Crea sfondo"
        self.expOpzioni.IsExpanded = bool(apri_opzioni)
        if n_sfondi:
            self.btnSyncAll.Content = u"Sincronizza tutte (%d)" % n_sfondi
        else:
            self.btnSyncAll.Visibility = Visibility.Collapsed

        self.txtDepthValue.TextChanged += lambda s, e: self.aggiorna()
        self.btnPiu5.Click += lambda s, e: self._oltre(5.0)
        self.btnPiu10.Click += lambda s, e: self._oltre(10.0)
        self.btnPiu20.Click += lambda s, e: self._oltre(20.0)
        self.btnSyncAll.Click += self.on_sync_all
        self.btnCancel.Click += lambda s, e: self.Close()
        self.btnApply.Click += self.on_apply
        self.aggiorna()
        self.txtDepthValue.Focus()
        self.txtDepthValue.SelectAll()

    def _oltre(self, metri):
        self.txtDepthValue.Text = u"%.2f" % (self.d1 + metri)

    def aggiorna(self):
        testo, ok = PS.testo_anteprima(self.d1, self.txtDepthValue.Text)
        self.lblAnteprima.Text = testo
        self.lblAnteprima.Foreground = self._pennelli.ConvertFromString("#5B6B78" if ok else "#DC2626")
        self.btnApply.IsEnabled = ok

    def opzioni(self):
        rgb = _parse_float(self.txtGreyRgb.Text, 140)
        return {
            "halftone": bool(self.chkHalftone.IsChecked),
            "grigio": bool(self.chkGreyColor.IsChecked),
            "grigio_rgb": max(0, min(255, int(round(rgb)))),
            "nascondi_retini": bool(self.chkHideCutPatterns.IsChecked),
        }

    def on_apply(self, sender, args):
        val = _parse_float(self.txtDepthValue.Text)
        if val is None or not PS.testo_anteprima(self.d1, self.txtDepthValue.Text)[1]:
            return
        MF.salva(self, _MEMORIA, _CONTROLLI)
        self.cfg = dict(self.opzioni(), modalita=u"totale", valore_m=val)
        self.in_tavola = bool(self.chkSyncSheet.IsChecked)
        self.azione = u"una"
        self.Close()

    def on_sync_all(self, sender, args):
        self.in_tavola = bool(self.chkSyncSheet.IsChecked)
        self.azione = u"tutte"
        self.Close()


def _transazione(doc, nome):
    t = DB.Transaction(doc, nome)
    opts = t.GetFailureHandlingOptions()
    opts.SetFailuresPreprocessor(WarningSwallower())
    t.SetFailureHandlingOptions(opts)
    return t


def crea_o_sincronizza(doc, madre, cfg, in_tavola):
    t = _transazione(doc, u"Profondita' sezione")
    t.Start()
    try:
        vista_sfondo, creata, tavole = PS.crea_o_aggiorna_sfondo(doc, madre, cfg, impagina_in_tavola=in_tavola)
        t.Commit()
    except Exception as ex:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        AVW.errore(u"Sfondo non creato: %s" % ex)
        return
    msg = (u"Sfondo creato" if creata else u"Sfondo sincronizzato") + u" per %s" % madre.Name
    if tavole > 0:
        msg += u" \u00b7 %d tavole" % tavole
    AVW.mostra(msg)


def sincronizza_tutte(doc, coppie, in_tavola):
    t = _transazione(doc, u"Sincronizza tutti gli sfondi")
    ok, tavole_tot, errori = 0, 0, []
    t.Start()
    try:
        for item in coppie:
            try:
                PS.sincronizza_vista_sfondo(doc, item["madre"], item["sfondo"], item["cfg"] or CFG_PREDEFINITA)
                if in_tavola:
                    tavole_tot += PS.sincronizza_in_tavola(doc, item["madre"], item["sfondo"], crea_se_manca=True)
                ok += 1
            except Exception as ex:
                errori.append(u"%s: %s" % (item["madre"].Name, ex))
        t.Commit()
    except Exception as ex:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        AVW.errore(u"Sincronizzazione non riuscita: %s" % ex)
        return
    msg = u"Sfondi sincronizzati: %d" % ok
    if tavole_tot:
        msg += u" \u00b7 %d tavole" % tavole_tot
    if errori:
        AVW.attenzione(AV.con_errori(msg, errori))
    else:
        AVW.mostra(msg)


def main(madre_uid=None):
    """madre_uid: sezione scelta dal tasto della palette (apre sempre la finestra)."""
    doc = revit.doc
    uidoc = revit.uidoc
    if not doc or not uidoc:
        return

    coppie, madre_to_sfondo, sfondo_to_madre = PS.trova_coppie_sezioni(doc)
    sfondo_ids = set(PS._id_val(item["sfondo"].Id) for item in coppie)
    viste = [
        v for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements()
        if PS.e_vista_supportata(v) and PS._id_val(v.Id) not in sfondo_ids
    ]
    madre = None
    if madre_uid:
        madre = next((v for v in viste if v.UniqueId == madre_uid), None)
    if madre is None:
        madre = _rileva_madre_iniziale(doc, uidoc, viste, sfondo_to_madre)
    if madre is None:
        AVW.errore(u"Apri o seleziona una sezione (o un prospetto)")
        return

    try:
        d1_m = PS.piedi_a_metri(PS.profondita_madre_piedi(madre))
    except ValueError:
        AVW.errore(u"Attiva il ritaglio lontano della sezione: lo sfondo parte da lì")
        return

    sfondo = madre_to_sfondo.get(PS._id_val(madre.Id))
    if sfondo is not None and not madre_uid and not EXEC_PARAMS.config_mode:
        cfg = PS.leggi_config_sfondo(sfondo) or CFG_PREDEFINITA
        crea_o_sincronizza(doc, madre, cfg, bool(MF.valore(_MEMORIA, u"chkSyncSheet", True)))
        return

    xaml = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui.xaml")
    win = SectionDepthWindow(xaml, madre, d1_m, sfondo, len(coppie), EXEC_PARAMS.config_mode)
    win.ShowDialog()
    if win.azione == u"una":
        crea_o_sincronizza(doc, madre, win.cfg, win.in_tavola)
    elif win.azione == u"tutte":
        sincronizza_tutte(doc, coppie, win.in_tavola)


if __name__ == "__main__":
    main()
