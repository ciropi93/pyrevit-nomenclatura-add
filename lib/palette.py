# -*- coding: utf-8 -*-
"""Palette contestuale "stile ArchiCAD" (senza API Revit).

Selezionando qualcosa, accanto al cursore compare una palette piccola:
  - sopra, la fila fissa (uguale per tutte le categorie): nascondi, mezzitoni,
    copia grafica, blocca...;
  - sotto, una riga di tasti "famiglia": prima gli strumenti CDV del contesto
    (tasti_contestuali.py: Inverti muro, allineamenti...), poi Trasforma, Forma,
    Seleziona, Vista, Isola. Il tasto mostra l'ultimo strumento usato della famiglia
    (clic = lo rifa'); passando sopra si apre la griglia con tutti gli strumenti,
    icona e nome.
Qui stanno il catalogo (con le icone a due colori), le famiglie, le categorie
(chiave nostra -> OST_*), la configurazione (predefinita + file personale in
%APPDATA%), la struttura della palette per una selezione e la posizione sullo schermo.
"""
import io
import json
import os

# ==============================================================================
# FAMIGLIE E CATALOGO
# ==============================================================================

TRASFORMA = u"trasforma"
FORMA = u"forma"
SELEZIONA = u"seleziona"
VISTA = u"vista"
ISOLA = u"isola"

FAMIGLIE = [
    (TRASFORMA, u"Trasforma"),     # dove sta l'oggetto
    (FORMA, u"Forma"),             # com'e' fatto
    (SELEZIONA, u"Seleziona"),     # trova simili
    (VISTA, u"Vista"),             # come si vede (di serie tutti nella fila fissa)
    (ISOLA, u"Isola"),             # cosa vedo, temporaneo
]
NOMI_FAMIGLIE = dict(FAMIGLIE)

# Esecuzione: "revit" = comando nativo (PostCommand con il nome di PostableCommand),
# "api" = azione nostra in palette_azioni.py.
REVIT = u"revit"
API = u"api"

# Icone: livelli in un quadrato 16x16, disegnati da noi nello stile di Revit
# ("f", colore, tracciato) = riempimento; ("s", colore, tracciato, spessore[, tratteggio])
# = contorno. Blu per l'oggetto, arancio per l'azione, scuro per i riferimenti.
BLU = u"#1F6FB2"
AZZURRO = u"#CFE3F4"
ARANCIO = u"#E5862A"
SCURO = u"#3C4650"
GRIGIO = u"#AAB4BC"
BIANCO = u"#FFFFFF"

_OCCHIALI = [(u"f", SCURO, u"M1,2.5 H7 V5.5 C7,7 5.6,7.6 4,7.6 C2.4,7.6 1,7 1,5.5 Z "
                           u"M9,2.5 H15 V5.5 C15,7 13.6,7.6 12,7.6 C10.4,7.6 9,7 9,5.5 Z"),
             (u"s", SCURO, u"M7,3.6 H9", 1.2)]
_CURSORE = [(u"f", BIANCO, u"M7.5,7 V15.6 L9.5,13.6 L11,16 L12.6,15.2 L11.1,12.9 H14 Z"),
            (u"s", SCURO, u"M7.5,7 V15.6 L9.5,13.6 L11,16 L12.6,15.2 L11.1,12.9 H14 Z", 0.9)]

