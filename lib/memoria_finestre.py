# -*- coding: utf-8 -*-
"""Ricorda le ultime scelte fatte nelle finestre dei comandi (senza API Revit).

Ogni comando indica per nome i controlli da ricordare (caselle, scelte, campi di testo,
elenchi a tendina). Al clic su Applica lo stato viene salvato; alla riapertura viene
rimesso com'era. Tutte le finestre stanno in un solo file:
%APPDATA%\\pyRevit\\CDVTools\\finestre.json  ->  {comando: {controllo: valore}}.

I controlli si riconoscono da come sono fatti (duck typing), cosi' il modulo si prova
senza WPF:
  - scelta (RadioButton): ha IsChecked e GroupName; si rimette solo quella accesa;
  - casella (CheckBox): ha IsChecked;
  - elenco (ComboBox): ha SelectedItem; si ricorda il testo della voce scelta;
  - campo (TextBox): ha Text.
"""
import io
import json
import os

_TESTO = type(u"")


def percorso_file():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "pyRevit", "CDVTools", "finestre.json")


def leggi_tutto(percorso=None):
    """{comando: {controllo: valore}}; vuoto se il file manca o e' rovinato."""
    percorso = percorso or percorso_file()
    try:
        with io.open(percorso, "r", encoding="utf-8-sig") as f:
            dati = json.load(f)
    except Exception:
        return {}
    if not isinstance(dati, dict):
        return {}
    return dict((k, v) for k, v in dati.items() if isinstance(v, dict))


def scrivi_tutto(dati, percorso=None):
    percorso = percorso or percorso_file()
    cartella = os.path.dirname(percorso)
    if cartella and not os.path.isdir(cartella):
        os.makedirs(cartella)
    testo = json.dumps(dati, indent=2, ensure_ascii=False, sort_keys=True)
    if not isinstance(testo, _TESTO):
        testo = testo.decode("utf-8")
    with io.open(percorso, "w", encoding="utf-8") as f:
        f.write(testo + u"\n")


def impostazioni(comando, percorso=None):
    """Lo stato salvato per il comando ({} se mai salvato)."""
    return leggi_tutto(percorso).get(comando, {})


def ha_impostazioni(comando, percorso=None):
    return bool(impostazioni(comando, percorso))


# ------------------------------------------------------------------------------
# CONTROLLI
# ------------------------------------------------------------------------------

def testo_voce(voce):
    """Il testo con cui una voce di elenco compare (Name, Content o la voce stessa)."""
    for attr in ("Name", "Content"):
        v = getattr(voce, attr, None)
        if v is not None:
            return u"%s" % v
    return u"%s" % voce


def _tipo(ctrl):
    if hasattr(ctrl, "IsChecked"):
        return u"scelta" if hasattr(ctrl, "GroupName") else u"casella"
    if hasattr(ctrl, "SelectedItem"):
        return u"elenco"
    if hasattr(ctrl, "Text"):
        return u"campo"
    return None


def leggi_controllo(ctrl):
    """Valore da salvare, o None se il controllo non si sa leggere."""
    tipo = _tipo(ctrl)
    if tipo in (u"scelta", u"casella"):
        return bool(ctrl.IsChecked)
    if tipo == u"elenco":
        return testo_voce(ctrl.SelectedItem) if ctrl.SelectedItem is not None else None
    if tipo == u"campo":
        return u"%s" % ctrl.Text
    return None


def scrivi_controllo(ctrl, valore):
    """Rimette il valore; True se il controllo e' stato cambiato."""
    tipo = _tipo(ctrl)
    if tipo == u"scelta":
        if valore:  # spegnere una scelta lascerebbe il gruppo senza nessuna accesa
            ctrl.IsChecked = True
            return True
        return False
    if tipo == u"casella":
        ctrl.IsChecked = bool(valore)
        return True
    if tipo == u"elenco":
        for i, voce in enumerate(ctrl.Items):
            if testo_voce(voce) == valore:
                ctrl.SelectedIndex = i
                return True
        return False  # la voce non c'e' piu' (es. tipo eliminato): resta quella predefinita
    if tipo == u"campo":
        ctrl.Text = valore
        return True
    return False


def stato_finestra(win, nomi):
    stato = {}
    for nome in nomi:
        try:
            v = leggi_controllo(getattr(win, nome))
        except Exception:
            v = None
        if v is not None:
            stato[nome] = v
    return stato


def salva(win, comando, nomi, percorso=None):
    """Salva lo stato dei controlli 'nomi'; non solleva mai eccezioni."""
    try:
        dati = leggi_tutto(percorso)
        dati[comando] = stato_finestra(win, nomi)
        scrivi_tutto(dati, percorso)
    except Exception:
        pass


def ripristina(win, comando, nomi, percorso=None):
    """Rimette le ultime scelte; True se c'era qualcosa da rimettere."""
    stato = impostazioni(comando, percorso)
    # prima caselle/campi/elenchi, poi le scelte: accendere una scelta puo' attivare
    # parti della finestra che leggono gli altri controlli
    ordine = sorted((n for n in nomi if n in stato),
                    key=lambda n: 1 if _tipo(getattr(win, n, None)) == u"scelta" else 0)
    for nome in ordine:
        try:
            scrivi_controllo(getattr(win, nome), stato[nome])
        except Exception:
            pass
    return bool(stato)


# ------------------------------------------------------------------------------
# VALORI SINGOLI (es. "da quale modello e' stata sganciata questa vista")
# ------------------------------------------------------------------------------

def valore(comando, chiave, predefinito=None, percorso=None):
    return impostazioni(comando, percorso).get(chiave, predefinito)


def imposta_valore(comando, chiave, val, percorso=None):
    """Salva un valore (None lo toglie); non solleva mai eccezioni."""
    try:
        dati = leggi_tutto(percorso)
        voci = dati.setdefault(comando, {})
        if val is None:
            voci.pop(chiave, None)
        else:
            voci[chiave] = val
        scrivi_tutto(dati, percorso)
    except Exception:
        pass
