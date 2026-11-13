# -*- coding: utf-8 -*-
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "CDVTools.extension", "lib"))

import profondita_sezione as PS  # noqa: E402


def test_conversione_metri_piedi():
    piedi = PS.metri_a_piedi(3.048)
    assert abs(piedi - 10.0) < 1e-9
    assert abs(PS.piedi_a_metri(piedi) - 3.048) < 1e-9


def test_calcola_profondita_sfondo_totale():
    spessore, totale = PS.calcola_profondita_sfondo(5.0, 20.0, u"totale")
    assert abs(spessore - 15.0) < 1e-9
    assert abs(totale - 20.0) < 1e-9


def test_calcola_profondita_sfondo_aggiuntiva():
    spessore, totale = PS.calcola_profondita_sfondo(5.0, 12.5, u"aggiuntiva")
    assert abs(spessore - 12.5) < 1e-9
    assert abs(totale - 17.5) < 1e-9


def test_calcola_profondita_sfondo_errori():
    with pytest.raises(ValueError):
        PS.calcola_profondita_sfondo(5.0, 5.0, u"totale")
    with pytest.raises(ValueError):
        PS.calcola_profondita_sfondo(5.0, 3.0, u"totale")
    with pytest.raises(ValueError):
        PS.calcola_profondita_sfondo(5.0, 0.0, u"aggiuntiva")
    with pytest.raises(ValueError):
        PS.calcola_profondita_sfondo(5.0, -2.0, u"aggiuntiva")


def test_origine_piano_sfondo():
    # ViewDirection = (0, -1, 0): la vista guarda verso +Y, quindi indietro e' +Y
    ox, oy, oz = PS.origine_piano_sfondo((10.0, 2.0, 1.0), (0.0, -1.0, 0.0), 5.0)
    assert abs(ox - 10.0) < 1e-9
    assert abs(oy - 7.0) < 1e-9
    assert abs(oz - 1.0) < 1e-9


def test_angolo_rotazione_xy():
    assert abs(PS.angolo_rotazione_xy((1.0, 0.0), (1.0, 0.0))) < 1e-9
    assert abs(PS.angolo_rotazione_xy((1.0, 0.0), (0.0, 1.0)) - math.pi / 2.0) < 1e-9
    assert abs(PS.angolo_rotazione_xy((1.0, 0.0), (0.0, -1.0)) + math.pi / 2.0) < 1e-9
    assert abs(abs(PS.angolo_rotazione_xy((1.0, 0.0), (-1.0, 0.0))) - math.pi) < 1e-9


def test_nome_vista_sfondo():
    assert PS.nome_vista_sfondo(u"Sezione A-A") == u"Sezione A-A (Sfondo)"
    assert PS.nome_vista_sfondo(u"Sezione A-A (Sfondo)") == u"Sezione A-A (Sfondo)"