ICONE = {
    u"sposta": [(u"f", BLU, u"M8,0.5 L11,3.5 H9 V7 H12.5 V5 L15.5,8 L12.5,11 V9 H9 V12.5 H11 "
                           u"L8,15.5 L5,12.5 H7 V9 H3.5 V11 L0.5,8 L3.5,5 V7 H7 V3.5 H5 Z"),
                (u"f", ARANCIO, u"M6.6,6.6 H9.4 V9.4 H6.6 Z")],
    u"copia": [(u"f", BIANCO, u"M1.5,1.5 H10 V10 H1.5 Z"), (u"s", SCURO, u"M1.5,1.5 H10 V10 H1.5 Z", 1),
               (u"f", AZZURRO, u"M5.5,5.5 H14.5 V14.5 H5.5 Z"),
               (u"s", BLU, u"M5.5,5.5 H14.5 V14.5 H5.5 Z", 1.2),
               (u"f", ARANCIO, u"M9.25,7.5 H10.75 V9.25 H12.5 V10.75 H10.75 V12.5 H9.25 V10.75 "
                               u"H7.5 V9.25 H9.25 Z")],
    u"ruota": [(u"f", AZZURRO, u"M5.6,6.2 L11.4,7.6 L10,13.2 L4.2,11.8 Z"),
               (u"s", BLU, u"M5.6,6.2 L11.4,7.6 L10,13.2 L4.2,11.8 Z", 1.1),
               (u"s", ARANCIO, u"M2.2,6.5 A6.2,6.2 0 0 1 12.6,3.2", 1.5),
               (u"f", ARANCIO, u"M15,1.6 L14.6,6.4 L10.6,4.4 Z")],
    u"specchia": [(u"f", SCURO, u"M7.4,0.5 H8.6 V3 H7.4 Z M7.4,4.5 H8.6 V7 H7.4 Z "
                               u"M7.4,8.5 H8.6 V11 H7.4 Z M7.4,12.5 H8.6 V15.5 H7.4 Z"),
                  (u"f", BLU, u"M6,3 V13 H1 Z"), (u"f", u"#FCE3C4", u"M10,3 V13 H15 Z"),
                  (u"s", ARANCIO, u"M10,3 V13 H15 Z", 1)],
    u"serie": [(u"f", BLU, u"M1,4.5 H4.5 V8 H1 Z"),
               (u"f", AZZURRO, u"M6.25,4.5 H9.75 V8 H6.25 Z M11.5,4.5 H15 V8 H11.5 Z"),
               (u"s", BLU, u"M6.25,4.5 H9.75 V8 H6.25 Z M11.5,4.5 H15 V8 H11.5 Z", 1),
               (u"s", ARANCIO, u"M2.75,12 H13.25 M2.75,10.5 V13.5 M8,10.5 V13.5 M13.25,10.5 V13.5", 1.2)],
    u"scala": [(u"s", SCURO, u"M1.5,1.5 H14.5 V14.5 H1.5 Z", 1, (1.6, 1.2)),
               (u"f", BLU, u"M1.5,9 H7 V14.5 H1.5 Z"),
               (u"s", ARANCIO, u"M6,10 L12,4", 1.5), (u"f", ARANCIO, u"M13.8,2.2 L13.3,7.2 L8.8,2.7 Z")],
    u"allinea": [(u"s", SCURO, u"M2,1 V15", 1.8), (u"f", AZZURRO, u"M8.5,3.5 H15 V12.5 H8.5 Z"),
                 (u"s", BLU, u"M8.5,3.5 H15 V12.5 H8.5 Z", 1.1),
                 (u"s", ARANCIO, u"M8,8 H5.5", 1.6), (u"f", ARANCIO, u"M3.2,8 L6.4,5.4 V10.6 Z")],
    u"offset": [(u"s", SCURO, u"M1,2.5 H15", 1.6), (u"s", BLU, u"M1,13.5 H15", 1.8),
                (u"s", ARANCIO, u"M8,4.5 V9.5", 1.5), (u"f", ARANCIO, u"M8,11.8 L5.4,8.8 H10.6 Z")],
    u"dividi": [(u"s", BLU, u"M1,8 H6.2 M9.8,8 H15", 2), (u"s", ARANCIO, u"M10.8,1.5 L5.2,14.5", 1.7)],
    u"taglia_estendi": [(u"s", GRIGIO, u"M4,12 V15.5 M4,12 H0.5", 1.4, (1.4, 1)),
                        (u"s", BLU, u"M4,1.5 V12 H15", 2.4),
                        (u"f", ARANCIO, u"M4,9.8 A2.2,2.2 0 1 1 4,14.2 A2.2,2.2 0 1 1 4,9.8 Z")],
    u"crea_simile": [(u"f", AZZURRO, u"M1.5,1.5 H9.5 V9.5 H1.5 Z"),
                     (u"s", BLU, u"M1.5,1.5 H9.5 V9.5 H1.5 Z", 1.2),
                     (u"f", ARANCIO, u"M10.8,7.5 H12.7 V10.6 H15.8 V12.5 H12.7 V15.6 H10.8 V12.5 "
                                     u"H7.7 V10.6 H10.8 Z")],
    u"sel_tipo_vista": [(u"f", BLU, u"M1,1 H5 V5 H1 Z M7,1 H11 V5 H7 Z M1,7 H5 V11 H1 Z")] + _CURSORE,
    u"sel_tipo_progetto": [(u"f", BLU, u"M1,1 H4 V4 H1 Z M6.5,1 H9.5 V4 H6.5 Z M12,1 H15 V4 H12 Z "
                                       u"M1,6.5 H4 V9.5 H1 Z M12,6.5 H15 V9.5 H12 Z M1,12 H4 V15 H1 Z "
                                       u"M6.5,12 H9.5 V15 H6.5 Z M12,12 H15 V15 H12 Z"),
                           (u"f", ARANCIO, u"M6.5,6.5 H9.5 V9.5 H6.5 Z")],
    u"sel_categoria_vista": [(u"f", BLU, u"M1,1 H5.5 V5.5 H1 Z"),
                             (u"f", ARANCIO, u"M10,1 A2.3,2.3 0 1 1 10,5.6 A2.3,2.3 0 1 1 10,1 Z"),
                             (u"f", BLU, u"M3.2,7 L5.6,11.5 H0.8 Z")] + _CURSORE,
    u"nascondi_elementi": [(u"s", SCURO, u"M1,8 C3.8,3.6 12.2,3.6 15,8 C12.2,12.4 3.8,12.4 1,8 Z", 1.2),
                           (u"f", BLU, u"M8,5.8 A2.2,2.2 0 1 1 8,10.2 A2.2,2.2 0 1 1 8,5.8 Z"),
                           (u"s", ARANCIO, u"M2.5,14 L13.5,2", 1.7)],
    u"nascondi_categoria": [(u"f", AZZURRO, u"M1,9 H6 V14 H1 Z M10,9 H15 V14 H10 Z M5.5,2 H10.5 V7 H5.5 Z"),
                            (u"s", BLU, u"M1,9 H6 V14 H1 Z M10,9 H15 V14 H10 Z M5.5,2 H10.5 V7 H5.5 Z", 1),
                            (u"s", ARANCIO, u"M1.5,15 L14.5,1.5", 1.7)],
    # cerchio diviso in diagonale: meta' piena, meta' a puntini (retino a mezzitoni)
    u"mezzitoni": [(u"f", BLU, u"M3.2,12.8 A6.8,6.8 0 0 1 12.8,3.2 Z"),
                   (u"f", BLU, u"M9.6,8.5 A1.1,1.1 0 1 1 9.6,10.7 A1.1,1.1 0 1 1 9.6,8.5 Z "
                               u"M12.6,7 A1,1 0 1 1 12.6,9 A1,1 0 1 1 12.6,7 Z "
                               u"M7,11.6 A1,1 0 1 1 7,13.6 A1,1 0 1 1 7,11.6 Z "
                               u"M11.4,11 A0.9,0.9 0 1 1 11.4,12.8 A0.9,0.9 0 1 1 11.4,11 Z"),
                   (u"s", SCURO, u"M8,1.2 A6.8,6.8 0 1 1 8,14.8 A6.8,6.8 0 1 1 8,1.2 Z", 1.2)],
    u"copia_grafica": [(u"s", u"#8A6A4F", u"M14.6,1.4 L9,7", 2.2),
                       (u"f", SCURO, u"M7.4,6.6 L9.4,8.6 L8.4,9.6 L6.4,7.6 Z"),
                       (u"f", ARANCIO, u"M6.4,7.6 L8.4,9.6 C7.8,12.6 5.2,14.6 1.4,14.6 "
                                       u"C1.8,11.8 3.4,8.8 6.4,7.6 Z")],
    u"blocca": [(u"f", ARANCIO, u"M5,1 H11 V2.6 H10 V6.5 L12.6,9.2 V10.6 H3.4 V9.2 L6,6.5 V2.6 H5 Z"),
                (u"s", SCURO, u"M8,10.6 V15.5", 1.4)],
    u"isola_elementi": _OCCHIALI + [(u"f", AZZURRO, u"M5,9.5 H11 V15 H5 Z"),
                                    (u"s", BLU, u"M5,9.5 H11 V15 H5 Z", 1.2)],
    u"isola_categoria": _OCCHIALI + [(u"f", BLU, u"M1.5,10 H5 V13.5 H1.5 Z M6.25,10 H9.75 V13.5 H6.25 Z "
                                                 u"M11,10 H14.5 V13.5 H11 Z")],
    u"ripristina_temporaneo": _OCCHIALI + [(u"s", ARANCIO, u"M3.5,11 A4.6,3.6 0 0 0 12.2,12", 1.5),
                                           (u"f", ARANCIO, u"M14.6,10.6 L12.8,14.6 L10.2,11.6 Z")],
}


