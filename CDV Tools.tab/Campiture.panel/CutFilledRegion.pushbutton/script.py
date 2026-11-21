# -*- coding: utf-8 -*-
"""Crea una campitura sulla parte sezionata degli elementi selezionati (pianta o sezione).
Shift+clic: impostazioni (campiture singole o unica, tipo campitura)."""

from System.Collections.Generic import List
from pyrevit import revit, DB, forms, script, EXEC_PARAMS
import avviso_wpf as AVW
import campiture_taglio as CT

SINGOLE = u"Campiture singole (una per elemento)"
UNICA = u"Campitura unica (tutti gli elementi uniti)"


def campiture(doc, view, tipo_id, gruppi, unica):
    """gruppi: lista di liste di solidi (una per elemento). Ritorna le campiture create."""
    piano = CT.piano_di_taglio(doc, view)
    if unica:
        gruppi = [[s for g in gruppi for s in g]]
    return [r for g in gruppi for r in CT.crea(doc, view, tipo_id, CT.facce_di_taglio(g, piano))]


def impostazioni(doc, cfg):
    """Chiede modo e tipo campitura e li salva. Ritorna False se annullato."""
    modo = forms.CommandSwitchWindow.show([SINGOLE, UNICA], message=u"Come creare le campiture?")
    if not modo:
        return False
    tipo = forms.SelectFromList.show(sorted(CT.tipi_campitura(doc)), title=u"Tipo campitura", button_name=u"Usa")
    if not tipo:
        return False
    cfg.unica = modo == UNICA
    cfg.tipo = tipo
    script.save_config()
    return True


def main():
    doc, uidoc, view = revit.doc, revit.uidoc, revit.active_view
    CT.vista_valida(view)
    cfg = script.get_config()
    if EXEC_PARAMS.config_mode or cfg.get_option("tipo", None) is None:
        if not impostazioni(doc, cfg) or EXEC_PARAMS.config_mode:
            return
    tipo = CT.tipi_campitura(doc).get(cfg.tipo)
    if tipo is None:
        AVW.attenzione(u"Il tipo di campitura %s non c'è più: scegline un altro" % cfg.tipo)
        if not impostazioni(doc, cfg):
            return
        tipo = CT.tipi_campitura(doc)[cfg.tipo]

    elementi = CT.scegli_elementi(doc, uidoc)
    if not elementi:
        return
    gruppi = [CT.solidi(e, t) for e, t in elementi]
    with revit.Transaction(u"Campitura sezionato"):
        create = campiture(doc, view, tipo.Id, gruppi, cfg.unica)
    if not create:
        AVW.errore(u"Nessuna parte tagliata: gli elementi sono tagliati dal piano della vista?")
        return
    uidoc.Selection.SetElementIds(List[DB.ElementId]([r.Id for r in create]))
    AVW.mostra(u"Campiture create: %d (Maiusc+clic: impostazioni)" % len(create))


if __name__ == "__main__":
    main()
