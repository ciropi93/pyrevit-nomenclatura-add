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


def test_bersagli_per_tutti_gli_oggetti():
    # bordo sinistro di tutti a 0, anche di chi resta fermo
    assert AO.bersagli(BOXES, u"ogg_sinistra") == {1: 0.0, 2: 0.0, 3: 0.0}
    # bordo destro di tutti a 14; centri verticali a 2.5
    assert AO.bersagli(BOXES, u"ogg_destra") == {1: 14.0, 2: 14.0, 3: 14.0}
    assert AO.bersagli(BOXES, u"ogg_centro_y") == {1: 2.5, 2: 2.5, 3: 2.5}
    # distribuisci: gli estremi restano dove sono, quello in mezzo va a 5.5
    assert AO.bersagli(BOXES, u"ogg_distribuisci_x") == {1: 0.0, 2: 5.5, 3: 10.0}


def test_residui_correggono_gli_oggetti_trascinati():
    # muro (1), la sua porta (2) e un altro muro (3) allineati a destra: u_max = 14
    obiettivi = AO.bersagli(BOXES, u"ogg_destra")
    # primo giro: il muro 1 si sposta di +12 e trascina la porta, poi la porta riceve
    # anche il suo +8 calcolato sulla posizione vecchia: finisce a 26 invece che a 14
    dopo = [(1, 12.0, 0.0, 14.0, 1.0), (2, 25.0, 3.0, 26.0, 5.0), (3, 10.0, 1.0, 14.0, 2.0)]
    assert AO.residui(dopo, obiettivi, u"ogg_destra") == {2: (-12.0, 0.0)}
    # tutto a posto: nessun residuo
    a_posto = [(1, 12.0, 0.0, 14.0, 1.0), (2, 13.0, 3.0, 14.0, 5.0), (3, 10.0, 1.0, 14.0, 2.0)]
    assert AO.residui(a_posto, obiettivi, u"ogg_destra") == {}


def test_residui_guardano_solo_il_lato_del_comando():
    # dopo lo spostamento l'ingombro del muro 1 si e' allargato a sinistra (giunzione) e
    # si e' alzato un po': il bordo destro e' a posto, quindi non c'e' niente da correggere
    obiettivi = AO.bersagli(BOXES, u"ogg_destra")
    dopo = [(1, 11.7, 0.2, 14.0, 1.2), (2, 13.0, 3.0, 14.0, 5.0), (3, 10.0, 1.0, 14.0, 2.0)]
    assert AO.residui(dopo, obiettivi, u"ogg_destra") == {}


def test_niente_allinea_nelle_viste_3d():
    for tipo in (u"FloorPlan", u"CeilingPlan", u"Section", u"Elevation", u"DraftingView"):
        assert AO.vista_ammessa(tipo), tipo
    for tipo in (u"ThreeD", u"Schedule", u"DrawingSheet", u"Walkthrough"):
        assert not AO.vista_ammessa(tipo), tipo


def test_icone_oggetti_uguali_a_quelle_delle_viste():
    assert TC.ICONE[u"ogg_sinistra"] is TC.ICONE[u"box_sinistra"]
    assert TC.ICONE[u"ogg_distribuisci_y"] is TC.ICONE[u"distribuisci_y"]