class Comando(object):
    def __init__(self, id_, famiglia, etichetta, suggerimento, esecuzione,
                 postable=None, categorie=None, max_elementi=None, interattivo=False,
                 ripetibile=False):
        self.id = id_
        self.famiglia = famiglia
        self.etichetta = etichetta
        self.suggerimento = suggerimento
        self.icona = ICONE[id_]
        self.esecuzione = esecuzione
        self.postable = postable          # nome in Autodesk.Revit.UI.PostableCommand
        self.categorie = categorie        # None = tutte; altrimenti insieme di chiavi
        self.max_elementi = max_elementi  # es. 1 per "Crea simile"
        self.interattivo = interattivo    # chiede di cliccare nella vista: palette via intanto
        # Comando di Revit che resta attivo dopo ogni operazione (Allinea, Offset...):
        # ogni operazione salva il modello, quindi non si puo' capire dalla modifica che
        # il comando e' finito; se ne esce con due Esc (il primo annulla solo il passo).
        self.ripetibile = ripetibile

    @property
    def esc_per_uscire(self):
        """Quanti Esc servono per uscire dal comando di Revit (Sposta 1, Allinea 2)."""
        return 2 if self.ripetibile else 1

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

CATALOGO = [
    # --- Trasforma: comandi di Revit, partono con la selezione corrente ------------
    Comando(u"sposta", TRASFORMA, u"Sposta", u"Sposta gli elementi selezionati (Revit: Sposta)",
            REVIT, postable=u"Move"),
    Comando(u"copia", TRASFORMA, u"Copia", u"Copia gli elementi selezionati (Revit: Copia)",
            REVIT, postable=u"Copy"),
    Comando(u"ruota", TRASFORMA, u"Ruota", u"Ruota gli elementi selezionati (Revit: Ruota)",
            REVIT, postable=u"Rotate"),
    Comando(u"specchia", TRASFORMA, u"Specchia",
            u"Specchia scegliendo l'asse (Revit: Specchia - Seleziona asse)",
            REVIT, postable=u"MirrorPickAxis"),
    Comando(u"serie", TRASFORMA, u"Serie", u"Crea una serie degli elementi selezionati (Revit: Serie)",
            REVIT, postable=u"Array",
            categorie=_MODELLO | frozenset([u"dettagli", u"linee", u"annotazioni"])),
    Comando(u"scala", TRASFORMA, u"Scala", u"Scala gli elementi selezionati (Revit: Scala)",
            REVIT, postable=u"Scale", categorie=frozenset([u"linee", u"muri"])),
    # --- Forma -------------------------------------------------------------------------
    Comando(u"allinea", FORMA, u"Allinea", u"Allinea a un riferimento (Revit: Allinea)",
            REVIT, postable=u"Align", ripetibile=True),
    Comando(u"offset", FORMA, u"Offset", u"Sposta o copia parallelamente (Revit: Offset)",
            REVIT, postable=u"Offset", categorie=_LINEARI, ripetibile=True),
    Comando(u"dividi", FORMA, u"Dividi", u"Dividi l'elemento in un punto (Revit: Dividi elemento)",
            REVIT, postable=u"SplitElement", categorie=_LINEARI, ripetibile=True),
    Comando(u"taglia_estendi", FORMA, u"Taglia/Estendi",
            u"Taglia o estendi fino a formare un angolo (Revit: Taglia/Estendi ad angolo)",
            REVIT, postable=u"TrimOrExtendToCorner", categorie=_LINEARI, ripetibile=True),
    Comando(u"crea_simile", FORMA, u"Crea simile",
            u"Disegna un nuovo elemento dello stesso tipo (Revit: Crea simile)",
            REVIT, postable=u"CreateSimilar", max_elementi=1, ripetibile=True),
    # --- Seleziona ---------------------------------------------------------------------
    Comando(u"sel_tipo_vista", SELEZIONA, u"Stesso tipo nella vista",
            u"Seleziona tutti gli elementi dello stesso tipo visibili nella vista", API),
    Comando(u"sel_tipo_progetto", SELEZIONA, u"Stesso tipo nel progetto",
            u"Seleziona tutti gli elementi dello stesso tipo in tutto il progetto", API),
    Comando(u"sel_categoria_vista", SELEZIONA, u"Stessa categoria nella vista",
            u"Seleziona tutti gli elementi della stessa categoria visibili nella vista", API),
    # --- Vista (di serie nella fila fissa) ----------------------------------------------
    Comando(u"nascondi_elementi", VISTA, u"Nascondi elementi",
            u"Nasconde gli elementi selezionati nella vista (annullabile)", API),
    Comando(u"nascondi_categoria", VISTA, u"Nascondi categoria",
            u"Nasconde la categoria degli elementi selezionati nella vista (annullabile)", API),
    Comando(u"mezzitoni", VISTA, u"Mezzitoni",
            u"Attiva o toglie i mezzitoni sugli elementi selezionati in questa vista (annullabile)",
            API),
    Comando(u"copia_grafica", VISTA, u"Copia grafica",
            u"Come il matchprop di AutoCAD, nella vista attiva: con un elemento selezionato "
            u"clicca gli elementi a cui copiarne la grafica (Esc per finire); con piu' elementi "
            u"selezionati clicca l'elemento da cui copiarla. Annullabile.",
            API, interattivo=True),
    Comando(u"blocca", VISTA, u"Blocca/Sblocca",
            u"Blocca gli elementi selezionati; se sono gia' tutti bloccati li sblocca (annullabile)",
            API),
    # --- Isola (temporaneo) -----------------------------------------------------------
    Comando(u"isola_elementi", ISOLA, u"Isola elementi",
            u"Mostra solo gli elementi selezionati (nascondi/isola temporaneo)", API),
    Comando(u"isola_categoria", ISOLA, u"Isola categoria",
            u"Mostra solo le categorie selezionate (nascondi/isola temporaneo)", API),
    Comando(u"ripristina_temporaneo", ISOLA, u"Ripristina",
            u"Toglie il nascondi/isola temporaneo della vista", API),
]

