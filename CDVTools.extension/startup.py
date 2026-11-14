# -*- coding: utf-8 -*-
"""Avvio di CDV Tools: accende il tasto in sovraimpressione di Profondita' Sezione."""
import os
import sys

_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB not in sys.path:
    sys.path.append(_LIB)

try:
    from pyrevit import HOST_APP
    import sezione_overlay
    sezione_overlay.attiva(HOST_APP.uiapp)
except Exception as ex:
    # Il resto dell'estensione deve funzionare anche se il tasto non si attiva
    try:
        from pyrevit.coreutils import logger
        logger.get_logger(__name__).warning(u"Tasto Profondita' Sezione non attivo: %s" % ex)
    except Exception:
        pass
