# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import allinea_in_tavola as AIT  # noqa: E402
import tasti_contestuali as TC  # noqa: E402


def _comandi(gruppi):
    return [c for _, tasti in gruppi for c, _, _ in tasti]


def _nomi(gruppi):
    return [nome for nome, _ in gruppi]


def test_viste_distinte_sfondo_conta_come_madre():
    # 11 e' lo sfondo di 10: madre + sfondo selezionati = una sola vista
    assert TC.viste_distinte([10, 11], {11: 10}) == [10]
    assert TC.viste_distinte([11, 20, 20], {11: 10}) == [10, 20]
    assert TC.viste_distinte([], {}) == []


def test_niente_tasti_senza_viste():
    assert TC.comandi_per_selezione(0) == []
    # linea di sezione senza sfondo (fuori tavola)
    assert TC.comandi_per_selezione(1, in_tavola=False, sezione_con_sfondo=False) == []


def test_linea_di_sezione_con_sfondo():
    gruppi = TC.comandi_per_selezione(1, in_tavola=False, sezione_con_sfondo=True)
    assert _nomi(gruppi) == [u"Sezione"]
    assert _comandi(gruppi) == [TC.SEZIONE_APRI, TC.SEZIONE_SINCRONIZZA]


def test_una_vista_in_tavola():
    gruppi = TC.comandi_per_selezione(1)
    assert _nomi(gruppi) == [u"Titolo"]
    assert set(_comandi(gruppi)) == {u"titolo_bordo_sinistro", u"titolo_larghezza_vista"}
    gruppi = TC.comandi_per_selezione(1, sezione_con_sfondo=True)
    assert _nomi(gruppi) == [u"Sezione", u"Titolo"]


def test_piu_viste_in_tavola():
    due = TC.comandi_per_selezione(2, sezione_con_sfondo=True)
    assert _nomi(due) == [u"Titoli", u"Allinea viste"]  # niente tasti sezione con 2 viste
    assert u"distribuisci_x" not in _comandi(due)
    tre = TC.comandi_per_selezione(3)
    assert _nomi(tre) == [u"Titoli", u"Allinea viste", u"Distribuisci"]


def test_comandi_esistono_negli_strumenti_di_allineamento():
    validi = set(AIT._COMANDO_TO_OPZ) | {
        u"titolo_larghezza_vista", u"titolo_bordo_sinistro", u"distribuisci_x", u"distribuisci_y",
        TC.SEZIONE_APRI, TC.SEZIONE_SINCRONIZZA,
    }
    for gruppi in (TC.comandi_per_selezione(3, sezione_con_sfondo=True),
                   TC.comandi_per_selezione(1, sezione_con_sfondo=True)):
        for c in _comandi(gruppi):
            assert c in validi, c