PER_ID = dict((c.id, c) for c in CATALOGO)
MAX_FISSA = 6
FISSA_PREDEFINITA = [u"nascondi_elementi", u"nascondi_categoria", u"mezzitoni",
                     u"copia_grafica", u"blocca"]


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
    if _c.famiglia in (VISTA, ISOLA) and _c.id != u"blocca" and _c.categorie is None:
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
# {"attiva": bool, "fissa": [id...], "categorie": {chiave: [id...]}}
# Per ogni categoria: gli strumenti che compaiono nelle famiglie (quelli nella fila
# fissa non si ripetono). Un comando non elencato e' nascosto per quella categoria.

def ammessi_per_categoria(chiave):
    """Comandi del catalogo che si possono usare per una categoria (in ordine di catalogo)."""
    return [c.id for c in CATALOGO if c.ammesso([chiave], 1)]


def _unici(ids):
    out = []
    for i in ids:
        if i not in out:
            out.append(i)
    return out


def _pulisci(chiave, ids):
    """Solo comandi ammessi per la categoria, senza doppioni, in ordine di catalogo."""
    scelti = set(ids)
    return [i for i in ammessi_per_categoria(chiave) if i in scelti]


def _predefiniti(chiave):
    if chiave == u"viste_tavola":
        return _pulisci(chiave, [u"sposta", u"sel_tipo_vista"])
    if chiave == u"sezioni":
        return _pulisci(chiave, [u"sposta", u"copia", u"ruota", u"specchia", u"sel_categoria_vista",
                                 u"isola_elementi", u"ripristina_temporaneo"])
    return ammessi_per_categoria(chiave)


