# -*- coding: utf-8 -*-
"""Finestra per scegliere gli strumenti della palette contestuale.

A sinistra la fila fissa (uguale per tutte le categorie) e le categorie; a destra le
caselle degli strumenti divise per famiglia (Trasforma, Forma, Seleziona, Vista, Isola).
Lavora su una copia della configurazione e salva in
%APPDATA%\\pyRevit\\CDVTools\\palette.json solo con "Salva"; l'overlay rilegge il
file appena cambia, quindi la palette si aggiorna senza riavviare.
"""
import os

from System.Windows import FontWeights, Thickness, VerticalAlignment
from System.Windows.Controls import CheckBox, Orientation, StackPanel, TextBlock

from pyrevit import forms

import palette as PAL
import icone_wpf as IW

TITOLO = u"CDV Tools"
CARTELLA_ONOFF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              u"PaletteOnOff.pushbutton")
FISSA = u"__fissa__"


def _colore(hex_):
    return IW.colore(hex_)


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
        self.voci = [FISSA] + list(PAL.CHIAVI)
        self.chiave = PAL.CHIAVI[0]
        self._in_aggiornamento = False

        self.chkAttiva.IsChecked = self.cfg[u"attiva"]
        self.chkAttiva.Click += self.su_attiva
        self.riempi_categorie(selezione=1)
        self.lstCategorie.SelectionChanged += self.su_categoria
        self.riempi_comandi()

        self.btnRipristinaCat.Click += self.su_ripristina_categoria
        self.btnCopiaTutte.Click += self.su_copia_tutte
        self.btnRipristinaTutto.Click += self.su_ripristina_tutto
        self.btnAnnulla.Click += lambda s, a: self.Close()
        self.btnSalva.Click += self.su_salva

    # --- elenco a sinistra --------------------------------------------------------
    def _voce(self, chiave):
        if chiave == FISSA:
            return u"★ Fila fissa  (%d)" % len(self.cfg[u"fissa"])
        n = len([i for i in self.cfg[u"categorie"].get(chiave, []) if i not in self.cfg[u"fissa"]])
        return u"%s  (%d)" % (PAL.NOMI_CATEGORIE[chiave], n)

    def riempi_categorie(self, selezione=None):
        sel = self.lstCategorie.SelectedIndex if selezione is None else selezione
        self._in_aggiornamento = True
        self.lstCategorie.Items.Clear()
        for k in self.voci:
            self.lstCategorie.Items.Add(self._voce(k))
        self.lstCategorie.SelectedIndex = sel if sel >= 0 else 1
        self._in_aggiornamento = False

    def aggiorna_voce_corrente(self):
        i = self.voci.index(self.chiave)
        self._in_aggiornamento = True
        self.lstCategorie.Items[i] = self._voce(self.chiave)
        self.lstCategorie.SelectedIndex = i
        self._in_aggiornamento = False
        self.aggiorna_conteggio()

    def su_categoria(self, sender, args):
        if self._in_aggiornamento or self.lstCategorie.SelectedIndex < 0:
            return
        self.chiave = self.voci[self.lstCategorie.SelectedIndex]
        self.riempi_comandi()

    # --- caselle a destra ---------------------------------------------------------
    def _casella(self, cmd, spuntata, nota=None):
        icona = IW.crea_icona(cmd.icona, 16)
        icona.Margin = Thickness(0, 0, 8, 0)
        testo = TextBlock()
        testo.Text = cmd.etichetta if not nota else u"%s  (%s)" % (cmd.etichetta, nota)
        testo.VerticalAlignment = VerticalAlignment.Center
        riga = StackPanel()
        riga.Orientation = Orientation.Horizontal
        riga.Children.Add(icona)
        riga.Children.Add(testo)
        c = CheckBox()
        c.Content = riga
        c.ToolTip = cmd.suggerimento
        c.IsChecked = spuntata
        c.Tag = cmd.id
        if nota:
            c.IsEnabled = False
        c.Click += self.su_casella
        return c

    def _titolo_famiglia(self, testo):
        t = TextBlock()
        t.Text = testo
        t.FontWeight = FontWeights.SemiBold
        t.Foreground = _colore("#475569")
        t.Margin = Thickness(0, 8 if self.pnlComandi.Children.Count else 0, 0, 2)
        return t

    def riempi_comandi(self):
        pnl = self.pnlComandi
        pnl.Children.Clear()
        fissa = self.chiave == FISSA
        self.btnCopiaTutte.IsEnabled = not fissa
        if fissa:
            self.txtCategoria.Text = u"Fila fissa (tutte le categorie)"
            ammessi = None
            scelti = set(self.cfg[u"fissa"])
        else:
            self.txtCategoria.Text = PAL.NOMI_CATEGORIE[self.chiave]
            ammessi = set(PAL.ammessi_per_categoria(self.chiave))
            scelti = set(self.cfg[u"categorie"].get(self.chiave, []))
        for fid, nome in PAL.FAMIGLIE:
            comandi = [c for c in PAL.CATALOGO if c.famiglia == fid
                       and (ammessi is None or c.id in ammessi)]
            if not comandi:
                continue
            pnl.Children.Add(self._titolo_famiglia(nome))
            for cmd in comandi:
                if not fissa and cmd.id in self.cfg[u"fissa"]:
                    pnl.Children.Add(self._casella(cmd, True, u"nella fila fissa"))
                else:
                    pnl.Children.Add(self._casella(cmd, cmd.id in scelti))
        self.aggiorna_conteggio()

    def aggiorna_conteggio(self):
        if self.chiave == FISSA:
            self.txtConteggio.Text = u"%d / %d" % (len(self.cfg[u"fissa"]), PAL.MAX_FISSA)
        else:
            self.txtConteggio.Text = u""

    def su_casella(self, sender, args):
        attivo = bool(sender.IsChecked)
        if self.chiave == FISSA:
            if not PAL.imposta_fissa(self.cfg, sender.Tag, attivo):
                forms.alert(u"Nella fila fissa ci stanno al massimo %d strumenti." % PAL.MAX_FISSA,
                            title=TITOLO)
                sender.IsChecked = False
                return
            # entrare/uscire dalla fila fissa cambia anche le categorie
            self.riempi_categorie()
            self.aggiorna_conteggio()
        else:
            PAL.imposta_comando(self.cfg, self.chiave, sender.Tag, attivo)
            self.aggiorna_voce_corrente()

    # --- pulsanti -----------------------------------------------------------------
    def su_attiva(self, sender, args):
        self.cfg[u"attiva"] = bool(self.chkAttiva.IsChecked)

    def su_ripristina_categoria(self, sender, args):
        if self.chiave == FISSA:
            for cid in list(self.cfg[u"fissa"]):
                PAL.imposta_fissa(self.cfg, cid, False)
            for cid in PAL.FISSA_PREDEFINITA:
                PAL.imposta_fissa(self.cfg, cid, True)
            self.riempi_categorie()
        else:
            PAL.ripristina_categoria(self.cfg, self.chiave)
            self.aggiorna_voce_corrente()
        self.riempi_comandi()

    def su_copia_tutte(self, sender, args):
        nome = PAL.NOMI_CATEGORIE[self.chiave]
        if not forms.alert(u"Applicare a tutte le categorie la scelta fatta per '%s'?\n"
                           u"(dove un comando non ha senso, ad esempio Offset sulle porte, "
                           u"viene saltato)" % nome, title=TITOLO, yes=True, no=True):
            return
        PAL.copia_su_tutte(self.cfg, self.chiave)
        self.riempi_categorie()
        self.riempi_comandi()

    def su_ripristina_tutto(self, sender, args):
        if not forms.alert(u"Tornare alla palette predefinita per tutte le categorie e la fila fissa?",
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
