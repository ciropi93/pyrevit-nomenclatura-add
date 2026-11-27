# -*- coding: utf-8 -*-
"""Applica uno schema di facciata a curtain wall dritte (unico modulo con le API Revit).

Per ogni muro:
1. tipo "<tipo> CDV": copia del tipo di facciata con le griglie del tipo spente (layout
   Nessuno), cosi' restano solo le linee messe dal ritmo; bordi e pannello predefinito restano
   quelli del tipo;
2. tolte le linee griglia di prima, si aggiungono quelle calcolate da ritmo.calcola;
3. celle unite: si tolgono i segmenti interni;
4. montanti su ogni segmento, col tipo della classe della linea;
5. pannelli: ognuno prende il tipo della classe della sua cella;
6. lo schema si salva sul muro (ExtensibleStorage), per "Aggiorna facciata" e per riaprirlo.

Coordinate dello schema: x da sinistra guardando la facciata da fuori (lato verso cui punta
wall.Orientation), y dal basso del muro; in mm.
"""
from System import Guid
from Autodesk.Revit import DB

from facciate import ritmo as R
from facciate import schema as S

MM = 1.0 / 304.8
TOLL_MM = 1.0
NESSUNO = S.NESSUNO              # tipo di una classe di montanti: niente montante su quelle linee

GUID_SCHEMA = u"c2b1d45a-492d-469a-a1cb-317aefbbe9fd"
NOME_SCHEMA = u"CDVFacciataContinua"
CAMPO = u"SchemaJson"
SUFFISSO_TIPO = u" CDV"

# parametri del tipo di facciata
_LAYOUT = (u"SPACING_LAYOUT_VERT", u"SPACING_LAYOUT_HORIZ")
# montanti interni predefiniti: (linee verticali, linee orizzontali); se l'ordine fosse
# l'opposto lo dice la prova (prova_revit: "parametri_tipo")
_MONTANTI_INTERNI = (u"AUTO_MULLION_INTERIOR_GRID2", u"AUTO_MULLION_INTERIOR_GRID1")


class FacciataErrore(Exception):
    pass


# --- aiuti ----------------------------------------------------------------------------
def nome_el(e):
    return DB.Element.Name.__get__(e)


def chiave_id(eid):
    v = getattr(eid, u"Value", None)          # Revit 2024+
    return v if v is not None else eid.IntegerValue


def chiave_tipo(t):
    """"Famiglia: Tipo", per riconoscere un tipo anche se due famiglie hanno tipi omonimi."""
    try:
        fam = t.FamilyName
    except Exception:
        fam = u""
    return u"%s: %s" % (fam, nome_el(t)) if fam else nome_el(t)


def _bip(nome):
    return getattr(DB.BuiltInParameter, nome, None)


def _param(el, nome):
    b = _bip(nome)
    return el.get_Parameter(b) if b is not None else None


def e_facciata(el):
    return isinstance(el, DB.Wall) and el.WallType is not None and el.WallType.Kind == DB.WallKind.Curtain


def facciate_selezionate(uidoc):
    doc = uidoc.Document
    return [e for e in (doc.GetElement(i) for i in uidoc.Selection.GetElementIds()) if e_facciata(e)]


class _Avvisi(DB.IFailuresPreprocessor):
    """Toglie gli avvisi di Revit (montanti sovrapposti...) e se li segna."""

    def __init__(self, messaggi):
        self.messaggi = messaggi

    def PreprocessFailures(self, accessor):
        for f in accessor.GetFailureMessages():
            if f.GetSeverity() == DB.FailureSeverity.Warning:
                try:
                    testo = f.GetDescriptionText()
                except Exception:
                    testo = u"avviso di Revit"
                if testo not in self.messaggi:
                    self.messaggi.append(testo)
                accessor.DeleteWarning(f)
        return DB.FailureProcessingResult.Continue


def transazione(doc, nome, messaggi):
    t = DB.Transaction(doc, nome)
    opz = t.GetFailureHandlingOptions()
    opz.SetFailuresPreprocessor(_Avvisi(messaggi))
    t.SetFailureHandlingOptions(opz)
    return t