def config_predefinita():
    return {
        u"attiva": True,
        u"fissa": list(FISSA_PREDEFINITA),
        u"categorie": dict((k, _predefiniti(k)) for k in CHIAVI),
    }


def unisci_config(utente):
    """Predefinita aggiornata con il file personale.

    Comandi sconosciuti, doppi o non ammessi vengono scartati; le categorie non presenti
    nel file restano quelle predefinite. Legge anche il formato precedente
    ({"vista": [...], "menu": [...]} per categoria).
    """
    cfg = config_predefinita()
    if not isinstance(utente, dict):
        return cfg
    if u"attiva" in utente:
        cfg[u"attiva"] = bool(utente[u"attiva"])
    if isinstance(utente.get(u"fissa"), list):
        cfg[u"fissa"] = [i for i in _unici(utente[u"fissa"]) if i in PER_ID][:MAX_FISSA]
    cat = utente.get(u"categorie")
    if isinstance(cat, dict):
        for k in CHIAVI:
            voce = cat.get(k)
            if isinstance(voce, dict):
                voce = list(voce.get(u"vista", [])) + list(voce.get(u"menu", []))
            if isinstance(voce, list):
                cfg[u"categorie"][k] = _pulisci(k, voce)
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
# STRUTTURA DELLA PALETTE PER UNA SELEZIONE
# ==============================================================================

