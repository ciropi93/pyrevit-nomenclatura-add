# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import palette as PAL  # noqa: E402
import tasti_contestuali as TC  # noqa: E402


def _ids(gruppi):
    return [c for _, tasti in gruppi for c, _, _ in tasti]


def test_catalogo_valido():
    ids = [c.id for c in PAL.CATALOGO]
    assert len(ids) == len(set(ids))
    gruppi = set(g for g, _ in PAL.TITOLI_GRUPPI)
    for c in PAL.CATALOGO:
        assert c.gruppo in gruppi, c.id
        assert c.icona and c.etichetta and c.suggerimento, c.id
        assert c.esecuzione in (PAL.REVIT, PAL.API), c.id
        if c.esecuzione == PAL.REVIT:
            assert c.postable, c.id
        if c.categorie is not None:
            assert set(c.categorie) <= set(PAL.CHIAVI), c.id
    # nessun conflitto con i comandi CDV contestuali
    assert not set(ids) & set(TC.ICONE)


def test_azioni_api_hanno_una_funzione():
    # palette_azioni usa le API Revit: qui si controlla solo che i nomi combacino
    testo = open(os.path.join(os.path.dirname(__file__), "..", "lib", "palette_azioni.py")).read()
    for c in PAL.CATALOGO:
        if c.esecuzione == PAL.API:
            assert u'u"%s":' % c.id in testo, c.id


def test_chiave_categoria():
    assert PAL.chiave_categoria(u"OST_Walls") == u"muri"
    assert PAL.chiave_categoria(u"OST_DetailComponents", u"FilledRegion") == u"campiture"
    assert PAL.chiave_categoria(u"OST_DetailComponents", u"FamilyInstance") == u"dettagli"
    assert PAL.chiave_categoria(u"OST_DoorTags") == u"annotazioni"
    assert PAL.chiave_categoria(u"OST_Qualcosa") == u"altro"
    assert PAL.chiave_categoria(None) == u"altro"


def test_config_predefinita_rispetta_le_categorie():
    cfg = PAL.config_predefinita()
    assert cfg[u"attiva"] is True
    assert set(cfg[u"categorie"]) == set(PAL.CHIAVI)
    for k, ids in cfg[u"categorie"].items():
        assert set(ids) <= set(PAL.ammessi_per_categoria(k)), k
    assert u"offset" in cfg[u"categorie"][u"muri"]
    assert u"offset" not in cfg[u"categorie"][u"porte"]


def test_unisci_config_scarta_comandi_ignoti():
    cfg = PAL.unisci_config({u"attiva": False,
                             u"categorie": {u"porte": [u"sposta", u"offset", u"inventato"],
                                            u"categoria_ignota": [u"sposta"]}})
    assert cfg[u"attiva"] is False
    assert cfg[u"categorie"][u"porte"] == [u"sposta"]
    assert u"categoria_ignota" not in cfg[u"categorie"]
    # categorie non presenti nel file: predefinite
    assert cfg[u"categorie"][u"muri"] == PAL.config_predefinita()[u"categorie"][u"muri"]
    assert PAL.unisci_config(None) == PAL.config_predefinita()


def test_palette_per_un_muro():
    cfg = PAL.config_predefinita()
    gruppi = PAL.palette_per_selezione([u"muri"], 1, cfg)
    assert [g for g, _ in gruppi] == [u"Modifica", u"Selezione", u"Visibilità"]
    ids = _ids(gruppi)
    assert ids[0] == u"sposta"
    assert u"offset" in ids and u"crea_simile" in ids


def test_selezione_mista_solo_comandi_comuni():
    cfg = PAL.config_predefinita()
    ids = _ids(PAL.palette_per_selezione([u"muri", u"porte"], 2, cfg))
    assert u"sposta" in ids
    assert u"offset" not in ids          # non ammesso per le porte
    assert u"crea_simile" not in ids     # solo con un elemento


def test_palette_spenta_o_vuota():
    cfg = PAL.config_predefinita()
    cfg[u"attiva"] = False
    assert PAL.palette_per_selezione([u"muri"], 1, cfg) == []
    assert PAL.palette_per_selezione([], 0, PAL.config_predefinita()) == []


def test_comandi_non_disponibili_spariscono():
    cfg = PAL.config_predefinita()
    ids = _ids(PAL.palette_per_selezione([u"muri"], 1, cfg, disponibili={u"sposta", u"blocca"}))
    assert ids == [u"sposta", u"blocca"]


def test_salva_carica_e_on_off(tmp_path):
    percorso = str(tmp_path / u"sub" / u"palette.json")
    assert PAL.carica_config(percorso) == PAL.config_predefinita()
    PAL.imposta_attiva(False, percorso)
    assert PAL.carica_config(percorso)[u"attiva"] is False
    PAL.imposta_attiva(True, percorso)
    assert PAL.carica_config(percorso)[u"attiva"] is True
    # file rovinato: predefinita
    with open(percorso, "w") as f:
        f.write("{non json")
    assert PAL.carica_config(percorso) == PAL.config_predefinita()


FINESTRA = (100, 50, 900, 650)
ZOOM = ((0.0, 0.0), (8.0, 6.0))


def test_schermo_a_vista_inverso_di_proietta():
    for uv in [(0.0, 0.0), (8.0, 6.0), (2.5, 4.25)]:
        x, y = TC.proietta(uv, ZOOM, FINESTRA)
        u, v = PAL.schermo_a_vista((x, y), ZOOM, FINESTRA)
        assert abs(u - uv[0]) < 1e-9 and abs(v - uv[1]) < 1e-9


def test_posizione_palette_accanto_al_cursore():
    assert PAL.posizione_palette((300, 200), FINESTRA, 120, 60) == (312, 212)


def test_posizione_palette_si_ribalta_agli_angoli():
    # in basso a destra: va sopra e a sinistra del cursore
    assert PAL.posizione_palette((880, 640), FINESTRA, 120, 60) == (880 - 12 - 120, 640 - 12 - 60)
    # in alto a sinistra: resta in basso a destra
    assert PAL.posizione_palette((101, 51), FINESTRA, 120, 60) == (113, 63)
    # palette piu' larga dello spazio a sinistra: resta dentro la vista
    x, y = PAL.posizione_palette((850, 300), FINESTRA, 790, 60)
    assert x >= 100 and x + 790 <= 900


def test_posizione_palette_fuori_vista():
    assert PAL.posizione_palette((50, 300), FINESTRA, 120, 60) is None
    assert PAL.posizione_palette(None, FINESTRA, 120, 60) is None
