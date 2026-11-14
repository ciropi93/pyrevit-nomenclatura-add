# -*- coding: utf-8 -*-
"""Palette contestuale "stile ArchiCAD" (senza API Revit).

Selezionando qualcosa, vicino al cursore compare una palette di icone con i comandi
adatti alla categoria selezionata. Qui stanno:
  - il catalogo dei comandi (modifica di Revit, selezione rapida, visibilita');
  - le categorie (chiave nostra -> categorie Revit OST_*);
  - la configurazione per categoria (predefinita + file personale in %APPDATA%);
  - quali comandi mostrare per una selezione (anche mista);
  - dove mettere la palette sullo schermo.
I comandi CDV legati al contesto (sezioni, viste in tavola, muri) restano in
tasti_contestuali.py e vengono aggiunti dall'overlay come ultima riga.
"""
import io
import json
import os

# ==============================================================================
# GRUPPI E CATALOGO
# ==============================================================================

MODIFICA = u"modifica"
SELEZIONE = u"selezione"
VISIBILITA = u"visibilita"

TITOLI_GRUPPI = [
    (MODIFICA, u"Modifica"),
    (SELEZIONE, u"Selezione"),
    (VISIBILITA, u"Visibilità"),
]

# Esecuzione: "revit" = comando nativo (PostCommand con il nome di PostableCommand),
# "api" = azione nostra in palette_azioni.py.
REVIT = u"revit"
API = u"api"


class Comando(object):
    def __init__(self, id_, gruppo, etichetta, suggerimento, icona, esecuzione,
                 postable=None, categorie=None, max_elementi=None):
        self.id = id_
        self.gruppo = gruppo
        self.etichetta = etichetta
        self.suggerimento = suggerimento
        self.icona = icona
        self.esecuzione = esecuzione
        self.postable = postable          # nome in Autodesk.Revit.UI.PostableCommand
        self.categorie = categorie        # None = tutte; altrimenti insieme di chiavi
        self.max_elementi = max_elementi  # es. 1 per "Crea simile"

    def ammesso(self, chiavi, n):
        if self.max_elementi is not None and n > self.max_elementi:
            return False
        if self.categorie is None:
            return True
        return all(k in self.categorie for k in chiavi)


# Categorie su cui hanno senso alcuni comandi di Revit
_LINEARI = frozenset([u"muri", u"linee", u"strutture"])
_MODELLO = frozenset([u"muri", u"porte", u"finestre", u"pavimenti", u"controsoffitti",
                      u"tetti", u"scale", u"strutture", u"arredi"])

# Icone: tracciati "Path Markup" di WPF in un quadrato 16x16 (F1 = riempimento pieno)
_OCCHIO = (u"M1,8 C4,3 12,3 15,8 C12,13 4,13 1,8 Z "
           u"M8,5.5 A2.5,2.5 0 1 1 8,10.5 A2.5,2.5 0 1 1 8,5.5 Z")

