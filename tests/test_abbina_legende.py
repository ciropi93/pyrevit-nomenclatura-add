# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import abbina_legende as AL  # noqa: E402

PORTA_PIANTA = (101, -8)
PORTA_PROSP = (101, -7)
MURO_PIANTA = (202, -8)


def test_abbina_per_tipo_e_vista_del_componente():
    sorgenti = [(PORTA_PIANTA, 1), (PORTA_PROSP, 2), (MURO_PIANTA, 3)]
    destinazioni = [(MURO_PIANTA, 30), (PORTA_PROSP, 20), (PORTA_PIANTA, 10)]
    coppie, senza = AL.abbina(sorgenti, destinazioni)
    assert sorted(coppie) == [(1, 10), (2, 20), (3, 30)]
    assert senza == 0


def test_stesso_tipo_ma_vista_diversa_non_si_abbina():
    coppie, senza = AL.abbina([(PORTA_PIANTA, 1)], [(PORTA_PROSP, 20)])
    assert coppie == []
    assert senza == 1


def test_piu_destinazioni_uguali_ricevono_tutte_e_vale_la_prima_sorgente():
    sorgenti = [(PORTA_PIANTA, 1), (PORTA_PIANTA, 2)]
    destinazioni = [(PORTA_PIANTA, 10), (PORTA_PIANTA, 11), (MURO_PIANTA, 30)]
    coppie, senza = AL.abbina(sorgenti, destinazioni)
    assert coppie == [(1, 10), (1, 11)]
    assert senza == 1


def test_chiave_mancante_ignorata():
    coppie, senza = AL.abbina([(None, 1)], [(None, 10)])
    assert coppie == []
    assert senza == 1
