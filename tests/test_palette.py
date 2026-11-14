# -*- coding: utf-8 -*-
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import palette as PAL  # noqa: E402
import tasti_contestuali as TC  # noqa: E402


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
    percorso = os.path.join(os.path.dirname(__file__), "..", "lib", "palette_azioni.py")
    with io.open(percorso, encoding="utf-8") as f:
        testo = f.read()
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


def _menu_ids(st):
    return [c for _, tasti in st[u"menu"] for c, _, _ in tasti]


def _ids(lista):
    return [v[0] for v in lista]


def test_config_predefinita():
    cfg = PAL.config_predefinita()
    assert cfg[u"attiva"] is True
    assert cfg[u"fissa"] == [u"nascondi_elementi", u"nascondi_categoria", u"mezzitoni",
                             u"copia_grafica", u"blocca"]
    assert set(cfg[u"categorie"]) == set(PAL.CHIAVI)
    for k, voce in cfg[u"categorie"].items():
        ammessi = set(PAL.ammessi_per_categoria(k))
        assert set(voce[PAL.IN_VISTA]) <= ammessi, k
        assert set(voce[PAL.NEL_MENU]) <= ammessi, k
        assert len(voce[PAL.IN_VISTA]) <= PAL.MAX_IN_VISTA, k
        # niente doppioni tra livelli e con la fila fissa
        assert not set(voce[PAL.IN_VISTA]) & set(voce[PAL.NEL_MENU]), k
        assert not (set(voce[PAL.IN_VISTA]) | set(voce[PAL.NEL_MENU])) & set(cfg[u"fissa"]), k
    assert cfg[u"categorie"][u"muri"][PAL.IN_VISTA] == [u"sposta", u"copia", u"ruota", u"specchia"]
    assert u"offset" in cfg[u"categorie"][u"muri"][PAL.NEL_MENU]
    assert u"offset" not in cfg[u"categorie"][u"porte"][PAL.NEL_MENU]


def test_unisci_config_scarta_comandi_ignoti_e_vecchio_formato():
    cfg = PAL.unisci_config({
        u"attiva": False,
        u"fissa": [u"blocca", u"inventato", u"blocca"],
        u"categorie": {u"porte": {u"vista": [u"sposta", u"offset", u"inventato"],
                                  u"menu": [u"sposta", u"copia"]},
                       u"muri": [u"sposta"],                  # formato della fase 1
                       u"categoria_ignota": {u"vista": [u"sposta"]}}})
    assert cfg[u"attiva"] is False
    assert cfg[u"fissa"] == [u"blocca"]
    assert cfg[u"categorie"][u"porte"] == {u"vista": [u"sposta"], u"menu": [u"copia"]}
    assert u"categoria_ignota" not in cfg[u"categorie"]
    assert cfg[u"categorie"][u"muri"][PAL.IN_VISTA] == [u"sposta", u"copia", u"ruota", u"specchia"]
    assert PAL.unisci_config(None) == PAL.config_predefinita()


def test_struttura_per_un_muro():
    cfg = PAL.config_predefinita()
    cdv = [(u"Muri", [(TC.MURO_INVERTI, u"Inverti muro sul centro", u"...")])]
    st = PAL.struttura_palette([u"muri"], 1, cfg, cdv=cdv)
    assert st[u"cdv"] == [(u"tasto", TC.MURO_INVERTI, u"Inverti muro sul centro", u"...")]
    assert _ids(st[u"vista"]) == [u"sposta", u"copia", u"ruota", u"specchia"]
    assert [t for t, _ in st[u"menu"]] == [u"Modifica", u"Selezione", u"Visibilità"]
    assert u"offset" in _menu_ids(st) and u"crea_simile" in _menu_ids(st)
    assert _ids(st[u"fissa"]) == cfg[u"fissa"]
    assert not set(_menu_ids(st)) & set(_ids(st[u"fissa"]))


