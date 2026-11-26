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


# Prova dei preset degli infissi in Revit, per lo sviluppo: risponde solo se in pyRevit
# (Settings -> Routes) il server e' acceso. http://localhost:48884/cdv-tools/infissi/prova/
try:
    from pyrevit import routes

    _api = routes.API("cdv-tools")

    @_api.route("/infissi/prova/", methods=["GET"])
    def _prova_infissi(request, uiapp):
        from infissi import prova_revit
        params = getattr(request, "params", None) or {}
        nome = params.get("nome") if hasattr(params, "get") else None
        try:
            dati = prova_revit.prova(uiapp.Application, nomi=[nome] if nome else None)
            return routes.make_response(data={"preset": dati})
        except Exception:
            import traceback
            return routes.make_response(data={"errore": traceback.format_exc()}, status=500)
except Exception:
    pass
