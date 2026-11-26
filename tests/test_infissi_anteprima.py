# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

from infissi import anteprima as AN  # noqa: E402
from infissi import catalogo as C  # noqa: E402
from infissi import geometria as G  # noqa: E402
from infissi import schema as S  # noqa: E402


def preset(nome):
    return S.copia([s for s in C.preimpostati() if s["nome"] == nome][0])


def chiavi_profili(gruppi):
    return set(k for _t, ks in gruppi for k in ks)


# --- profili -----------------------------------------------------------------------------
def test_i_gruppi_coprono_tutti_i_profili_una_volta():
    tutte = [k for _t, ks in AN.GRUPPI_PROFILI for k in ks]
    assert sorted(tutte) == sorted(k for k, _e, _v, _m in S.PROFILI)


def test_maniglie_solo_se_ci_sono():
    s = preset("2 ante")
    for _p, c in S.celle(s["radice"]):
        c["maniglia"] = S.NESSUNA
    assert "maniglia_l" not in chiavi_profili(AN.profili_per_gruppo(s))
    s = S.imposta_maniglia(s, (0,), S.INTERNA)
    assert "maniglia_l" in chiavi_profili(AN.profili_per_gruppo(s))


def test_frecce_solo_con_gli_scorrevoli():
    assert "freccia_l" not in chiavi_profili(AN.profili_per_gruppo(preset("2 ante")))
    assert "freccia_l" in chiavi_profili(AN.profili_per_gruppo(preset("Scorrevole 2 ante")))


def test_soglia_o_luce_a_terra():
    s = preset("1 anta")
    s["soglia"] = True
    k = chiavi_profili(AN.profili_per_gruppo(s))
    assert "soglia" in k and "terra" not in k
    s["soglia"] = False
    k = chiavi_profili(AN.profili_per_gruppo(s))
    assert "terra" in k and "soglia" not in k


def test_con_errori_si_vedono_tutti_i_profili():
    s = preset("1 anta")
    s["larghezza"] = 50.0          # non ci sta niente
    assert chiavi_profili(AN.profili_per_gruppo(s)) == set(k for k, _e, _v, _m in S.PROFILI)


# --- quote ----------------------------------------------------------------------------------
def test_quote_esterne_e_della_colonna():
    s = preset("2 ante")
    q = AN.quote(s, G.calcola(s))
    per_chiave = dict((x["chiave"], x) for x in q)
    assert per_chiave[("larghezza",)]["lato"] == "basso" and per_chiave[("larghezza",)]["valore"] == 1200
    assert per_chiave[("altezza",)]["lato"] == "sinistra" and per_chiave[("altezza",)]["valore"] == 1500
    col = per_chiave[("misura", (), 0)]
    assert col["lato"] == "alto" and (col["a"], col["b"], col["valore"]) == (0.0, 600.0, 600.0)


def test_ogni_divisione_ha_la_sua_corsia():
    s = preset("3 ante + sopraluce diviso")
    q = [x for x in AN.quote(s, G.calcola(s)) if x["lato"] == "alto"]
    # due righe divise in colonne: le loro quote non stanno sulla stessa corsia
    corsie = dict(((x["chiave"][1], x["corsia"])) for x in q)
    assert len(set(corsie.values())) == len(corsie) == 2
    destra = [x for x in AN.quote(s, G.calcola(s)) if x["lato"] == "destra"]
    assert len(destra) == 1 and destra[0]["valore"] == 1500


# --- prospetto e pianta ---------------------------------------------------------------------
def test_prospetto_per_livello_di_dettaglio():
    s = preset("2 ante")
    s["maniglie"] = True
    ris = G.calcola(s)
    tipi = lambda d: set(pz["tipo"] for pz in AN.pezzi_prospetto(ris, d))  # noqa: E731
    assert tipi(G.BASSO) == {"telaio", "vetro"}
    assert "anta" in tipi(G.MEDIO) and "maniglia" not in tipi(G.MEDIO)
    assert "maniglia" in tipi(G.ALTO)


def test_prospetto_senza_ante_scorrevoli_aperte():
    s = preset("Scorrevole 2 ante")
    ris = G.calcola(s)
    assert any(pz["stato"] == "aperta" for pz in ris["pezzi"])
    assert all(pz["stato"] != "aperta" for pz in AN.pezzi_prospetto(ris))


def test_pianta_taglia_telaio_e_ante():
    s = preset("2 ante")
    s["simbolo_pianta"] = "nessuno"
    p = AN.pianta(s, G.calcola(s))
    telaio = [r for r in p["rettangoli"] if r[4] == "telaio"]
    # il telaio tagliato: montante sinistro e destro, profondita' telaio_prof centrata sull'asse
    assert sorted((r[0], r[2]) for r in telaio) == [(0.0, 70.0), (1130.0, 1200.0)]
    assert all((r[1], r[3]) == (-35.0, 35.0) for r in telaio)
    assert any(r[4] == "anta" for r in p["rettangoli"])
    assert not p["linee"] and not p["archi"]


def test_pianta_a_basso_solo_telaio_e_vetro_unico():
    s = preset("2 ante")
    p = AN.pianta(s, G.calcola(s), G.BASSO)
    assert set(r[4] for r in p["rettangoli"]) == {"telaio", "vetro", "muro"}


