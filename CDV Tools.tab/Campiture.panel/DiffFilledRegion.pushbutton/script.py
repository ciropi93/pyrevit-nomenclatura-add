# -*- coding: utf-8 -*-
"""Campiture della differenza tra elementi dello stato di fatto e dello stato di progetto,
sul piano di taglio della vista: TOLTO (fatto meno progetto) e AGGIUNTO (progetto meno fatto).
Shift+clic: impostazioni (tipi campitura per tolto e aggiunto)."""

from System.Collections.Generic import List
from pyrevit import revit, DB, forms, script, EXEC_PARAMS
import campiture_taglio as CT

VOCI = (("tolto", u"Tipo campitura per il TOLTO (demolito)"),
        ("aggiunto", u"Tipo campitura per l'AGGIUNTO (nuovo)"))


def impostazioni(doc, cfg):
    """Chiede i due tipi campitura e li salva. Ritorna False se annullato."""
    nomi = sorted(CT.tipi_campitura(doc))
    for chiave, titolo in VOCI:
        scelto = forms.SelectFromList.show(nomi, title=titolo, button_name=u"Usa")
        if not scelto:
            return False
        setattr(cfg, chiave, scelto)
    script.save_config()
    return True


def main():
    doc, uidoc, view = revit.doc, revit.uidoc, revit.active_view
    CT.vista_valida(view)
    cfg = script.get_config()
    tipi = CT.tipi_campitura(doc)
    mancante = any(tipi.get(cfg.get_option(k, None)) is None for k, _ in VOCI)
    if EXEC_PARAMS.config_mode or mancante:
        if not impostazioni(doc, cfg) or EXEC_PARAMS.config_mode:
            return

    fatto = CT.scegli_elementi(doc, uidoc, u"gli elementi dello STATO DI FATTO")
    if not fatto:
        return
    progetto = CT.scegli_elementi(doc, uidoc, u"gli elementi dello STATO DI PROGETTO", usa_selezione=False)
    if not progetto:
        return

    s_fatto = [s for e, t in fatto for s in CT.solidi(e, t)]
    s_progetto = [s for e, t in progetto for s in CT.solidi(e, t)]
    tolto, err_t = CT.sottrai(s_fatto, s_progetto)
    aggiunto, err_a = CT.sottrai(s_progetto, s_fatto)
    piano = CT.piano_di_taglio(doc, view)

    with revit.Transaction(u"Campitura differenza"):
        r_tolto = CT.crea(doc, view, tipi[cfg.tolto].Id, CT.facce_di_taglio(tolto, piano))
        r_aggiunto = CT.crea(doc, view, tipi[cfg.aggiunto].Id, CT.facce_di_taglio(aggiunto, piano))

    create = r_tolto + r_aggiunto
    if create:
        uidoc.Selection.SetElementIds(List[DB.ElementId]([r.Id for r in create]))
    if err_t or err_a:
        forms.alert(u"Revit non e' riuscito a sottrarre {} coppie di solidi: in quei punti la differenza "
                    u"puo' essere sbagliata, controllala.".format(err_t + err_a))
    elif not create:
        forms.alert(u"Nessuna differenza sul piano di taglio della vista.")


if __name__ == "__main__":
    main()
