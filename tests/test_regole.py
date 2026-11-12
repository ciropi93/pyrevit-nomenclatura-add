# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "CDVTools.extension", "lib"))

import pytest  # noqa: E402

from nomenclatura import regole as R  # noqa: E402


@pytest.fixture(scope="module")
def ctx():
    return R.Contesto()


# ---------------- elementi ----------------
@pytest.mark.parametrize("nome", [
    "MUR-EST-VER_INC_CLC_INC_VER_290mm-01",
    "MUR-INT-CRT_150mm-03",
    "FNT-ISO-LanaDiRoccia_100mm-01",
    "POR-ADB-REI180_900x2100mm-01",
    "CLN-CLC_500x700mm-03",
    "TRV-TRT-IPE_140mm-01",
    "VEG-ARB-BuxusSempervirens_H600mm-01",
])
def test_elementi_validi(ctx, nome):
    r = R.controlla_elemento(nome, ctx)
    assert r.ok, r


def test_elemento_spazi_proposta(ctx):
    r = R.controlla_elemento("FNT-ISO-lana di roccia_100mm-1", ctx)
    assert r.ha_errori
    assert r.proposta == "FNT-ISO-LanaDiRoccia_100mm-01"


def test_elemento_tipo_inesistente(ctx):
    r = R.controlla_elemento("XYZ-EST-300mm-01", ctx)
    assert r.ha_errori and r.proposta is None


def test_elemento_sottotipo_non_previsto_e_avviso(ctx):
    r = R.controlla_elemento("POR-SEZ-MTL_2500x2400mm-01", ctx)
    assert r.livello == R.AVVISO


def test_elemento_caratteri_vietati_senza_proposta(ctx):
    r = R.controlla_elemento("POR-AVV-Lamiera6/10-01", ctx)
    assert r.ha_errori and r.proposta is None


def test_elemento_troppo_lungo(ctx):
    r = R.controlla_elemento("MUR-EST-" + "A" * 50 + "-01", ctx)
    assert r.ha_errori


def test_elemento_manca_descrizione(ctx):
    assert R.controlla_elemento("MUR-EST-01", ctx).ha_errori


def test_elemento_categoria_insolita(ctx):
    r = R.controlla_elemento("POR-AVV-Serranda_2500x2400mm-01", ctx, categoria="OST_Walls")
    assert r.livello == R.AVVISO


def test_nome_revit_qualsiasi(ctx):
    r = R.controlla_elemento("Muro di base 300", ctx)
    assert r.ha_errori


# ---------------- famiglie e contrassegno ----------------
def test_famiglia(ctx):
    assert R.controlla_famiglia("POR-AVV-Serranda", ctx).ok
    assert R.controlla_famiglia("VEG-ARB-Buxus", ctx).ok
    assert R.controlla_famiglia("POR-AVV-Serranda-01", ctx).ha_errori
    r = R.controlla_famiglia("POR-AVV-Serranda", ctx, prefissi_tipi=["POR-AVV", "POR-SCO"])
    assert r.livello == R.AVVISO


def test_contrassegno(ctx):
    assert R.contrassegno_atteso("SOL-TET-MBR_ISO_CLC_450mm-02", ctx) == "SOL-TET-02"
    assert R.contrassegno_atteso("CLN-CLC_500x700mm-03", ctx) == "CLN-03"
    r = R.controlla_contrassegno("A1", "MUR-EST-300mm-01", ctx)
    assert r.proposta == "MUR-EST-01"
    assert R.controlla_contrassegno("MUR-EST-01", "MUR-EST-300mm-01", ctx).ok


# ---------------- materiali ----------------
@pytest.mark.parametrize("nome", [
    "0-CLC-Magrone",
    "1-MTL-RTE-LamieraStirata",
    "1-MBR-MembranaBPE_ArmPoliestereVetro_FlessMeno25C_4mm",
])
def test_materiali_validi(ctx, nome):
    assert R.controlla_materiale(nome, ctx).ok


def test_materiale_slash_avviso(ctx):
    r = R.controlla_materiale("1-CLC-STR-CA_C32/40_XC4_XF1_250mm", ctx)
    assert r.livello == R.AVVISO


def test_materiale_dettaglio_pfte(ctx):
    assert R.controlla_materiale("2-MRT-MattoneForato_250x250x80mm", ctx).livello == R.AVVISO
    assert R.controlla_materiale("5-MRT-Mattone", ctx).ha_errori


