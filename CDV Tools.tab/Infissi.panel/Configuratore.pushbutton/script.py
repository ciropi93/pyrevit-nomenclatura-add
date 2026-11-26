# -*- coding: utf-8 -*-
"""Configuratore infissi: crea una famiglia parametrica di finestra o portafinestra."""
from pyrevit import revit, script

import avviso_wpf as AVW
from infissi import ui as UI


def main():
    uidoc = revit.uidoc
    if uidoc is None or uidoc.Document.IsFamilyDocument:
        AVW.errore(u"Apri un progetto (non una famiglia)")
        return
    risultato = UI.apri()
    if not risultato:
        script.exit()
    UI.crea_e_carica(uidoc, risultato)


if __name__ == "__main__":
    main()
