# -*- coding: utf-8 -*-
"""Raccolta dei nomi dal modello Revit e applicazione delle correzioni.

Funziona con i motori IronPython 2.7 e CPython 3 di pyRevit.
"""
import os
import re

from Autodesk.Revit import DB

from nomenclatura import regole as R
from nomenclatura import suggerimenti as SG

MM = 304.8  # piedi -> mm

# Ambiti di controllo (chiave -> etichetta mostrata all'utente)
AMBITI = [
    ("file", u"Nome file modello"),
    ("livelli", u"Livelli"),
    ("tipi", u"Tipi (famiglie caricabili e di sistema)"),
    ("famiglie", u"Famiglie caricabili"),
    ("contrassegni", u"Contrassegno tipo (Type Mark)"),
    ("materiali", u"Materiali"),
    ("locali", u"Locali (numero e nome)"),
    ("tavole", u"Tavole (numero)"),
    ("coerenza", u"Coerenza nome / dati (spessori, strati, funzione muro, dimensioni porte e finestre)"),
]

# Campi modificabili
CAMPO_FILE = u"NomeFile"
CAMPO_LIVELLO = u"NomeLivello"
CAMPO_TIPO = u"NomeTipo"
CAMPO_FAMIGLIA = u"NomeFamiglia"
CAMPO_CONTRASSEGNO = u"ContrassegnoTipo"
CAMPO_MATERIALE = u"NomeMateriale"
CAMPO_NUM_LOCALE = u"NumeroLocale"
CAMPO_NOME_LOCALE = u"NomeLocale"
CAMPO_TAVOLA = u"NumeroTavola"

_FUNZIONE_MURO = {0: "INT", 1: "EST", 2: "EST", 3: "EST", 4: "EST", 5: "INT"}


class Voce(object):
    """Un nome controllato nel modello."""

    def __init__(self, elemento, ambito, campo, categoria, risultato, contesto=u""):
        self.elemento = elemento
        self.ambito = ambito
        self.campo = campo
        self.categoria = categoria
        self.risultato = risultato
        self.contesto = contesto  # info utile (es. nome famiglia)

    @property
    def id(self):
        return id_valore(self.elemento.Id) if self.elemento is not None else u""

    @property
    def valore(self):
        return self.risultato.valore

    @property
    def proposta(self):
        return self.risultato.proposta


# --------------------------------------------------------------------------
# Utilita' API (compatibili 2020-2025+)
# --------------------------------------------------------------------------
def id_valore(eid):
    try:
        return eid.Value  # Revit 2024+
    except AttributeError:
        return eid.IntegerValue


def nuovo_id(valore):
    return DB.ElementId(int(valore))


def leggi_nome(el):
    try:
        return DB.Element.Name.__get__(el)
    except Exception:
        return el.Name


def scrivi_nome(el, valore):
    try:
        DB.Element.Name.__set__(el, valore)
    except AttributeError:
        el.Name = valore


def bic_nome(categoria):
    """Nome BuiltInCategory (es. 'OST_Walls') o '' per categorie non di sistema."""
    if categoria is None:
        return u""
    try:
        return str(categoria.BuiltInCategory)
    except Exception:
        pass
    try:
        import System
        return str(System.Enum.ToObject(DB.BuiltInCategory, id_valore(categoria.Id)))
    except Exception:
        return u""


def _param(el, bip, nomi):
    p = el.get_Parameter(bip) if bip is not None else None
    if p is None:
        for n in nomi:
            p = el.LookupParameter(n)
            if p is not None:
                break
    return p


def param_contrassegno(tipo):
    bip = getattr(DB.BuiltInParameter, "ALL_MODEL_TYPE_MARK", None) or DB.BuiltInParameter.WINDOW_TYPE_ID
    return _param(tipo, bip, [u"Contrassegno tipo", u"Type Mark"])


def _percorso_modello(doc):
    """Percorso del file (per i modelli condivisi quello del file centrale)."""
    percorso = u""
    try:
        if doc.IsWorkshared:
            mp = doc.GetWorksharingCentralModelPath()
            percorso = DB.ModelPathUtils.ConvertModelPathToUserVisiblePath(mp)
    except Exception:
        percorso = u""
    return percorso or doc.PathName or u""