# --- geometria del muro -------------------------------------------------------------
class Facciata(object):
    """Il muro visto come rettangolo: lunghezza, altezza, livelli e passaggio mm <-> XYZ."""

    def __init__(self, doc, muro):
        if not e_facciata(muro):
            raise FacciataErrore(u"Non è una facciata continua.")
        curva = muro.Location.Curve if isinstance(muro.Location, DB.LocationCurve) else None
        if not isinstance(curva, DB.Line):
            raise FacciataErrore(u"Per ora solo facciate dritte.")
        self.muro = muro
        self.p0 = curva.GetEndPoint(0)
        d = curva.GetEndPoint(1) - self.p0
        self.d = DB.XYZ(d.X, d.Y, 0).Normalize()
        self.lunghezza = curva.Length / MM
        # da fuori (Orientation) la destra e' Z x n: se il muro va verso destra, x parte dall'inizio
        destra = DB.XYZ.BasisZ.CrossProduct(muro.Orientation)
        self.da_fine = self.d.DotProduct(destra) < 0
        livello = doc.GetElement(muro.LevelId)
        base = _param(muro, u"WALL_BASE_OFFSET")
        self.z0 = livello.ProjectElevation + (base.AsDouble() if base is not None else 0.0)
        h = _param(muro, u"WALL_USER_HEIGHT_PARAM")
        self.altezza = h.AsDouble() / MM if h is not None else 0.0
        if self.altezza <= R.TOLLERANZA:
            bb = muro.get_BoundingBox(None)
            self.altezza = (bb.Max.Z - self.z0) / MM if bb is not None else 0.0
        if self.lunghezza <= R.TOLLERANZA or self.altezza <= R.TOLLERANZA:
            raise FacciataErrore(u"Facciata senza lunghezza o altezza.")
        self.quote_livelli = sorted((lv.ProjectElevation - self.z0) / MM
                                    for lv in DB.FilteredElementCollector(doc).OfClass(DB.Level))

    def punto(self, x, y):
        s = self.lunghezza - x if self.da_fine else x
        return DB.XYZ(self.p0.X + self.d.X * s * MM, self.p0.Y + self.d.Y * s * MM, self.z0 + y * MM)

    def coordinate(self, p):
        s = ((p.X - self.p0.X) * self.d.X + (p.Y - self.p0.Y) * self.d.Y) / MM
        return (self.lunghezza - s if self.da_fine else s), (p.Z - self.z0) / MM


def leggi(doc, muro):
    return Facciata(doc, muro)


# --- tipi disponibili -----------------------------------------------------------------
def _ordina(tipi):
    out = {}
    for t in tipi:
        out.setdefault(chiave_tipo(t), t)
    return out


def tipi_montante(doc):
    """{"Famiglia: Tipo": MullionType}"""
    return _ordina(DB.FilteredElementCollector(doc).OfClass(DB.MullionType))


def tipi_pannello(doc):
    """{"Famiglia: Tipo": tipo} di cio' che puo' stare in una cella: pannelli di sistema,
    famiglie di pannelli, muri di base, porte e finestre (quelle non da facciata le rifiuta
    Revit al momento di cambiare il pannello: finiscono negli avvisi)."""
    tipi = list(DB.FilteredElementCollector(doc).OfClass(DB.PanelType))
    for cat in (DB.BuiltInCategory.OST_CurtainWallPanels, DB.BuiltInCategory.OST_Doors,
                DB.BuiltInCategory.OST_Windows):
        tipi += list(DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol).OfCategory(cat))
    tipi += [w for w in DB.FilteredElementCollector(doc).OfClass(DB.WallType)
             if w.Kind == DB.WallKind.Basic]
    return _ordina(tipi)


# --- schema salvato sul muro ------------------------------------------------------------
def _storage():
    guid = Guid(GUID_SCHEMA)
    s = DB.ExtensibleStorage.Schema.Lookup(guid)
    if s is not None:
        return s
    sb = DB.ExtensibleStorage.SchemaBuilder(guid)
    sb.SetSchemaName(NOME_SCHEMA)
    sb.SetReadAccessLevel(DB.ExtensibleStorage.AccessLevel.Public)
    sb.SetWriteAccessLevel(DB.ExtensibleStorage.AccessLevel.Public)
    sb.AddSimpleField(CAMPO, str)
    return sb.Finish()


def salva_schema(muro, schema):
    ent = DB.ExtensibleStorage.Entity(_storage())
    ent.Set(CAMPO, S.to_json(schema))
    muro.SetEntity(ent)


