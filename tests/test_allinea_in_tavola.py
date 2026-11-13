# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "CDVTools.extension", "lib"))

import allinea_in_tavola as AIT  # noqa: E402


def test_calcola_delta_box_x():
    ref = (10.0, 5.0, 30.0, 15.0)   # centro X=20
    tgt = (14.0, 2.0, 22.0, 8.0)    # centro X=18

    assert AIT.calcola_delta_box(ref, tgt, u"nessuno", u"nessuno") == (0.0, 0.0)
    assert AIT.calcola_delta_box(ref, tgt, u"sinistra", u"nessuno") == (-4.0, 0.0)
    assert AIT.calcola_delta_box(ref, tgt, u"centro", u"nessuno") == (2.0, 0.0)
    assert AIT.calcola_delta_box(ref, tgt, u"destra", u"nessuno") == (8.0, 0.0)


def test_calcola_delta_box_y():
    ref = (10.0, 5.0, 30.0, 15.0)   # centro Y=10
    tgt = (14.0, 2.0, 22.0, 8.0)    # centro Y=5

    assert AIT.calcola_delta_box(ref, tgt, u"nessuno", u"basso") == (0.0, 3.0)
    assert AIT.calcola_delta_box(ref, tgt, u"nessuno", u"centro") == (0.0, 5.0)
    assert AIT.calcola_delta_box(ref, tgt, u"nessuno", u"alto") == (0.0, 7.0)


def test_calcola_delta_box_modello():
    ref = (10.0, 5.0, 30.0, 15.0)
    tgt = (14.0, 2.0, 22.0, 8.0)
    dx, dy = AIT.calcola_delta_box(
        ref, tgt, u"modello", u"modello",
        ref_model_xy=(12.5, 9.0),
        tgt_model_xy=(15.5, 6.0),
    )
    assert abs(dx - (-3.0)) < 1e-9
    assert abs(dy - 3.0) < 1e-9


def test_calcola_nuovo_label_offset():
    ref_min = (10.0, 20.0)
    ref_off = (1.5, -0.5)   # posizione assoluta titolo: (11.5, 19.5)
    tgt_min = (25.0, 18.0)
    tgt_off = (0.2, -1.0)

    assert AIT.calcola_nuovo_label_offset(
        ref_min, ref_off, tgt_min, tgt_off, u"nessuno", u"nessuno"
    ) == (0.2, -1.0)

    ox, oy = AIT.calcola_nuovo_label_offset(
        ref_min, ref_off, tgt_min, tgt_off, u"foglio", u"foglio"
    )
    assert abs((tgt_min[0] + ox) - 11.5) < 1e-9
    assert abs((tgt_min[1] + oy) - 19.5) < 1e-9

    assert AIT.calcola_nuovo_label_offset(
        ref_min, ref_off, tgt_min, tgt_off, u"relativo", u"relativo"
    ) == (1.5, -0.5)

    assert AIT.calcola_nuovo_label_offset(
        ref_min, ref_off, tgt_min, tgt_off, u"bordo_sinistro", u"nessuno"
    ) == (0.0, -1.0)


def test_calcola_nuovo_label_offset_con_annotazioni_sporgenti():
    # ref: outline parte a X=8, Y=19 (annotazioni sporgenti), puro CropBox parte a X=10, Y=20.
    # ref_off = (2.0, -0.5) -> ref_abs = (10.0, 18.5) -> relativo al crop: (0.0, -1.5).
    # tgt: outline parte a X=22, Y=17 (annotazioni diverse), puro CropBox parte a X=25, Y=18.
    ref_box_min = (8.0, 19.0)
    ref_crop_min = (10.0, 20.0)
    ref_off = (2.0, -0.5)   # ref_abs = (10.0, 18.5) -> relativo al crop: (0.0, -1.5)

    tgt_box_min = (22.0, 17.0)
    tgt_crop_min = (25.0, 18.0)
    tgt_off = (0.0, 0.0)

    # bordo_sinistro: titolo va a X=25.0 (tgt_crop_min.X); Y relativo va a 18.0 - 1.5 = 16.5
    ox, oy = AIT.calcola_nuovo_label_offset(
        ref_box_min, ref_off, tgt_box_min, tgt_off,
        modo_titolo_x=u"bordo_sinistro", modo_titolo_y=u"relativo",
        ref_crop_min=ref_crop_min, tgt_crop_min=tgt_crop_min,
    )
    assert abs((tgt_box_min[0] + ox) - 25.0) < 1e-9
    assert abs((tgt_box_min[1] + oy) - 16.5) < 1e-9

    # relativo su X e Y rispetto al puro ritaglio (+0.5 su X, -1.5 su Y -> 25.5, 16.5)
    ox_r, oy_r = AIT.calcola_nuovo_label_offset(
        ref_box_min, (2.5, -0.5), tgt_box_min, tgt_off,
        modo_titolo_x=u"relativo", modo_titolo_y=u"relativo",
        ref_crop_min=ref_crop_min, tgt_crop_min=tgt_crop_min,
    )
    assert abs((tgt_box_min[0] + ox_r) - 25.5) < 1e-9
    assert abs((tgt_box_min[1] + oy_r) - 16.5) < 1e-9


