# -*- coding: utf-8 -*-
"""Palette contestuale "stile ArchiCAD" (senza API Revit).

Selezionando qualcosa, vicino al cursore compare una palette piccola su tre livelli:
  1. riga principale: in blu gli strumenti CDV della categoria (tasti_contestuali.py,
     es. Inverti muro), poi al massimo 5 comandi "in vista" scelti per categoria e il
     tasto "..." che apre il menu con il resto, diviso per gruppi;
  2. menu "...": i comandi "nel menu" della categoria, con nome;
  3. fila fissa, piccola e uguale per tutte le categorie: nascondi, mezzitoni,
     copia grafica (matchprop), blocca...
Qui stanno il catalogo dei comandi, le categorie (chiave nostra -> OST_*), la
configurazione (predefinita + file personale in %APPDATA%), la struttura della
palette per una selezione (anche mista) e la posizione sullo schermo.
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
                 postable=None, categorie=None, max_elementi=None, interattivo=False):
        self.id = id_
        self.gruppo = gruppo
        self.etichetta = etichetta
        self.suggerimento = suggerimento
        self.icona = icona
        self.esecuzione = esecuzione
        self.postable = postable          # nome in Autodesk.Revit.UI.PostableCommand
        self.categorie = categorie        # None = tutte; altrimenti insieme di chiavi
        self.max_elementi = max_elementi  # es. 1 per "Crea simile"
        self.interattivo = interattivo    # chiede di cliccare nella vista: palette via intanto

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
    Comando(u"copia_grafica", VISIBILITA, u"Copia grafica",
            u"Come il matchprop di AutoCAD, nella vista attiva: con un elemento selezionato "
            u"clicca gli elementi a cui copiarne la grafica (Esc per finire); con piu' elementi "
            u"selezionati clicca l'elemento da cui copiarla. Annullabile.",
            u"F1 M10,1 L15,6 L13.6,7.4 L12.5,6.3 L6.2,12.6 C5.4,13.4 4.2,13.6 3.4,13.2 "
            u"L1.6,15 L1,14.4 L2.8,12.6 C2.4,11.8 2.6,10.6 3.4,9.8 L9.7,3.5 L8.6,2.4 Z",
            API, interattivo=True),
    Comando(u"mezzitoni", VISIBILITA, u"Mezzitoni",
            u"Attiva o toglie i mezzitoni sugli elementi selezionati in questa vista (annullabile)",
            u"M1,1 H15 V15 H1 Z M2.5,2.5 V13.5 H8 V2.5 Z", API),
]

PER_ID = dict((c.id, c) for c in CATALOGO)

# Livelli di un comando per una categoria
IN_VISTA = u"vista"
NEL_MENU = u"menu"
NASCOSTO = u"no"
MAX_IN_VISTA = 5
MAX_FISSA = 6

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


# Visibilita' e grafica non hanno senso sui riquadri delle viste in tavola
for _c in CATALOGO:
    if _c.gruppo == VISIBILITA and _c.categorie is None:
        _c.categorie = frozenset(k for k in CHIAVI if k != u"viste_tavola")


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
# {"attiva": bool, "fissa": [id...],
#  "categorie": {chiave: {"vista": [id...], "menu": [id...]}}}
# Un comando non elencato ne' in "vista" ne' in "menu" e' nascosto per quella categoria.

FISSA_PREDEFINITA = [u"nascondi_elementi", u"nascondi_categoria", u"mezzitoni",
                     u"copia_grafica", u"blocca"]
_VISTA_STD = [u"sposta", u"copia", u"ruota", u"specchia"]


def ammessi_per_categoria(chiave):
    """Comandi del catalogo che si possono usare per una categoria (in ordine di catalogo)."""
    return [c.id for c in CATALOGO if c.ammesso([chiave], 1)]


def _pulisci(chiave, ids, escludi=()):
    ammessi = set(ammessi_per_categoria(chiave)) - set(escludi)
    visti = set()
    out = []
    for i in ids:
        if i in ammessi and i not in visti:
            out.append(i)
            visti.add(i)
    return out


def _predefiniti(chiave, fissa):
    if chiave == u"viste_tavola":
        vista, menu = [u"sposta"], [u"sel_tipo_vista"]
    else:
        vista = list(_VISTA_STD)
        menu = [c.id for c in CATALOGO if c.id not in vista]
        if chiave == u"sezioni":
            menu = [i for i in menu if i in (u"sel_categoria_vista", u"isola_elementi",
                                             u"ripristina_temporaneo")]
    vista = _pulisci(chiave, vista, fissa)[:MAX_IN_VISTA]
    menu = _pulisci(chiave, menu, set(fissa) | set(vista))
    return {IN_VISTA: vista, NEL_MENU: menu}


def config_predefinita():
    fissa = list(FISSA_PREDEFINITA)
    return {
        u"attiva": True,
        u"fissa": fissa,
        u"categorie": dict((k, _predefiniti(k, fissa)) for k in CHIAVI),
    }


def _normalizza_categoria(chiave, voce, fissa):
    vista = _pulisci(chiave, voce.get(IN_VISTA, []), fissa)[:MAX_IN_VISTA]
    menu = _pulisci(chiave, voce.get(NEL_MENU, []), set(fissa) | set(vista))
    return {IN_VISTA: vista, NEL_MENU: menu}


def unisci_config(utente):
    """Predefinita aggiornata con il file personale.

    Comandi sconosciuti, doppi o non ammessi vengono scartati; le categorie non presenti
    nel file (o salvate nel vecchio formato a lista) restano quelle predefinite.
    """
    cfg = config_predefinita()
    if not isinstance(utente, dict):
        return cfg
    if u"attiva" in utente:
        cfg[u"attiva"] = bool(utente[u"attiva"])
    if isinstance(utente.get(u"fissa"), list):
        cfg[u"fissa"] = [i for i in _unici(utente[u"fissa"]) if i in PER_ID][:MAX_FISSA]
    fissa = cfg[u"fissa"]
    cat = utente.get(u"categorie")
    for k in CHIAVI:
        voce = cat.get(k) if isinstance(cat, dict) else None
        if isinstance(voce, dict):
            cfg[u"categorie"][k] = _normalizza_categoria(k, voce, fissa)
        else:
            cfg[u"categorie"][k] = _normalizza_categoria(k, cfg[u"categorie"][k], fissa)
    return cfg


def _unici(ids):
    out = []
    for i in ids:
        if i not in out:
            out.append(i)
    return out


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
# STRUTTURA DELLA PALETTE PER UNA SELEZIONE
# ==============================================================================

def _voce(c):
    return (c.id, c.etichetta, c.suggerimento)


def struttura_palette(chiavi, n, cfg, disponibili=None, cdv=None):
    """Cosa mostrare per una selezione, oppure None se non c'e' nulla.

    chiavi: categorie (chiavi della palette) degli elementi selezionati; n: quanti sono;
    cdv: gruppi di strumenti CDV del contesto [(nome, [(id, etichetta, suggerimento)])].
    Con una selezione mista valgono i comandi comuni a tutte le categorie.

    Ritorna {"cdv": [...], "vista": [...], "menu": [...], "fissa": [...]}:
      cdv: voci ("tasto", id, etichetta, suggerimento) per i gruppi di 1-2 strumenti,
           ("gruppo", nome, [tasti]) per quelli piu' grandi (si aprono come menu);
      vista, fissa: [(id, etichetta, suggerimento)];
      menu: [(titolo_gruppo, [(id, etichetta, suggerimento)])].
    """
    if not cfg.get(u"attiva", True) or not chiavi or n < 1:
        return None
    chiavi = sorted(set(chiavi))
    per_cat = cfg.get(u"categorie", {})

    def utilizzabile(c):
        return c.ammesso(chiavi, n) and (disponibili is None or c.id in disponibili)

    def comuni(livello):
        scelti = None
        for k in chiavi:
            ids = set(per_cat.get(k, per_cat.get(u"altro", {})).get(livello, []))
            scelti = ids if scelti is None else (scelti & ids)
        return scelti or set()

    fissa_ids = set(cfg.get(u"fissa", []))
    fissa = [_voce(PER_ID[i]) for i in cfg.get(u"fissa", [])
             if i in PER_ID and utilizzabile(PER_ID[i])]
    in_vista = comuni(IN_VISTA) - fissa_ids
    vista = [_voce(c) for c in CATALOGO if c.id in in_vista and utilizzabile(c)][:MAX_IN_VISTA]
    gia = fissa_ids | set(v[0] for v in vista)
    nel_menu = comuni(NEL_MENU) - gia
    menu = []
    for gruppo, titolo in TITOLI_GRUPPI:
        tasti = [_voce(c) for c in CATALOGO
                 if c.gruppo == gruppo and c.id in nel_menu and utilizzabile(c)]
        if tasti:
            menu.append((titolo, tasti))
    voci_cdv = []
    for nome, tasti in (cdv or []):
        if len(tasti) <= 2:
            voci_cdv.extend((u"tasto",) + tuple(t) for t in tasti)
        elif tasti:
            voci_cdv.append((u"gruppo", nome, list(tasti)))
    if not (voci_cdv or vista or menu or fissa):
        return None
    return {u"cdv": voci_cdv, u"vista": vista, u"menu": menu, u"fissa": fissa}


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



# ==============================================================================
# MODIFICHE DALLA FINESTRA DI PERSONALIZZAZIONE
# ==============================================================================

def copia_config(cfg):
    """Copia indipendente (la finestra lavora su questa finche' non si salva)."""
    return {
        u"attiva": bool(cfg.get(u"attiva", True)),
        u"fissa": list(cfg.get(u"fissa", [])),
        u"categorie": dict((k, {IN_VISTA: list(v.get(IN_VISTA, [])),
                                NEL_MENU: list(v.get(NEL_MENU, []))})
                           for k, v in cfg.get(u"categorie", {}).items()),
    }


def livello(cfg, chiave, comando):
    voce = cfg[u"categorie"].get(chiave, {})
    if comando in voce.get(IN_VISTA, []):
        return IN_VISTA
    if comando in voce.get(NEL_MENU, []):
        return NEL_MENU
    return NASCOSTO


def imposta_livello(cfg, chiave, comando, nuovo):
    """Mette un comando in vista, nel menu o lo nasconde per una categoria.

    Ritorna False (senza cambiare nulla) se in vista ci sono gia' MAX_IN_VISTA comandi
    o se il comando sta nella fila fissa.
    """
    if comando in cfg.get(u"fissa", []) or comando not in ammessi_per_categoria(chiave):
        return False
    voce = cfg[u"categorie"].setdefault(chiave, {IN_VISTA: [], NEL_MENU: []})
    vista = [i for i in voce.get(IN_VISTA, []) if i != comando]
    menu = [i for i in voce.get(NEL_MENU, []) if i != comando]
    if nuovo == IN_VISTA:
        if len(vista) >= MAX_IN_VISTA:
            return False
        vista.append(comando)
    elif nuovo == NEL_MENU:
        menu.append(comando)
    ordine = ammessi_per_categoria(chiave)
    voce[IN_VISTA] = [i for i in ordine if i in vista]
    voce[NEL_MENU] = [i for i in ordine if i in menu]
    return True


def imposta_fissa(cfg, comando, attivo):
    """Aggiunge/toglie un comando dalla fila fissa (False se e' gia' piena).

    Un comando nella fila fissa sparisce da vista e menu di tutte le categorie;
    tolto dalla fila torna nel menu delle categorie dove e' ammesso.
    """
    fissa = [i for i in cfg.get(u"fissa", []) if i != comando]
    if attivo:
        if len(fissa) >= MAX_FISSA:
            return False
        fissa.append(comando)
    cfg[u"fissa"] = [c.id for c in CATALOGO if c.id in fissa]
    for k in CHIAVI:
        voce = cfg[u"categorie"].setdefault(k, {IN_VISTA: [], NEL_MENU: []})
        if attivo:
            voce[IN_VISTA] = [i for i in voce[IN_VISTA] if i != comando]
            voce[NEL_MENU] = [i for i in voce[NEL_MENU] if i != comando]
        elif comando in ammessi_per_categoria(k):
            imposta_livello(cfg, k, comando, NEL_MENU)
    return True


def ripristina_categoria(cfg, chiave):
    cfg[u"categorie"][chiave] = _predefiniti(chiave, cfg.get(u"fissa", []))
    return cfg


def copia_su_tutte(cfg, chiave):
    """Stessa scelta della categoria 'chiave' su tutte le altre (dove il comando e' ammesso)."""
    sorgente = cfg[u"categorie"].get(chiave, {})
    fissa = cfg.get(u"fissa", [])
    for k in CHIAVI:
        cfg[u"categorie"][k] = _normalizza_categoria(k, sorgente, fissa)
    return cfg
