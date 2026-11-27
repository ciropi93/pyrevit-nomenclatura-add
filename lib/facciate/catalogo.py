# -*- coding: utf-8 -*-
"""Schemi di facciata pronti e schemi dell'utente (senza API Revit).

Gli schemi dell'utente stanno in %APPDATA%\\pyRevit\\CDVTools\\facciate\\schemi\\<nome>.json.
"""
import os

from facciate import ritmo as R
from facciate import schema as S
from infissi import catalogo as IC     # stessi file JSON e nomi di file degli infissi


def _vetro_con_parapetto(parapetto=900.0):
    """Righe: parapetto bloccato e vetro libero, che ripartono in ogni piano."""
    return S.regola([S.modulo(u"P", parapetto, True), S.modulo(u"V", 2100)], [u"P", u"V"],
                    livelli=S.livelli(True))


def preimpostati():
    M, Rg = S.modulo, S.regola
    righe_piano = Rg([M(u"V", 3000)], [u"V"], livelli=S.livelli(True))
    return [
        S.nuovo(Rg([M(u"A", 1500)], [u"A"]), righe_piano, u"Modulo costante"),
        S.nuovo(Rg([M(u"A", 1200)], [u"A"], R.FISSO, origine=R.CENTRO, resto=u"cieco",
                   resto_minimo=300),
                Rg([M(u"A", 1200)], [u"A"], R.FISSO, livelli=S.livelli(False)),
                u"Griglia fissa centrata"),
        S.nuovo(Rg([M(u"A", 1500), M(u"B", 600, True)], [u"A", u"B"], finisci_con=0),
                righe_piano, u"A-B alternato", celle={u"1,*": u"cieco"}),
        S.nuovo(Rg([M(u"A", 1350), M(u"B", 400, True)], [u"A", u"A", u"B"]), righe_piano,
                u"A A B con lesena", celle={u"2,*": u"cieco"},
                linee={u"colonne": [R.MONTANTE, u"lesena", u"lesena"]}),
        S.nuovo(Rg([M(u"A", 1500)], [u"A"]), _vetro_con_parapetto(), u"Vetro con parapetto",
                celle={u"*,0": u"cieco"}),
        S.nuovo(Rg([M(u"A", 1500)], [u"A"]),
                Rg([M(u"V", 2400), M(u"S", 600, True)], [u"V", u"S"], livelli=S.livelli(True)),
                u"Fasce marcapiano", celle={u"*,1": u"cieco"}),
        S.nuovo(Rg([M(u"A", 1350), M(u"B", 1350)], [u"A", u"A", u"B"]), _vetro_con_parapetto(),
                u"Parapetto continuo", celle={u"*,0": u"cieco"},
                unioni=[{u"colonne": [0, 2], u"righe": [0, 0]}]),
    ]


# --- percorsi -------------------------------------------------------------------------
def cartella_base():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "pyRevit", "CDVTools", "facciate")


def cartella_schemi(base=None):
    return os.path.join(base or cartella_base(), "schemi")


def salva_schema(schema, base=None):
    percorso = os.path.join(cartella_schemi(base), IC.nome_file(schema.get(u"nome")))
    IC._scrivi(percorso, schema)
    return percorso


def schemi_utente(base=None):
    """[(percorso, schema)] ordinati per nome; i file rovinati si saltano."""
    cartella = cartella_schemi(base)
    if not os.path.isdir(cartella):
        return []
    out = []
    for nome in sorted(os.listdir(cartella)):
        if not nome.lower().endswith(".json"):
            continue
        percorso = os.path.join(cartella, nome)
        try:
            out.append((percorso, S.normalizza(IC._leggi(percorso))))
        except Exception:
            continue
    return out


def elimina_schema(percorso):
    if os.path.exists(percorso):
        os.remove(percorso)
