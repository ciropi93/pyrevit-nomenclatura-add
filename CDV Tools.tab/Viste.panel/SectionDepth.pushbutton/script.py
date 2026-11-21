# -*- coding: utf-8 -*-
"""Profondita' Sezione (Sfondo Vettoriale) - CDV Tools

Crea e mantiene sincronizzata una vista di sfondo vettoriale (grigio/mezzitoni)
che parte esattamente alla profondita' d1 della sezione madre e si estende fino a d2,
allineandosi al millimetro anche sulle tavole.
"""

import os
import clr

clr.AddReference('System')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from System.Windows.Media import BrushConverter
from Autodesk.Revit import DB
from pyrevit import revit, forms
import stile_finestre as SF

import avviso as AV
import avviso_wpf as AVW

import profondita_sezione as PS


VIEW_TYPE_NAMES = {
    DB.ViewType.Section: u"Sezione",
    DB.ViewType.Elevation: u"Prospetto",
}


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
    """Determina la sezione madre iniziale da selezione o vista attiva."""
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

    return source_views[0] if source_views else None


class SectionDepthWindow(forms.WPFWindow):
    def __init__(self, xaml_file, doc, source_views, initial_view, coppie, madre_to_sfondo):
        forms.WPFWindow.__init__(self, SF.xaml(xaml_file), literal_string=True)
        self.doc = doc
        self.source_views = source_views
        self.current_view = initial_view
        self.coppie = coppie
        self.madre_to_sfondo = madre_to_sfondo
        self.vp_map = PS._mappa_viewport_per_vista(doc)
        self._brushes = BrushConverter()
        self._updating_ui = False

        self.setup_combobox()
        self.btnSyncAll.Content = u"Sincronizza Tutte (%d)" % len(self.coppie)
        self.btnSyncAll.IsEnabled = len(self.coppie) > 0

        self.cmbSourceView.SelectionChanged += self.on_source_changed
        self.rbModeTotal.Checked += self.on_mode_changed
        self.rbModeAdd.Checked += self.on_mode_changed
        self.txtDepthValue.TextChanged += self.on_depth_text_changed
        self.btnSyncAll.Click += self.on_sync_all
        self.btnCancel.Click += self.on_cancel
        self.btnApply.Click += self.on_apply

        self.refresh_for_current_view()

    def setup_combobox(self):
        self.cmbSourceView.Items.Clear()
        sel_idx = 0
        for i, v in enumerate(self.source_views):
            tname = VIEW_TYPE_NAMES.get(v.ViewType, u"Vista")
            has_bg = PS._id_val(v.Id) in self.madre_to_sfondo
            tag = u" [Sfondo attivo]" if has_bg else u""
            self.cmbSourceView.Items.Add(u"[%s] %s%s" % (tname, v.Name, tag))
            if self.current_view and PS._id_val(v.Id) == PS._id_val(self.current_view.Id):
                sel_idx = i
        if self.cmbSourceView.Items.Count > 0:
            self.cmbSourceView.SelectedIndex = sel_idx

    def _d1_corrente_m(self):
        if not self.current_view:
            return None, u"Nessuna vista selezionata"
        try:
            d1_ft = PS.profondita_madre_piedi(self.current_view)
            return PS.piedi_a_metri(d1_ft), None
        except ValueError as ex:
            return None, u"%s" % ex

    def refresh_for_current_view(self):
        v = self.current_view
        if not v:
            return
        self._updating_ui = True
        try:
            d1_m, err = self._d1_corrente_m()
            if err:
                self.lblDepth1.Text = u"Profondita' madre (d1): Non attiva"
                self.lblDepth1.Foreground = self._brushes.ConvertFromString("#DC2626")
                self.bdrDepth1.Background = self._brushes.ConvertFromString("#FEE2E2")
            else:
                self.lblDepth1.Text = u"Profondita' madre (d1): %.2f m" % d1_m
                self.lblDepth1.Foreground = self._brushes.ConvertFromString("#185A91")
                self.bdrDepth1.Background = self._brushes.ConvertFromString("#E8F1FA")

            self.lblScale.Text = u"Scala: 1:%d" % v.Scale if v.Scale > 0 else u"Scala: -"

            sfondo = self.madre_to_sfondo.get(PS._id_val(v.Id))
            if sfondo is not None:
                self.lblBgStatus.Text = u"Sfondo: %s" % sfondo.Name
                self.lblBgStatus.Foreground = self._brushes.ConvertFromString("#065F46")
                self.bdrBgStatus.Background = self._brushes.ConvertFromString("#D1FAE5")
                cfg = PS.leggi_config_sfondo(sfondo)
                if cfg:
                    if cfg.get("modalita") == u"aggiuntiva":
                        self.rbModeAdd.IsChecked = True
                    else:
                        self.rbModeTotal.IsChecked = True
                    self.txtDepthValue.Text = u"%.2f" % float(cfg.get("valore_m", 15.0))
                    self.chkHalftone.IsChecked = bool(cfg.get("halftone", True))
                    self.chkGreyColor.IsChecked = bool(cfg.get("grigio", True))
                    self.txtGreyRgb.Text = u"%d" % int(cfg.get("grigio_rgb", 140))
                    self.chkHideCutPatterns.IsChecked = bool(cfg.get("nascondi_retini", True))
            else:
                self.lblBgStatus.Text = u"Sfondo: Non creato"
                self.lblBgStatus.Foreground = self._brushes.ConvertFromString("#5B6B78")
                self.bdrBgStatus.Background = self._brushes.ConvertFromString("#EEF2F5")
                default_val = (d1_m + 10.0) if (d1_m is not None and self.rbModeTotal.IsChecked) else 10.0
                self.txtDepthValue.Text = u"%.2f" % default_val

            vps = self.vp_map.get(PS._id_val(v.Id), [])
            if vps:
                sheets_str = u", ".join(s.SheetNumber for (s, _) in vps)
                self.lblSheetStatus.Text = u"Tavola: %s" % sheets_str
            else:
                self.lblSheetStatus.Text = u"Tavola: Non impaginata"
        finally:
            self._updating_ui = False

        self.update_depth_preview()

    def update_depth_preview(self):
        d1_m, err = self._d1_corrente_m()
        if err:
            self.lblDepthPreview.Text = u"Attenzione: la sezione madre deve avere il ritaglio lontano attivo (> 0 m)."
            self.lblDepthPreview.Foreground = self._brushes.ConvertFromString("#DC2626")
            self.bdrDepthPreview.Background = self._brushes.ConvertFromString("#FEE2E2")
            return

        val = _parse_float(self.txtDepthValue.Text)
        if val is None:
            self.lblDepthPreview.Text = u"Inserisci un valore numerico valido in metri."
            self.lblDepthPreview.Foreground = self._brushes.ConvertFromString("#B45309")
            self.bdrDepthPreview.Background = self._brushes.ConvertFromString("#FEF3C7")
            return

        modalita = u"aggiuntiva" if self.rbModeAdd.IsChecked else u"totale"
        try:
            spessore_m, totale_m = PS.calcola_profondita_sfondo(d1_m, val, modalita)
            self.lblDepthPreview.Text = (
                u"Primo piano: 0.00 -> %.2f m  |  Sfondo grigio: %.2f -> %.2f m (spessore %.2f m)"
                % (d1_m, d1_m, totale_m, spessore_m)
            )
            self.lblDepthPreview.Foreground = self._brushes.ConvertFromString("#2B3640")
            self.bdrDepthPreview.Background = self._brushes.ConvertFromString("#EEF2F5")
        except ValueError as ex:
            self.lblDepthPreview.Text = u"%s" % ex
            self.lblDepthPreview.Foreground = self._brushes.ConvertFromString("#DC2626")
            self.bdrDepthPreview.Background = self._brushes.ConvertFromString("#FEE2E2")

    def on_source_changed(self, sender, args):
        idx = self.cmbSourceView.SelectedIndex
        if 0 <= idx < len(self.source_views):
            self.current_view = self.source_views[idx]
            self.refresh_for_current_view()

    def on_mode_changed(self, sender, args):
        if self._updating_ui:
            return
        d1_m, _ = self._d1_corrente_m()
        val = _parse_float(self.txtDepthValue.Text)
        if d1_m is not None and val is not None:
            self._updating_ui = True
            try:
                if self.rbModeAdd.IsChecked:
                    # Da totale a aggiuntiva
                    self.txtDepthValue.Text = u"%.2f" % max(1.0, val - d1_m)
                else:
                    # Da aggiuntiva a totale
                    self.txtDepthValue.Text = u"%.2f" % (d1_m + val)
            finally:
                self._updating_ui = False
        self.update_depth_preview()

    def on_depth_text_changed(self, sender, args):
        if not self._updating_ui:
            self.update_depth_preview()

    def _leggi_config_da_ui(self):
        val = _parse_float(self.txtDepthValue.Text)
        if val is None:
            raise ValueError(u"Inserisci una profondita' valida in metri.")
        rgb_val = _parse_float(self.txtGreyRgb.Text, 140)
        rgb_int = max(0, min(255, int(round(rgb_val))))
        modalita = u"aggiuntiva" if self.rbModeAdd.IsChecked else u"totale"
        return {
            "modalita": modalita,
            "valore_m": val,
            "halftone": bool(self.chkHalftone.IsChecked),
            "grigio": bool(self.chkGreyColor.IsChecked),
            "grigio_rgb": rgb_int,
            "nascondi_retini": bool(self.chkHideCutPatterns.IsChecked),
        }

    def on_cancel(self, sender, args):
        self.Close()

    def on_apply(self, sender, args):
        if not self.current_view:
            return
        try:
            cfg = self._leggi_config_da_ui()
            d1_ft = PS.profondita_madre_piedi(self.current_view)
            PS.calcola_profondita_sfondo(PS.piedi_a_metri(d1_ft), cfg["valore_m"], cfg["modalita"])
        except ValueError as ex:
            forms.alert(u"%s" % ex, title=u"CDV Tools")
            return

        sync_sheet = bool(self.chkSyncSheet.IsChecked)
        t = DB.Transaction(self.doc, u"Profondita' Sezione")
        opts = t.GetFailureHandlingOptions()
        opts.SetFailuresPreprocessor(WarningSwallower())
        t.SetFailureHandlingOptions(opts)

        t.Start()
        try:
            vista_sfondo, creata, tavole = PS.crea_o_aggiorna_sfondo(
                self.doc, self.current_view, cfg, impagina_in_tavola=sync_sheet
            )
            t.Commit()
        except Exception as ex:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            forms.alert(u"Errore durante la sincronizzazione della sezione:\n%s" % ex, title=u"CDV Tools")
            return

        self.Close()
        azione = u"creata" if creata else u"sincronizzata"
        msg = u"Vista di sfondo '%s' %s con successo!" % (vista_sfondo.Name, azione)
        if tavole > 0:
            msg += u"\nTavole allineate: %d." % tavole
        AVW.mostra(msg)

    def on_sync_all(self, sender, args):
        if not self.coppie:
            return
        sync_sheet = bool(self.chkSyncSheet.IsChecked)

        t = DB.Transaction(self.doc, u"Sincronizza Tutte le Sezioni con Sfondo")
        opts = t.GetFailureHandlingOptions()
        opts.SetFailuresPreprocessor(WarningSwallower())
        t.SetFailureHandlingOptions(opts)

        ok = 0
        tavole_tot = 0
        errori = []

        t.Start()
        try:
            for item in self.coppie:
                madre = item["madre"]
                sfondo = item["sfondo"]
                cfg = item["cfg"] or {
                    "modalita": u"totale",
                    "valore_m": 20.0,
                    "halftone": True,
                    "grigio": True,
                    "grigio_rgb": 140,
                    "nascondi_retini": True,
                }
                try:
                    PS.sincronizza_vista_sfondo(self.doc, madre, sfondo, cfg)
                    if sync_sheet:
                        tavole_tot += PS.sincronizza_in_tavola(self.doc, madre, sfondo, crea_se_manca=True)
                    ok += 1
                except Exception as ex:
                    errori.append(u"%s: %s" % (madre.Name, ex))
            t.Commit()
        except Exception as ex:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            forms.alert(u"Errore durante la sincronizzazione globale:\n%s" % ex, title=u"CDV Tools")
            return

        self.Close()
        if errori:
            AVW.attenzione(AV.con_errori(
                u"Sincronizzate %d sezioni (%d tavole)" % (ok, tavole_tot), errori))
        else:
            msg = u"Sincronizzate %d sezioni con sfondo!" % ok
            if tavole_tot > 0:
                msg += u"\nTavole allineate: %d." % tavole_tot
            AVW.mostra(msg)


