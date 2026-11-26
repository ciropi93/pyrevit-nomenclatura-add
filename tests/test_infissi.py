# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import pytest  # noqa: E402

from infissi import catalogo as C  # noqa: E402
from infissi import geometria as G  # noqa: E402
from infissi import parametri as PA  # noqa: E402
from infissi import schema as S  # noqa: E402

EPS = 1e-6


def due_ante():
    return S.nuovo(S.divisione("v", [S.cella("battente_sx"), S.cella("anta_ribalta_dx")], [600],
                               montante=False), 1200, 1500, "2 ante")


def tre_ante_sopraluce():
    return [s for s in C.preimpostati() if s["nome"] == "3 ante + sopraluce diviso"][0]


def rett(ris, ids):
    return G.rettangolo(ris, ids)


def area_rett(r):
    return (r[2] - r[0]) * (r[3] - r[1])


# --- schema --------------------------------------------------------------------------
def test_json_andata_e_ritorno():
    s = tre_ante_sopraluce()
    assert S.from_json(S.to_json(s)) == s


def test_json_rovinato():
    with pytest.raises(S.SchemaErrore):
        S.from_json("{non json")
    with pytest.raises(S.SchemaErrore):
        S.from_json('{"larghezza": 1}')


def test_profili_mancanti_predefiniti():
    s = S.normalizza({"radice": {"tipo": "cella", "anta": "fisso"}, "larghezza": 800,
                      "altezza": 800, "profili": {"telaio": 60, "sconosciuto": 3}})
    assert s["profili"]["telaio"] == 60
    assert s["profili"]["anta"] == S.PROFILI_PREDEFINITI["anta"]
    assert "sconosciuto" not in s["profili"]


def test_battuta_vuole_ante_apribili():
    s = S.nuovo(S.divisione("v", [S.cella("fisso"), S.cella("battente_dx")], [600], False),
                1200, 1500)
    assert any("senza montante" in e for e in S.errori_struttura(s))


def test_battuta_non_mischia_scorrevoli():
    s = S.nuovo(S.divisione("v", [S.cella("scorrevole_dx"), S.cella("battente_dx")], [600],
                            False), 1200, 1500)
    assert any("scorrevoli" in e for e in S.errori_struttura(s))


def test_numero_misure():
    s = S.nuovo(S.divisione("v", [S.cella(), S.cella(), S.cella()], [400]), 1200, 1500)
    assert any("servono 2 misure" in e for e in S.errori_struttura(s))


def test_dividi_togli_e_anta():
    s = S.nuovo(S.cella("battente_sx"), 1200, 1500)
    s2 = S.dividi(s, (), "v", 600, montante=False)
    assert [c["anta"] for _p, c in S.celle(s2["radice"])] == ["battente_sx", "battente_sx"]
    s3 = S.imposta_anta(s2, (1,), "battente_dx")
    assert S.nodo_in(s3["radice"], (1,))["anta"] == "battente_dx"
    assert S.nodo_in(s2["radice"], (1,))["anta"] == "battente_sx"   # originale intatto
    s4 = S.togli_divisione(s3, (1,))
    assert s4["radice"] == S.cella("battente_dx")
    with pytest.raises(S.SchemaErrore):
        S.togli_divisione(s4, ())


def test_sigla_nomi_descrizione():
    s = tre_ante_sopraluce()
    assert S.sigla(s) == "2A4F"
    assert S.nome_famiglia(s) == "CDV_Finestra_2A4F"
    assert S.nome_tipo(s) == "180x200"
    assert "4 Fisso" in S.descrizione(s)
    s["larghezza"] = 1205
    assert S.nome_tipo(s) == "1205x2000 mm"


# --- geometria ------------------------------------------------------------------------
@pytest.mark.parametrize("schema", C.preimpostati(), ids=lambda s: s["nome"])
def test_preimpostati_validi(schema):
    ris = G.calcola(schema)
    assert ris["errori"] == []
    assert PA.elenco(schema, ris)


def chiusi(ris):
    """I pezzi della vista normale: livello Medio, ante chiuse."""
    return [p for p in ris["pezzi"] if G.MEDIO in p["dettaglio"] and p["stato"] != "aperta"]


def strisce(est, inn):
    """Una cornice divisa in quattro rettangoli (sotto, sopra, sinistra, destra)."""
    return [(est[0], est[1], est[2], inn[1]), (est[0], inn[3], est[2], est[3]),
            (est[0], inn[1], inn[0], inn[3]), (inn[2], inn[1], est[2], inn[3])]


