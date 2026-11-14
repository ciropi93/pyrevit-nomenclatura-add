# -*- coding: utf-8 -*-
"""Finestra per scegliere i tasti della palette contestuale, categoria per categoria.

Lavora su una copia della configurazione: si salva in
%APPDATA%\\pyRevit\\CDVTools\\palette.json solo con "Salva". L'overlay rilegge il
file appena cambia, quindi la palette si aggiorna senza riavviare.
"""
import os

from System.Windows import FontWeights, Thickness
from System.Windows.Controls import CheckBox, Orientation, StackPanel, TextBlock
from System.Windows.Media import BrushConverter, Geometry, Stretch
from System.Windows.Shapes import Path

from pyrevit import forms

import palette as PAL

TITOLO = u"CDV Tools"
CARTELLA_ONOFF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              u"PaletteOnOff.pushbutton")
_PENNELLI = BrushConverter()


def _colore(hex_):
    return _PENNELLI.ConvertFromString(hex_)


def _aggiorna_icona_onoff(attiva):
    """Mette l'icona giusta sul pulsante Palette On/Off (se non ci si riesce, va bene lo stesso)."""
    try:
        from pyrevit.coreutils import ribbon
        icona = os.path.join(CARTELLA_ONOFF, u"on.png" if attiva else u"off.png")
        for tab in ribbon.get_current_ui().get_pyrevit_tabs():
            for pannello in tab:
                for pulsante in pannello:
                    if u"paletteonoff" in (getattr(pulsante, "name", u"") or u"").lower():
                        pulsante.set_icon(icona)
    except Exception:
        pass