def schema_salvato(muro):
    """Lo schema applicato l'ultima volta a questo muro, o None."""
    s = DB.ExtensibleStorage.Schema.Lookup(Guid(GUID_SCHEMA))
    if s is None:
        return None
    try:
        ent = muro.GetEntity(s)
        if ent is None or not ent.IsValid():
            return None
        testo = ent.Get[str](CAMPO)
        return S.from_json(testo) if testo else None
    except Exception:
        return None


# --- tipo CDV ----------------------------------------------------------------------------
def tipo_cdv(doc, muro):
    """Il tipo "<tipo> CDV" del muro (creato se manca), con le griglie del tipo spente."""
    base = muro.WallType
    nome = nome_el(base)
    if not nome.endswith(SUFFISSO_TIPO):
        nome += SUFFISSO_TIPO
        esistente = [t for t in DB.FilteredElementCollector(doc).OfClass(DB.WallType)
                     if nome_el(t) == nome and t.Kind == DB.WallKind.Curtain]
        tipo = esistente[0] if esistente else base.Duplicate(nome)
    else:
        tipo = base
    for n in _LAYOUT:
        p = _param(tipo, n)
        if p is not None and not p.IsReadOnly and p.AsInteger() != 0:
            p.Set(0)                         # layout Nessuno
    return tipo


def montante_predefinito(doc, tipo, verticale):
    """Il montante interno del tipo di facciata per quella direzione (o l'altro, se manca)."""
    nomi = _MONTANTI_INTERNI if verticale else tuple(reversed(_MONTANTI_INTERNI))
    for n in nomi:
        p = _param(tipo, n)
        if p is not None and p.AsElementId() != DB.ElementId.InvalidElementId:
            t = doc.GetElement(p.AsElementId())
            if isinstance(t, DB.MullionType):
                return t
    return None


def pannello_predefinito(doc, tipo):
    p = _param(tipo, u"AUTO_PANEL_WALL")
    return doc.GetElement(p.AsElementId()) if p is not None else None


# --- linee -------------------------------------------------------------------------------
def _verticale(curva):
    d = curva.GetEndPoint(1) - curva.GetEndPoint(0)
    return abs(d.Z) > abs(DB.XYZ(d.X, d.Y, 0).GetLength())


def linee_esistenti(doc, griglia):
    return [doc.GetElement(i) for i in list(griglia.GetUGridLineIds()) + list(griglia.GetVGridLineIds())]


class _Linee(object):
    """Aggiunge le linee: quale fra U e V sia verticale lo si vede dalla prima linea creata."""

    def __init__(self, doc, griglia):
        self.doc = doc
        self.griglia = griglia
        self.u_orizzontale = True
        self.confermato = False      # una linea e' gia' venuta nel verso giusto

    def aggiungi(self, punto, verticale):
        errore = None
        for _giro in (0, 1):
            u = (not self.u_orizzontale) if verticale else self.u_orizzontale
            try:
                linea = self.griglia.AddGridLine(u, punto, False)
            except Exception as ex:
                linea, errore = None, ex
            if linea is not None and _verticale(linea.FullCurve) == verticale:
                self.confermato = True
                return linea
            if linea is not None:
                self.doc.Delete(linea.Id)
            if self.confermato:
                break
            self.u_orizzontale = not self.u_orizzontale
        raise FacciataErrore(u"%s" % (errore or u"verso della linea sbagliato"))


def _sblocca(el):
    try:
        if el.Pinned:
            el.Pinned = False
    except Exception:
        pass
    try:
        if getattr(el, u"Lockable", False) and el.Lock:
            el.Lock = False
    except Exception:
        pass


def _indice(tratti, v):
    for i, t in enumerate(tratti):
        if t[u"da"] - R.TOLLERANZA <= v <= t[u"a"] + R.TOLLERANZA:
            return i
    return None


def _tipo_di(classi, classe, tipi, predefinito):
    """Tipo di Revit di una classe: quello scelto, None per NESSUNO, se no il predefinito."""
    scelto = (classi or {}).get(classe) or u""
    if scelto == NESSUNO:
        return None
    return tipi.get(scelto) or predefinito