def nome_file_modello(doc):
    """Nome del file senza estensione; per i modelli condivisi usa il file centrale."""
    percorso = _percorso_modello(doc) or doc.Title
    nome = os.path.splitext(os.path.basename(percorso.replace(u"\\", u"/")))[0]
    return nome


def cartella_modello(doc):
    """Cartella che contiene il modello (o il centrale), None se non salvato o su cloud."""
    cartella = os.path.dirname(_percorso_modello(doc))
    try:
        return cartella if cartella and os.path.isdir(cartella) else None
    except Exception:
        return None


def crea_contesto(doc):
    """Contesto con le impostazioni del progetto del modello aperto (vedi regole.carica_config)."""
    return R.Contesto(cartella_progetto=cartella_modello(doc))


# --------------------------------------------------------------------------
# Dati del tipo per i controlli incrociati
# --------------------------------------------------------------------------
def _param_mm(el, bips):
    for b in bips:
        bip = getattr(DB.BuiltInParameter, b, None)
        p = el.get_Parameter(bip) if bip is not None else None
        if p is not None and p.HasValue and p.StorageType == DB.StorageType.Double:
            return p.AsDouble() * MM
    return None


def dati_tipo(t, doc):
    """Dizionario con i dati che servono a suggerimenti.py."""
    cat = t.Category
    d = {"bic": bic_nome(cat), "nome": leggi_nome(t)}
    cs = None
    try:
        cs = t.GetCompoundStructure()
    except Exception:
        cs = None
    if cs is not None:
        strati = []
        for ly in cs.GetLayers():
            mid = ly.MaterialId
            mat = doc.GetElement(mid) if mid != DB.ElementId.InvalidElementId else None
            strati.append({"materiale": leggi_nome(mat) if mat is not None else None,
                           "spessore": ly.Width * MM})
        d["strati"] = strati
        d["spessore"] = cs.GetWidth() * MM
    if d["bic"] == "OST_Walls":
        p = t.get_Parameter(DB.BuiltInParameter.FUNCTION_PARAM)
        if p is not None and p.HasValue:
            d["funzione"] = _FUNZIONE_MURO.get(p.AsInteger())
    if d["bic"] in SG.APERTURE:
        d["larghezza"] = _param_mm(t, ["DOOR_WIDTH", "WINDOW_WIDTH", "FAMILY_WIDTH_PARAM"])
        d["altezza"] = _param_mm(t, ["DOOR_HEIGHT", "WINDOW_HEIGHT", "FAMILY_HEIGHT_PARAM"])
    return d


def classe_materiale(m):
    try:
        return m.MaterialClass
    except Exception:
        return None


# --------------------------------------------------------------------------
# Raccolta
# --------------------------------------------------------------------------
def _tipi_usati(doc):
    usati = set()
    for el in DB.FilteredElementCollector(doc).WhereElementIsNotElementType():
        try:
            tid = el.GetTypeId()
        except Exception:
            continue
        if tid is not None and tid != DB.ElementId.InvalidElementId:
            usati.add(id_valore(tid))
    return usati


def _tipi_modello(doc, ctx):
    cfg = ctx.cfg.get("tipi", {})
    escluse = set(cfg.get("categorie_escluse", []))
    usati = _tipi_usati(doc) if cfg.get("solo_tipi_usati", True) else None
    out = []
    for t in DB.FilteredElementCollector(doc).WhereElementIsElementType():
        cat = t.Category
        if cat is None or cat.CategoryType != DB.CategoryType.Model:
            continue
        bic = bic_nome(cat)
        if bic in escluse:
            continue
        if usati is not None and id_valore(t.Id) not in usati:
            continue
        out.append((t, bic, cat.Name))
    return out