def test_materiale_proposta(ctx):
    r = R.controlla_materiale("1-clc-calcestruzzo magro", ctx)
    assert r.proposta == "1-CLC-CalcestruzzoMagro"


def test_materiale_escluso(ctx):
    assert R.materiale_escluso("Default Floor", ctx)


# ---------------- livelli ----------------
def test_livelli(ctx):
    assert R.controlla_livello("GF-A", ctx).ok
    assert R.controlla_livello("G1-S", ctx).ok
    assert R.controlla_livello("GF-U_BOX01", ctx).livello == R.AVVISO
    assert R.controlla_livello("Piano terra", ctx).ha_errori
    assert R.controlla_livello("gf_a", ctx).proposta == "GF-A"
    assert R.controlla_livello("GF-Q", ctx).ha_errori


# ---------------- locali ----------------
def test_locali(ctx):
    assert R.controlla_numero_locale("BOX-001", ctx).ok
    assert R.controlla_numero_locale("box 1", ctx).proposta == "BOX-001"
    assert R.controlla_numero_locale("QQQ-001", ctx).ha_errori
    assert R.controlla_nome_locale("Box auto", "BOX-001", ctx).ok
    assert R.controlla_nome_locale("box auto", "BOX-001", ctx).proposta == "Box auto"
    r = R.controlla_nome_locale("Garage 3", "BOX-003", ctx)
    assert r.livello == R.AVVISO and r.proposta == "Box auto"
    assert R.controlla_nome_locale("Vano tecnico", "TEC-001", ctx).ok


# ---------------- file modello e tavole ----------------
def test_file_modello(ctx):
    r = R.controlla_file_modello("AQD0031-ADD-CFNNNNNNN-ZZ-M3-U-PN0001", ctx)
    assert r.livello == R.AVVISO  # segnaposto CFNNNNNNN
    assert R.controlla_file_modello("AQD0031-ADD-CF1234567-ZZ-M3-U-PN0001", ctx).ok
    assert R.controlla_file_modello("AQD0031-ADD-CF1234567-ZZ-M3-A-PD0001", ctx).ok
    assert R.controlla_file_modello("Progetto1", ctx).ha_errori
    assert R.controlla_file_modello("AQD0031-ADD-CF1234567-ZZ-DR-U-PN0001", ctx).ha_errori


def test_tavole(ctx):
    assert R.controlla_tavola("AQD0031-ADD-PLANGENER-ZZ-DR-Z-P00001", ctx).ok
    assert R.controlla_tavola("AQD0031-ADD-ABACOELEM-ZZ-DR-A-P00001", ctx).ok
    assert R.controlla_tavola("AQD0031-ADD-PLANLIVEL-01-DR-A-P00101", ctx).ok
    assert R.controlla_tavola("AQD0031-ADD- PLANLIVEL-01-DR-A-P00101", ctx).proposta == \
        "AQD0031-ADD-PLANLIVEL-01-DR-A-P00101"
    assert R.controlla_tavola("A101", ctx).ha_errori
    assert R.controlla_tavola("AQD0031-ADD-NUOVOCODX-ZZ-DR-A-P00001", ctx).livello == R.AVVISO
    assert R.controlla_tavola("AQD0031-ADD-PLANGENER-ZZ-DR-Z-E00001", ctx).livello == R.AVVISO


# ---------------- verifiche aggiunte con la revisione della knowledge base ----------------
def test_livello_disciplina_non_a_s_e_avviso(ctx):
    assert R.controlla_livello("GF-U", ctx).livello == R.AVVISO
    assert R.controlla_livello("01-A", ctx).ok


def test_modello_federato_tipo_file(ctx):
    assert R.controlla_file_modello("AQD0031-ADD-CF1234567-ZZ-M3-K-S00001", ctx).ha_errori
    assert not R.controlla_file_modello("AQD0031-ADD-CF1234567-ZZ-MR-K-P00001", ctx).ha_errori
    assert R.controlla_file_modello("AQD0031-ADD-MFEDERATO-ZZ-M3-A-P00001", ctx).ha_errori
    assert R.controlla_file_modello("AQD0031-ADD-CF1234567-ZZ-MR-Y-P00001", ctx).ha_errori
    assert not R.controlla_file_modello("AQD0031-ADD-MFEDERATO-ZZ-MR-Y-P00001", ctx).ha_errori