PREFISSO_CDV = u"cdv:"


def _voce(c):
    return (c.id, c.etichetta, c.suggerimento)


def struttura_palette(chiavi, n, cfg, disponibili=None, cdv=None):
    """Cosa mostrare per una selezione, oppure None se non c'e' nulla.

    chiavi: categorie (chiavi della palette) degli elementi selezionati; n: quanti sono;
    cdv: gruppi di strumenti CDV del contesto [(nome, [(id, etichetta, suggerimento)])].
    Con una selezione mista valgono i comandi comuni a tutte le categorie.

    Ritorna {"fissa": [voci], "famiglie": [famiglia]} con
      famiglia = {"id", "nome", "cdv": bool, "voci": [(id, etichetta, suggerimento)]};
    prima le famiglie CDV (id "cdv:<nome>"), poi Trasforma, Forma, Seleziona, Vista, Isola,
    solo quelle con almeno uno strumento.
    """
    if not cfg.get(u"attiva", True) or not chiavi or n < 1:
        return None
    chiavi = sorted(set(chiavi))
    per_cat = cfg.get(u"categorie", {})

    def utilizzabile(c):
        return c.ammesso(chiavi, n) and (disponibili is None or c.id in disponibili)

    scelti = None
    for k in chiavi:
        ids = set(per_cat.get(k, per_cat.get(u"altro", [])))
        scelti = ids if scelti is None else (scelti & ids)
    fissa_ids = set(cfg.get(u"fissa", []))
    scelti = (scelti or set()) - fissa_ids

    fissa = [_voce(PER_ID[i]) for i in cfg.get(u"fissa", [])
             if i in PER_ID and utilizzabile(PER_ID[i])]
    famiglie = []
    for nome, tasti in (cdv or []):
        if tasti:
            famiglie.append({u"id": PREFISSO_CDV + nome, u"nome": nome, u"cdv": True,
                             u"voci": [tuple(t) for t in tasti]})
    for fid, nome in FAMIGLIE:
        voci = [_voce(c) for c in CATALOGO
                if c.famiglia == fid and c.id in scelti and utilizzabile(c)]
        if voci:
            famiglie.append({u"id": fid, u"nome": nome, u"cdv": False, u"voci": voci})
    if not (famiglie or fissa):
        return None
    return {u"fissa": fissa, u"famiglie": famiglie}


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
# TRASPARENZA "ALLA OFFICE"
# ==============================================================================
# Come la mini barra di Word: la palette compare semitrasparente accanto al cursore,
# diventa piena quando ci si avvicina e sparisce se ci si allontana; torna se il
# cursore ritorna vicino al punto dove stava.

