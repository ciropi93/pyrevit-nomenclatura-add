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
    famiglie = [f for f, _ in PAL.FAMIGLIE]
    for c in PAL.CATALOGO:
        assert c.famiglia in famiglie, c.id
        assert c.etichetta and c.suggerimento, c.id
        assert c.esecuzione in (PAL.REVIT, PAL.API), c.id
        if c.esecuzione == PAL.REVIT:
            assert c.postable, c.id
        if c.categorie is not None:
            assert set(c.categorie) <= set(PAL.CHIAVI), c.id
    # nel catalogo i comandi stanno raggruppati per famiglia, nell'ordine delle famiglie
    ordine = [famiglie.index(c.famiglia) for c in PAL.CATALOGO]
    assert ordine == sorted(ordine)
    # nessun conflitto con i comandi CDV contestuali
    assert not set(ids) & set(TC.ICONE)


def test_icone_a_livelli():
    assert set(PAL.ICONE) == set(c.id for c in PAL.CATALOGO)
    for cid, livelli in PAL.ICONE.items():
        assert livelli, cid
        for liv in livelli:
            assert liv[0] in (u"f", u"s"), cid
            assert liv[1].startswith(u"#") and liv[2], cid
            if liv[0] == u"s":
                assert len(liv) >= 4 and liv[3] > 0, cid


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


def _fam(st):
    return [f[u"nome"] for f in st[u"famiglie"]]


def _ids_fam(st, nome):
    for f in st[u"famiglie"]:
        if f[u"nome"] == nome:
            return [v[0] for v in f[u"voci"]]
    return []


def _ids(lista):
    return [v[0] for v in lista]


def test_config_predefinita():
    cfg = PAL.config_predefinita()
    assert cfg[u"attiva"] is True
    assert cfg[u"fissa"] == [u"nascondi_elementi", u"nascondi_categoria", u"mezzitoni",
                             u"copia_grafica", u"blocca"]
    assert set(cfg[u"categorie"]) == set(PAL.CHIAVI)
    for k, ids in cfg[u"categorie"].items():
        assert set(ids) <= set(PAL.ammessi_per_categoria(k)), k
    assert u"offset" in cfg[u"categorie"][u"muri"]
    assert u"offset" not in cfg[u"categorie"][u"porte"]
    assert cfg[u"categorie"][u"viste_tavola"] == [u"sposta", u"sel_tipo_vista"]


def test_unisci_config_scarta_comandi_ignoti_e_legge_il_formato_precedente():
    cfg = PAL.unisci_config({
        u"attiva": False,
        u"fissa": [u"blocca", u"inventato", u"blocca"],
        u"categorie": {u"porte": [u"copia", u"offset", u"inventato", u"sposta"],
                       u"muri": {u"vista": [u"sposta"], u"menu": [u"offset"]},
                       u"categoria_ignota": [u"sposta"]}})
    assert cfg[u"attiva"] is False
    assert cfg[u"fissa"] == [u"blocca"]
    assert cfg[u"categorie"][u"porte"] == [u"sposta", u"copia"]   # ordine del catalogo
    assert cfg[u"categorie"][u"muri"] == [u"sposta", u"offset"]
    assert u"categoria_ignota" not in cfg[u"categorie"]
    assert cfg[u"categorie"][u"finestre"] == PAL.config_predefinita()[u"categorie"][u"finestre"]
    assert PAL.unisci_config(None) == PAL.config_predefinita()


def test_struttura_per_un_muro():
    cfg = PAL.config_predefinita()
    cdv = [(u"Muri", [(TC.MURO_INVERTI, u"Inverti muro sul centro", u"...")])]
    st = PAL.struttura_palette([u"muri"], 1, cfg, cdv=cdv)
    assert _fam(st) == [u"Muri", u"Trasforma", u"Forma", u"Seleziona", u"Isola"]
    assert st[u"famiglie"][0][u"cdv"] is True
    assert st[u"famiglie"][0][u"id"] == PAL.PREFISSO_CDV + u"Muri"
    assert _ids_fam(st, u"Trasforma") == [u"sposta", u"copia", u"ruota", u"specchia", u"serie", u"scala"]
    assert u"offset" in _ids_fam(st, u"Forma") and u"crea_simile" in _ids_fam(st, u"Forma")
    # la famiglia Vista e' tutta nella fila fissa: non compare
    assert _ids(st[u"fissa"]) == cfg[u"fissa"]


