# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import aggiorna_modello as AM  # noqa: E402
import memoria_finestre as MF  # noqa: E402


def test_testi():
    assert AM.testo_viste(0) == u"nessuna vista"
    assert AM.testo_viste(1) == u"1 vista"
    assert AM.testo_viste(12) == u"12 viste"
    assert AM.nota_impatto(0) == u"Nessun'altra vista usa questo modello."
    assert u"12 viste" in AM.nota_impatto(12)
    assert AM.testo_pulsante(u"Piante 1:100", False) == u"Aggiorna Piante 1:100"
    assert AM.testo_pulsante(None, False) == u"Scegli un modello"
    assert AM.testo_pulsante(u"x", True) == u"Crea modello"


def test_nome_nuovo_modello():
    assert AM.nome_nuovo_modello(u"Pianta PT", []) == u"Pianta PT - Modello"
    assert AM.nome_nuovo_modello(u"Pianta PT", [u"Pianta PT - Modello"]) == u"Pianta PT - Modello (2)"
    assert AM.nome_nuovo_modello(u"P", [u"P - Modello", u"P - Modello (2)"]) == u"P - Modello (3)"


def test_indice_proposto_solo_se_ricordato():
    assert AM.indice_proposto([u"a", u"b", u"c"], u"b") == 1
    assert AM.indice_proposto([u"a", u"b"], u"z") is None
    assert AM.indice_proposto([u"a", u"b"], None) is None


def test_memoria_valori(tmp_path):
    p = str(tmp_path / u"finestre.json")
    assert MF.valore(u"cmd", u"k", percorso=p) is None
    MF.imposta_valore(u"cmd", u"k", u"v1", p)
    MF.imposta_valore(u"cmd", u"k2", u"v2", p)
    assert MF.valore(u"cmd", u"k", percorso=p) == u"v1"
    MF.imposta_valore(u"cmd", u"k", None, p)
    assert MF.valore(u"cmd", u"k", percorso=p) is None
    assert MF.valore(u"cmd", u"k2", percorso=p) == u"v2"
