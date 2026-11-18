# -*- coding: utf-8 -*-
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import ritaglio_immagine as RI  # noqa: E402


def test_rettangolo_pixel_ordina_e_limita():
    # trascinato da destra-basso a sinistra-alto, oltre il bordo
    assert RI.rettangolo_pixel(120, 90, -10, 10, 2.0, 200, 100) == (0, 20, 200, 80)


def test_rettangolo_pixel_troppo_piccolo():
    with pytest.raises(ValueError):
        RI.rettangolo_pixel(10, 10, 10.4, 50, 1.0, 200, 100)


def test_nuova_geometria_quarto_in_alto_a_destra():
    # immagine 2x1 (piedi) da 200x100 px, tengo il quarto in alto a destra
    w, h, dx, dy = RI.nuova_geometria(2.0, 1.0, 200, 100, (100, 0, 100, 50))
    assert (w, h) == (1.0, 0.5)
    assert abs(dx - 0.5) < 1e-9 and abs(dy - 0.25) < 1e-9


def test_geometria_completa_inverte_nuova_geometria():
    rett = (30, 10, 120, 60)
    w, h, dx, dy = RI.nuova_geometria(2.0, 1.0, 200, 100, rett)
    piena_l, piena_a, dx2, dy2 = RI.geometria_completa(w, h, 200, 100, rett)
    assert abs(piena_l - 2.0) < 1e-9 and abs(piena_a - 1.0) < 1e-9
    assert abs(dx2 - dx) < 1e-9 and abs(dy2 - dy) < 1e-9


def test_nome_univoco():
    assert RI.nome_univoco(u"foto", [u"foto_ritaglio_1", u"FOTO_RITAGLIO_2"]) == u"foto_ritaglio_3"
