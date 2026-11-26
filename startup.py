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


# Strumenti per lo sviluppo via pyRevit Routes (rispondono solo se in pyRevit -> Settings ->
# Routes il server e' acceso):
#   GET  http://localhost:48884/cdv-tools/infissi/prova/   prova dei preset (vedi prova_revit)
#   POST http://localhost:48884/cdv-tools/ricarica/         ricarica pyRevit
# Quando gira un handler pyRevit ha gia' svuotato le variabili globali di questo script e
# ripristinato sys.path: ogni handler prende tutto da dentro (o da argomenti di default),
# e tutto nel try, perche' un errore che esce pyRevit lo nasconde dietro un 408.
try:
    from pyrevit import routes

    _api = routes.API("cdv-tools")

    @_api.route("/infissi/prova/", methods=["GET"])
    def _prova_infissi(request, uiapp, _lib=_LIB):
        from pyrevit import routes
        try:
            import os as _os
            import sys as _sys
            # in pyRevit __file__ dello startup non e' questo file: la cartella vera
            # e' quella del codice che sta girando
            try:
                _lib = _os.path.join(_os.path.dirname(_os.path.abspath(
                    _sys._getframe(0).f_code.co_filename)), "lib")
            except Exception:
                pass
            if not _os.path.isdir(_os.path.join(_lib, "infissi")):
                raise ImportError("cartella lib non trovata: %s" % _lib)
            if _lib not in _sys.path:
                _sys.path.append(_lib)
            from infissi import prova_revit
            try:
                from importlib import reload as _ricarica
            except ImportError:             # IronPython 2.7
                import __builtin__
                _ricarica = __builtin__.reload
            prova_revit = _ricarica(prova_revit)    # cosi' le modifiche valgono senza Reload
            query = getattr(request, "query_params", None) or {}
            return routes.make_response(data=prova_revit.da_route(uiapp.Application, query))
        except Exception:
            import traceback
            return routes.make_response(data={"errore": traceback.format_exc()}, status=500)

    @_api.route("/ricarica/", methods=["POST"])
    def _ricarica_pyrevit(uiapp):
        from pyrevit.loader import sessionmgr
        return {"sessione": "%s" % sessionmgr.reload_pyrevit()}
except Exception:
    pass
