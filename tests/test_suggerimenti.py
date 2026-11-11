# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "NomenclaturaADD.extension", "lib"))

import pytest  # noqa: E402

from nomenclatura import regole as R  # noqa: E402
from nomenclatura import suggerimenti as SG  # noqa: E402


@pytest.fixture(scope="module")
def ctx():
    return R.Contesto()


STRATI_MURO = [
    {"materiale": "1-VER-PitturaSilossanica", "spessore": 0},
    {"materiale": "1-INC-IntonacoCalce_20mm", "spessore": 20},
    {"materiale": "1-CLC-STR-CA_C32/40_250mm", "spessore": 250},
    {"materiale": "1-INC-IntonacoCalce_20mm", "spessore": 20},
    {"materiale": "1-VER-PitturaLavabile", "spessore": 0},
]


def muro(nome, **kw):
    d = {"bic": "OST_Walls", "nome": nome, "funzione": "EST", "strati": STRATI_MURO, "spessore": 290}
    d.update(kw)
    return d


def test_muro_coerente(ctx):
    assert SG.controlla_coerenza(muro("MUR-EST-VER_INC_CLC_INC_VER_290mm-01"), ctx).ok


def test_muro_spessore_sbagliato(ctx):
    r = SG.controlla_coerenza(muro("MUR-EST-VER_INC_CLC_INC_VER_300mm-01"), ctx)
    assert r.ha_errori and "spessore" in r.messaggio()
    assert r.proposta == "MUR-EST-VER_INC_CLC_INC_VER_290mm-01"


def test_muro_strati_diversi(ctx):
    r = SG.controlla_coerenza(muro("MUR-EST-INC_MRT_INC_290mm-01"), ctx)
    assert r.ha_errori and "strati" in r.messaggio()


def test_muro_funzione_diversa(ctx):
    r = SG.controlla_coerenza(muro("MUR-INT-VER_INC_CLC_INC_VER_290mm-01"), ctx)
    assert r.ha_errori
    assert r.proposta == "MUR-EST-VER_INC_CLC_INC_VER_290mm-01"


def test_materiale_spessore_diverso_dallo_strato(ctx):
    strati = [dict(s) for s in STRATI_MURO]
    strati[2]["spessore"] = 300
    r = SG.controlla_coerenza(muro("MUR-EST-VER_INC_CLC_INC_VER_340mm-01", strati=strati, spessore=340), ctx)
    assert r.ha_errori and "250mm" in r.messaggio()


def test_materiale_non_codificato(ctx):
    strati = [{"materiale": "Calcestruzzo", "spessore": 300}]
    r = SG.controlla_coerenza(muro("MUR-EST-CLC_300mm-01", strati=strati, spessore=300), ctx)
    assert r.livello == R.AVVISO


def test_suggerisci_da_nome_revit(ctx):
    p = SG.suggerisci_tipo(muro("Muro di base 30cm"), ctx, occupati={"MUR-EST-VER_INC_CLC_INC_VER_290mm-01"})
    assert p == "MUR-EST-VER_INC_CLC_INC_VER_290mm-02"


def test_suggerisci_copertura(ctx):
    d = {"bic": "OST_Roofs", "nome": "Tetto generico", "spessore": 450,
         "strati": [{"materiale": "1-MBR-Bitume_4mm", "spessore": 4},
                    {"materiale": "1-ISO-XPS_140mm", "spessore": 140},
                    {"materiale": "1-CLC-STR-Soletta_306mm", "spessore": 306}]}
    assert SG.suggerisci_tipo(d, ctx) == "SOL-TET-MBR_ISO_CLC_450mm-01"


def test_porta(ctx):
    d = {"bic": "OST_Doors", "nome": "POR-ADB-REI120_800x2100mm-01", "larghezza": 900, "altezza": 2100}
    r = SG.controlla_coerenza(d, ctx)
    assert r.ha_errori
    assert r.proposta == "POR-ADB-REI120_900x2100mm-01"
    d["nome"] = "POR-ADB-REI120_900x2100mm-01"
    assert SG.controlla_coerenza(d, ctx).ok


def test_suggerisci_materiale(ctx):
    assert SG.suggerisci_materiale("Calcestruzzo armato C25/30", "Concrete", ctx) == \
        "1-CLC-CalcestruzzoArmatoC25/30"
    assert SG.suggerisci_materiale("1-CLC-Magrone", "Concrete", ctx) is None
    assert SG.suggerisci_materiale("Boh", "Sconosciuta", ctx) is None