CATALOGO = [
    # --- Modifica (comandi nativi di Revit, partono con la selezione corrente) -----
    Comando(u"sposta", MODIFICA, u"Sposta", u"Sposta gli elementi selezionati (Revit: Sposta)",
            u"F1 M8,0.5 L11,3.5 H9 V7 H12.5 V5 L15.5,8 L12.5,11 V9 H9 V12.5 H11 L8,15.5 "
            u"L5,12.5 H7 V9 H3.5 V11 L0.5,8 L3.5,5 V7 H7 V3.5 H5 Z",
            REVIT, postable=u"Move"),
    Comando(u"copia", MODIFICA, u"Copia", u"Copia gli elementi selezionati (Revit: Copia)",
            u"M1,1 H10 V3 H3 V10 H1 Z M5,5 H15 V15 H5 Z M6.5,6.5 V13.5 H13.5 V6.5 Z",
            REVIT, postable=u"Copy"),
    Comando(u"ruota", MODIFICA, u"Ruota", u"Ruota gli elementi selezionati (Revit: Ruota)",
            u"F1 M8,2 A6,6 0 1 1 2,8 H4 A4,4 0 1 0 8,4 V6.5 L4.5,3 L8,-0.5 Z",
            REVIT, postable=u"Rotate"),
    Comando(u"specchia", MODIFICA, u"Specchia", u"Specchia scegliendo l'asse (Revit: Specchia - Seleziona asse)",
            u"F1 M7.25,0.5 H8.75 V15.5 H7.25 Z M6,3 V13 H1 Z M10,3 V13 H15 Z",
            REVIT, postable=u"MirrorPickAxis"),
    Comando(u"serie", MODIFICA, u"Serie", u"Crea una serie degli elementi selezionati (Revit: Serie)",
            u"F1 M1,5 H4 V10 H1 Z M6,5 H9 V10 H6 Z M11,5 H14 V10 H11 Z M1,12 H15 V13.5 H1 Z",
            REVIT, postable=u"Array", categorie=_MODELLO | frozenset([u"dettagli", u"linee",
                                                                       u"annotazioni"])),
    Comando(u"allinea", MODIFICA, u"Allinea", u"Allinea a un riferimento (Revit: Allinea)",
            u"F1 M1,1 H2.5 V15 H1 Z M4,8 L8,4.5 V7 H15 V9 H8 V11.5 Z",
            REVIT, postable=u"Align"),
    Comando(u"offset", MODIFICA, u"Offset", u"Sposta o copia parallelamente (Revit: Offset)",
            u"F1 M1,2 H15 V3.5 H1 Z M1,12.5 H15 V14 H1 Z M8,5 L10.5,8 H9 V11 H7 V8 H5.5 Z",
            REVIT, postable=u"Offset", categorie=_LINEARI),
    Comando(u"dividi", MODIFICA, u"Dividi", u"Dividi l'elemento in un punto (Revit: Dividi elemento)",
            u"F1 M1,7.25 H6.5 V8.75 H1 Z M9.5,7.25 H15 V8.75 H9.5 Z M7.5,2 H9.5 L8.5,14 H6.5 Z",
            REVIT, postable=u"SplitElement", categorie=_LINEARI),
    Comando(u"taglia_estendi", MODIFICA, u"Taglia/Estendi",
            u"Taglia o estendi fino a formare un angolo (Revit: Taglia/Estendi ad angolo)",
            u"F1 M2,2 H3.5 V12.5 H14 V14 H2 Z M6,4 H12 V10 H10.5 V5.5 H6 Z",
            REVIT, postable=u"TrimOrExtendToCorner", categorie=_LINEARI),
    Comando(u"scala", MODIFICA, u"Scala", u"Scala gli elementi selezionati (Revit: Scala)",
            u"M1,8 H8 V15 H1 Z M2.5,9.5 V13.5 H6.5 V9.5 Z "
            u"M9,1 H15 V7 H13.5 V3.6 L9.6,7.5 L8.5,6.4 L12.4,2.5 H9 Z",
            REVIT, postable=u"Scale", categorie=frozenset([u"linee", u"muri"])),
    Comando(u"crea_simile", MODIFICA, u"Crea simile",
            u"Disegna un nuovo elemento dello stesso tipo (Revit: Crea simile)",
            u"F1 M1,1 H9 V9 H1 Z M10,7 H12 V10 H15 V12 H12 V15 H10 V12 H7 V10 H10 Z",
            REVIT, postable=u"CreateSimilar", max_elementi=1),
    Comando(u"blocca", MODIFICA, u"Blocca/Sblocca",
            u"Blocca gli elementi selezionati; se sono gia' tutti bloccati li sblocca (annullabile)",
            u"F1 M5,1 H11 V3 H10 V7 L12.5,9.5 V11 H8.75 V15.5 H7.25 V11 H3.5 V9.5 L6,7 V3 H5 Z",
            API),
    # --- Selezione rapida -----------------------------------------------------------
    Comando(u"sel_tipo_vista", SELEZIONE, u"Stesso tipo nella vista",
            u"Seleziona tutti gli elementi dello stesso tipo visibili nella vista",
            u"F1 M1,1 H5 V5 H1 Z M6,1 H10 V5 H6 Z M11,1 H15 V5 H11 Z M1,6 H5 V10 H1 Z "
            u"M6,6 V15.5 L8.5,13 L10.5,16 L12,15 L10,12 H13.5 Z",
            API),
    Comando(u"sel_tipo_progetto", SELEZIONE, u"Stesso tipo nel progetto",
            u"Seleziona tutti gli elementi dello stesso tipo in tutto il progetto",
            u"F1 M1,1 H4 V4 H1 Z M6.5,1 H9.5 V4 H6.5 Z M12,1 H15 V4 H12 Z M1,6.5 H4 V9.5 H1 Z "
            u"M6.5,6.5 H9.5 V9.5 H6.5 Z M12,6.5 H15 V9.5 H12 Z M1,12 H4 V15 H1 Z "
            u"M6.5,12 H9.5 V15 H6.5 Z M12,12 H15 V15 H12 Z",
            API),
    Comando(u"sel_categoria_vista", SELEZIONE, u"Stessa categoria nella vista",
            u"Seleziona tutti gli elementi della stessa categoria visibili nella vista",
            u"F1 M1,1 H7 V7 H1 Z M9,1 H15 V7 H9 Z M1,9 H7 V15 H1 Z "
            u"M9,12 A3,3 0 1 1 15,12 A3,3 0 1 1 9,12 Z",
            API),
    # --- Visibilita' nella vista attiva ----------------------------------------------
    Comando(u"nascondi_elementi", VISIBILITA, u"Nascondi elementi",
            u"Nasconde gli elementi selezionati nella vista (annullabile)",
            _OCCHIO + u" M2,13.5 L13.5,2 L14.5,3 L3,14.5 Z", API),
    Comando(u"nascondi_categoria", VISIBILITA, u"Nascondi categoria",
            u"Nasconde la categoria degli elementi selezionati nella vista (annullabile)",
            u"M1,9 H6 V14 H1 Z M10,9 H15 V14 H10 Z M5.5,2 H10.5 V7 H5.5 Z "
            u"M1,14.5 L14,1.5 L15,2.5 L2,15.5 Z", API),
    Comando(u"isola_elementi", VISIBILITA, u"Isola elementi (temporaneo)",
            u"Mostra solo gli elementi selezionati (nascondi/isola temporaneo)",
            u"M0.5,0.5 H15.5 V15.5 H0.5 Z M2,2 V14 H14 V2 Z M5,5 H11 V11 H5 Z", API),
    Comando(u"isola_categoria", VISIBILITA, u"Isola categoria (temporaneo)",
            u"Mostra solo le categorie selezionate (nascondi/isola temporaneo)",
            u"M0.5,0.5 H15.5 V15.5 H0.5 Z M2,2 V14 H14 V2 Z M4,4 H7 V7 H4 Z M9,4 H12 V7 H9 Z "
            u"M4,9 H7 V12 H4 Z M9,9 H12 V12 H9 Z", API),
    Comando(u"ripristina_temporaneo", VISIBILITA, u"Ripristina nascondi/isola",
            u"Toglie il nascondi/isola temporaneo della vista",
            _OCCHIO, API),
    Comando(u"mezzitoni", VISIBILITA, u"Mezzitoni",
            u"Attiva o toglie i mezzitoni sugli elementi selezionati in questa vista (annullabile)",
            u"M1,1 H15 V15 H1 Z M2.5,2.5 V13.5 H8 V2.5 Z", API),
]