def main(madre_uid=None):
    """madre_uid: UniqueId della sezione da proporre (usato dal tasto in sovraimpressione)."""
    doc = revit.doc
    uidoc = revit.uidoc
    if not doc or not uidoc:
        AVW.errore(u"Nessun documento attivo in Revit.")
        return

    coppie, madre_to_sfondo, sfondo_to_madre = PS.trova_coppie_sezioni(doc)
    sfondo_ids = set(PS._id_val(item["sfondo"].Id) for item in coppie)

    all_views = [
        v for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements()
        if PS.e_vista_supportata(v) and PS._id_val(v.Id) not in sfondo_ids
    ]
    all_views.sort(key=lambda x: (str(x.ViewType), x.Name))

    if not all_views:
        AVW.errore(u"Nessuna sezione o prospetto trovato nel progetto.")
        return

    initial_view = _rileva_madre_iniziale(doc, uidoc, all_views, sfondo_to_madre)
    if madre_uid:
        for v in all_views:
            if v.UniqueId == madre_uid:
                initial_view = v
                break
    xaml_path = os.path.join(os.path.dirname(__file__), "ui.xaml")
    win = SectionDepthWindow(xaml_path, doc, all_views, initial_view, coppie, madre_to_sfondo)
    win.ShowDialog()


if __name__ == "__main__":
    main()