def sovrapposti(a, b):
    return min(a[2], b[2]) - max(a[0], b[0]) > EPS and min(a[3], b[3]) - max(a[1], b[1]) > EPS


@pytest.mark.parametrize("schema", C.preimpostati(), ids=lambda s: s["nome"])
def test_pezzi_riempiono_il_vano_senza_sovrapporsi(schema):
    """Telaio + montanti + ante intere + vetri fissi coprono esattamente L x H."""
    ris = G.calcola(schema)
    celle = dict((c["percorso"], c) for c in ris["celle"])
    pezzi = []
    for pz in chiusi(ris):
        if pz["tipo"] == "maniglia":
            continue        # sta sopra il profilo dell'anta, sul lato interno
        if pz["tipo"] in ("vetro", "zoccolo", "pannello") and pz["cella"] is not None \
                and celle[pz["cella"]]["anta_interna"] is not None:
            continue        # vetro, zoccolo e pannello stanno dentro l'anta
        est = rett(ris, pz["esterni"])
        if pz["interni"] and pz["tipo"] == "telaio":
            pezzi.extend(strisce(est, rett(ris, pz["interni"])))
        else:
            pezzi.append(est)
    for i, a in enumerate(pezzi):
        assert area_rett(a) > 0
        for b in pezzi[i + 1:]:
            assert not sovrapposti(a, b), (a, b)
    atteso = schema["larghezza"] * schema["altezza"]
    if not schema["soglia"]:
        # senza soglia resta libera la luce a terra tra i due montanti del telaio
        pr = schema["profili"]
        atteso -= (schema["larghezza"] - 2 * pr["telaio"]) * pr["terra"]
    assert abs(sum(area_rett(r) for r in pezzi) - atteso) < 1e-3


@pytest.mark.parametrize("schema", C.preimpostati(), ids=lambda s: s["nome"])
def test_dentro_anta_vetro_e_zoccolo_riempiono(schema):
    ris = G.calcola(schema)
    for c in ris["celle"]:
        if c["anta_interna"] is None:
            continue
        dentro = [rett(ris, p["esterni"]) for p in chiusi(ris)
                  if p["cella"] == c["percorso"] and p["tipo"] in ("vetro", "zoccolo", "pannello")]
        assert abs(sum(area_rett(r) for r in dentro) - area_rett(rett(ris, c["anta_interna"]))) < 1e-3


@pytest.mark.parametrize("schema", C.preimpostati(), ids=lambda s: s["nome"])
def test_piani_rispettano_base_e_parametro(schema):
    ris = G.calcola(schema)
    per_id = dict((p["id"], p) for p in ris["piani"])
    valori = dict(ris["valori"])
    for p in ris["piani"]:
        if p["base"] is None:
            continue
        atteso = per_id[p["base"]]["pos"] + p["segno"] * valori[p["param"]]
        assert abs(p["pos"] - atteso) < EPS
        assert per_id[p["base"]]["verso"] == p["verso"]
        # la formula della posizione da' lo stesso numero
        f = G.formula_posizione(per_id, p["id"])
        assert abs(PA.valuta(f, valori) - p["pos"]) < EPS


def test_ultima_colonna_prende_il_resto():
    ris = G.calcola(tre_ante_sopraluce())
    celle = dict((c["percorso"], c) for c in ris["celle"])
    x0, _y0, x1, _y1 = rett(ris, celle[(0, 2)]["regione"])
    assert (x0, x1) == (1200, 1800)
    _x0, y0, _x1, y1 = rett(ris, celle[(1, 0)]["regione"])
    assert (y0, y1) == (1500, 2000)


def test_battuta_senza_montante():
    ris = G.calcola(due_ante())
    assert [p["tipo"] for p in ris["pezzi"]].count("montante") == 0
    sx, dx = ris["celle"]
    assert rett(ris, sx["luce"])[2] == 600 == rett(ris, dx["luce"])[0]


def test_misure_troppo_grandi():
    s = S.imposta_misura(due_ante(), (), 0, 1300)
    ris = G.calcola(s)
    assert any("superano" in e for e in ris["errori"])


def test_anta_troppo_piccola():
    s = S.imposta_misura(due_ante(), (), 0, 200)
    ris = G.calcola(s)
    assert any("Zona 1" in e and "anta" in e for e in ris["errori"])


