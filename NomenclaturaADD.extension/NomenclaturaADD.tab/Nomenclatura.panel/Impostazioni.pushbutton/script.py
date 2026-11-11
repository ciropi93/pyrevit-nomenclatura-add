# -*- coding: utf-8 -*-
"""Apre le impostazioni: del progetto (accanto al modello) o personali (%APPDATA%)."""
import os
import shutil

from pyrevit import forms, revit, script

from nomenclatura import regole as R
from nomenclatura import revit_dati as RD

PROGETTO = u"Di questo progetto (file accanto al modello)"
PERSONALI = u"Personali (valgono per tutti i modelli)"


def apri_personali():
    utente = R.percorso_config_utente()
    if not os.path.exists(utente):
        cartella = os.path.dirname(utente)
        if not os.path.isdir(cartella):
            os.makedirs(cartella)
        shutil.copyfile(R.percorso_config_default(), utente)
        forms.alert(u"Creata la copia delle impostazioni personali in:\n%s\n\nModificala e salva: "
                    u"vale dal prossimo controllo." % utente)
    os.startfile(utente)


def apri_progetto(cartella):
    percorso = R.percorso_config_progetto(cartella)
    if not os.path.exists(percorso):
        try:
            base = R.carica_config()  # predefinite + personali
        except R.ConfigErrore:
            base = R.config_predefinita()
        dati = {u"_nota": u"Impostazioni di questa commessa: prevalgono su quelle personali. "
                          u"Si possono aggiungere anche le altre chiavi di progetto.json."}
        for k in R.CHIAVI_PROGETTO:
            if k in base:
                dati[k] = base[k]
        R.scrivi_json(percorso, dati)
        forms.alert(u"Creato il file di impostazioni del progetto:\n%s\n\nControlla codice bene, "
                    u"codici fabbricato/area e fase, poi salva." % percorso)
    os.startfile(percorso)


cartella = RD.cartella_modello(revit.doc)
if cartella is None:
    forms.alert(u"Il modello non e' salvato in una cartella locale o di rete (nuovo o su cloud): "
                u"si aprono le impostazioni personali.")
    apri_personali()
    script.exit()

scelta = forms.CommandSwitchWindow.show([PROGETTO, PERSONALI],
                                        message=u"Quali impostazioni vuoi modificare?")
if scelta == PROGETTO:
    apri_progetto(cartella)
elif scelta == PERSONALI:
    apri_personali()