# --- applicazione ---------------------------------------------------------------------
def applica_a_muro(doc, muro, schema, tipi_m=None, tipi_p=None):
    """Applica lo schema al muro (dentro una transazione aperta). Ritorna il report:
    {"linee_v", "linee_o", "segmenti_tolti", "montanti", "pannelli", "avvisi"}."""
    tipi_m = tipi_m if tipi_m is not None else tipi_montante(doc)
    tipi_p = tipi_p if tipi_p is not None else tipi_pannello(doc)
    fac = Facciata(doc, muro)
    ris = R.calcola(schema, fac.lunghezza, fac.altezza, fac.quote_livelli)
    avvisi = []

    # 1. tipo CDV
    tipo = tipo_cdv(doc, muro)
    if muro.WallType.Id != tipo.Id:
        muro.WallType = tipo
    doc.Regenerate()

    # 2. via le linee di prima, dentro quelle nuove
    griglia = muro.CurtainGrid
    vecchie = linee_esistenti(doc, griglia)
    for ln in vecchie:
        _sblocca(ln)
    if vecchie:
        doc.Delete(_lista_id([ln.Id for ln in vecchie]))
    doc.Regenerate()
    griglia = muro.CurtainGrid
    nuove = _Linee(doc, griglia)
    senza = ris[u"senza_linea"]
    create = []          # (verticale, linea, dati della linea)
    for verticale, linee, chiave in ((True, ris[u"linee_v"], u"verticali"),
                                     (False, ris[u"linee_o"], u"orizzontali")):
        for l in linee:
            if l[u"indice"] in senza[chiave]:
                continue
            p = fac.punto(l[u"pos"], fac.altezza / 2.0) if verticale else fac.punto(fac.lunghezza / 2.0, l[u"pos"])
            try:
                create.append((verticale, nuove.aggiungi(p, verticale).Id, l))
            except Exception as ex:
                avvisi.append(u"Linea a %d mm non creata: %s" % (round(l[u"pos"]), ex))
    doc.Regenerate()

    # 3. celle unite
    tolti = 0
    for verticale, lid, l in create:
        da_togliere = ris[u"tolti"][u"verticali" if verticale else u"orizzontali"].get(l[u"indice"])
        if not da_togliere:
            continue
        linea = doc.GetElement(lid)
        for seg in list(linea.AllSegmentCurves):
            x, y = fac.coordinate(seg.Evaluate(0.5, True))
            i = _indice(ris[u"righe"], y) if verticale else _indice(ris[u"colonne"], x)
            if i in da_togliere:
                try:
                    linea.RemoveSegment(seg)
                    tolti += 1
                except Exception as ex:
                    avvisi.append(u"Segmento non tolto: %s" % ex)
    doc.Regenerate()

    # 4. montanti
    classi_m = schema[u"classi"][u"montanti"]
    predef = {True: montante_predefinito(doc, tipo, True), False: montante_predefinito(doc, tipo, False)}
    voluto = {}          # id linea -> tipo voluto (None = nessun montante)
    for verticale, lid, l in create:
        t = _tipo_di(classi_m, l[u"classe"], tipi_m, predef[verticale])
        voluto[chiave_id(lid)] = (verticale, l[u"pos"], t)
        if t is None:
            continue
        linea = doc.GetElement(lid)
        for seg in list(linea.ExistingSegmentCurves):
            try:
                linea.AddMullions(seg, t, True)
            except Exception as ex:
                avvisi.append(u"Montante non messo (%s): %s" % (l[u"classe"], ex))
    doc.Regenerate()
    montanti = _sistema_montanti(doc, muro.CurtainGrid, fac, voluto, avvisi)
    doc.Regenerate()

    # 5. pannelli
    classi_p = schema[u"classi"][u"pannelli"]
    pan_predef = pannello_predefinito(doc, tipo)
    pannelli = {}
    griglia = muro.CurtainGrid
    for pid in list(griglia.GetPanelIds()):
        el = doc.GetElement(pid)
        bb = el.get_BoundingBox(None) if el is not None else None
        if bb is None:
            continue
        x, y = fac.coordinate((bb.Min + bb.Max) * 0.5)
        cella = R.trova_cella(ris[u"celle"], ris[u"colonne"], ris[u"righe"], x, y)
        if cella is None:
            avvisi.append(u"Pannello fuori dal ritmo a %d, %d mm" % (round(x), round(y)))
            continue
        t = _tipo_di(classi_p, cella[u"classe"], tipi_p, pan_predef)
        pannelli[cella[u"classe"]] = pannelli.get(cella[u"classe"], 0) + 1
        if t is None or el.GetTypeId() == t.Id:
            continue
        _sblocca(el)
        try:
            griglia.ChangePanelType(el, t)
        except Exception as ex:
            avvisi.append(u"Pannello %s non cambiato in %s: %s" % (cella[u"classe"], chiave_tipo(t), ex))

    # 6. schema sul muro
    salva_schema(muro, schema)
    return {u"tipo": nome_el(tipo), u"lunghezza": round(fac.lunghezza, 1),
            u"altezza": round(fac.altezza, 1), u"da_fine": fac.da_fine,
            u"linee_v": len([c for c in create if c[0]]), u"linee_o": len([c for c in create if not c[0]]),
            u"segmenti_tolti": tolti, u"montanti": montanti, u"pannelli": pannelli, u"avvisi": avvisi}