def test_profilo_sotto_il_minimo():
    s = due_ante()
    s["profili"]["telaio"] = 5
    assert any("Telaio sezione" in e for e in G.calcola(s)["errori"])


def test_zoccolo_solo_nelle_porte():
    s = [x for x in C.preimpostati() if x["nome"] == "Portafinestra + laterale fisso"][0]
    ris = G.calcola(s)
    zoccoli = [p for p in ris["pezzi"] if p["tipo"] == "zoccolo"]
    assert len(zoccoli) == 1 and zoccoli[0]["cella"] == (1,)
    z = rett(ris, zoccoli[0]["esterni"])
    vetro = [p for p in ris["pezzi"] if p["tipo"] == "vetro" and p["cella"] == (1,)][0]
    assert rett(ris, vetro["esterni"])[1] == z[3]
    assert z[3] - z[1] == 200


def test_scorrevoli_su_due_binari():
    s = [x for x in C.preimpostati() if x["nome"] == "Scorrevole 2 ante"][0]
    ris = G.calcola(s)
    assert [c["livello"] for c in ris["celle"]] == ["a", "b"]
    prof = sorted(p["profondita"] for p in chiusi(ris) if p["tipo"] == "anta")
    assert prof == ["anta_a", "anta_b"]


def test_cella_in_punto():
    ris = G.calcola(tre_ante_sopraluce())
    assert G.cella_in_punto(ris, 100, 100) == (0, 0)
    assert G.cella_in_punto(ris, 1700, 1900) == (1, 2)
    assert G.cella_in_punto(ris, 5000, 100) is None


# --- simboli --------------------------------------------------------------------------
def _segmenti(schema):
    ris = G.calcola(schema)
    return ris, [seg for s in ris["simboli"] for seg in s["segmenti"]]


def test_battente_punta_verso_le_cerniere():
    s = S.nuovo(S.cella("battente_sx"), 800, 1400)
    ris, segs = _segmenti(s)
    luce = rett(ris, ris["celle"][0]["luce"])
    punte = set(seg["p1"] for seg in segs)
    assert punte == {(luce[0], (luce[1] + luce[3]) / 2.0)}          # lato sinistro, a meta'
    assert set(seg["p0"][0] for seg in segs) == {luce[2]}             # parte dalla maniglia


def test_vasistas_punta_in_basso():
    ris, segs = _segmenti(S.nuovo(S.cella("vasistas"), 800, 600))
    luce = rett(ris, ris["celle"][0]["luce"])
    assert set(seg["p1"] for seg in segs) == {((luce[0] + luce[2]) / 2.0, luce[1])}


def test_anta_ribalta_quattro_segmenti_e_fisso_nessuno():
    _r, segs = _segmenti(S.nuovo(S.cella("anta_ribalta_dx"), 800, 1400))
    assert len(segs) == 4
    _r, segs = _segmenti(S.nuovo(S.cella("fisso"), 800, 1400))
    assert segs == []


def test_freccia_scorrevole_verso_giusto():
    ris, segs = _segmenti(S.nuovo(S.cella("scorrevole_sx"), 1000, 2000))
    luce = rett(ris, ris["celle"][0]["luce"])
    asta = segs[0]
    assert asta["p1"][0] == luce[0] and asta["p0"][0] > asta["p1"][0]


@pytest.mark.parametrize("schema", C.preimpostati(), ids=lambda s: s["nome"])
def test_coordinate_simboli_quotabili(schema):
    """Ogni coordinata = piano base + segno * parametro, come la quota che la blocca in Revit."""
    ris, segs = _segmenti(schema)
    per_id = dict((p["id"], p) for p in ris["piani"])
    valori = ris["valori"]
    for seg in segs:
        cx0, cy0, cx1, cy1 = seg["coord"]
        for (pid, param, segno), atteso in ((cx0, seg["p0"][0]), (cy0, seg["p0"][1]),
                                            (cx1, seg["p1"][0]), (cy1, seg["p1"][1])):
            assert pid is not None and param
            assert abs(per_id[pid]["pos"] + segno * valori[param] - atteso) < EPS