def raccogli(doc, ambiti, ctx=None):
    ctx = ctx or R.Contesto()
    voci = []

    if "file" in ambiti:
        nome = nome_file_modello(doc)
        voci.append(Voce(None, u"File", CAMPO_FILE, u"Modello", R.controlla_file_modello(nome, ctx)))

    if "livelli" in ambiti:
        for lv in DB.FilteredElementCollector(doc).OfClass(DB.Level):
            voci.append(Voce(lv, u"Livelli", CAMPO_LIVELLO, u"Livelli",
                             R.controlla_livello(leggi_nome(lv), ctx)))

    tipi = None
    if set(ambiti) & set(["tipi", "famiglie", "contrassegni", "coerenza"]):
        tipi = _tipi_modello(doc, ctx)

    if "tipi" in ambiti:
        voci_tipi = []
        for t, bic, catnome in tipi:
            fam = getattr(t, "FamilyName", u"") or u""
            voci_tipi.append(Voce(t, u"Tipi", CAMPO_TIPO, catnome,
                                  R.controlla_elemento(leggi_nome(t), ctx, categoria=bic), fam))
        # Lo stesso TIPO-[SOTTOTIPO-]NN su piu' tipi rende ambiguo il contrassegno
        doppi = R.progressivi_doppi([v.valore for v in voci_tipi], ctx)
        for v in voci_tipi:
            if v.valore in doppi:
                R.segnala_progressivo_doppio(v.risultato, doppi[v.valore], ctx)
        voci.extend(voci_tipi)

    if "coerenza" in ambiti:
        for t, bic, catnome in tipi:
            if bic not in SG.STRATIFICATI and bic not in SG.APERTURE:
                continue
            r = SG.controlla_coerenza(dati_tipo(t, doc), ctx)
            if r.ok or (len(r.problemi) == 1 and u"non codificato" in r.messaggio()):
                continue  # i nomi non codificati sono gia' segnalati da 'Tipi'
            voci.append(Voce(t, u"Coerenza", CAMPO_TIPO, catnome, r,
                             getattr(t, "FamilyName", u"") or u""))

    if "contrassegni" in ambiti and ctx.cfg.get("tipi", {}).get("contrassegno_tipo", True):
        for t, bic, catnome in tipi:
            p = param_contrassegno(t)
            if p is None or p.IsReadOnly:
                continue
            nome_tipo = leggi_nome(t)
            voci.append(Voce(t, u"Contrassegno tipo", CAMPO_CONTRASSEGNO, catnome,
                             R.controlla_contrassegno(p.AsString(), nome_tipo, ctx), nome_tipo))

    if "famiglie" in ambiti:
        prefissi = {}
        famiglie = {}
        for t, bic, catnome in tipi:
            if isinstance(t, DB.FamilySymbol):
                fam = t.Family
                k = id_valore(fam.Id)
                famiglie[k] = (fam, catnome)
                prefissi.setdefault(k, []).append(R.prefisso_codice(leggi_nome(t), ctx))
        for k, (fam, catnome) in famiglie.items():
            if fam.IsInPlace:
                continue
            voci.append(Voce(fam, u"Famiglie", CAMPO_FAMIGLIA, catnome,
                             R.controlla_famiglia(leggi_nome(fam), ctx, prefissi.get(k))))

    if "materiali" in ambiti:
        for m in DB.FilteredElementCollector(doc).OfClass(DB.Material):
            nome = leggi_nome(m)
            if R.materiale_escluso(nome, ctx):
                continue
            voci.append(Voce(m, u"Materiali", CAMPO_MATERIALE, u"Materiali",
                             R.controlla_materiale(nome, ctx)))

    if "locali" in ambiti:
        locali = DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Rooms) \
            .WhereElementIsNotElementType()
        for rm in locali:
            if rm.Area <= 0:  # locali non posizionati o non chiusi
                continue
            num = rm.get_Parameter(DB.BuiltInParameter.ROOM_NUMBER).AsString() or u""
            nome = rm.get_Parameter(DB.BuiltInParameter.ROOM_NAME).AsString() or u""
            voci.append(Voce(rm, u"Locali", CAMPO_NUM_LOCALE, u"Locali",
                             R.controlla_numero_locale(num, ctx), nome))
            voci.append(Voce(rm, u"Locali", CAMPO_NOME_LOCALE, u"Locali",
                             R.controlla_nome_locale(nome, num, ctx), num))

    if "tavole" in ambiti:
        for sh in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
            if sh.IsPlaceholder:
                continue
            voci.append(Voce(sh, u"Tavole", CAMPO_TAVOLA, u"Tavole",
                             R.controlla_tavola(sh.SheetNumber, ctx), sh.Name))

    return voci


