# -*- coding: utf-8 -*-
"""Aggiorna facciata: riapplica il ritmo salvato sulle curtain wall selezionate.
Maiusc+clic apre la finestra del ritmo."""
from pyrevit import EXEC_PARAMS, revit

from facciate import comandi as CF


def main(finestra=False):
    CF.aggiorna(revit.uidoc, finestra)


if __name__ == "__main__":
    main(EXEC_PARAMS.config_mode)
