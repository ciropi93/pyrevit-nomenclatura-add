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


def test_ogni_comando_ha_la_sua_icona():
    for n in (1, 3):
        for gruppi in (TC.comandi_per_selezione(n, sezione_con_sfondo=True),
                       TC.comandi_per_selezione(n, in_tavola=False, sezione_con_sfondo=True)):
            for c in _comandi(gruppi):
                assert TC.ICONE.get(c), c


FINESTRA = (100, 50, 900, 650)          # area della vista sullo schermo (pixel)
ZOOM = ((0.0, 0.0), (8.0, 6.0))          # 1 unita' = 100 pixel


def test_proietta_angoli_e_asse_y_rovesciato():
    assert TC.proietta((0.0, 0.0), ZOOM, FINESTRA) == (100, 650)
    assert TC.proietta((8.0, 6.0), ZOOM, FINESTRA) == (900, 50)
    assert TC.riquadro_schermo([(1.0, 1.0), (3.0, 4.0)], ZOOM, FINESTRA) == (200, 250, 400, 550)
    assert TC.riquadro_schermo([], ZOOM, FINESTRA) is None


def test_striscia_sopra_il_bordo_superiore():
    assert TC.posizione_striscia((200, 250, 400, 550), FINESTRA, 120, 24) == (200, 223)


def test_striscia_sotto_se_sopra_non_ce_posto():
    assert TC.posizione_striscia((200, 60, 400, 300), FINESTRA, 120, 24) == (200, 303)


def test_striscia_dentro_se_la_selezione_riempie_la_vista():
    assert TC.posizione_striscia((50, 20, 950, 700), FINESTRA, 120, 24) == (100, 53)


def test_striscia_resta_nella_vista_in_orizzontale():
    x, _ = TC.posizione_striscia((850, 250, 1200, 550), FINESTRA, 120, 24)
    assert x == 900 - 120


def test_niente_striscia_se_la_selezione_e_fuori_vista():
    assert TC.posizione_striscia((1000, 250, 1200, 550), FINESTRA, 120, 24) is None
    assert TC.posizione_striscia(None, FINESTRA, 120, 24) is None