PER_ID = dict((c.id, c) for c in CATALOGO)

# ==============================================================================
# CATEGORIE
# ==============================================================================

# (chiave, nome per l'utente, categorie Revit)
CATEGORIE = [
    (u"muri", u"Muri", [u"OST_Walls"]),
    (u"porte", u"Porte", [u"OST_Doors"]),
    (u"finestre", u"Finestre", [u"OST_Windows"]),
    (u"pavimenti", u"Pavimenti e solai", [u"OST_Floors"]),
    (u"controsoffitti", u"Controsoffitti", [u"OST_Ceilings"]),
    (u"tetti", u"Tetti", [u"OST_Roofs"]),
    (u"scale", u"Scale e ringhiere", [u"OST_Stairs", u"OST_StairsRailing", u"OST_Ramps"]),
    (u"strutture", u"Pilastri e travi", [u"OST_StructuralColumns", u"OST_StructuralFraming",
                                         u"OST_Columns"]),
    (u"arredi", u"Arredi e componenti", [u"OST_Furniture", u"OST_GenericModel", u"OST_Casework",
                                         u"OST_PlumbingFixtures", u"OST_SpecialityEquipment",
                                         u"OST_LightingFixtures", u"OST_MechanicalEquipment",
                                         u"OST_ElectricalFixtures", u"OST_Planting",
                                         u"OST_Entourage"]),
    (u"dettagli", u"Componenti di dettaglio", [u"OST_DetailComponents"]),
    (u"campiture", u"Campiture", []),           # FilledRegion: si riconosce dalla classe
    (u"linee", u"Linee", [u"OST_Lines"]),
    (u"annotazioni", u"Testi, quote e etichette", [u"OST_TextNotes", u"OST_Dimensions",
                                                   u"OST_GenericAnnotation"]),
    (u"locali", u"Locali e aree", [u"OST_Rooms", u"OST_Areas"]),
    (u"viste_tavola", u"Viste in tavola", [u"OST_Viewports"]),
    (u"sezioni", u"Sezioni e prospetti", [u"OST_Viewers", u"OST_Elev"]),
    (u"altro", u"Altro", []),
]

