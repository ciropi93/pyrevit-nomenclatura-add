# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "CDVTools.extension", "lib"))

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


def test_colonna_modello(tmp_path):
    p = str(tmp_path / "m.csv")
    T.scrivi_csv(p, [{"Modello": "AQD0031-ADD-CF1234567-ZZ-M3-A-PN0001", "Id": 7,
                      "ValoreAttuale": "x", "NuovoValore": "y"}])
    letti = T.leggi_csv(p)
    assert letti[0]["Modello"] == "AQD0031-ADD-CF1234567-ZZ-M3-A-PN0001"
    assert T.COLONNE[0] == "Modello"


def test_csv_risalvato_da_excel_in_cp1252(tmp_path):
    # "CSV (delimitato dal separatore di elenco)" di Excel italiano: cp1252, ';', a capo CRLF
    p = tmp_path / "excel.csv"
    testo = 'Id;Campo;ValoreAttuale;NuovoValore\r\n9;NomeLocale;Città;"Uffici, sala"\r\n'
    p.write_bytes(testo.encode("cp1252"))
    letti = T.leggi_csv(str(p))
    assert letti == [{"Id": "9", "Campo": "NomeLocale", "ValoreAttuale": "Città",
                      "NuovoValore": "Uffici, sala"}]


def test_a_capo_dentro_cella_normalizzati(tmp_path):
    p = tmp_path / "c.csv"
    p.write_bytes('Id;Messaggio\r\n1;"a\r\nb"\r\n'.encode("utf-8"))
    assert T.leggi_csv(str(p)) == [{"Id": "1", "Messaggio": "a\nb"}]
