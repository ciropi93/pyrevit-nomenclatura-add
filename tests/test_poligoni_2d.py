# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from poligoni_2d import differenza, area


def rett(x0, y0, x1, y1):
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]


def area_tot(facce):
    return sum(area(f[0]) + sum(area(h) for h in f[1:]) for f in facce)


def test_sovrapposti():
    assert abs(area_tot(differenza([rett(0, 0, 10, 10)], [rett(5, 5, 15, 15)])) - 75) < 1e-6


def test_lato_coincidente():
    r = differenza([rett(0, 0, 10, 2)], [rett(0, 1, 10, 2)])
    assert len(r) == 1 and len(r[0]) == 1 and len(r[0][0]) == 4
    assert abs(area_tot(r) - 10) < 1e-6


def test_foro():
    r = differenza([rett(0, 0, 10, 10)], [rett(4, 4, 6, 6)])
    assert len(r) == 1 and len(r[0]) == 2
    assert abs(area_tot(r) - 96) < 1e-6


def test_tutto_coperto():
    assert differenza([rett(2, 2, 4, 4)], [rett(0, 0, 10, 10)]) == []


def test_bordo_inclinato_in_comune():
    # fatto: fondo piano, sopra spezzata; progetto: stessa spezzata sopra, fondo piu' alto
    sopra = [(10, 3), (6, 2.5), (3, 3.2), (0, 3)]
    fatto = [[(0, 0), (10, 0)] + sopra]
    progetto = [[(0, 2), (10, 2)] + sopra]
    r = differenza([fatto], [progetto])
    assert abs(area_tot(r) - 20) < 1e-6   # resta la fascia 0..2
    assert differenza([progetto], [fatto]) == []


def test_unione_senza_b():
    r = differenza([rett(0, 0, 2, 2), rett(1, 0, 3, 2)], [])
    assert len(r) == 1 and abs(area_tot(r) - 6) < 1e-6


def test_pezzi_che_si_toccano_in_un_punto_restano_separati():
    # Revit rifiuta i contorni "a otto": ogni pezzo deve avere il suo anello
    r = differenza([rett(0, 0, 2, 2), rett(2, 2, 4, 4)], [])
    assert sorted(len(f[0]) for f in r) == [4, 4] and len(r) == 2


def test_incrocio_tra_fatto_e_progetto():
    # le linee superiori si incrociano: il tolto sono due triangoli che si toccano nel punto d'incrocio
    fatto = [[(0, 0), (4, 0), (4, 1), (0, 3)]]
    progetto = [[(0, 0), (4, 0), (4, 3), (0, 1)]]
    r = differenza([fatto], [progetto])
    assert all(len(set(f[0])) == len(f[0]) for f in r)
    assert abs(area_tot(r) - 2) < 1e-6


def test_vertici_quasi_allineati_non_lasciano_strisce():
    # il progetto copre fino a 8.0003 invece di 8: senza aggancio resta una striscia di 0.1 mm
    # tra foro e contorno, che Revit rifiuta; deve uscire una sola forma a C
    r = differenza([rett(0, 0, 10, 4)], [rett(2, 1, 8, 3), rett(8.0003, 0, 10, 4)])
    assert len(r) == 1 and len(r[0]) == 1
    assert abs(area_tot(r) - 20) < 1e-2
