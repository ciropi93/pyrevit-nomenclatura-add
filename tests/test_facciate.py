# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import pytest  # noqa: E402

from facciate import catalogo as C  # noqa: E402
from facciate import ritmo as R  # noqa: E402
from facciate import schema as S  # noqa: E402

EPS = 1e-6
M = S.modulo


def misure(tratti):
    return [round(t["a"] - t["da"], 3) for t in tratti]


def moduli(tratti):
    return [t["modulo"] for t in tratti]


def continui(tratti, lunghezza):
    assert abs(tratti[0]["da"]) < EPS
    assert abs(tratti[-1]["a"] - lunghezza) < EPS
    for t, u in zip(tratti, tratti[1:]):
        assert abs(t["a"] - u["da"]) < EPS


# --- divisione migliore -----------------------------------------------------------
def test_migliore_modulo_unico_sceglie_il_numero_piu_vicino():
    r = S.regola([M("A", 1500)], ["A"])
    t = R.posizioni(10000, r)
    continui(t, 10000)
    # 10000/1500 = 6,67: con 7 moduli 1428,6 (piu' vicino a 1500 di 1666,7)
    assert len(t) == 7
    assert all(abs(m - 10000 / 7.0) < 1e-3 for m in misure(t))


def test_migliore_moduli_bloccati_restano_fermi():
    r = S.regola([M("A", 1500), M("B", 600, True)], ["A", "B"], finisci_con=0)
    t = R.posizioni(9000, r)
    continui(t, 9000)
    assert moduli(t)[0] == "A" and moduli(t)[-1] == "A"       # finisce con A: simmetrico
    assert all(abs(m - 600) < EPS for m, i in zip(misure(t), moduli(t)) if i == "B")
    a = [m for m, i in zip(misure(t), moduli(t)) if i == "A"]
    assert max(a) - min(a) < EPS


def test_migliore_tutti_bloccati_errore():
    r = S.regola([M("A", 1500, True)], ["A"])
    with pytest.raises(R.RitmoErrore):
        R.posizioni(10000, r)
    # ma se la misura torna esatta va bene
    assert len(R.posizioni(6000, r)) == 4


def test_migliore_bloccati_che_non_ci_stanno():
    r = S.regola([M("A", 1000), M("B", 3000, True)], ["B", "A"])
    with pytest.raises(R.RitmoErrore):
        R.posizioni(2000, r)


def test_giri_e_posizioni():
    r = S.regola([M("A", 1000), M("B", 500, True)], ["A", "A", "B"])
    t = R.posizioni(5000, r)
    assert [x["pos"] for x in t] == [0, 1, 2, 0, 1, 2]
    assert [x["giro"] for x in t] == [0, 0, 0, 1, 1, 1]


# --- misura fissa ------------------------------------------------------------------
def test_fisso_dall_inizio_taglia_alla_fine():
    r = S.regola([M("A", 1200)], ["A"], R.FISSO)
    t = R.posizioni(5000, r)
    continui(t, 5000)
    assert misure(t) == [1200, 1200, 1200, 1200, 200]
    assert [x["resto"] for x in t] == [False] * 4 + [True]


def test_fisso_dalla_fine_e_scarto():
    r = S.regola([M("A", 1200)], ["A"], R.FISSO, origine=R.FINE)
    assert misure(R.posizioni(5000, r)) == [200, 1200, 1200, 1200, 1200]
    r = S.regola([M("A", 1200)], ["A"], R.FISSO, scarto=300)
    assert misure(R.posizioni(5000, r)) == [300, 1200, 1200, 1200, 1100]


def test_fisso_centrato():
    r = S.regola([M("A", 1200)], ["A"], R.FISSO, origine=R.CENTRO)
    t = R.posizioni(5000, r)
    assert misure(t) == [100, 1200, 1200, 1200, 1200, 100]
    assert t[0]["giro"] == 0          # i giri partono da 0 anche col primo tagliato


def test_fisso_ritagli_corti_uniti():
    r = S.regola([M("A", 1200)], ["A"], R.FISSO, origine=R.CENTRO, resto_minimo=300)
    t = R.posizioni(5000, r)
    continui(t, 5000)
    assert misure(t) == [1300, 1200, 1200, 1300]
    assert t[0]["resto"] and t[-1]["resto"]


def test_fisso_piu_corto_del_motivo():
    r = S.regola([M("A", 1200)], ["A"], R.FISSO, origine=R.CENTRO)
    assert misure(R.posizioni(800, r)) == [800]


# --- ripetizioni -------------------------------------------------------------------
def test_ripetizioni():
    r = S.regola([M("A", 1000), M("B", 500, True)], ["A", "B"], R.RIPETIZIONI, ripetizioni=3)
    t = R.posizioni(6000, r)
    continui(t, 6000)
    assert moduli(t) == ["A", "B"] * 3
    assert misure(t) == [1500, 500] * 3


# --- righe sui livelli -----------------------------------------------------------
def test_fasce_sui_livelli():
    assert R.fasce(9000, [0, 3000, 6000, 9000, 12000]) == [(0, 3000), (3000, 6000), (6000, 9000)]
    assert R.fasce(9000, [3000], offset=-100) == [(0, 2900), (2900, 9000)]


def test_righe_ripartono_in_ogni_piano():
    r = S.regola([M("P", 900, True), M("V", 2100)], ["P", "V"], livelli=S.livelli(True))
    t = R.righe(7000, r, [0, 3500, 7000])
    continui(t, 7000)
    assert moduli(t) == ["P", "V", "P", "V"]
    assert [x["piano"] for x in t] == [0, 0, 1, 1]
    assert misure(t) == [900, 2600, 900, 2600]


