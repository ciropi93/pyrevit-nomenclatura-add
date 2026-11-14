# -*- coding: utf-8 -*-
"""Avvio di CDV Tools: accende la palette contestuale e i tasti in sovraimpressione."""
import os
import sys

_LIB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib")
if _LIB not in sys.path:
    sys.path.append(_LIB)

try:
    from pyrevit import HOST_APP
    import tasti_overlay
    tasti_overlay.attiva(HOST_APP.uiapp)
except Exception as ex:
    # Il resto dell'estensione deve funzionare anche se il tasto non si attiva
    try:
        from pyrevit.coreutils import logger
        logger.get_logger(__name__).warning(u"Tasti in sovraimpressione non attivi: %s" % ex)
    except Exception:
        pass