CHIAVI = [k for k, _, _ in CATEGORIE]
NOMI_CATEGORIE = dict((k, nome) for k, nome, _ in CATEGORIE)
_DA_OST = dict((ost, k) for k, _, osts in CATEGORIE for ost in osts)


def chiave_categoria(nome_ost, nome_classe=None):
    """Chiave della palette per un elemento: dalla classe .NET o dalla categoria OST_*."""
    if nome_classe == u"FilledRegion":
        return u"campiture"
    if nome_ost:
        if nome_ost in _DA_OST:
            return _DA_OST[nome_ost]
        if nome_ost.endswith(u"Tags"):
            return u"annotazioni"
    return u"altro"


# ==============================================================================
# CONFIGURAZIONE
# ==============================================================================

_BASE_MODIFICA = [u"sposta", u"copia", u"ruota", u"specchia", u"serie", u"allinea", u"blocca"]
_LINEARI_EXTRA = [u"offset", u"dividi", u"taglia_estendi"]
_SELEZIONE = [u"sel_tipo_vista", u"sel_tipo_progetto", u"sel_categoria_vista"]
_VISIBILITA = [u"nascondi_elementi", u"nascondi_categoria", u"isola_elementi",
               u"isola_categoria", u"ripristina_temporaneo", u"mezzitoni"]
_STANDARD = _BASE_MODIFICA + _SELEZIONE + _VISIBILITA


def _predefiniti(chiave):
    if chiave == u"viste_tavola":
        return [u"sposta", u"blocca", u"sel_tipo_vista"]
    if chiave == u"sezioni":
        return [u"sposta", u"copia", u"ruota", u"specchia", u"blocca", u"sel_categoria_vista",
                u"nascondi_elementi", u"isola_elementi", u"ripristina_temporaneo"]
    out = list(_STANDARD)
    if chiave in (u"muri", u"strutture"):
        out += _LINEARI_EXTRA + [u"crea_simile"]
    elif chiave == u"linee":
        out += _LINEARI_EXTRA + [u"scala", u"crea_simile"]
    elif chiave in _MODELLO or chiave in (u"dettagli", u"campiture", u"annotazioni"):
        out += [u"crea_simile"]
    return out


def ammessi_per_categoria(chiave):
    """Comandi del catalogo che si possono usare per una categoria (in ordine di catalogo)."""
    return [c.id for c in CATALOGO if c.ammesso([chiave], 1)]


def _pulisci(chiave, ids):
    ammessi = set(ammessi_per_categoria(chiave))
    return [i for i in ids if i in ammessi]


def config_predefinita():
    return {
        u"attiva": True,
        u"categorie": dict((k, _pulisci(k, _predefiniti(k))) for k in CHIAVI),
    }


def unisci_config(utente):
    """Predefinita aggiornata con il file personale.

    Comandi sconosciuti o non ammessi per la categoria vengono scartati; le categorie
    non presenti nel file restano quelle predefinite (cosi' le novita' arrivano da sole).
    """
    cfg = config_predefinita()
    if not isinstance(utente, dict):
        return cfg
    if u"attiva" in utente:
        cfg[u"attiva"] = bool(utente[u"attiva"])
    cat = utente.get(u"categorie")
    if isinstance(cat, dict):
        for k, ids in cat.items():
            if k in cfg[u"categorie"] and isinstance(ids, list):
                cfg[u"categorie"][k] = _pulisci(k, ids)
    return cfg


