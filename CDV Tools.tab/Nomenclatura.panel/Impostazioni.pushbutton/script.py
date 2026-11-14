# -*- coding: utf-8 -*-
"""Impostazioni: codice fabbricato, codice bene, fase; file del progetto (accanto al modello) o personali."""
import os
import shutil

from pyrevit import forms, revit, script

from nomenclatura import regole as R
from nomenclatura import revit_dati as RD

FABBRICATO = u"Codice fabbricato"
BENE = u"Codice bene"
FASE = u"Fase (servizio)"
PROGETTO = u"Apri il file di questo progetto (accanto al modello)"
PERSONALI = u"Apri il file personale (vale per tutti i modelli)"


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
progetto = R.percorso_config_progetto(cartella)
# Il file di progetto prevale sulle personali: se esiste, i valori si salvano li'
destinazione = progetto if progetto and os.path.exists(progetto) else None

try:
    cfg = R.carica_config(cartella)
except R.ConfigErrore as ex:
    forms.alert(u"%s" % ex)
    cfg = R.config_predefinita()

opzioni = [
    u"%s: %s" % (FABBRICATO, cfg.get("codice_fabbricato") or u"(non impostato)"),
    u"%s: %s" % (BENE, cfg.get("codice_bene") or u"(non impostato)"),
    u"%s: %s" % (FASE, cfg.get("servizio") or u"P"),
]
if cartella:
    opzioni.append(PROGETTO)
opzioni.append(PERSONALI)

scelta = forms.CommandSwitchWindow.show(opzioni, message=u"Cosa vuoi modificare?")
if not scelta:
    script.exit()

valori = None
if scelta.startswith(FABBRICATO):
    while True:
        val = forms.ask_for_string(
            default=cfg.get("codice_fabbricato") or u"CF",
            prompt=u"Codice fabbricato (CF + 7 cifre) o area (CA + 4 cifre).\n"
                   u"Lascia vuoto per toglierlo.",
            title=u"Codice fabbricato")
        if val is None:
            script.exit()
        val = val.strip().upper()
        if R.valida_codice_fabbricato(val):
            break
        forms.alert(u"'%s' non e' valido: servono CF + 7 cifre (es. CF1234567) o CA + 4 cifre." % val)
    valori = {"codice_fabbricato": val}

elif scelta.startswith(BENE):
    val = forms.ask_for_string(default=cfg.get("codice_bene") or u"",
                               prompt=u"Codice bene (3 lettere + 4 cifre, es. AQD0031)",
                               title=u"Codice bene")
    if val is not None:
        valori = {"codice_bene": val.strip().upper()}

elif scelta.startswith(FASE):
    fasi = [u"S - As Is", u"P - PFTE", u"D - Progetto definitivo", u"E - Progetto esecutivo",
            u"A - As Built"]
    val = forms.CommandSwitchWindow.show(fasi, message=u"Fase del servizio")
    if val:
        valori = {"servizio": val[0]}

elif scelta == PROGETTO:
    apri_progetto(cartella)

else:
    apri_personali()

if valori:
    salvato = R.salva_config_utente(valori, destinazione)
    forms.alert(u"Salvato in:\n%s" % salvato)
