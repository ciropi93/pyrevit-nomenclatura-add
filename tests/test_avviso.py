# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import avviso as AV  # noqa: E402


def test_posizione_in_basso_a_destra_nella_vista():
    # vista tra il browser (a sinistra) e il pannello Proprieta' (a destra)
    vista = (300, 150, 1500, 900)
    assert AV.posizione_avviso(vista, 200, 22) == (1500 - 10 - 200, 900 - 10 - 22)


def test_posizione_vista_piccola_resta_dentro():
    assert AV.posizione_avviso((100, 100, 250, 120), 200, 22) == (100, 100)


def test_posizione_monitor_a_sinistra():
    x, y = AV.posizione_avviso((-1920, 0, -100, 1000), 200, 22)
    assert (x, y) == (-310, 968)


def test_durata_errore_piu_lunga():
    assert AV.durata_avviso(AV.ERRORE) > AV.durata_avviso(AV.INFO)
    assert AV.durata_avviso(u"sconosciuto") == AV.durata_avviso(AV.INFO)
    assert AV.livello_valido(u"sconosciuto") == AV.INFO


def test_una_riga():
    assert AV.una_riga(u"Sfondo sincronizzato.\nTavole allineate: 2.") == \
        u"Sfondo sincronizzato. · Tavole allineate: 2."
    assert AV.una_riga(u"  troppi   spazi \n\n") == u"troppi spazi"
    assert AV.una_riga(None) == u""
    assert AV.una_riga(b"testo") == u"testo"


def test_contatore():
    assert AV.testo_con_contatore(u"Mezzitoni attivati.", 1) == u"Mezzitoni attivati."
    assert AV.testo_con_contatore(u"Mezzitoni attivati.", 3) == u"Mezzitoni attivati.  ×3"


def test_con_errori():
    assert AV.con_errori(u"Allineate 4 viste", []) == u"Allineate 4 viste"
    assert AV.con_errori(u"Allineate 4 viste", [u"A: x", u"B: y"]) == \
        u"Allineate 4 viste · 2 con errori: A: x; B: y"
    testo = AV.con_errori(u"Allineate 1 vista", [u"A", u"B", u"C"])
    assert testo.endswith(u"3 con errori: A; B; …")
    assert AV.con_errori(u"Impossibile allineare", [u"A\nriga due"]) == \
        u"Impossibile allineare · 1 con errori: A · riga due"