OPACITA_VICINO = 1.0       # cursore sopra la palette
OPACITA_COMPARSA = 0.75    # appena comparsa, cursore accanto
DISTANZA_SPARISCE = 150    # pixel: oltre, la palette sparisce
DISTANZA_RITORNA = 40      # pixel: sotto, una palette sparita ricompare


def distanza_da_rettangolo(punto, rett):
    """Distanza in pixel di un punto da un rettangolo (sinistra, alto, destra, basso); 0 dentro."""
    x, y = punto
    sx, alto, dx, basso = rett
    ddx = max(sx - x, 0.0, x - dx)
    ddy = max(alto - y, 0.0, y - basso)
    return (ddx * ddx + ddy * ddy) ** 0.5


def opacita_palette(distanza, sparita=False):
    """(opacita', sparita) della palette con il cursore a 'distanza' pixel.

    Sopra la palette e' piena; vicino e' semitrasparente e sbiadisce allontanandosi;
    oltre DISTANZA_SPARISCE sparisce. Una volta sparita ricompare solo se il cursore
    torna entro DISTANZA_RITORNA (cosi' non lampeggia sul bordo). L'opacita' e'
    arrotondata a 0.05 per non ridisegnare la finestra a ogni pixel.
    """
    if sparita and distanza > DISTANZA_RITORNA:
        return 0.0, True
    if distanza <= 0:
        return OPACITA_VICINO, False
    if distanza >= DISTANZA_SPARISCE:
        return 0.0, True
    frazione = float(distanza) / DISTANZA_SPARISCE
    valore = OPACITA_COMPARSA * (1.0 - frazione) + 0.15 * frazione
    return round(valore * 20) / 20.0, False


# ==============================================================================
# MODIFICHE DALLA FINESTRA DI PERSONALIZZAZIONE
# ==============================================================================

def copia_config(cfg):
    """Copia indipendente (la finestra lavora su questa finche' non si salva)."""
    return {
        u"attiva": bool(cfg.get(u"attiva", True)),
        u"fissa": list(cfg.get(u"fissa", [])),
        u"categorie": dict((k, list(v)) for k, v in cfg.get(u"categorie", {}).items()),
    }


def imposta_comando(cfg, chiave, comando, attivo):
    """Mostra o nasconde un comando nelle famiglie di una categoria (False se non ammesso)."""
    if comando not in ammessi_per_categoria(chiave):
        return False
    attuali = set(cfg[u"categorie"].get(chiave, []))
    if attivo:
        attuali.add(comando)
    else:
        attuali.discard(comando)
    cfg[u"categorie"][chiave] = _pulisci(chiave, attuali)
    return True


def imposta_fissa(cfg, comando, attivo):
    """Aggiunge/toglie un comando dalla fila fissa (False se e' gia' piena).

    Nella fila fissa un comando non compare piu' nella sua famiglia; tolto dalla fila
    torna nella famiglia per le categorie dove e' ammesso.
    """
    fissa = [i for i in cfg.get(u"fissa", []) if i != comando]
    if attivo:
        if len(fissa) >= MAX_FISSA:
            return False
        fissa.append(comando)
    else:
        for k in CHIAVI:
            imposta_comando(cfg, k, comando, True)
    cfg[u"fissa"] = [c.id for c in CATALOGO if c.id in fissa]
    return True


def ripristina_categoria(cfg, chiave):
    cfg[u"categorie"][chiave] = _predefiniti(chiave)
    return cfg


def copia_su_tutte(cfg, chiave):
    """Stessa scelta della categoria 'chiave' su tutte le altre (dove il comando e' ammesso)."""
    sorgente = cfg[u"categorie"].get(chiave, [])
    for k in CHIAVI:
        cfg[u"categorie"][k] = _pulisci(k, sorgente)
    return cfg