def test_famiglia_vista_compare_se_tolgo_dalla_fila_fissa():
    cfg = PAL.copia_config(PAL.config_predefinita())
    PAL.imposta_fissa(cfg, u"mezzitoni", False)
    st = PAL.struttura_palette([u"porte"], 1, cfg)
    assert _ids_fam(st, u"Vista") == [u"mezzitoni"]
    assert u"mezzitoni" not in _ids(st[u"fissa"])


def test_viste_in_tavola():
    cfg = PAL.config_predefinita()
    st = PAL.struttura_palette([u"viste_tavola"], 3, cfg, cdv=TC.comandi_per_selezione(3))
    assert _fam(st) == [u"Titoli", u"Allinea viste", u"Distribuisci", u"Trasforma", u"Seleziona"]
    # in tavola la fila fissa tiene solo Blocca (niente visibilita' sui riquadri)
    assert _ids(st[u"fissa"]) == [u"blocca"]


def test_selezione_mista_solo_comandi_comuni():
    cfg = PAL.config_predefinita()
    st = PAL.struttura_palette([u"muri", u"porte"], 2, cfg)
    assert u"sposta" in _ids_fam(st, u"Trasforma")
    assert u"offset" not in _ids_fam(st, u"Forma")       # non ammesso per le porte
    assert u"crea_simile" not in _ids_fam(st, u"Forma")  # solo con un elemento


def test_palette_spenta_o_vuota():
    cfg = PAL.config_predefinita()
    cfg[u"attiva"] = False
    assert PAL.struttura_palette([u"muri"], 1, cfg) is None
    assert PAL.struttura_palette([], 0, PAL.config_predefinita()) is None


def test_comandi_non_disponibili_spariscono():
    cfg = PAL.config_predefinita()
    st = PAL.struttura_palette([u"muri"], 1, cfg, disponibili={u"sposta", u"blocca"})
    assert _fam(st) == [u"Trasforma"]
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


def test_imposta_comando():
    cfg = PAL.copia_config(PAL.config_predefinita())
    assert PAL.imposta_comando(cfg, u"muri", u"offset", False)
    assert u"offset" not in cfg[u"categorie"][u"muri"]
    assert PAL.imposta_comando(cfg, u"muri", u"offset", True)
    assert u"offset" in cfg[u"categorie"][u"muri"]
    assert not PAL.imposta_comando(cfg, u"porte", u"offset", True)     # non ammesso
    # la copia non tocca l'originale
    PAL.imposta_comando(cfg, u"muri", u"sposta", False)
    assert u"sposta" in PAL.config_predefinita()[u"categorie"][u"muri"]


def test_imposta_fissa():
    cfg = PAL.copia_config(PAL.config_predefinita())
    assert PAL.imposta_fissa(cfg, u"isola_elementi", True)              # sesto
    assert not PAL.imposta_fissa(cfg, u"sposta", True)                  # pieno
    assert PAL.imposta_fissa(cfg, u"blocca", False)
    assert u"blocca" not in cfg[u"fissa"]
    assert u"blocca" in cfg[u"categorie"][u"porte"]                     # torna nella famiglia
    assert not PAL.imposta_fissa(cfg, u"inventato", True)
    assert cfg[u"fissa"] == [u"nascondi_elementi", u"nascondi_categoria", u"mezzitoni",
                             u"copia_grafica", u"isola_elementi"]


def test_ripristina_e_copia_su_tutte():
    cfg = PAL.copia_config(PAL.config_predefinita())
    cfg[u"categorie"][u"muri"] = [u"sposta", u"offset"]
    PAL.copia_su_tutte(cfg, u"muri")
    assert cfg[u"categorie"][u"linee"] == [u"sposta", u"offset"]
    assert cfg[u"categorie"][u"porte"] == [u"sposta"]      # offset non ammesso
    PAL.ripristina_categoria(cfg, u"porte")
    assert cfg[u"categorie"][u"porte"] == PAL.config_predefinita()[u"categorie"][u"porte"]