# --------------------------------------------------------------------------
# Scrittura
# --------------------------------------------------------------------------
def applica(doc, elemento, campo, valore):
    """Scrive il nuovo valore. Da chiamare dentro una Transaction."""
    if campo in (CAMPO_TIPO, CAMPO_FAMIGLIA, CAMPO_MATERIALE, CAMPO_LIVELLO):
        scrivi_nome(elemento, valore)
    elif campo == CAMPO_CONTRASSEGNO:
        param_contrassegno(elemento).Set(valore)
    elif campo == CAMPO_NUM_LOCALE:
        elemento.get_Parameter(DB.BuiltInParameter.ROOM_NUMBER).Set(valore)
    elif campo == CAMPO_NOME_LOCALE:
        elemento.get_Parameter(DB.BuiltInParameter.ROOM_NAME).Set(valore)
    elif campo == CAMPO_TAVOLA:
        elemento.SheetNumber = valore
    elif campo == CAMPO_FILE:
        raise ValueError(u"il nome del file va cambiato con 'Salva con nome'")
    else:
        raise ValueError(u"campo sconosciuto: %s" % campo)


def applica_lista(doc, modifiche, titolo=u"Correzione nomenclatura ADD"):
    """modifiche: lista di (elemento, campo, nuovo_valore). Ritorna (ok, errori)."""
    ok, errori = [], []
    t = DB.Transaction(doc, titolo)
    t.Start()
    try:
        for el, campo, val in modifiche:
            try:
                applica(doc, el, campo, val)
                ok.append((el, campo, val))
            except Exception as ex:
                errori.append((el, campo, val, u"%s" % ex))
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return ok, errori


def leggi_valore(el, campo):
    """Valore attuale del campo nel modello, None se l'elemento non e' del tipo giusto."""
    try:
        if campo == CAMPO_TIPO and isinstance(el, DB.ElementType):
            return leggi_nome(el)
        if campo == CAMPO_FAMIGLIA and isinstance(el, DB.Family):
            return leggi_nome(el)
        if campo == CAMPO_MATERIALE and isinstance(el, DB.Material):
            return leggi_nome(el)
        if campo == CAMPO_LIVELLO and isinstance(el, DB.Level):
            return leggi_nome(el)
        if campo == CAMPO_CONTRASSEGNO and isinstance(el, DB.ElementType):
            p = param_contrassegno(el)
            return (p.AsString() or u"") if p is not None else None
        if campo in (CAMPO_NUM_LOCALE, CAMPO_NOME_LOCALE) and isinstance(el, DB.Architecture.Room):
            bip = DB.BuiltInParameter.ROOM_NUMBER if campo == CAMPO_NUM_LOCALE \
                else DB.BuiltInParameter.ROOM_NAME
            return el.get_Parameter(bip).AsString() or u""
        if campo == CAMPO_TAVOLA and isinstance(el, DB.ViewSheet):
            return el.SheetNumber
    except Exception:
        return None
    return None


# --------------------------------------------------------------------------
# Nomi doppi
# --------------------------------------------------------------------------
def spazio_nomi(el, campo):
    """Ambito in cui il valore deve essere unico (None = duplicati ammessi).

    Tipi caricabili: unici dentro la famiglia; tipi di sistema: dentro la loro classe
    (WallType, FloorType...); famiglie, materiali, livelli e tavole: in tutto il modello.
    Numeri dei locali e contrassegni: Revit li accetta doppi, ma la codifica li vuole univoci.
    """
    if campo == CAMPO_TIPO:
        if isinstance(el, DB.FamilySymbol):
            return (campo, id_valore(el.Family.Id))
        return (campo, el.GetType().Name)
    if campo in (CAMPO_FAMIGLIA, CAMPO_MATERIALE, CAMPO_LIVELLO, CAMPO_TAVOLA,
                 CAMPO_NUM_LOCALE, CAMPO_CONTRASSEGNO):
        return (campo,)
    return None


def _chiave(valore):
    return (valore or u"").strip().lower()


