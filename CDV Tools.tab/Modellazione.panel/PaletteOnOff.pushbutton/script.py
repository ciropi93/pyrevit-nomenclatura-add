# -*- coding: utf-8 -*-
"""Accende o spegne la palette contestuale (con i tasti in sovraimpressione e le lettere E/I).

Lo stato sta in %APPDATA%\\pyRevit\\CDVTools\\palette.json: l'overlay lo rilegge da solo
appena cambia, quindi non serve ricaricare pyRevit.
"""
from pyrevit import forms, script

import palette as PAL


def __selfinit__(script_cmp, ui_button_cmp, __rvt__):
    """All'avvio l'icona mostra lo stato salvato (accesa / spenta)."""
    try:
        attiva = PAL.carica_config()[u"attiva"]
        icona = script_cmp.get_bundle_file("on.png" if attiva else "off.png")
        if icona:
            ui_button_cmp.set_icon(icona)
    except Exception:
        pass


def main():
    attiva = not PAL.carica_config()[u"attiva"]
    PAL.imposta_attiva(attiva)
    try:
        script.toggle_icon(attiva)
    except Exception:
        pass
    forms.toast(u"Palette attiva" if attiva else u"Palette spenta", title=u"CDV Tools")


if __name__ == "__main__":
    main()
