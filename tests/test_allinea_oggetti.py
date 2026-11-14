# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import allinea_oggetti as AO  # noqa: E402
import tasti_contestuali as TC  # noqa: E402

# (id, u_min, v_min, u_max, v_max)
BOXES = [(1, 0.0, 0.0, 2.0, 1.0), (2, 5.0, 3.0, 6.0, 5.0), (3, 10.0, 1.0, 14.0, 2.0)]


def test_allinea_ai_bordi_sull_oggetto_piu_esterno():
    assert AO.spostamenti(BOXES, u"ogg_sinistra") == {2: (-5.0, 0.0), 3: (-10.0, 0.0)}
    assert AO.spostamenti(BOXES, u"ogg_destra") == {1: (12.0, 0.0), 2: (8.0, 0.0)}
    assert AO.spostamenti(BOXES, u"ogg_alto") == {1: (0.0, 4.0), 3: (0.0, 3.0)}
    assert AO.spostamenti(BOXES, u"ogg_basso") == {2: (0.0, -3.0), 3: (0.0, -1.0)}


def test_allinea_ai_centri_sul_centro_del_gruppo():
    # gruppo da u=0 a u=14: centro 7
    assert AO.spostamenti(BOXES, u"ogg_centro_x") == {1: (6.0, 0.0), 2: (1.5, 0.0), 3: (-5.0, 0.0)}
    # gruppo da v=0 a v=5: centro 2.5
    assert AO.spostamenti(BOXES, u"ogg_centro_y") == {1: (0.0, 2.0), 2: (0.0, -1.5), 3: (0.0, 1.0)}


def test_distribuisci_lascia_fermi_gli_estremi():
    # spazio libero 14 - (2+1+4) = 7 -> 3.5 tra ciascuno: il secondo va da 5.5 a 6.5
    assert AO.spostamenti(BOXES, u"ogg_distribuisci_x") == {2: (0.5, 0.0)}
    assert AO.spostamenti(BOXES[:2], u"ogg_distribuisci_x") == {}


def test_tasti_compaiono_con_piu_oggetti():
    nomi = lambda n: [g for g, _ in TC.comandi_per_selezione(0, in_tavola=False, n_oggetti=n)]
    assert nomi(1) == []
    assert nomi(2) == [u"Allinea oggetti"]
    assert nomi(3) == [u"Allinea oggetti", u"Distribuisci oggetti"]
    for _, tasti in TC.comandi_per_selezione(0, in_tavola=False, n_oggetti=3):
        for c, _, _ in tasti:
            assert c in AO.COMANDI and TC.ICONE.get(c), c