def test_box_ritaglio_foglio_mock():
    class FakeXYZ(object):
        def __init__(self, x, y, z=0.0):
            self.X, self.Y, self.Z = x, y, z

    class FakeTransform(object):
        def OfPoint(self, pt):
            return FakeXYZ(10.0 + pt.X, 20.0 + pt.Y, pt.Z)

    class FakeCropBox(object):
        Min = FakeXYZ(-100.0, -50.0, 0.0)
        Max = FakeXYZ(100.0, 50.0, 0.0)

    class FakeOutline(object):
        # Outline gonfiato dalle annotazioni rispetto al CropBox
        MinimumPoint = FakeXYZ(7.0, 18.0, 0.0)
        MaximumPoint = FakeXYZ(13.0, 22.0, 0.0)

    class FakeView(object):
        CropBox = FakeCropBox()
        Scale = 100

    class FakeViewport(object):
        ViewId = 1

        def HasViewportTransforms(self):
            return True

        def GetProjectionToSheetTransform(self):
            return FakeTransform()

        def GetBoxOutline(self):
            return FakeOutline()

    class FakeDoc(object):
        def GetElement(self, eid):
            return FakeView()

    orig_db = AIT.DB
    try:
        class FakeDB(object):
            XYZ = FakeXYZ
        AIT.DB = FakeDB
        box = AIT._box_ritaglio_foglio(FakeDoc(), FakeViewport())
        assert box == (9.0, 19.5, 11.0, 20.5)
    finally:
        AIT.DB = orig_db


def test_calcola_distribuzione_x():
    # Box A: [0..4], Box B: [5..9] (da spostare a [10..14]), Box C: [20..24]
    # span=24, sum_sizes=12 -> gap=6: A=[0..4], B=[10..14], C=[20..24] -> dx_B = +5
    boxes = [
        (1, 0.0, 0.0, 4.0, 2.0),
        (2, 5.0, 0.0, 9.0, 2.0),
        (3, 20.0, 0.0, 24.0, 2.0),
    ]
    d = AIT.calcola_distribuzione(boxes, asse=u"x")
    assert d[1] == 0.0
    assert d[3] == 0.0
    assert abs(d[2] - 5.0) < 1e-9


def test_calcola_distribuzione_y_sovrapposti():
    # span <= sum_sizes: distribuisce uniformemente i centri
    boxes = [
        (1, 0.0, 0.0, 4.0, 10.0),   # centro 5
        (2, 0.0, 2.0, 4.0, 12.0),   # centro 7 -> deve andare a centro 10 (+3)
        (3, 0.0, 10.0, 4.0, 20.0),  # centro 15
    ]
    d = AIT.calcola_distribuzione(boxes, asse=u"y")
    assert d[1] == 0.0
    assert d[3] == 0.0
    assert abs(d[2] - 3.0) < 1e-9


def test_scegli_indice_riferimento():
    boxes = [
        (10.0, 5.0, 20.0, 15.0),
        (2.0, 20.0, 12.0, 30.0),
        (25.0, 1.0, 40.0, 8.0),
    ]
    assert AIT.scegli_indice_riferimento(boxes, u"box_sinistra") == 1
    assert AIT.scegli_indice_riferimento(boxes, u"titolo_colonna") == 1
    assert AIT.scegli_indice_riferimento(boxes, u"box_destra") == 2
    assert AIT.scegli_indice_riferimento(boxes, u"box_alto") == 1
    assert AIT.scegli_indice_riferimento(boxes, u"box_basso") == 2
    assert AIT.scegli_indice_riferimento(boxes, u"titolo_riga") == 2
