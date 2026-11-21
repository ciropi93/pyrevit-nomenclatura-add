# -*- coding: utf-8 -*-
"""Voci per gli elenchi delle finestre (ListBox con ItemTemplate).

Una Voce e' un oggetto Python che WPF sa leggere nei {Binding ...}: basta dargli
attributi (Nome, Dettaglio, Abilitato, Spuntata...). Spuntata avvisa WPF quando cambia,
cosi' le caselle restano allineate se la si cambia dal codice (es. "Seleziona tutte").
"""
import clr
clr.AddReference("System")

from System.ComponentModel import INotifyPropertyChanged, PropertyChangedEventArgs


class Voce(INotifyPropertyChanged):
    def __init__(self, oggetto=None, nome=u"", dettaglio=u"", abilitato=True, spuntata=False):
        self._gestori = []
        self.oggetto = oggetto
        self.Nome = nome
        self.Dettaglio = dettaglio
        self.Abilitato = abilitato
        self._spuntata = spuntata

    def add_PropertyChanged(self, gestore):
        self._gestori.append(gestore)

    def remove_PropertyChanged(self, gestore):
        if gestore in self._gestori:
            self._gestori.remove(gestore)

    def _avvisa(self, nome):
        args = PropertyChangedEventArgs(nome)
        for g in list(self._gestori):
            g(self, args)

    @property
    def Spuntata(self):
        return self._spuntata

    @Spuntata.setter
    def Spuntata(self, valore):
        valore = bool(valore)
        if valore != self._spuntata:
            self._spuntata = valore
            self._avvisa("Spuntata")
