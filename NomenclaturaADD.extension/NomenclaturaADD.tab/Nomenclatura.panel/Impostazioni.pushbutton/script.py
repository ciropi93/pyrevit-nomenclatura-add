# -*- coding: utf-8 -*-
"""Apre il file di impostazioni di progetto (copia personale in %APPDATA%)."""
import os
import shutil

from pyrevit import forms

from nomenclatura import regole as R

utente = R.percorso_config_utente()
if not os.path.exists(utente):
    cartella = os.path.dirname(utente)
    if not os.path.isdir(cartella):
        os.makedirs(cartella)
    shutil.copyfile(R.percorso_config_default(), utente)
    forms.alert(u"Creata la copia delle impostazioni in:\n%s\n\nModificala e salva: "
                u"vale dal prossimo controllo." % utente)
os.startfile(utente)
