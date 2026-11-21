# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import crea_filtro as CF  # noqa: E402


def test_ordine_proposte():
    proposte = [(u"Larghezza", True), (u"Commenti", False), (u"Nome tipo", True), (u"Livello", True)]
    ordinate = [p[0] for p in CF.ordina(proposte)]
    assert ordinate == [u"Nome tipo", u"Livello", u"Larghezza", u"Commenti"]


def test_descrivi_valori():
    assert CF.descrivi_valori([u"A", u"A"]) == u"A"
    assert CF.descrivi_valori([u"B", u"A"]) == u"A o B"
    assert CF.descrivi_valori([u"C", u"A", u"B"]) == u"A, B o C"
    assert CF.descrivi_valori([u"A", u"B", u"C", u"D", u"E"]) == u"5 valori: A, B, C..."


def test_nome_filtro():
    assert CF.nome_filtro([u"Muri"], [u"Muro esterno 30"]) == u"Muri - Muro esterno 30"
    assert CF.nome_filtro([u"Muri", u"Pavimenti"], [u"a", u"b"]) == u"Muri e Pavimenti - 2 valori"
    assert CF.nome_filtro([u"Muri"], [u"Tipo [A]: B"]) == u"Muri - Tipo A B"


def test_nome_libero():
    assert CF.nome_libero(u"F", []) == u"F"
    assert CF.nome_libero(u"F", [u"F", u"F (2)"]) == u"F (3)"