# --- parametri ------------------------------------------------------------------------
@pytest.mark.parametrize("schema", C.preimpostati(), ids=lambda s: s["nome"])
def test_formule_coerenti(schema):
    params = PA.elenco(schema)
    nomi = [p["nome"] for p in params]
    assert len(nomi) == len(set(nomi))
    valori = {}
    for p in params:                     # ogni formula usa solo parametri gia' creati
        if p["tipo"] != PA.LUNGHEZZA:
            continue
        if p["formula"]:
            assert abs(PA.valuta(p["formula"], valori) - p["valore"]) < EPS, p["nome"]
        valori[p["nome"]] = p["valore"]


def test_parametri_usati_soltanto():
    nomi = [p["nome"] for p in PA.elenco(S.nuovo(S.cella("fisso"), 800, 800))]
    assert "Anta sezione" not in nomi and "Montante mezzo" not in nomi
    assert "Freccia lunghezza" not in nomi
    nomi = [p["nome"] for p in PA.elenco(tre_ante_sopraluce())]
    assert {"L zona 1.1", "L zona 1.2", "L zona 2.1", "L zona 2.2", "H zona 1",
            "Montante mezzo", "Anta sezione"} <= set(nomi)


def test_elenco_con_errori():
    s = S.imposta_misura(due_ante(), (), 0, 1300)
    with pytest.raises(S.SchemaErrore):
        PA.elenco(s)


def test_tokenizza_e_rinomina():
    nomi = ["Larghezza", "Telaio sezione", "L zona 1", "L zona 1.1"]
    assert PA.dipendenze("(Larghezza - L zona 1.1) / 2", nomi) == ["Larghezza", "L zona 1.1"]
    assert PA.rinomina("(Larghezza - Telaio sezione) / 2", {"Larghezza": "Width"}, nomi) == \
        "(Width - Telaio sezione) / 2"
    with pytest.raises(PA.FormulaErrore):
        PA.tokenizza("Sconosciuto + 1", nomi)
    assert PA.valuta("-Larghezza / 2", {"Larghezza": 100}) == -50


def test_schema_da_valori():
    s = tre_ante_sopraluce()
    s2 = PA.schema_da_valori(s, {"Larghezza": 2000, "L zona 1.2": 700, "Telaio sezione": 80,
                                 "H zona 1": 1600, "altro": 3})
    assert s2["larghezza"] == 2000 and s2["profili"]["telaio"] == 80
    assert S.nodo_in(s2["radice"], (0,))["misure"] == [600, 700]
    assert s2["radice"]["misure"] == [1600]
    assert s["larghezza"] == 1800


def test_valori_input_senza_formule():
    v = PA.valori_input(PA.elenco(due_ante()))
    assert v["Larghezza"] == 1200 and v["L zona 1"] == 600
    assert "Telaio inizio" not in v and "Mezza altezza 1" not in v


# --- catalogo e impostazioni ------------------------------------------------------------
@pytest.fixture
def cartella():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


def test_schemi_utente(cartella):
    s = due_ante()
    s["nome"] = "Mia/finestra: 2"
    percorso = C.salva_schema(s, base=cartella)
    assert os.path.basename(percorso) == "Mia_finestra_ 2.json"
    with open(os.path.join(C.cartella_schemi(cartella), "rotto.json"), "w") as f:
        f.write("{")
    letti = C.schemi_utente(base=cartella)
    assert [x[1] for x in letti] == [s]
    C.elimina_schema(percorso)
    assert C.schemi_utente(base=cartella) == []


def test_impostazioni(cartella):
    assert C.carica_impostazioni(base=cartella) == C.IMPOSTAZIONI_PREDEFINITE
    C.salva_impostazioni({"cartella": "X:\\infissi", "modello_porte": "", "modello_finestre": ""},
                         base=cartella)
    assert C.carica_impostazioni(base=cartella)["cartella"] == "X:\\infissi"


def test_trova_modello(cartella):
    sotto = os.path.join(cartella, "Italian")
    os.makedirs(sotto)
    for nome in ("Window.rft", "Finestra metrica.rft"):
        open(os.path.join(sotto, nome), "w").close()
    assert C.trova_modello(S.FINESTRE, [cartella]).endswith("Finestra metrica.rft")
    assert C.trova_modello(S.PORTE, [cartella, None]) is None
    scelto = os.path.join(sotto, "Window.rft")
    assert C.trova_modello(S.FINESTRE, [cartella], {"modello_finestre": scelto}) == scelto


def test_anteprima_anche_con_errori_non_bloccanti():
    s = S.nuovo(S.divisione("v", [S.cella("fisso"), S.cella("battente_dx")], [600], False),
                1200, 1500)
    ris = G.calcola(s)
    assert ris["errori"] and len(ris["celle"]) == 2