def test_codici_aggiunti_dalla_revisione(ctx):
    assert "SPK" in ctx.sottotipi("ANT")
    assert "RIM" in ctx.sottotipi("FCO")
    assert "REM" in ctx.sottotipi("ELR") and "RES" in ctx.sottotipi("ELR")
    assert "PNT" in ctx.tipi
    assert R.controlla_tavola("AQD0031-ADD-RELBARARC-ZZ-RT-A-P00001", ctx).livello != R.ERRORE


# ---------------- codice fabbricato dalle Impostazioni ----------------
def _ctx_con_cf(ctx, cf):
    cfg = dict(ctx.cfg)
    cfg["codice_fabbricato"] = cf
    return R.Contesto(codici=ctx.codici, config=cfg)


def test_codice_fabbricato_usato_nei_controlli(ctx):
    c = _ctx_con_cf(ctx, "CF7654321")
    assert R.controlla_file_modello("AQD0031-ADD-CF7654321-ZZ-M3-U-PN0001", c).ok
    assert R.controlla_file_modello("AQD0031-ADD-CF1234567-ZZ-M3-U-PN0001", c).ha_errori
    assert R.controlla_file_modello("AQD0031-ADD-CFNNNNNNN-ZZ-M3-U-PN0001", c).ha_errori
    r = R.controlla_tavola("AQD0031-ADD-CFNNNNNNN-GF-DR-A-P00001", c)
    assert r.proposta == "AQD0031-ADD-CF7654321-GF-DR-A-P00001"
    assert R.controlla_tavola("AQD0031-ADD-PLANGENER-ZZ-DR-Z-P00001", c).ok


def test_valida_e_salva_codice_fabbricato(tmp_path):
    assert R.valida_codice_fabbricato("CF1234567")
    assert R.valida_codice_fabbricato("")
    assert not R.valida_codice_fabbricato("CF12")
    p = str(tmp_path / "x" / "progetto.json")
    R.salva_config_utente({"codice_fabbricato": "CF1234567"}, p)
    R.salva_config_utente({"servizio": "E"}, p)
    assert R.leggi_config_file(p) == {"codice_fabbricato": "CF1234567", "servizio": "E"}


# ---------------- proposte: unita' di misura e simboli ----------------
@pytest.mark.parametrize("testo, atteso", [
    ("lana di roccia 100 mm", "LanaDiRoccia100mm"),
    ("pilastro 500 x 700 mm", "Pilastro500x700mm"),
    ("IPE 140 rinforzato", "IPE140Rinforzato"),
    ("carico 10 kN", "Carico10kN"),
])
def test_pulisci_descrizione_unita(testo, atteso):
    assert R.pulisci_descrizione(testo) == atteso


def test_elemento_proposta_con_unita(ctx):
    r = R.controlla_elemento("MUR-EST-muro 300 mm-1", ctx)
    assert r.proposta == "MUR-EST-Muro300mm-01"


def test_elemento_lettere_non_ascii(ctx):
    r = R.controlla_elemento("MUR-EST-Ü_Wand-01", ctx)
    assert r.ha_errori and r.proposta == "MUR-EST-U_Wand-01"
    r = R.controlla_elemento("CLN-CLC_500×700mm-03", ctx)
    assert r.ha_errori and "non ASCII" in r.messaggio()
    assert r.proposta == "CLN-CLC_500x700mm-03"


# ---------------- spazi iniziali/finali ----------------
def test_spazi_esterni(ctx):
    r = R.controlla_elemento(" MUR-EST-Muro-01", ctx)
    assert r.ha_errori and r.proposta == "MUR-EST-Muro-01"
    r = R.controlla_elemento("MUR-EST-muro 300 mm-1 ", ctx)
    assert r.proposta == "MUR-EST-Muro300mm-01"
    assert R.controlla_livello("GF-A ", ctx).proposta == "GF-A"
    assert R.controlla_famiglia("POR-AVV-Serranda ", ctx).proposta == "POR-AVV-Serranda"
    assert R.controlla_materiale(" 0-CLC-Magrone", ctx).proposta == "0-CLC-Magrone"
    r = R.controlla_file_modello("AQD0031-ADD-CF1234567-ZZ-M3-U-PN0001 ", ctx)
    assert r.ha_errori


