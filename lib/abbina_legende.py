# -*- coding: utf-8 -*-
"""Abbina i componenti di due legende (senza API Revit).

Ogni legenda ha i suoi componenti, con id diversi anche quando disegnano la stessa cosa.
Due componenti si corrispondono se mostrano lo stesso tipo (parametro "Componente") con la
stessa vista del componente (Pianta, Prospetto anteriore, ...): la chiave e' la coppia
(id del tipo, vista del componente).
"""


def abbina(sorgenti, destinazioni):
    """Coppie (id_sorgente, id_destinazione) dei componenti con la stessa chiave.

    sorgenti, destinazioni: liste di (chiave, id). Se nella sorgente la stessa chiave
    compare piu' volte vale la prima; nella destinazione ogni componente con quella
    chiave riceve la grafica. Ritorna (coppie, n_destinazioni_senza_corrispondente).
    """
    per_chiave = {}
    for chiave, eid in sorgenti:
        if chiave is not None and chiave not in per_chiave:
            per_chiave[chiave] = eid
    coppie, senza = [], 0
    for chiave, eid in destinazioni:
        if chiave in per_chiave:
            coppie.append((per_chiave[chiave], eid))
        else:
            senza += 1
    return coppie, senza