def test_struttura_rotta_non_esplode():
    s = S.nuovo(S.divisione("v", [S.cella(), S.cella(), S.cella()], [400]), 1200, 1500)
    ris = G.calcola(s)
    assert ris["errori"] and ris["celle"] == []


# --- soglia, chiusura, maniglie, evidenziazione ----------------------------------------
def _preimpostato(nome):
    return [x for x in C.preimpostati() if x["nome"] == nome][0]


def test_schemi_vecchi_restano_come_erano():
    vecchio = {"larghezza": 900, "altezza": 2400, "categoria": "finestre",
               "profili": {"zoccolo": 200},
               "radice": {"tipo": "cella", "anta": "porta_sx"}}
    s = S.normalizza(vecchio)
    assert s["soglia"] is True and s["maniglie"] is False
    assert s["radice"]["riempimento"] == S.ZOCCOLO
    assert "_riempimento_mancante" not in s["radice"]
    senza_zoccolo = S.normalizza(dict(vecchio, profili={"zoccolo": 0}))
    assert senza_zoccolo["radice"]["riempimento"] == S.VETRO
    # e si rilegge uguale dal JSON
    assert S.from_json(S.to_json(s)) == s


def test_nuovi_schemi_porte_senza_soglia():
    assert _preimpostato("Portafinestra 1 anta")["soglia"] is False
    assert _preimpostato("2 ante")["soglia"] is True
    assert _preimpostato("Scorrevole 2 ante")["soglia"] is True     # binario in basso
    assert _preimpostato("2 ante")["maniglie"] is True


def test_chiusura_conservata_e_zoccolo_solo_porte():
    s = S.nuovo(S.cella("porta_sx", S.PANNELLO), 900, 2400)
    s2 = S.imposta_anta(s, (), "porta_dx")
    assert s2["radice"]["riempimento"] == S.PANNELLO
    s3 = S.dividi(s2, (), "o", 2000)
    assert [c["riempimento"] for _p, c in S.celle(s3["radice"])] == [S.PANNELLO, S.PANNELLO]
    assert S.togli_divisione(s3, (0,))["radice"]["riempimento"] == S.PANNELLO
    s4 = S.imposta_riempimento(S.nuovo(S.cella("battente_sx"), 800, 1400), (), S.ZOCCOLO)
    assert s4["radice"]["riempimento"] == S.VETRO          # lo zoccolo e' delle porte
    with pytest.raises(S.SchemaErrore):
        S.imposta_riempimento(s, (), "legno")
    assert "cieca" in S.descrizione(s)


def test_senza_soglia_telaio_a_u_e_anta_quasi_a_terra():
    s = _preimpostato("Portafinestra 1 anta")
    ris = G.calcola(s)
    assert ris["errori"] == []
    telai = [p for p in ris["pezzi"] if p["tipo"] == "telaio"]
    assert len(telai) == 3 and all(p["interni"] is None for p in telai)
    # nessun pezzo del telaio sotto l'anta
    anta = [p for p in ris["pezzi"] if p["tipo"] == "anta"][0]
    x0, y0, x1, _y1 = rett(ris, anta["esterni"])
    assert y0 == s["profili"]["terra"]
    for t in telai:
        tx0, ty0, tx1, _ty1 = rett(ris, t["esterni"])
        assert not (ty0 < y0 and min(tx1, x1) - max(tx0, x0) > EPS)
    assert "Soglia sezione" not in [p["nome"] for p in PA.elenco(s, ris)]


def test_pannello_al_posto_del_vetro():
    s = S.nuovo(S.divisione("v", [S.cella("fisso", S.PANNELLO), S.cella("porta_sx", S.PANNELLO)], [500]),
                1400, 2400)
    ris = G.calcola(s)
    assert ris["errori"] == []
    tipi = [p["tipo"] for p in chiusi(ris)]
    assert "vetro" not in tipi and tipi.count("pannello") == 2
    assert "Materiale pannello" in [p["nome"] for p in PA.elenco(s, ris)]
    assert "Materiale pannello" not in [p["nome"] for p in PA.elenco(due_ante())]


@pytest.mark.parametrize("anta,lato", [("battente_sx", "dx"), ("anta_ribalta_dx", "sx"),
                                       ("scorrevole_sx", "dx"), ("porta_dx", "sx"),
                                       ("vasistas", "alto")])