def test_gruppi_cdv_grandi_diventano_menu():
    cfg = PAL.config_predefinita()
    st = PAL.struttura_palette([u"viste_tavola"], 3, cfg, cdv=TC.comandi_per_selezione(3))
    tipi = [v[0] for v in st[u"cdv"]]
    assert tipi == [u"gruppo", u"gruppo", u"tasto", u"tasto"]   # Titoli, Allinea, Distribuisci x2
    # in tavola la fila fissa tiene solo Blocca (niente visibilita' sui riquadri)
    assert _ids(st[u"fissa"]) == [u"blocca"]


def test_selezione_mista_solo_comandi_comuni():
    cfg = PAL.config_predefinita()
    st = PAL.struttura_palette([u"muri", u"porte"], 2, cfg)
    assert u"sposta" in _ids(st[u"vista"])
    assert u"offset" not in _menu_ids(st)       # non ammesso per le porte
    assert u"crea_simile" not in _menu_ids(st)  # solo con un elemento


def test_palette_spenta_o_vuota():
    cfg = PAL.config_predefinita()
    cfg[u"attiva"] = False
    assert PAL.struttura_palette([u"muri"], 1, cfg) is None
    assert PAL.struttura_palette([], 0, PAL.config_predefinita()) is None


def test_comandi_non_disponibili_spariscono():
    cfg = PAL.config_predefinita()
    st = PAL.struttura_palette([u"muri"], 1, cfg, disponibili={u"sposta", u"blocca"})
    assert _ids(st[u"vista"]) == [u"sposta"]
    assert st[u"menu"] == []
    assert _ids(st[u"fissa"]) == [u"blocca"]


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


def test_imposta_livello_e_limite_in_vista():
    cfg = PAL.copia_config(PAL.config_predefinita())
    assert PAL.imposta_livello(cfg, u"muri", u"offset", PAL.IN_VISTA)
    assert PAL.livello(cfg, u"muri", u"offset") == PAL.IN_VISTA
    assert u"offset" not in cfg[u"categorie"][u"muri"][PAL.NEL_MENU]
    # in vista ce ne stanno al massimo 5
    assert not PAL.imposta_livello(cfg, u"muri", u"dividi", PAL.IN_VISTA)
    assert PAL.livello(cfg, u"muri", u"dividi") == PAL.NEL_MENU
    assert PAL.imposta_livello(cfg, u"muri", u"dividi", PAL.NASCOSTO)
    assert PAL.livello(cfg, u"muri", u"dividi") == PAL.NASCOSTO
    # non ammesso o nella fila fissa: rifiutato
    assert not PAL.imposta_livello(cfg, u"porte", u"offset", PAL.NEL_MENU)
    assert not PAL.imposta_livello(cfg, u"muri", u"blocca", PAL.IN_VISTA)
    # la copia non tocca l'originale
    assert u"offset" not in PAL.config_predefinita()[u"categorie"][u"muri"][PAL.IN_VISTA]


def test_imposta_fissa():
    cfg = PAL.copia_config(PAL.config_predefinita())
    assert PAL.imposta_fissa(cfg, u"blocca", False)
    assert u"blocca" not in cfg[u"fissa"]
    assert PAL.livello(cfg, u"porte", u"blocca") == PAL.NEL_MENU   # torna nel menu
    assert PAL.imposta_fissa(cfg, u"isola_elementi", True)
    assert PAL.livello(cfg, u"muri", u"isola_elementi") == PAL.NASCOSTO
    assert PAL.imposta_fissa(cfg, u"sposta", True)                  # sesto
    assert not PAL.imposta_fissa(cfg, u"copia", True)               # pieno


def test_ripristina_e_copia_su_tutte():
    cfg = PAL.copia_config(PAL.config_predefinita())
    cfg[u"categorie"][u"muri"] = {PAL.IN_VISTA: [u"sposta", u"offset"], PAL.NEL_MENU: [u"copia"]}
    PAL.copia_su_tutte(cfg, u"muri")
    assert cfg[u"categorie"][u"linee"] == {PAL.IN_VISTA: [u"sposta", u"offset"],
                                           PAL.NEL_MENU: [u"copia"]}
    assert cfg[u"categorie"][u"porte"][PAL.IN_VISTA] == [u"sposta"]   # offset non ammesso
    PAL.ripristina_categoria(cfg, u"porte")
    assert cfg[u"categorie"][u"porte"] == PAL.config_predefinita()[u"categorie"][u"porte"]
