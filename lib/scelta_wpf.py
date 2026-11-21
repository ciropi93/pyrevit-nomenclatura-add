# -*- coding: utf-8 -*-
"""Finestra condivisa "scegli da un elenco" (Copia ritaglio, Copia grafica, Allinea su tavole).

    ris = SCW.scegli(
        titolo=u"Copia ritaglio", sottotitolo=u"da Pianta Piano Terra",
        voci=[(vista, u"Pianta Piano Primo", u"Piano Primo", False), ...],
        pulsante=(u"Copia su 1 vista", u"Copia su %d viste", u"Scegli le viste"),
        opzioni=[(u"chkAnnotazioni", u"Copia anche il ritaglio delle annotazioni", True)],
        memoria=u"copia_ritaglio", apri_opzioni=EXEC_PARAMS.config_mode)
    if ris:
        oggetti, opzioni = ris          # opzioni: {nome: True/False}

Ritorna None se si annulla. Le opzioni stanno chiuse in "Opzioni avanzate" e si
ricordano (memoria_finestre); Maiusc+clic sul comando le apre subito.
"""
import os

import clr
clr.AddReference("PresentationFramework")

from System.Windows import Visibility
from System.Windows.Controls import CheckBox
from pyrevit import forms

import elenco_wpf as EW
import memoria_finestre as MF
import scelta as S
import stile_finestre as SF

XAML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scelta.xaml")


class FinestraScelta(forms.WPFWindow):
    def __init__(self, titolo, sottotitolo, voci, pulsante, opzioni, memoria, apri_opzioni, nota):
        forms.WPFWindow.__init__(self, SF.xaml(XAML), literal_string=True)
        self.Title = titolo
        self.lblTitolo.Text = titolo
        self.lblSottotitolo.Text = sottotitolo or u""
        if nota:
            self.lblNota.Text = nota
            self.lblNota.Visibility = Visibility.Visible
        self.pulsante = pulsante
        self.memoria = memoria
        self.confermato = False

        self.voci = []
        for v in voci:
            oggetto, nome, dettaglio = v[0], v[1], v[2]
            spuntata = v[3] if len(v) > 3 else False
            voce = EW.Voce(oggetto, nome, dettaglio, spuntata=spuntata)
            voce.add_PropertyChanged(lambda s, e: self.aggiorna())
            self.voci.append(voce)

        self.nomi_opzioni = []
        for nome, testo, predefinito in (opzioni or []):
            chk = CheckBox()
            chk.Content = testo
            chk.IsChecked = bool(predefinito)
            self.pnlOpzioni.Children.Add(chk)
            setattr(self, nome, chk)          # cosi' memoria_finestre li trova per nome
            self.nomi_opzioni.append(nome)
        if not self.nomi_opzioni:
            self.expOpzioni.Visibility = Visibility.Collapsed
        elif memoria:
            MF.ripristina(self, memoria, self.nomi_opzioni)
        self.expOpzioni.IsExpanded = bool(apri_opzioni)

        self.txtSearch.TextChanged += lambda s, e: self.filtra()
        self.btnTutte.Click += self.on_tutte
        self.btnCancel.Click += lambda s, e: self.Close()
        self.btnApply.Click += self.on_apply
        self.filtra()
        self.txtSearch.Focus()

    def visibili(self):
        cerca = self.txtSearch.Text
        return [v for v in self.voci if S.corrisponde(cerca, v.Nome, v.Dettaglio)]

    def filtra(self):
        vis = self.visibili()
        self.lstVoci.ItemsSource = vis
        self.lblVuoto.Visibility = Visibility.Collapsed if vis else Visibility.Visible
        self.aggiorna()

    def aggiorna(self):
        n = len([v for v in self.voci if v.Spuntata])
        self.btnApply.Content = S.testo_pulsante(n, *self.pulsante)
        self.btnApply.IsEnabled = n > 0
        vis = self.lstVoci.ItemsSource or []
        self.btnTutte.Content = S.testo_tutte(len([v for v in vis if v.Spuntata]), len(vis))

    def on_tutte(self, sender, args):
        vis = list(self.lstVoci.ItemsSource or [])
        tutte = bool(vis) and all(v.Spuntata for v in vis)
        for v in vis:
            v.Spuntata = not tutte
        self.aggiorna()

    def on_apply(self, sender, args):
        if not any(v.Spuntata for v in self.voci):
            return
        if self.memoria and self.nomi_opzioni:
            MF.salva(self, self.memoria, self.nomi_opzioni)
        self.confermato = True
        self.Close()

    def risultato(self):
        scelti = [v.oggetto for v in self.voci if v.Spuntata]
        opzioni = dict((n, bool(getattr(self, n).IsChecked)) for n in self.nomi_opzioni)
        return scelti, opzioni


def scegli(titolo, sottotitolo, voci, pulsante, opzioni=None, memoria=None, apri_opzioni=False, nota=None):
    win = FinestraScelta(titolo, sottotitolo, voci, pulsante, opzioni, memoria, apri_opzioni, nota)
    win.ShowDialog()
    if not win.confermato:
        return None
    return win.risultato()