def test_maniglia_sul_lato_giusto(anta, lato):
    s = S.nuovo(S.cella(anta), 900, 2400 if S.porta(anta) else 1400)
    ris = G.calcola(s)
    assert ris["errori"] == []
    man = [p for p in ris["pezzi"] if p["tipo"] == "maniglia"]
    assert len(man) == 1
    mx0, my0, mx1, my1 = rett(ris, man[0]["esterni"])
    lx0, ly0, lx1, ly1 = rett(ris, ris["celle"][0]["luce"])
    if lato == "dx":
        assert mx1 == lx1
    elif lato == "sx":
        assert mx0 == lx0
    else:
        assert my1 == ly1 and abs((mx0 + mx1) / 2 - (lx0 + lx1) / 2) < EPS
    if S.porta(anta):
        assert my0 == s["profili"]["maniglia_porta"]           # quota da terra
    elif lato != "alto":
        assert abs((my0 + my1) / 2 - (ly0 + ly1) / 2) < EPS     # a meta' altezza
    assert "Maniglia inizio" in [p["nome"] for p in PA.elenco(s, ris)]


def test_niente_maniglie_su_fissi_o_se_spente():
    s = S.nuovo(S.cella("fisso"), 800, 800)
    assert not [p for p in G.calcola(s)["pezzi"] if p["tipo"] == "maniglia"]
    s = S.nuovo(S.cella("battente_sx"), 800, 1400, maniglie=False)
    assert not [p for p in G.calcola(s)["pezzi"] if p["tipo"] == "maniglia"]


def test_maniglia_che_non_sta():
    s = S.nuovo(S.cella("battente_sx"), 800, 400)
    s["profili"]["maniglia_l"] = 500
    assert any("maniglia" in e for e in G.calcola(s)["errori"])


def test_evidenzia():
    s = tre_ante_sopraluce()
    ris = G.calcola(s)
    ev = G.evidenzia(ris, s, ("larghezza",))
    assert ev["quota"] == (0.0, 2000.0, 1800.0, 2000.0)
    ev = G.evidenzia(ris, s, ("misura", (0,), 1))           # colonna centrale delle ante
    assert ev["rettangoli"] == [(600.0, 0.0, 1200.0, 1500.0)]
    assert ev["quota"] == (600.0, 1500.0, 1200.0, 1500.0)
    ev = G.evidenzia(ris, s, ("profilo", "soglia"))
    assert ev["rettangoli"] == [(0.0, 0.0, 1800.0, s["profili"]["soglia"])]
    assert len(G.evidenzia(ris, s, ("profilo", "montante"))["rettangoli"]) >= 2
    assert G.evidenzia(ris, s, None)["rettangoli"] == []


# --- pianta, ante aperte, livelli di dettaglio --------------------------------------------
def _pos(ris):
    """{id piano: pos} di piani x/z e piani y insieme."""
    d = dict((p["id"], p["pos"]) for p in ris["piani"])
    d.update((p["id"], p["pos"]) for p in ris["piani_y"])
    return d


@pytest.mark.parametrize("schema", C.preimpostati(), ids=lambda s: s["nome"])
def test_simboli_in_pianta_quotabili(schema):
    ris = G.calcola(schema)
    pos, valori = _pos(ris), ris["valori"]
    for p in ris["piani_y"]:
        if p["base"] is not None:
            assert abs(pos[p["base"]] + p["segno"] * valori[p["param"]] - p["pos"]) < EPS
            assert abs(PA.valuta(G.formula_posizione(dict((q["id"], q) for q in ris["piani_y"]), p["id"]),
                                 valori) - p["pos"]) < EPS
    for simb in ris["pianta"]:
        for seg in simb["segmenti"]:
            cx0, cy0, cx1, cy1 = seg["coord"]
            for (pid, param, segno), atteso in ((cx0, seg["p0"][0]), (cy0, seg["p0"][1]),
                                                (cx1, seg["p1"][0]), (cy1, seg["p1"][1])):
                assert pid is not None and param
                assert abs(pos[pid] + segno * valori[param] - atteso) < EPS