def test_linee_classi_e_marcapiano():
    r = S.regola([M("P", 900, True), M("V", 2100)], ["P", "V"], livelli=S.livelli(True))
    t = R.righe(7000, r, [3500])
    lin = R.linee(t, ["parapetto"], R.TRAVERSO)
    assert [(round(x["pos"]), x["classe"]) for x in lin] == [
        (900, "parapetto"), (3500, R.MARCAPIANO), (4400, "parapetto")]


# --- celle e unioni ---------------------------------------------------------------
def parapetto_continuo():
    return [s for s in C.preimpostati() if s["nome"] == "Parapetto continuo"][0]


def test_classi_delle_celle():
    s = [s for s in C.preimpostati() if s["nome"] == "A-B alternato"][0]
    ris = R.calcola(s, 9000, 3000)
    per_modulo = dict((ris["colonne"][c["col"][0]]["modulo"], c["classe"]) for c in ris["celle"])
    assert per_modulo == {"A": "vetro", "B": "cieco"}


def test_classe_cella_ordine():
    celle = {"0,1": "x", "0,*": "y", "*,1": "z"}
    assert R.classe_cella(celle, 0, 1) == "x"
    assert R.classe_cella(celle, 0, 0) == "y"
    assert R.classe_cella(celle, 2, 1) == "z"
    assert R.classe_cella(celle, 2, 0) == "vetro"


def test_unioni_per_giro_e_segmenti_tolti():
    s = parapetto_continuo()
    ris = R.calcola(s, 8100, 3000)       # 6 colonne da 1350 = due giri A A B
    assert len(ris["colonne"]) == 6
    unite = [c for c in ris["celle"] if c["col"][0] != c["col"][1]]
    assert [c["col"] for c in unite] == [[0, 2], [3, 5]]   # non scavalca il giro
    assert all(c["riga"] == [0, 0] and c["classe"] == "cieco" for c in unite)
    tolti = ris["tolti"]["verticali"]
    assert tolti == {0: [0], 1: [0], 3: [0], 4: [0]}       # la linea 2 (fra i giri) resta
    assert ris["senza_linea"]["verticali"] == []
    assert len(ris["celle"]) == 2 + 6                       # 2 parapetti + 6 vetri sopra


def test_unione_su_tutta_l_altezza_non_crea_la_linea():
    s = S.nuovo(S.regola([M("A", 1000)], ["A", "A"]), S.regola([M("V", 3000)], ["V"]),
                unioni=[{"colonne": [0, 1], "righe": [0, 0]}])
    ris = R.calcola(s, 4000, 3000)
    assert sorted(ris["senza_linea"]["verticali"]) == [0, 2]


def test_trova_cella():
    s = parapetto_continuo()
    ris = R.calcola(s, 8100, 3000)
    c = R.trova_cella(ris["celle"], ris["colonne"], ris["righe"], 2000, 400)
    assert c["col"] == [0, 2] and c["classe"] == "cieco"
    c = R.trova_cella(ris["celle"], ris["colonne"], ris["righe"], 2000, 2000)
    assert c["col"] == [1, 1] and c["classe"] == "vetro"
    assert R.trova_cella(ris["celle"], ris["colonne"], ris["righe"], 9000, 400) is None


def test_resto_prende_la_sua_classe():
    s = [s for s in C.preimpostati() if s["nome"] == "Griglia fissa centrata"][0]
    ris = R.calcola(s, 5000, 2400)
    prima = [c for c in ris["celle"] if c["col"][0] == 0]
    assert all(c["classe"] == "cieco" for c in prima)


# --- schema --------------------------------------------------------------------------
def test_sequenza_scritta_a_mano():
    assert S.leggi_sequenza("A A B") == ["A", "A", "B"]
    assert S.leggi_sequenza("A,A-B") == ["A", "A", "B"]
    assert S.leggi_sequenza("AAB", ["A", "B"]) == ["A", "A", "B"]
    assert S.leggi_sequenza("AB", ["AB", "A"]) == ["AB"]
    assert S.scrivi_sequenza(["A", "B"]) == "A B"


def test_json_andata_e_ritorno_e_classi():
    for s in C.preimpostati():
        assert S.normalizza(S.from_json(S.to_json(s))) == s
        pan, mon = S.classi_usate(s)
        assert set(pan) <= set(s["classi"]["pannelli"])
        assert set(mon) <= set(s["classi"]["montanti"])


def test_errori():
    s = S.nuovo(S.regola([M("A", 1000), M("A", 500)], ["A", "C"]), S.regola([M("V", 0)], ["V"]))
    err = S.errori(s)
    assert any("stesso nome" in e for e in err)
    assert any("C" in e for e in err)
    assert any("misura" in e for e in err)
    with pytest.raises(S.SchemaErrore):
        S.from_json("{rotto")


def test_errori_sulla_facciata_vera():
    s = S.nuovo(S.regola([M("A", 1500, True)], ["A"]), S.regola([M("V", 3000)], ["V"]))
    assert S.errori(s, 10000, 3000)
    assert not S.errori(s, 9000, 3000)


def test_preimpostati_si_calcolano():
    for s in C.preimpostati():
        assert not S.errori(s, 12000, 7000, [3500]), s["nome"]
        assert S.descrizione(s)


def test_schemi_utente():
    base = tempfile.mkdtemp()
    try:
        s = C.preimpostati()[2]
        p = C.salva_schema(s, base)
        assert [x for _p, x in C.schemi_utente(base)] == [s]
        C.elimina_schema(p)
        assert C.schemi_utente(base) == []
    finally:
        shutil.rmtree(base)