def percorso_config():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "pyRevit", "CDVTools", "palette.json")


def carica_config(percorso=None):
    """Config della palette; se il file manca o e' rovinato, quella predefinita."""
    percorso = percorso or percorso_config()
    dati = None
    if os.path.exists(percorso):
        try:
            with io.open(percorso, "r", encoding="utf-8-sig") as f:
                dati = json.load(f)
        except Exception:
            dati = None
    return unisci_config(dati)


def salva_config(cfg, percorso=None):
    percorso = percorso or percorso_config()
    cartella = os.path.dirname(percorso)
    if cartella and not os.path.isdir(cartella):
        os.makedirs(cartella)
    testo = json.dumps(cfg, indent=2, ensure_ascii=False, sort_keys=True)
    if not isinstance(testo, type(u"")):
        testo = testo.decode("utf-8")
    with io.open(percorso, "w", encoding="utf-8") as f:
        f.write(testo + u"\n")


def imposta_attiva(attiva, percorso=None):
    """Accende/spegne la palette mantenendo il resto della configurazione."""
    cfg = carica_config(percorso)
    cfg[u"attiva"] = bool(attiva)
    salva_config(cfg, percorso)
    return cfg


# ==============================================================================
# COMANDI PER UNA SELEZIONE
# ==============================================================================

def palette_per_selezione(chiavi, n, cfg, disponibili=None):
    """Gruppi di tasti: [(titolo_gruppo, [(id, etichetta, suggerimento)])].

    chiavi: categorie (chiavi della palette) degli elementi selezionati; n: quanti sono.
    Con una selezione mista si mostrano i comandi comuni a tutte le categorie.
    disponibili: id utilizzabili in questa versione di Revit (None = tutti).
    """
    if not cfg.get(u"attiva", True) or not chiavi or n < 1:
        return []
    chiavi = sorted(set(chiavi))
    per_cat = cfg.get(u"categorie", {})
    scelti = None
    for k in chiavi:
        ids = set(per_cat.get(k, per_cat.get(u"altro", [])))
        scelti = ids if scelti is None else (scelti & ids)
    gruppi = []
    for gruppo, titolo in TITOLI_GRUPPI:
        tasti = [(c.id, c.etichetta, c.suggerimento) for c in CATALOGO
                 if c.gruppo == gruppo and c.id in scelti and c.ammesso(chiavi, n)
                 and (disponibili is None or c.id in disponibili)]
        if tasti:
            gruppi.append((titolo, tasti))
    return gruppi


# ==============================================================================
# POSIZIONE SULLO SCHERMO
# ==============================================================================

def schermo_a_vista(punto, zoom_uv, finestra):
    """Pixel sullo schermo (x, y) -> coordinate della vista (u, v). Inverso di proietta."""
    (u0, v0), (u1, v1) = zoom_uv
    sx, alto, dx, basso = finestra
    larg = (dx - sx) or 1e-9
    alt = (basso - alto) or 1e-9
    u = u0 + (punto[0] - sx) / float(larg) * (u1 - u0)
    v = v0 + (basso - punto[1]) / float(alt) * (v1 - v0)
    return u, v


def dentro(punto, finestra):
    sx, alto, dx, basso = finestra
    return sx <= punto[0] <= dx and alto <= punto[1] <= basso


def posizione_palette(cursore, finestra, larghezza, altezza, distacco=12):
    """Angolo in alto a sinistra della palette: in basso a destra del cursore.

    Se esce dalla vista si ribalta a sinistra e/o sopra il cursore, e comunque resta
    dentro la vista. None se il cursore e' fuori dalla vista.
    """
    if cursore is None or not dentro(cursore, finestra):
        return None
    cx, cy = cursore
    sx, alto, dx, basso = finestra
    x = cx + distacco
    y = cy + distacco
    if x + larghezza > dx:
        x = cx - distacco - larghezza
    if y + altezza > basso:
        y = cy - distacco - altezza
    x = max(min(x, dx - larghezza), sx)
    y = max(min(y, basso - altezza), alto)
    return x, y