def test_pianta_con_simboli_secondo_la_scelta():
    s = preset("2 ante")
    s["simbolo_pianta"] = "tratteggio"
    p = AN.pianta(s, G.calcola(s))
    assert p["archi"] and all(a[3] for a in p["archi"])
    s["simbolo_pianta"] = "continuo"
    p = AN.pianta(s, G.calcola(s))
    assert p["archi"] and not any(a[3] for a in p["archi"])
    # l'anta aperta va verso l'interno: la pianta si allarga in y positivo
    assert p["y"][1] > 500


def test_porte_sempre_con_simbolo():
    s = preset("Porta + laterale fisso")
    s["simbolo_pianta"] = "nessuno"
    p = AN.pianta(s, G.calcola(s))
    assert p["archi"] and not any(a[3] for a in p["archi"])


# --- contorno (passo 5) -------------------------------------------------------------------------
from infissi import parametri as PA  # noqa: E402


def con_contorno(nome, **kw):
    s = preset(nome)
    misure = kw.pop("misure", {})
    s["contorno"].update(kw)
    s["contorno"]["misure"].update(misure)
    return s


def elementi(s):
    return G.calcola(s)["contorno"]


def test_senza_contorno_come_prima():
    s = preset("1 anta")
    ris = G.calcola(s)
    assert ris["contorno"] == [] and ris["asse"] == "centro" and ris["asse_y"] == 0.0
    nomi = set(p["nome"] for p in PA.elenco(s))
    assert not any(e in nomi for _k, e, _v, _m in S.MISURE_CONTORNO)


def test_schemi_di_prima_senza_contorno():
    s = preset("1 anta")
    del s["contorno"]
    assert S.from_json(S.to_json(s))["contorno"] == S.contorno_vuoto()


def test_telaio_dal_filo_esterno():
    s = con_contorno("1 anta", posizione="filo_esterno", misure={"posizione": 50.0, "muro": 300.0})
    p = AN.pianta(s, G.calcola(s))
    telaio = [r for r in p["rettangoli"] if r[4] == "telaio"]
    # esterno in basso (y negativa): faccia esterna del muro a -150, telaio da -100 a -30
    assert all((r[1], r[3]) == (-100.0, -30.0) for r in telaio)
    assert "Posizione telaio" in set(x["nome"] for x in PA.elenco(s))


def test_telaio_che_esce_dal_muro():
    s = con_contorno("1 anta", misure={"muro": 60.0})
    assert any("esce dal muro" in e for e in G.calcola(s)["errori"])


def test_mazzetta_riseghe_davanti_al_telaio():
    s = con_contorno("1 anta", posizione="filo_esterno", mazzetta=True, misure={"posizione": 50.0})
    ris = G.calcola(s)
    riseghe = [e for e in ris["contorno"] if e["tipo"] == "mazzetta"]
    assert len(riseghe) == 3 and not ris["errori"]
    # da fuori il muro copre il bordo del telaio: 40 mm ai lati e sopra
    muro = sorted(r for r in AN.contorno_prospetto(ris) if r[4] == "muro")
    assert muro[0][:4] == (0.0, 0.0, 40.0, 1400.0)
    assert "Mazzetta esterna" in set(p["nome"] for p in PA.elenco(s))


def test_mazzetta_senza_spazio_davanti_al_telaio():
    s = con_contorno("1 anta", posizione="filo_esterno", mazzetta=True, misure={"posizione": 0.0})
    assert any("Mazzetta" in e for e in G.calcola(s)["errori"])


def test_mostre_e_davanzale():
    s = con_contorno("1 anta", mostra_est=True, mostra_int=True)
    pezzi = [e for e in elementi(s) if e["tipo"] == "mostra"]
    assert len(pezzi) == 8                     # finestra senza davanzali: cornici chiuse
    s["contorno"]["dav_est"] = True
    est = [e for e in elementi(s) if e["chiave"] == "mostra_est"]
    assert len(est) == 3                       # sotto c'e' il davanzale
    nomi = set(p["nome"] for p in PA.elenco(s))
    assert {"Mostra esterna", "Mostra interna", "Davanzale esterno", "Mostra larghezza",
            "Davanzale est. sporgenza", "Materiale mostre", "Materiale davanzali"} <= nomi
    assert "Spessore muro (anteprima)" not in nomi


def test_porte_soglia_e_niente_davanzali():
    s = con_contorno("Porta + laterale fisso", dav_est=True, dav_int=True, soglia_pietra=True, mostra_est=True)
    chiavi = set(e["chiave"] for e in elementi(s))
    assert chiavi == {"soglia_pietra", "mostra_est"}
    assert len([e for e in elementi(s) if e["chiave"] == "mostra_est"]) == 3   # niente traverso a terra


def test_imbotte_senza_spazio_a_filo_interno():
    s = con_contorno("1 anta", posizione="filo_interno", imbotte=True, misure={"posizione": 0.0})
    assert any("Imbotte" in e for e in G.calcola(s)["errori"])


def test_pianta_disegna_il_contorno():
    s = con_contorno("1 anta", mostra_est=True, mostra_int=True, dav_int=True, imbotte=True)
    tipi = set(r[4] for r in AN.pianta(s, G.calcola(s))["rettangoli"])
    assert {"mostra", "davanzale", "imbotte", "muro"} <= tipi