def nomi_in_uso(doc, campi):
    """{spazio_nomi: {valore minuscolo: set(id elementi)}} per i campi indicati."""
    uso = {}

    def aggiungi(el, campo, valore):
        ns = spazio_nomi(el, campo)
        if ns is not None and valore:
            uso.setdefault(ns, {}).setdefault(_chiave(valore), set()).add(id_valore(el.Id))

    if CAMPO_TIPO in campi or CAMPO_CONTRASSEGNO in campi:
        for t in DB.FilteredElementCollector(doc).WhereElementIsElementType():
            if CAMPO_TIPO in campi:
                aggiungi(t, CAMPO_TIPO, leggi_nome(t))
            if CAMPO_CONTRASSEGNO in campi:
                cat = t.Category
                if cat is None or cat.CategoryType != DB.CategoryType.Model:
                    continue
                p = param_contrassegno(t)
                if p is not None:
                    aggiungi(t, CAMPO_CONTRASSEGNO, p.AsString())
    if CAMPO_FAMIGLIA in campi:
        for f in DB.FilteredElementCollector(doc).OfClass(DB.Family):
            aggiungi(f, CAMPO_FAMIGLIA, leggi_nome(f))
    if CAMPO_MATERIALE in campi:
        for m in DB.FilteredElementCollector(doc).OfClass(DB.Material):
            aggiungi(m, CAMPO_MATERIALE, leggi_nome(m))
    if CAMPO_LIVELLO in campi:
        for lv in DB.FilteredElementCollector(doc).OfClass(DB.Level):
            aggiungi(lv, CAMPO_LIVELLO, leggi_nome(lv))
    if CAMPO_TAVOLA in campi:
        for sh in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet):
            aggiungi(sh, CAMPO_TAVOLA, sh.SheetNumber)
    if CAMPO_NUM_LOCALE in campi:
        locali = DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Rooms) \
            .WhereElementIsNotElementType()
        for rm in locali:
            aggiungi(rm, CAMPO_NUM_LOCALE, rm.get_Parameter(DB.BuiltInParameter.ROOM_NUMBER).AsString())
    return uso


NOME_IN_USO = u"NOME GIA' IN USO"
NOME_DOPPIO = u"NOME DOPPIO"


def conflitti_nomi(doc, modifiche):
    """modifiche: lista di (elemento, campo, valore).

    Ritorna una lista parallela: NOME_IN_USO se il valore appartiene gia' a un altro elemento,
    NOME_DOPPIO se piu' modifiche portano allo stesso valore, u"" altrimenti.
    """
    uso = nomi_in_uso(doc, set(c for _, c, _ in modifiche))
    chiavi, conteggio = [], {}
    for el, campo, val in modifiche:
        ns = spazio_nomi(el, campo)
        k = (ns, _chiave(val)) if ns is not None else None
        chiavi.append(k)
        if k is not None:
            conteggio[k] = conteggio.get(k, 0) + 1
    esiti = []
    for (el, campo, val), k in zip(modifiche, chiavi):
        if k is None:
            esiti.append(u"")
            continue
        altri = uso.get(k[0], {}).get(k[1], set()) - set([id_valore(el.Id)])
        if altri:
            esiti.append(NOME_IN_USO)
        elif conteggio[k] > 1:
            esiti.append(NOME_DOPPIO)
        else:
            esiti.append(u"")
    return esiti


def ricontrolla(campo, valore, el, ctx):
    """Esito del nuovo valore: (livello, testo) con livello 'OK', AVVISO o ERRORE."""
    if campo == CAMPO_TIPO:
        r = R.controlla_elemento(valore, ctx, categoria=bic_nome(el.Category))
    elif campo == CAMPO_FAMIGLIA:
        r = R.controlla_famiglia(valore, ctx)
    elif campo == CAMPO_MATERIALE:
        r = R.controlla_materiale(valore, ctx)
    elif campo == CAMPO_LIVELLO:
        r = R.controlla_livello(valore, ctx)
    elif campo == CAMPO_CONTRASSEGNO:
        r = R.controlla_contrassegno(valore, leggi_nome(el), ctx)
    elif campo == CAMPO_NUM_LOCALE:
        r = R.controlla_numero_locale(valore, ctx)
    elif campo == CAMPO_NOME_LOCALE:
        num = el.get_Parameter(DB.BuiltInParameter.ROOM_NUMBER).AsString() or u""
        r = R.controlla_nome_locale(valore, num, ctx)
    elif campo == CAMPO_TAVOLA:
        r = R.controlla_tavola(valore, ctx)
    else:
        return R.ERRORE, u"campo sconosciuto"
    return r.livello, (r.livello if r.ok else u"%s: %s" % (r.livello, r.messaggio()))


def valido_per_revit(valore):
    """Caratteri che Revit rifiuta nei nomi."""
    return not re.search(u"[{}\\[\\]|;<>?`~:\\\\]", valore or u"")