def _lista_id(ids):
    from System.Collections.Generic import List
    out = List[DB.ElementId]()
    for i in ids:
        out.Add(i)
    return out


def _sistema_montanti(doc, griglia, fac, voluto, avvisi):
    """I montanti interni prendono il tipo della classe della loro linea (anche quelli messi
    da Revit da solo); quelli di classe NESSUNO si tolgono. {tipo: quanti}."""
    linee = [(v, pos, t) for v, pos, t in voluto.values()]
    via = []
    conta = {}
    for mid in list(griglia.GetMullionIds()):
        m = doc.GetElement(mid)
        curva = getattr(m, u"LocationCurve", None)
        if curva is None:
            continue
        verticale = _verticale(curva)
        x, y = fac.coordinate(curva.Evaluate(0.5, True))
        v = x if verticale else y
        trovata = [t for vv, pos, t in linee if vv == verticale and abs(pos - v) <= TOLL_MM]
        if not trovata:
            continue                     # bordo: resta quello del tipo
        t = trovata[0]
        if t is None:
            _sblocca(m)
            via.append(m.Id)
            continue
        if m.GetTypeId() != t.Id:
            _sblocca(m)
            try:
                m.ChangeTypeId(t.Id)
            except Exception as ex:
                avvisi.append(u"Montante non cambiato in %s: %s" % (chiave_tipo(t), ex))
                continue
        conta[chiave_tipo(t)] = conta.get(chiave_tipo(t), 0) + 1
    if via:
        doc.Delete(_lista_id(via))
    return conta


def applica(doc, muri, schema, nome=u"CDV Ritmo facciata"):
    """Applica lo stesso schema a ogni muro (vedi applica_coppie)."""
    return applica_coppie(doc, [(m, schema) for m in muri], nome)


def applica_coppie(doc, coppie, nome=u"CDV Ritmo facciata"):
    """Applica a ogni muro il suo schema [(muro, schema)] in una transazione sola (si annulla in
    un passo). {"muri": [{"muro": id, "report" | "errore"}], "avvisi_revit": [...]}; con un
    errore su un muro gli altri si fanno lo stesso."""
    messaggi = []
    out = []
    tipi_m, tipi_p = tipi_montante(doc), tipi_pannello(doc)
    t = transazione(doc, nome, messaggi)
    t.Start()
    try:
        for muro, schema in coppie:
            voce = {u"muro": chiave_id(muro.Id)}
            sub = DB.SubTransaction(doc)
            sub.Start()
            try:
                voce[u"report"] = applica_a_muro(doc, muro, schema, tipi_m, tipi_p)
                sub.Commit()
            except Exception as ex:
                sub.RollBack()
                voce[u"errore"] = u"%s" % ex
            out.append(voce)
        t.Commit()
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise
    return {u"muri": out, u"avvisi_revit": messaggi}


def ha_schema(muro):
    """True se sul muro c'e' uno schema CDV (senza leggerlo: per la palette)."""
    s = DB.ExtensibleStorage.Schema.Lookup(Guid(GUID_SCHEMA))
    if s is None:
        return False
    try:
        ent = muro.GetEntity(s)
        return ent is not None and ent.IsValid()
    except Exception:
        return False


def dati_facciata(fac):
    """Le misure della facciata per la finestra (senza API)."""
    return {u"lunghezza": fac.lunghezza, u"altezza": fac.altezza,
            u"quote_livelli": list(fac.quote_livelli)}


def nomi_tipi(doc):
    """{"pannelli": [...], "montanti": [...]} nomi "Famiglia: Tipo" per la finestra."""
    return {u"pannelli": sorted(tipi_pannello(doc)), u"montanti": sorted(tipi_montante(doc))}
