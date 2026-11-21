# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import cambia_livello as CL  # noqa: E402


def test_quota_testo():
    assert CL.quota_testo(0.0) == u"0.00 m"
    assert CL.quota_testo(3.4 / 0.3048) == u"+3.40 m"
    assert CL.quota_testo(-3.2 / 0.3048) == u"-3.20 m"


def test_livello_proposto_sopra_poi_sotto():
    q = [-3.2, 0.0, 3.4, 6.8]
    assert CL.livello_proposto(q, 1) == 2
    assert CL.livello_proposto(q, 3) == 2
    assert CL.livello_proposto(q, None) == 0
    assert CL.livello_proposto([0.0], 0) is None
    assert CL.livello_proposto([], None) is None


def test_nome_nuova_vista():
    assert CL.nome_nuova_vista(u"Pianta Piano Terra", u"Piano Terra", u"Piano Primo", False) == \
        u"Pianta Piano Primo"
    assert CL.nome_nuova_vista(u"Pianta Piano Terra", u"Piano Terra", u"Piano Primo", True) == \
        u"Pianta Piano Primo"
    assert CL.nome_nuova_vista(u"Arredi", u"Piano Terra", u"Piano Primo", False) == u"Arredi"
    assert CL.nome_nuova_vista(u"Arredi", u"Piano Terra", u"Piano Primo", True) == u"Arredi - Piano Primo"
    assert CL.nome_nuova_vista(u"Arredi", u"", u"Piano Primo", False) == u"Arredi"


def test_testo_pulsante():
    assert CL.testo_pulsante(u"Piano Primo", False) == u"Sposta su Piano Primo"
    assert CL.testo_pulsante(u"Piano Primo", True) == u"Duplica su Piano Primo"
    assert CL.testo_pulsante(None, False) == u"Scegli un livello"