class FinestraPalette(forms.WPFWindow):
    def __init__(self, xaml_file):
        forms.WPFWindow.__init__(self, xaml_file)
        self.originale = PAL.carica_config()
        self.cfg = PAL.copia_config(self.originale)
        self.chiave = PAL.CHIAVI[0]
        self._in_aggiornamento = False

        self.chkAttiva.IsChecked = self.cfg[u"attiva"]
        self.chkAttiva.Click += self.su_attiva
        self.riempi_categorie()
        self.lstCategorie.SelectionChanged += self.su_categoria
        self.riempi_comandi()

        self.btnTutti.Click += lambda s, a: self.imposta_tutti(True)
        self.btnNessuno.Click += lambda s, a: self.imposta_tutti(False)
        self.btnRipristinaCat.Click += self.su_ripristina_categoria
        self.btnCopiaTutte.Click += self.su_copia_tutte
        self.btnRipristinaTutto.Click += self.su_ripristina_tutto
        self.btnAnnulla.Click += lambda s, a: self.Close()
        self.btnSalva.Click += self.su_salva

    # --- elenco categorie ---------------------------------------------------------
    def _voce(self, chiave):
        n = len(self.cfg[u"categorie"].get(chiave, []))
        return u"%s  (%d)" % (PAL.NOMI_CATEGORIE[chiave], n)

    def riempi_categorie(self):
        sel = self.lstCategorie.SelectedIndex
        self._in_aggiornamento = True
        self.lstCategorie.Items.Clear()
        for k in PAL.CHIAVI:
            self.lstCategorie.Items.Add(self._voce(k))
        self.lstCategorie.SelectedIndex = sel if sel >= 0 else 0
        self._in_aggiornamento = False

    def aggiorna_voce_corrente(self):
        i = PAL.CHIAVI.index(self.chiave)
        self._in_aggiornamento = True
        self.lstCategorie.Items[i] = self._voce(self.chiave)
        self.lstCategorie.SelectedIndex = i
        self._in_aggiornamento = False

    def su_categoria(self, sender, args):
        if self._in_aggiornamento or self.lstCategorie.SelectedIndex < 0:
            return
        self.chiave = PAL.CHIAVI[self.lstCategorie.SelectedIndex]
        self.riempi_comandi()

    # --- caselle dei comandi ------------------------------------------------------
    def _casella(self, cmd, attivo):
        icona = Path()
        icona.Data = Geometry.Parse(cmd.icona)
        icona.Fill = _colore("#0369A1")
        icona.Width = 16
        icona.Height = 16
        icona.Stretch = Stretch.Uniform
        icona.Margin = Thickness(0, 0, 8, 0)
        testo = TextBlock()
        testo.Text = cmd.etichetta
        contenuto = StackPanel()
        contenuto.Orientation = Orientation.Horizontal
        contenuto.Children.Add(icona)
        contenuto.Children.Add(testo)
        c = CheckBox()
        c.Content = contenuto
        c.ToolTip = cmd.suggerimento
        c.IsChecked = attivo
        c.Tag = cmd.id
        c.Click += self.su_casella
        return c

    def riempi_comandi(self):
        self.txtCategoria.Text = PAL.NOMI_CATEGORIE[self.chiave]
        pnl = self.pnlComandi
        pnl.Children.Clear()
        scelti = set(self.cfg[u"categorie"].get(self.chiave, []))
        ammessi = set(PAL.ammessi_per_categoria(self.chiave))
        for gruppo, titolo in PAL.TITOLI_GRUPPI:
            comandi = [c for c in PAL.CATALOGO if c.gruppo == gruppo and c.id in ammessi]
            if not comandi:
                continue
            t = TextBlock()
            t.Text = titolo
            t.FontWeight = FontWeights.SemiBold
            t.Foreground = _colore("#475569")
            t.Margin = Thickness(0, 8 if pnl.Children.Count else 0, 0, 2)
            pnl.Children.Add(t)
            for cmd in comandi:
                pnl.Children.Add(self._casella(cmd, cmd.id in scelti))

    def su_casella(self, sender, args):
        PAL.imposta_comando(self.cfg, self.chiave, sender.Tag, bool(sender.IsChecked))
        self.aggiorna_voce_corrente()

    def imposta_tutti(self, attivo):
        for cid in PAL.ammessi_per_categoria(self.chiave):
            PAL.imposta_comando(self.cfg, self.chiave, cid, attivo)
        self.riempi_comandi()
        self.aggiorna_voce_corrente()

    # --- pulsanti -----------------------------------------------------------------
    def su_attiva(self, sender, args):
        self.cfg[u"attiva"] = bool(self.chkAttiva.IsChecked)

    def su_ripristina_categoria(self, sender, args):
        PAL.ripristina_categoria(self.cfg, self.chiave)
        self.riempi_comandi()
        self.aggiorna_voce_corrente()

    def su_copia_tutte(self, sender, args):
        nome = PAL.NOMI_CATEGORIE[self.chiave]
        if not forms.alert(u"Applicare a tutte le categorie i tasti scelti per '%s'?\n"
                           u"(dove un tasto non ha senso, ad esempio Offset sulle porte, "
                           u"viene saltato)" % nome, title=TITOLO, yes=True, no=True):
            return
        PAL.copia_su_tutte(self.cfg, self.chiave)
        self.riempi_categorie()
        self.riempi_comandi()

    def su_ripristina_tutto(self, sender, args):
        if not forms.alert(u"Tornare ai tasti predefiniti per tutte le categorie?",
                           title=TITOLO, yes=True, no=True):
            return
        attiva = self.cfg[u"attiva"]
        self.cfg = PAL.copia_config(PAL.config_predefinita())
        self.cfg[u"attiva"] = attiva
        self.riempi_categorie()
        self.riempi_comandi()

    def su_salva(self, sender, args):
        try:
            PAL.salva_config(self.cfg)
        except Exception as ex:
            forms.alert(u"Impossibile salvare le impostazioni:\n%s" % ex, title=TITOLO)
            return
        if self.cfg[u"attiva"] != self.originale[u"attiva"]:
            _aggiorna_icona_onoff(self.cfg[u"attiva"])
        self.Close()
        forms.toast(u"Palette aggiornata", title=TITOLO)


def main():
    xaml = os.path.join(os.path.dirname(os.path.abspath(__file__)), u"ui.xaml")
    FinestraPalette(xaml).ShowDialog()


if __name__ == "__main__":
    main()
