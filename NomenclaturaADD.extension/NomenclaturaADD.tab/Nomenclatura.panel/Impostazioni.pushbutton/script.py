# -*- coding: utf-8 -*-
"""Impostazioni di progetto: codice fabbricato, codice bene, fase. Salvate in %APPDATA%\\NomenclaturaADD."""
import os
import shutil

from pyrevit import forms, script

from nomenclatura import regole as R

FABBRICATO = u"Codice fabbricato"
BENE = u"Codice bene"
FASE = u"Fase (servizio)"
FILE = u"Apri il file completo delle impostazioni"

cfg = R.carica_config()
opzioni = [
    u"%s: %s" % (FABBRICATO, cfg.get("codice_fabbricato") or u"(non impostato)"),
    u"%s: %s" % (BENE, cfg.get("codice_bene") or u"(non impostato)"),
    u"%s: %s" % (FASE, cfg.get("servizio") or u"P"),
    FILE,
]
scelta = forms.CommandSwitchWindow.show(opzioni, message=u"Cosa vuoi modificare?")
if not scelta:
    script.exit()

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
    R.salva_config_utente({"codice_fabbricato": val})
    forms.alert(u"Codice fabbricato salvato: %s" % (val or u"(vuoto)"))

elif scelta.startswith(BENE):
    val = forms.ask_for_string(default=cfg.get("codice_bene") or u"",
                               prompt=u"Codice bene (3 lettere + 4 cifre, es. AQD0031)",
                               title=u"Codice bene")
    if val is not None:
        R.salva_config_utente({"codice_bene": val.strip().upper()})

elif scelta.startswith(FASE):
    fasi = [u"S - As Is", u"P - PFTE", u"D - Progetto definitivo", u"E - Progetto esecutivo",
            u"A - As Built"]
    val = forms.CommandSwitchWindow.show(fasi, message=u"Fase del servizio")
    if val:
        R.salva_config_utente({"servizio": val[0]})

else:
    utente = R.percorso_config_utente()
    if not os.path.exists(utente):
        cartella = os.path.dirname(utente)
        if not os.path.isdir(cartella):
            os.makedirs(cartella)
        shutil.copyfile(R.percorso_config_default(), utente)
    os.startfile(utente)
