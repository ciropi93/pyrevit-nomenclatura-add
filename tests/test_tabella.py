# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "NomenclaturaADD.extension", "lib"))

from nomenclatura import tabella as T  # noqa: E402


def test_andata_e_ritorno(tmp_path):
    p = str(tmp_path / "r.csv")
    righe = [
        {"Id": 123, "Ambito": "Tipi", "Campo": "NomeTipo", "ValoreAttuale": 'Muro "base"; 300',
         "Proposta": "", "NuovoValore": "MUR-EST-300mm-01", "Messaggio": "riga1\nriga2"},
        {"Id": "", "Ambito": "Locali", "Campo": "NomeLocale", "ValoreAttuale": "Città",
         "NuovoValore": ""},
    ]
    T.scrivi_csv(p, righe)
    letti = T.leggi_csv(p)
    assert len(letti) == 2
    assert letti[0]["Id"] == "123"
    assert letti[0]["ValoreAttuale"] == 'Muro "base"; 300'
    assert letti[0]["Messaggio"] == "riga1\nriga2"
    assert letti[1]["ValoreAttuale"] == "Città"


def test_csv_salvato_da_excel_con_virgola(tmp_path):
    p = tmp_path / "e.csv"
    p.write_text("Id,Campo,NuovoValore\n5,NomeTipo,MUR-EST-300mm-01\n", encoding="utf-8")
    letti = T.leggi_csv(str(p))
    assert letti == [{"Id": "5", "Campo": "NomeTipo", "NuovoValore": "MUR-EST-300mm-01"}]
