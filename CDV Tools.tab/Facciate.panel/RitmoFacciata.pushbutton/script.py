# -*- coding: utf-8 -*-
"""Ritmo facciata: dà alle curtain wall selezionate un ritmo di colonne e righe alla Archicad."""
from pyrevit import revit

from facciate import comandi as CF


def main():
    CF.ritmo(revit.uidoc)


if __name__ == "__main__":
    main()