# ---------------- locali: nome vuoto ----------------
def test_nome_locale_vuoto(ctx):
    r = R.controlla_nome_locale("", "BOX-001", ctx)
    assert r.ha_errori and r.proposta == "Box auto"
    r = R.controlla_nome_locale("  ", "AUL-001", ctx)
    assert r.ha_errori and r.proposta is None
    assert R.controlla_nome_locale("", "", ctx).ha_errori


# ---------------- progressivi doppi ----------------
def test_progressivi_doppi(ctx):
    nomi = ["MUR-EST-Muro_A-01", "MUR-EST-Muro_B-01", "MUR-EST-Muro_C-02",
            "MUR-INT-Muro_A-01", "CLN-CLC_500mm-01", "Muro di base"]
    doppi = R.progressivi_doppi(nomi, ctx)
    assert doppi == {"MUR-EST-Muro_A-01": ["MUR-EST-Muro_B-01"],
                     "MUR-EST-Muro_B-01": ["MUR-EST-Muro_A-01"]}


def test_progressivo_doppio_segnalato(ctx):
    r = R.controlla_elemento("MUR-EST-Muro_A-01", ctx)
    R.segnala_progressivo_doppio(r, ["MUR-EST-Muro_B-01"], ctx)
    assert r.ha_errori and "MUR-EST-01" in r.messaggio()
    r = R.controlla_elemento("POR-ASB-Porta-01", ctx)
    R.segnala_progressivo_doppio(r, ["POR-ASB-Porta-01"], ctx)
    assert "piu' famiglie" in r.messaggio()


# ---------------- impostazioni ----------------
def test_unisci_ricorsivo():
    base = {"a": 1, "tipi": {"solo_tipi_usati": True, "categorie_escluse": ["X", "Y"]}}
    agg = {"tipi": {"categorie_escluse": ["Z"]}, "b": 2}
    assert R.unisci(base, agg) == {"a": 1, "b": 2,
                                   "tipi": {"solo_tipi_usati": True, "categorie_escluse": ["Z"]}}
    assert base["tipi"]["categorie_escluse"] == ["X", "Y"]  # base non modificata


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    cartella = tmp_path / "appdata"
    cartella.mkdir()
    monkeypatch.setenv(str("APPDATA"), str(cartella))
    return cartella


def test_config_progetto_prevale(appdata, tmp_path):
    (appdata / "NomenclaturaADD").mkdir()
    R.scrivi_json(str(appdata / "NomenclaturaADD" / "progetto.json"),
                  {"codice_bene": "AAA0001", "tipi": {"solo_tipi_usati": False}})
    progetto = tmp_path / "commessa"
    progetto.mkdir()
    R.scrivi_json(R.percorso_config_progetto(str(progetto)), {"codice_bene": "BBB0002", "servizio": "E"})

    cfg = R.carica_config(str(progetto))
    assert cfg["codice_bene"] == "BBB0002"
    assert cfg["servizio"] == "E"
    assert cfg["tipi"]["solo_tipi_usati"] is False          # dalle personali
    assert "OST_Levels" in cfg["tipi"]["categorie_escluse"]  # dalle predefinite (unione ricorsiva)
    assert cfg["materiali"]["escludi_regex"]

    ctx = R.Contesto(cartella_progetto=str(progetto))
    assert len(ctx.fonti) == 3
    assert R.Contesto(cartella_progetto=None).cfg["codice_bene"] == "AAA0001"


def test_config_json_non_valido(appdata, tmp_path):
    progetto = tmp_path / "commessa"
    progetto.mkdir()
    with open(R.percorso_config_progetto(str(progetto)), "w") as f:
        f.write('{"codice_bene": "AQD0031",}')
    with pytest.raises(R.ConfigErrore) as info:
        R.carica_config(str(progetto))
    assert R.NOME_CONFIG_PROGETTO in "%s" % info.value


def test_scrivi_json_accenti(tmp_path):
    p = str(tmp_path / "x.json")
    R.scrivi_json(p, {"_nota": "Città", "codici_fabbricato_area": ["CF1234567"]})
    assert R.leggi_config_file(p) == {"_nota": "Città", "codici_fabbricato_area": ["CF1234567"]}