def test_distanza_da_rettangolo():
    r = (100, 100, 200, 150)
    assert PAL.distanza_da_rettangolo((150, 120), r) == 0
    assert PAL.distanza_da_rettangolo((90, 120), r) == 10
    assert PAL.distanza_da_rettangolo((230, 190), r) == 50   # 30, 40 -> 50


def test_opacita_alla_office():
    assert PAL.opacita_palette(0) == (1.0, False)              # sopra: piena
    op, sparita = PAL.opacita_palette(12)                       # appena comparsa
    assert 0.6 <= op <= 0.75 and not sparita
    assert PAL.opacita_palette(100)[0] < op                     # allontanandosi sbiadisce
    assert PAL.opacita_palette(PAL.DISTANZA_SPARISCE) == (0.0, True)
    # sparita: resta via finche' non si torna vicino
    assert PAL.opacita_palette(100, sparita=True) == (0.0, True)
    assert PAL.opacita_palette(20, sparita=True)[1] is False
    # valori arrotondati a 0.05 (niente ridisegni a ogni pixel)
    for d in range(1, PAL.DISTANZA_SPARISCE):
        v = PAL.opacita_palette(d)[0]
        assert abs(v * 20 - round(v * 20)) < 1e-9



def test_fila_fissa_non_tocca_le_scelte_per_categoria():
    cfg = PAL.copia_config(PAL.config_predefinita())
    PAL.imposta_comando(cfg, u"locali", u"sposta", False)
    prima = PAL.copia_config(cfg)[u"categorie"]
    # dentro e fuori dalla fila fissa (un clic sbagliato e uno per correggere)
    PAL.imposta_fissa(cfg, u"blocca", False)
    assert PAL.imposta_fissa(cfg, u"sposta", True)
    assert PAL.imposta_fissa(cfg, u"sposta", False)
    assert cfg[u"categorie"] == prima
    assert u"sposta" not in cfg[u"categorie"][u"locali"]
    assert u"copia" not in cfg[u"categorie"][u"viste_tavola"]
    PAL.ripristina_fissa(cfg)
    assert cfg[u"fissa"] == PAL.FISSA_PREDEFINITA and cfg[u"categorie"] == prima


def test_config_con_forma_sbagliata_non_da_errore(tmp_path):
    strane = [
        {u"fissa": [[u"sposta"], 3, None, u"blocca"]},
        {u"categorie": {u"muri": {u"vista": None, u"menu": 5}}},
        {u"categorie": {u"muri": [[u"sposta"], {u"a": 1}, u"copia"]}},
        {u"categorie": [u"muri"]},
        [u"non", u"un", u"oggetto"],
    ]
    for dati in strane:
        cfg = PAL.unisci_config(dati)
        assert set(cfg[u"categorie"]) == set(PAL.CHIAVI)
    assert PAL.unisci_config(strane[0])[u"fissa"] == [u"blocca"]
    assert PAL.unisci_config(strane[1])[u"categorie"][u"muri"] == []
    assert PAL.unisci_config(strane[2])[u"categorie"][u"muri"] == [u"copia"]
    # anche dal file: mai un'eccezione, al massimo la predefinita
    percorso = str(tmp_path / u"palette.json")
    with open(percorso, "w") as f:
        f.write('{"fissa": [["sposta"]], "categorie": {"muri": {"vista": null}}}')
    assert PAL.carica_config(percorso)[u"attiva"] is True


def test_posizione_griglia_sul_monitor_della_palette():
    principale = (0, 0, 1920, 1040)
    secondo = (1920, 0, 3840, 1040)          # monitor a destra del principale
    # sotto la palette, allineata a sinistra
    assert PAL.posizione_griglia(300, 200, 150, 210, 130, principale) == (300, 204)
    # sul secondo monitor resta li', non torna sul principale
    assert PAL.posizione_griglia(2500, 200, 150, 210, 130, secondo) == (2500, 204)
    # in basso non c'e' posto: va sopra la palette
    assert PAL.posizione_griglia(300, 1000, 950, 210, 130, principale) == (300, 950 - 4 - 130)
    # vicino al bordo destro resta dentro il monitor
    assert PAL.posizione_griglia(3800, 200, 150, 210, 130, secondo)[0] == 3840 - 210