def test_porta_in_pianta_anta_e_arco():
    s = S.nuovo(S.cella("porta_sx"), 900, 2400)
    ris = G.calcola(s)
    assert len(ris["pianta"]) == 1 and ris["pianta"][0]["stile"] == "porta"
    linea, arco = ris["pianta"][0]["segmenti"]
    luce = rett(ris, ris["celle"][0]["luce"])
    w = luce[2] - luce[0]
    filo = ris["valori"][G.FILO_ANTA] * G.INTERNO
    assert linea["p0"] == (luce[0], filo) and linea["p1"] == (luce[0], filo + G.INTERNO * w)
    cx, cy = arco["centro"]
    for p in (arco["p0"], arco["p1"]):                      # l'arco ha raggio = larghezza anta
        assert abs(((p[0] - cx) ** 2 + (p[1] - cy) ** 2) ** 0.5 - w) < EPS


def test_finestre_in_pianta_a_scelta():
    for scelta, stile in (("nessuno", None), ("tratteggio", "finestra_tratteggio"),
                          ("continuo", "finestra_continuo")):
        ris = G.calcola(S.nuovo(S.cella("battente_sx"), 800, 1400, simbolo_pianta=scelta))
        assert [p["stile"] for p in ris["pianta"]] == ([stile] if stile else [])
    # i fissi e i vasistas non hanno simbolo in pianta
    assert not G.calcola(S.nuovo(S.cella("vasistas"), 800, 600))["pianta"]
    # gli schemi di prima restano senza simbolo
    vecchio = S.normalizza({"larghezza": 800, "altezza": 1400, "radice": {"tipo": "cella", "anta": "battente_sx"}})
    assert vecchio["simbolo_pianta"] == "nessuno"


def test_anta_aperta_a_novanta_gradi():
    s = S.nuovo(S.cella("battente_dx"), 800, 1400)
    ris = G.calcola(s)
    pos = _pos(ris)
    anta = [p for p in ris["pezzi_aperti"] if p["tipo"] == "anta"][0]
    luce = rett(ris, ris["celle"][0]["luce"])
    assert pos[anta["piano_x"]] == luce[2] and anta["verso"] == -1       # cerniere a destra
    y0, y1 = pos[anta["y"][0]], pos[anta["y"][1]]
    assert abs(abs(y1 - y0) - (luce[2] - luce[0])) < EPS                   # sporge quanto e' larga
    assert (y1 - y0) * G.INTERNO > 0                                        # verso l'interno
    tipi = sorted(p["tipo"] for p in ris["pezzi_aperti"])
    assert tipi == ["anta", "vetro"]
    # le ante chiuse si vedono solo da chiuse
    assert all(p["stato"] == "chiusa" for p in ris["pezzi"] if p["cella"] == ())
    nomi = dict((p["nome"], p) for p in PA.elenco(s, ris))
    assert nomi[G.APERTA]["istanza"] and nomi[G.CHIUSA]["formula"] == PA.FORMULA_CHIUSA


def test_scorrevole_aperto_spostato():
    s = S.nuovo(S.cella("scorrevole_sx"), 1000, 2200)
    ris = G.calcola(s)
    chiusa = [p for p in ris["pezzi"] if p["tipo"] == "anta" and p["stato"] == "chiusa"][0]
    aperta = [p for p in ris["pezzi"] if p["tipo"] == "anta" and p["stato"] == "aperta"][0]
    a, b = rett(ris, chiusa["esterni"]), rett(ris, aperta["esterni"])
    assert abs((a[0] - b[0]) - (a[2] - a[0])) < EPS                        # verso sinistra
    assert not ris["pezzi_aperti"] and not ris["pianta"]


def test_vasistas_resta_chiuso():
    ris = G.calcola(S.nuovo(S.cella("vasistas"), 800, 600))
    assert not ris["pezzi_aperti"]
    assert all(p["stato"] is None for p in ris["pezzi"])
    assert G.APERTA not in [p["nome"] for p in PA.elenco(S.nuovo(S.cella("vasistas"), 800, 600))]


@pytest.mark.parametrize("schema", C.preimpostati(), ids=lambda s: s["nome"])
def test_livello_basso_telaio_e_vetro_unico(schema):
    ris = G.calcola(schema)
    basso = [p for p in ris["pezzi"] if G.BASSO in p["dettaglio"]]
    assert set(p["tipo"] for p in basso) == {"telaio", "vetro"}
    assert len([p for p in basso if p["tipo"] == "vetro"]) == 1
    # niente maniglie se non ad Alto
    assert all(p["dettaglio"] == G.SOLO_ALTO for p in ris["pezzi"] if p["tipo"] == "maniglia")
