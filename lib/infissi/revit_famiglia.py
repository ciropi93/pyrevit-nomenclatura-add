# -*- coding: utf-8 -*-
"""Crea la famiglia Revit di un infisso dallo schema (unico modulo con le API Revit).

Parte dal modello famiglia Finestra o Porta: ne riusa Larghezza/Altezza e i piani di bordo,
poi aggiunge piani di riferimento quotati ed etichettati, estrusioni bloccate ai piani,
simboli di apertura con gli estremi quotati, i tipi; infine fa una prova di flessione
(allarga di 30 cm, controlla che tutto segua, annulla) e salva la .rfa.
"""
from Autodesk.Revit import DB

from infissi import geometria as G
from infissi import parametri as PA
from infissi import schema as S

MM = 1.0 / 304.8
TOLL = 0.5 * MM            # 0,5 mm in piedi
FLEX_MM = 300.0

NOMI_SOTTOCATEGORIE = {
    u"telaio": ((u"Telaio/Montante", u"Telaio/montante", u"Frame/Mullion"), u"Telaio/Montante"),
    u"vetro": ((u"Vetro", u"Glass"), u"Vetro"),
    u"apertura": ((u"Apertura in prospetto", u"Rotazione in prospetto", u"Elevation Swing"),
                  u"Apertura in prospetto"),
    u"pianta_porta": ((u"Apertura in pianta", u"Rotazione in pianta", u"Plan Swing"),
                      u"Apertura in pianta"),
    u"pianta_finestra": ((u"Apertura in pianta finestre",), u"Apertura in pianta finestre"),
    u"mostre": ((u"Mostre", u"Trim"), u"Mostre"),
    u"davanzali": ((u"Davanzali", u"Sill"), u"Davanzali"),
    u"imbotte": ((u"Imbotte",), u"Imbotte"),
    u"mazzetta": ((u"Mazzetta",), u"Mazzetta"),
}
# sottocategoria delle linee in pianta per stile (vedi G: ris["pianta"][..]["stile"])
SOTTOCATEGORIA_PIANTA = {u"porta": u"pianta_porta", u"finestra_continuo": u"pianta_porta",
                         u"finestra_tratteggio": u"pianta_finestra"}
_BIP_LARGHEZZA = (u"WINDOW_WIDTH", u"DOOR_WIDTH", u"FAMILY_WIDTH_PARAM", u"GENERIC_WIDTH")
_BIP_ALTEZZA = (u"WINDOW_HEIGHT", u"DOOR_HEIGHT", u"FAMILY_HEIGHT_PARAM", u"GENERIC_HEIGHT")


class FamigliaErrore(Exception):
    pass


def ft(mm):
    return mm * MM


# --- aiuti generici ------------------------------------------------------------------
class _Errori(DB.IFailuresPreprocessor):
    """Toglie gli avvisi; gli errori (es. vincoli in conflitto) li risolve come propone Revit
    (di solito togliendo il vincolo) e se li segna, cosi' non compare la finestra di Revit."""

    GIRI_MAX = 5

    def __init__(self):
        self.messaggi = []
        self.elementi = []      # id degli elementi coinvolti negli errori (durante la gestione
        self.giri = 0           # degli errori GetElement non li trova: li descrive il costruttore)

    def PreprocessFailures(self, accessor):
        risolti = False
        for f in accessor.GetFailureMessages():
            if f.GetSeverity() == DB.FailureSeverity.Warning:
                accessor.DeleteWarning(f)
                continue
            try:
                testo = f.GetDescriptionText()
            except Exception:
                testo = u"errore di Revit"
            if testo not in self.messaggi:
                self.messaggi.append(testo)
            try:
                for eid in list(f.GetFailingElementIds()) + list(f.GetAdditionalElementIds()):
                    k = _chiave_id(eid)
                    if k not in self.elementi:
                        self.elementi.append(k)
            except Exception:
                pass
            if self.giri < self.GIRI_MAX and f.GetSeverity() == DB.FailureSeverity.Error \
                    and f.HasResolutions():
                accessor.ResolveFailure(f)
                risolti = True
            else:
                return DB.FailureProcessingResult.ProceedWithRollBack
        if risolti:
            self.giri += 1
            return DB.FailureProcessingResult.ProceedWithCommit
        return DB.FailureProcessingResult.Continue


def _chiave_id(eid):
    v = getattr(eid, u"Value", None)          # Revit 2024+
    return v if v is not None else eid.IntegerValue


# Linee dei simboli (prospetto e pianta): ognuna sul SUO piano di schizzo, poi si quotano
# tutti gli estremi. Revit unisce da solo le linee dello stesso piano di schizzo che hanno
# un estremo in comune, ma non sempre (dove se ne incontrano tre ne unisce due, e non si
# sa quali) e lo fa a una rigenerazione successiva (GetAdjoinedCurveElements prima non lo
# dice). Con linee unite, quotare entrambi gli estremi e' un vincolo doppio (Revit: troppi
# vincoli); quotarne uno solo lascia libero l'altro se Revit non le ha unite. Con un piano
# di schizzo per linea non si uniscono mai e ogni estremo ha le sue quote.


class OpzioniCaricamento(DB.IFamilyLoadOptions):
    """Ricarica sovrascrivendo famiglia e valori dei parametri."""

    def OnFamilyFound(self, familyInUse, overwriteParameterValues):
        overwriteParameterValues.Value = True
        return True

    def OnSharedFamilyFound(self, sharedFamily, familyInUse, source, overwriteParameterValues):
        source.Value = DB.FamilySource.Family
        overwriteParameterValues.Value = True
        return True


def _param_integrato(fm, nomi_bip, nomi_testo):
    for n in nomi_bip:
        bip = getattr(DB.BuiltInParameter, n, None)
        if bip is None:
            continue
        try:
            p = fm.get_Parameter(bip)
        except Exception:
            p = None
        if p is not None:
            return p
    for n in nomi_testo:
        p = fm.get_Parameter(n)
        if p is not None:
            return p
    raise FamigliaErrore(u"Nel modello famiglia manca il parametro %s." % nomi_testo[0])


def _aggiungi_parametro(fm, nome, tipo, gruppo, istanza=False):
    esistente = fm.get_Parameter(nome)
    if esistente is not None:
        return esistente
    try:
        spec = {PA.LUNGHEZZA: DB.SpecTypeId.Length, PA.TESTO: DB.SpecTypeId.String.Text,
                PA.MATERIALE: DB.SpecTypeId.Reference.Material,
                PA.SINO: DB.SpecTypeId.Boolean.YesNo}[tipo]
        grp = {PA.DIMENSIONI: DB.GroupTypeId.Geometry, PA.COSTRUZIONE: DB.GroupTypeId.Construction,
               PA.GRAFICA: DB.GroupTypeId.Graphics, PA.MATERIALI: DB.GroupTypeId.Materials,
               PA.DATI: DB.GroupTypeId.Data}[gruppo]
    except AttributeError:      # Revit 2021 e precedenti
        spec = {PA.LUNGHEZZA: DB.ParameterType.Length, PA.TESTO: DB.ParameterType.Text,
                PA.MATERIALE: DB.ParameterType.Material, PA.SINO: DB.ParameterType.YesNo}[tipo]
        G_ = DB.BuiltInParameterGroup
        grp = {PA.DIMENSIONI: G_.PG_GEOMETRY, PA.COSTRUZIONE: G_.PG_CONSTRUCTION,
               PA.GRAFICA: G_.PG_GRAPHICS, PA.MATERIALI: G_.PG_MATERIALS,
               PA.DATI: G_.PG_DATA}[gruppo]
    return fm.AddParameter(nome, grp, spec, bool(istanza))


def _sottocategoria(famdoc, chiave):
    nomi, nuovo = NOMI_SOTTOCATEGORIE[chiave]
    cat = famdoc.OwnerFamily.FamilyCategory
    for sc in cat.SubCategories:
        if sc.Name in nomi:
            return sc
    try:
        return famdoc.Settings.Categories.NewSubcategory(cat, nuovo)
    except Exception:
        return None


def _vista_pianta(famdoc):
    """La pianta del livello di riferimento del modello famiglia (None se manca)."""
    for v in DB.FilteredElementCollector(famdoc).OfClass(DB.ViewPlan):
        if not v.IsTemplate and v.ViewType == DB.ViewType.FloorPlan:
            return v
    return None


def _tratteggio(famdoc):
    """Un motivo di linea tratteggiato del modello famiglia (None se non ce n'e')."""
    for lp in DB.FilteredElementCollector(famdoc).OfClass(DB.LinePatternElement):
        n = (lp.Name or u"").lower()
        if any(k in n for k in (u"dash", u"tratt", u"nascost", u"hidden")):
            return lp.Id
    return None


def _visibilita(elemento, dettaglio, modello=True, pianta=True, motivi=None):
    """Livelli di dettaglio (e pianta si'/no) in cui l'elemento della famiglia si vede."""
    try:
        return _imposta_visibilita(elemento, dettaglio, modello, pianta)
    except Exception as ex:
        if motivi is not None and u"%s" % ex not in motivi:
            motivi.append(u"%s" % ex)
        return False


def _imposta_visibilita(elemento, dettaglio, modello, pianta):
    tipo = DB.FamilyElementVisibilityType.Model if modello else DB.FamilyElementVisibilityType.ViewSpecific
    vis = DB.FamilyElementVisibility(tipo)
    vis.IsShownInCoarse = G.BASSO in dettaglio
    vis.IsShownInMedium = G.MEDIO in dettaglio
    vis.IsShownInFine = G.ALTO in dettaglio
    if modello:
        # "Pianta/Controsoffitto" degli elementi di modello (IsShownInPlanRCP vale solo
        # per quelli specifici della vista)
        vis.IsShownInTopBottom = pianta
    elemento.SetVisibility(vis)
    return True


def _vista_prospetto(famdoc):
    candidate = []
    for v in DB.FilteredElementCollector(famdoc).OfClass(DB.View):
        if v.IsTemplate or v.ViewType != DB.ViewType.Elevation:
            continue
        if abs(v.ViewDirection.Y) > 0.99:
            candidate.append(v)
    if not candidate:
        raise FamigliaErrore(u"Nel modello famiglia non trovo il prospetto frontale.")
    # di solito "Esterno"/"Exterior" ha la direzione di vista verso +Y o -Y: va bene la prima
    return candidate[0]


class _PianoLivello(object):
    """Un livello usato come piano di bordo: quanto serve di un ReferencePlane."""

    def __init__(self, livello):
        self.livello = livello
        self.Id = livello.Id
        self.Name = livello.Name
        self.BubbleEnd = DB.XYZ(0, 0, livello.Elevation)

    def GetReference(self):
        return self.livello.GetPlaneReference()


def _piani_modello(famdoc, larghezza, altezza):
    """Piani di bordo del modello: {'sx', 'dx', 'basso', 'alto', 'centro'} (centro puo' mancare)."""
    vert, oriz, front = [], [], []
    for rp in DB.FilteredElementCollector(famdoc).OfClass(DB.ReferencePlane):
        n = rp.Normal
        if abs(n.X) > 0.99:
            vert.append((rp.BubbleEnd.X, rp))
        elif abs(n.Z) > 0.99:
            oriz.append((rp.BubbleEnd.Z, rp))
        elif abs(n.Y) > 0.99:
            front.append((rp.BubbleEnd.Y, rp))

    def coppia(lista, distanza, preferito):
        migliore = None
        for a, pa in lista:
            for b, pb in lista:
                if abs((b - a) - distanza) < TOLL:
                    scarto = abs(a - preferito)
                    if migliore is None or scarto < migliore[0]:
                        migliore = (scarto, pa, pb)
        return migliore

    cv = coppia(vert, larghezza, -larghezza / 2.0)
    co = coppia(oriz, altezza, 0.0)
    if co is None:
        # modello Porta: in basso non c'e' un piano, c'e' il livello di riferimento
        for lv in DB.FilteredElementCollector(famdoc).OfClass(DB.Level):
            oriz.append((lv.Elevation, _PianoLivello(lv)))
        co = coppia(oriz, altezza, 0.0)
    if cv is None or co is None:
        def elenco(lista):
            return u", ".join(u"%s %.0f" % (rp.Name, a / MM) for a, rp in sorted(lista, key=lambda v: v[0]))
        raise FamigliaErrore(u"Nel modello famiglia non trovo i piani di riferimento di "
                             u"larghezza e altezza (cerco %.0f x %.0f mm).\nVerticali: %s\n"
                             u"Orizzontali: %s" % (larghezza / MM, altezza / MM,
                                                    elenco(vert), elenco(oriz)))
    out = {u"sx": cv[1], u"dx": cv[2], u"basso": co[1], u"alto": co[2], u"centro": None}
    for y, rp in front:
        if abs(y) < TOLL:
            out[u"centro"] = rp
    return out


def _spessore_muro(famdoc):
    """Spessore (mm) del muro ospite del modello famiglia; None se non c'e' un muro."""
    for w in DB.FilteredElementCollector(famdoc).OfClass(DB.Wall):
        return w.Width / MM
    return None


def _facce_muro(famdoc, spessore_mm):
    """Piani del modello sulle facce del muro: {"esterno": rp, "interno": rp} (quelli che ci sono).
    Sono i piani Esterno/Interno del modello, legati alle facce: seguono lo spessore del muro."""
    out = {}
    if not spessore_mm:
        return out
    meta = ft(spessore_mm) / 2.0
    for rp in DB.FilteredElementCollector(famdoc).OfClass(DB.ReferencePlane):
        if abs(rp.Normal.Y) < 0.99:
            continue
        y = rp.BubbleEnd.Y
        for nome, pos in ((u"esterno", -G.INTERNO * meta), (u"interno", G.INTERNO * meta)):
            if abs(y - pos) < TOLL and nome not in out:
                out[nome] = rp
    return out


def _vista_lato(famdoc):
    """Un prospetto laterale (guarda lungo x): li' le facce parallele al muro sono linee."""
    for v in DB.FilteredElementCollector(famdoc).OfClass(DB.View):
        if not v.IsTemplate and v.ViewType == DB.ViewType.Elevation and abs(v.ViewDirection.X) > 0.99:
            return v
    return None


# --- costruzione ------------------------------------------------------------------------
class _Costruttore(object):
    def __init__(self, famdoc, schema):
        self.doc = famdoc
        self.crea = famdoc.FamilyCreate
        self.fm = famdoc.FamilyManager
        self.schema = schema
        # le facce del muro sono quelle del modello famiglia: si calcola con il suo spessore
        self.spessore_muro = _spessore_muro(famdoc)
        self.ris = G.calcola(schema, self.spessore_muro)
        if self.ris[u"errori"]:
            raise FamigliaErrore(u"\n".join(self.ris[u"errori"]))
        self.parametri = PA.elenco(schema, self.ris)
        self.report = {u"quote": 0, u"allineamenti": 0, u"simboli": 0, u"flex": u"",
                       u"pianta": 0, u"aperte": 0, u"visibilita": 0, u"formule": [],
                       u"motivi_quote": [], u"motivi_visibilita": [], u"linee_fuori": [],
                       u"contorno": 0, u"motivi_contorno": []}
        self.fp = {}
        self.rp = {}
        self.estrusioni = []
        self.simboli = []
        self.estrusioni_aperte = []
        self.contorno = []
        self.pianta = None
        self.descrizioni = {}       # id elemento -> cosa e' (per spiegare gli errori di Revit)

    def _descrivi(self, elemento, testo):
        try:
            self.descrizioni[_chiave_id(elemento.Id)] = testo
        except Exception:
            pass

    def spiega(self, ids):
        """Descrizione degli elementi coinvolti in un errore di Revit."""
        return [self.descrizioni.get(k, u"elemento %s" % k) for k in ids]

    # coordinate: mm dello schema -> piedi del modello famiglia
    def X(self, mm):
        return self.x0 + ft(mm)

    def Z(self, mm):
        return self.z0 + ft(mm)

    def punto(self, x_mm, z_mm):
        return DB.XYZ(self.X(x_mm), self.y0, self.Z(z_mm))

    def esegui(self, tipi):
        fm = self.fm
        nome0 = tipi[0][0]
        if fm.CurrentType is None:
            fm.NewType(nome0)
        else:
            fm.RenameCurrentType(nome0)
        self.fp[G.LARGHEZZA] = _param_integrato(fm, _BIP_LARGHEZZA, (u"Larghezza", u"Width"))
        self.fp[G.ALTEZZA] = _param_integrato(fm, _BIP_ALTEZZA, (u"Altezza", u"Height"))
        fm.Set(self.fp[G.LARGHEZZA], ft(self.schema[u"larghezza"]))
        fm.Set(self.fp[G.ALTEZZA], ft(self.schema[u"altezza"]))
        self.doc.Regenerate()

        self.vista = _vista_prospetto(self.doc)
        self.vista_lato = _vista_lato(self.doc)
        bordi = _piani_modello(self.doc, ft(self.schema[u"larghezza"]), ft(self.schema[u"altezza"]))
        for k in G.RADICI:
            self.rp[k] = bordi[k]
        self.x0 = bordi[u"sx"].BubbleEnd.X
        self.z0 = bordi[u"basso"].BubbleEnd.Z
        self.y0 = 0.0
        self.centro = bordi[u"centro"]
        self.piano_asse = self.centro

        self._togli_dal_modello()
        self._parametri()
        self._piani()
        self._prepara_y()
        self._estrusioni()
        self.doc.Regenerate()
        self._allinea()
        self._simboli()
        self._pianta_e_aperte()
        self._contorno()
        self._tipi(tipi)
        self._flex()
        return self.report

    def _nuovo_piano_schizzo(self):
        """Piano di schizzo del prospetto: sull'asse del telaio (di base il piano "centro" del
        modello, cioe' l'asse del muro)."""
        if self.piano_asse is not None:
            return DB.SketchPlane.Create(self.doc, self.piano_asse.Id)
        return DB.SketchPlane.Create(
            self.doc, DB.Plane.CreateByNormalAndOrigin(DB.XYZ.BasisY, DB.XYZ.Zero))

    def _togli_dal_modello(self):
        """Toglie i solidi del modello famiglia (la mostra del modello Porta: le mostre le fa il
        contorno). Il foro nel muro resta quello del modello."""
        ids = []
        for cls in (DB.Extrusion, DB.Sweep, DB.Blend, DB.Revolution, DB.SweptBlend):
            ids.extend(e.Id for e in DB.FilteredElementCollector(self.doc).OfClass(cls))
        for eid in ids:
            try:
                self.doc.Delete(eid)
            except Exception:
                pass
        if ids:
            self.doc.Regenerate()

    def _prepara_y(self):
        """Pianta del modello, piani paralleli al muro (asse del telaio, facce...) e piano di
        schizzo sull'asse del telaio: tutto il serramento si costruisce da li'."""
        self.pianta = _vista_pianta(self.doc)
        self.yc = self.centro.BubbleEnd.Y if self.centro is not None else 0.0
        self.rp[u"centro"] = self.centro
        self.rp.update(_facce_muro(self.doc, self.spessore_muro))
        if self.pianta is not None and self.centro is not None:
            self._piani_y()
        asse = self.ris[u"asse"]
        if asse != u"centro":
            if asse not in self.rp:
                raise FamigliaErrore(u"Non riesco a mettere il telaio nella posizione scelta: nel modello "
                                     u"famiglia mancano la pianta o i piani Esterno/Interno del muro.")
            self.piano_asse = self.rp[asse]
        self.y0 = self.yc + ft(self.ris[u"asse_y"])
        self.piano_schizzo = self._nuovo_piano_schizzo()

    def _parametri(self):
        fm = self.fm
        mappa = {G.LARGHEZZA: self.fp[G.LARGHEZZA].Definition.Name,
                 G.ALTEZZA: self.fp[G.ALTEZZA].Definition.Name}
        nomi = [p[u"nome"] for p in self.parametri]
        for p in self.parametri:
            if not p[u"integrato"]:
                self.fp[p[u"nome"]] = _aggiungi_parametro(fm, p[u"nome"], p[u"tipo"], p[u"gruppo"],
                                                          p.get(u"istanza", False))
        self._scrivi_valori(self.parametri)
        for p in self.parametri:
            if not p[u"formula"]:
                continue
            fp = self.fp[p[u"nome"]]
            try:
                if p[u"tipo"] == PA.SINO:
                    fm.SetFormula(fp, p[u"formula"])     # es. not(Aperta in 3D)
                else:
                    fm.SetFormula(fp, PA.rinomina(p[u"formula"], mappa, nomi))
            except Exception:
                # formula rifiutata: almeno il valore giusto, cosi' le quote non vanno a zero
                self.report[u"formule"].append(p[u"nome"])
                try:
                    if p[u"tipo"] == PA.LUNGHEZZA and p[u"valore"] is not None:
                        fm.Set(fp, ft(p[u"valore"]))
                    elif p[u"tipo"] == PA.SINO and p[u"valore"] is not None:
                        fm.Set(fp, int(p[u"valore"]))
                except Exception:
                    pass

    def _scrivi_valori(self, parametri):
        fm = self.fm
        for p in parametri:
            if p[u"formula"] or p[u"valore"] is None:
                continue
            fp = self.fp[p[u"nome"]]
            if p[u"tipo"] == PA.LUNGHEZZA:
                fm.Set(fp, ft(p[u"valore"]))
            elif p[u"tipo"] == PA.TESTO:
                fm.Set(fp, p[u"valore"])
            elif p[u"tipo"] == PA.SINO:
                fm.Set(fp, int(p[u"valore"]))

    def _quota(self, rif_a, rif_b, linea, param, vista=None):
        try:
            ra = DB.ReferenceArray()
            ra.Append(rif_a)
            ra.Append(rif_b)
            dim = self.crea.NewDimension(vista or self.vista, linea, ra)
            dim.FamilyLabel = self.fp[param]
            self._descrivi(dim, u"quota %s" % param)
            return True
        except Exception as ex:
            self.report[u"quote"] += 1
            motivo = u"%s: %s" % (param, ex)
            if motivo not in self.report[u"motivi_quote"]:
                self.report[u"motivi_quote"].append(motivo)
            return False

    def _piani(self):
        L, H = ft(self.schema[u"larghezza"]), ft(self.schema[u"altezza"])
        sporgenza = ft(300)
        livello_quote = {u"v": self.Z(self.schema[u"altezza"]) + ft(400),
                         u"o": self.X(self.schema[u"larghezza"]) + ft(400)}
        passo = ft(60)
        for p in self.ris[u"piani"]:
            if p[u"base"] is None:
                continue
            if p[u"verso"] == u"v":
                x = self.X(p[u"pos"])
                a = DB.XYZ(x, self.y0, self.z0 + H + sporgenza)
                b = DB.XYZ(x, self.y0, self.z0 - sporgenza)
            else:
                z = self.Z(p[u"pos"])
                a = DB.XYZ(self.x0 - sporgenza, self.y0, z)
                b = DB.XYZ(self.x0 + L + sporgenza, self.y0, z)
            rp = self.crea.NewReferencePlane(a, b, DB.XYZ.BasisY, self.vista)
            try:
                rp.Name = u"CDV %s" % p[u"id"]
            except Exception:
                pass
            self.rp[p[u"id"]] = rp
        # prima tutti i piani, poi le quote: un piano appena creato non e' ancora un
        # riferimento geometrico finche' Revit non rigenera
        self.doc.Regenerate()
        for i, p in enumerate(self.ris[u"piani"]):
            if p[u"base"] is None:
                continue
            rp = self.rp[p[u"id"]]
            base = self.rp[p[u"base"]]
            q = livello_quote[p[u"verso"]] + (i % 8) * passo
            pb = [x for x in self.ris[u"piani"] if x[u"id"] == p[u"base"]][0][u"pos"]
            if p[u"verso"] == u"v":
                linea = DB.Line.CreateBound(DB.XYZ(self.X(pb), self.y0, q),
                                            DB.XYZ(self.X(p[u"pos"]), self.y0, q))
            else:
                linea = DB.Line.CreateBound(DB.XYZ(q, self.y0, self.Z(pb)),
                                            DB.XYZ(q, self.y0, self.Z(p[u"pos"])))
            self._quota(base.GetReference(), rp.GetReference(), linea, p[u"param"])

    def _anello(self, ids):
        x0, y0, x1, y1 = G.rettangolo(self.ris, ids)
        pts = [self.punto(x0, y0), self.punto(x1, y0), self.punto(x1, y1), self.punto(x0, y1)]
        ca = DB.CurveArray()
        for i in range(4):
            ca.Append(DB.Line.CreateBound(pts[i], pts[(i + 1) % 4]))
        return ca

    def _estrusioni(self):
        fm = self.fm
        sc_telaio = _sottocategoria(self.doc, u"telaio")
        sc_vetro = _sottocategoria(self.doc, u"vetro")
        valori = dict((p[u"nome"], p[u"valore"]) for p in self.parametri
                      if p[u"tipo"] == PA.LUNGHEZZA)
        for pz in self.ris[u"pezzi"]:
            profilo = DB.CurveArrArray()
            profilo.Append(self._anello(pz[u"esterni"]))
            if pz[u"interni"]:
                profilo.Append(self._anello(pz[u"interni"]))
            n_inizio, n_fine = G.PROFONDITA[pz[u"profondita"]]
            inizio, fine = valori[n_inizio], valori[n_fine]
            ext = self.crea.NewExtrusion(True, profilo, self.piano_schizzo, ft(fine - inizio))
            ext.StartOffset = ft(inizio)
            ext.EndOffset = ft(fine)
            for bip, nome in ((DB.BuiltInParameter.EXTRUSION_START_PARAM, n_inizio),
                              (DB.BuiltInParameter.EXTRUSION_END_PARAM, n_fine)):
                fm.AssociateElementParameterToFamilyParameter(ext.get_Parameter(bip),
                                                              self.fp[nome])
            vetro = pz[u"tipo"] == u"vetro"
            mat = {u"vetro": PA.MATERIALE_VETRO,
                   u"pannello": PA.MATERIALE_PANNELLO}.get(pz[u"tipo"], PA.MATERIALE_TELAIO)
            try:
                fm.AssociateElementParameterToFamilyParameter(
                    ext.get_Parameter(DB.BuiltInParameter.MATERIAL_ID_PARAM), self.fp[mat])
            except Exception:
                pass
            sc = sc_vetro if vetro else sc_telaio
            if sc is not None:
                try:
                    ext.Subcategory = sc
                except Exception:
                    pass
            self._visibile(ext, pz)
            self.estrusioni.append((ext, pz))

    def _visibile(self, ext, pz, pianta=True):
        """Livelli di dettaglio e (ante) aperta/chiusa dal parametro di istanza."""
        if not _visibilita(ext, pz.get(u"dettaglio", G.TUTTI), pianta=pianta,
                           motivi=self.report[u"motivi_visibilita"]):
            self.report[u"visibilita"] += 1
        nome = {u"chiusa": G.CHIUSA, u"aperta": G.APERTA}.get(pz.get(u"stato"))
        if nome and nome in self.fp:
            try:
                self.fm.AssociateElementParameterToFamilyParameter(
                    ext.get_Parameter(DB.BuiltInParameter.IS_VISIBLE_PARAM), self.fp[nome])
            except Exception as ex:
                self.report[u"visibilita"] += 1
                self.report[u"motivi_visibilita"].append(u"%s: %s" % (nome, ex))

    def _allinea(self):
        opt = DB.Options()
        opt.ComputeReferences = True
        opt.IncludeNonVisibleObjects = True
        for ext, pz in self.estrusioni:
            ids = list(pz[u"esterni"]) + list(pz[u"interni"] or ())
            piani = [p for p in self.ris[u"piani"] if p[u"id"] in ids]
            for faccia in _facce(ext, opt):
                n = faccia.FaceNormal
                if abs(n.X) > 0.99:
                    pos, verso, conv = faccia.Origin.X, u"v", self.X
                elif abs(n.Z) > 0.99:
                    pos, verso, conv = faccia.Origin.Z, u"o", self.Z
                else:
                    continue
                for p in piani:
                    if p[u"verso"] == verso and abs(conv(p[u"pos"]) - pos) < TOLL:
                        try:
                            al = self.crea.NewAlignment(self.vista, self.rp[p[u"id"]].GetReference(),
                                                        faccia.Reference)
                            al.IsLocked = True
                        except Exception:
                            self.report[u"allineamenti"] += 1
                        break

    def _simboli(self):
        stile = None
        sc = _sottocategoria(self.doc, u"apertura")
        if sc is not None:
            try:
                stile = sc.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
            except Exception:
                stile = None
        for s in self.ris[u"simboli"]:
            for seg in s[u"segmenti"]:
                linea = DB.Line.CreateBound(self.punto(*seg[u"p0"]), self.punto(*seg[u"p1"]))
                # un piano di schizzo per linea: vedi il commento 'Linee dei simboli' in cima
                curva = self.crea.NewSymbolicCurve(linea, self._nuovo_piano_schizzo())
                if stile is not None:
                    try:
                        curva.Subcategory = stile
                    except Exception:
                        pass
                self._descrivi(curva, u"linea simbolo %s-%s" % (seg[u"p0"], seg[u"p1"]))
                self.simboli.append((curva, seg))
        self.doc.Regenerate()
        for curva, seg in self.simboli:
            for indice in (0, 1):
                self._quota_estremo_simbolo(curva, seg, indice)
        self.doc.Regenerate()   # i vincoli in conflitto emergono qui, non piu' avanti

    def _quota_estremo_simbolo(self, curva, seg, indice):
        """Quota l'estremo (x e z) dal suo piano base con il suo parametro."""
        punto = seg[u"p0"] if indice == 0 else seg[u"p1"]
        cx, cz = seg[u"coord"][2 * indice], seg[u"coord"][2 * indice + 1]
        try:
            rif_estremo = curva.GeometryCurve.GetEndPointReference(indice)
        except Exception:
            rif_estremo = None
        if rif_estremo is None:
            self.report[u"simboli"] += 1
            return
        for (pid, param, _segno), verso in ((cx, u"v"), (cz, u"o")):
            pb = [p for p in self.ris[u"piani"] if p[u"id"] == pid][0][u"pos"]
            if verso == u"v":
                z = self.Z(punto[1])
                linea = DB.Line.CreateBound(DB.XYZ(self.X(pb), self.y0, z),
                                            DB.XYZ(self.X(punto[0]), self.y0, z))
            else:
                x = self.X(punto[0])
                linea = DB.Line.CreateBound(DB.XYZ(x, self.y0, self.Z(pb)),
                                            DB.XYZ(x, self.y0, self.Z(punto[1])))
            if not self._quota(self.rp[pid].GetReference(), rif_estremo, linea, param):
                self.report[u"simboli"] += 1

    # --- pianta e ante aperte --------------------------------------------------------------
    def Y(self, mm):
        return self.yc + ft(mm)

    def _pianta_e_aperte(self):
        """Simboli in pianta e ante aperte (dove serve); i piani paralleli al muro ci sono gia'."""
        if not self.ris[u"pianta"] and not self.ris[u"pezzi_aperti"]:
            return
        if self.pianta is None or self.centro is None:
            self.report[u"pianta"] += len(self.ris[u"pianta"])
            self.report[u"aperte"] += len(self.ris[u"pezzi_aperti"])
            return
        self._simboli_pianta()
        self._aperte()

    def _piani_y(self):
        L = ft(self.schema[u"larghezza"])
        sporg = ft(300)
        x_quote = self.X(self.schema[u"larghezza"]) + ft(400)
        for p in self.ris[u"piani_y"]:
            if p[u"base"] is None:
                continue
            if p[u"base"] in (u"esterno", u"interno") and p[u"base"] not in self.rp:
                raise FamigliaErrore(u"Nel modello famiglia non trovo il piano %s sulla faccia del muro."
                                     % p[u"base"].capitalize())
            y = self.Y(p[u"pos"])
            rp = self.crea.NewReferencePlane(DB.XYZ(self.x0 - sporg, y, self.z0),
                                             DB.XYZ(self.x0 + L + sporg, y, self.z0),
                                             DB.XYZ.BasisZ, self.pianta)
            try:
                rp.Name = u"CDV %s" % p[u"id"]
            except Exception:
                pass
            self.rp[p[u"id"]] = rp
        self.doc.Regenerate()       # vedi _piani: prima i piani, poi le quote
        for i, p in enumerate(self.ris[u"piani_y"]):
            if p[u"base"] is None:
                continue
            y = self.Y(p[u"pos"])
            rp = self.rp[p[u"id"]]
            yb = [q for q in self.ris[u"piani_y"] if q[u"id"] == p[u"base"]][0][u"pos"]
            x = x_quote + (i % 6) * ft(60)
            linea = DB.Line.CreateBound(DB.XYZ(x, self.Y(yb), self.z0), DB.XYZ(x, y, self.z0))
            self._quota(self.rp[p[u"base"]].GetReference(), rp.GetReference(), linea, p[u"param"],
                        self.pianta)

    def _piano_orizzontale(self):
        return DB.SketchPlane.Create(self.doc, DB.Plane.CreateByNormalAndOrigin(
            DB.XYZ.BasisZ, DB.XYZ(0, 0, self.z0)))

    def _simboli_pianta(self):
        if not self.ris[u"pianta"]:
            return
        stili = {}
        for chiave in (u"pianta_porta", u"pianta_finestra"):
            sc = _sottocategoria(self.doc, chiave)
            if sc is None:
                continue
            if chiave == u"pianta_finestra":
                tr = _tratteggio(self.doc)
                if tr is not None:
                    try:
                        sc.SetLinePatternId(tr, DB.GraphicsStyleType.Projection)
                    except Exception:
                        pass
            try:
                stili[chiave] = sc.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
            except Exception:
                pass
        punto = lambda p: DB.XYZ(self.X(p[0]), self.Y(p[1]), self.z0)  # noqa: E731
        create = []
        for simb in self.ris[u"pianta"]:
            stile = stili.get(SOTTOCATEGORIA_PIANTA[simb[u"stile"]])
            for seg in simb[u"segmenti"]:
                piano = self._piano_orizzontale()      # uno per linea: commento 'Linee dei simboli'
                try:
                    if seg[u"tipo"] == u"arco":
                        c = seg[u"centro"]
                        r = ((seg[u"p0"][0] - c[0]) ** 2 + (seg[u"p0"][1] - c[1]) ** 2) ** 0.5
                        mx = (seg[u"p0"][0] + seg[u"p1"][0]) / 2.0 - c[0]
                        my = (seg[u"p0"][1] + seg[u"p1"][1]) / 2.0 - c[1]
                        k = r / max((mx * mx + my * my) ** 0.5, 1e-9)
                        geo = DB.Arc.Create(punto(seg[u"p0"]), punto(seg[u"p1"]),
                                            punto((c[0] + mx * k, c[1] + my * k)))
                    else:
                        geo = DB.Line.CreateBound(punto(seg[u"p0"]), punto(seg[u"p1"]))
                    curva = self.crea.NewSymbolicCurve(geo, piano)
                except Exception:
                    self.report[u"pianta"] += 1
                    continue
                if stile is not None:
                    try:
                        curva.Subcategory = stile
                    except Exception:
                        pass
                _visibilita(curva, G.TUTTI, modello=False)
                create.append((curva, seg))
        self.doc.Regenerate()
        for curva, seg in create:
            for indice in (0, 1):
                self._quota_estremo_pianta(curva, seg, indice)

    def _quota_estremo_pianta(self, curva, seg, indice):
        """Quota l'estremo: x da un piano x, y da un piano parallelo al muro (in pianta)."""
        punto = seg[u"p0"] if indice == 0 else seg[u"p1"]
        cx, cy = seg[u"coord"][2 * indice], seg[u"coord"][2 * indice + 1]
        tutti = dict((p[u"id"], p[u"pos"]) for p in self.ris[u"piani"])
        tutti_y = dict((p[u"id"], p[u"pos"]) for p in self.ris[u"piani_y"])
        try:
            rif = curva.GeometryCurve.GetEndPointReference(indice)
        except Exception:
            rif = None
        if rif is None:
            self.report[u"pianta"] += 1
            return
        for (pid, param, _segno), verso in ((cx, u"x"), (cy, u"y")):
            if verso == u"x":
                xb, y = self.X(tutti[pid]), self.Y(punto[1])
                linea = DB.Line.CreateBound(DB.XYZ(xb, y, self.z0), DB.XYZ(self.X(punto[0]), y, self.z0))
            else:
                x, yb = self.X(punto[0]), self.Y(tutti_y[pid])
                linea = DB.Line.CreateBound(DB.XYZ(x, yb, self.z0), DB.XYZ(x, self.Y(punto[1]), self.z0))
            if not self._quota(self.rp[pid].GetReference(), rif, linea, param, self.pianta):
                self.report[u"pianta"] += 1

    def _aperte(self):
        """Ante aperte a 90 gradi: estrusioni sul piano delle cerniere, verso il vano."""
        valori = dict((p[u"nome"], p[u"valore"]) for p in self.parametri if p[u"tipo"] == PA.LUNGHEZZA)
        pos = dict((p[u"id"], p[u"pos"]) for p in self.ris[u"piani"])
        pos_y = dict((p[u"id"], p[u"pos"]) for p in self.ris[u"piani_y"])
        sc_telaio = _sottocategoria(self.doc, u"telaio")
        sc_vetro = _sottocategoria(self.doc, u"vetro")
        piani_schizzo = {}
        for pz in self.ris[u"pezzi_aperti"]:
            try:
                rp = self.rp[pz[u"piano_x"]]
                if pz[u"piano_x"] not in piani_schizzo:
                    piani_schizzo[pz[u"piano_x"]] = DB.SketchPlane.Create(self.doc, rp.Id)
                sp = piani_schizzo[pz[u"piano_x"]]
                x = self.X(pos[pz[u"piano_x"]])

                def anello(y_ids, z_ids):
                    y0, y1 = sorted(pos_y[i] for i in y_ids)
                    z0, z1 = sorted(pos[i] for i in z_ids)
                    pts = [DB.XYZ(x, self.Y(y0), self.Z(z0)), DB.XYZ(x, self.Y(y1), self.Z(z0)),
                           DB.XYZ(x, self.Y(y1), self.Z(z1)), DB.XYZ(x, self.Y(y0), self.Z(z1))]
                    ca = DB.CurveArray()
                    for i in range(4):
                        ca.Append(DB.Line.CreateBound(pts[i], pts[(i + 1) % 4]))
                    return ca

                profilo = DB.CurveArrArray()
                profilo.Append(anello(pz[u"y"], pz[u"z"]))
                if pz[u"y_int"]:
                    profilo.Append(anello(pz[u"y_int"], pz[u"z_int"]))
                # spessore nel verso del vano, misurato lungo la normale del piano di schizzo
                normale = 1 if sp.GetPlane().Normal.X > 0 else -1
                tipo = u"vetro" if pz[u"spessore"] == u"vetro" else u"anta"
                n_inizio, n_fine = G.SPESSORI_APERTI[tipo][pz[u"verso"] * normale]
                inizio = valori[n_inizio] if n_inizio else 0.0
                fine = valori[n_fine]
                ext = self.crea.NewExtrusion(True, profilo, sp, ft(abs(fine - inizio)) or ft(1))
                ext.StartOffset = ft(inizio)
                ext.EndOffset = ft(fine)
                for bip, nome in ((DB.BuiltInParameter.EXTRUSION_START_PARAM, n_inizio),
                                  (DB.BuiltInParameter.EXTRUSION_END_PARAM, n_fine)):
                    if nome:
                        self.fm.AssociateElementParameterToFamilyParameter(ext.get_Parameter(bip),
                                                                           self.fp[nome])
                mat = {u"vetro": PA.MATERIALE_VETRO,
                       u"pannello": PA.MATERIALE_PANNELLO}.get(pz[u"tipo"], PA.MATERIALE_TELAIO)
                if mat in self.fp:
                    try:
                        self.fm.AssociateElementParameterToFamilyParameter(
                            ext.get_Parameter(DB.BuiltInParameter.MATERIAL_ID_PARAM), self.fp[mat])
                    except Exception:
                        pass
                sc = sc_vetro if pz[u"tipo"] == u"vetro" else sc_telaio
                if sc is not None:
                    try:
                        ext.Subcategory = sc
                    except Exception:
                        pass
                self.estrusioni_aperte.append((ext, pz))
            except Exception:
                self.report[u"aperte"] += 1
        self.doc.Regenerate()
        self._allinea_aperte()
        # in pianta valgono i simboli: l'anta aperta si vede in 3D, prospetti e sezioni
        # (visibilita' dopo gli allineamenti, che in pianta vogliono le facce visibili)
        for ext, pz in self.estrusioni_aperte:
            self._visibile(ext, pz, pianta=False)

    def _allinea_aperte(self):
        """Facce delle ante aperte: y ai piani paralleli al muro (in pianta), z ai piani orizzontali."""
        opt = DB.Options()
        opt.ComputeReferences = True
        opt.IncludeNonVisibleObjects = True
        for ext, pz in self.estrusioni_aperte:
            ids_y = list(pz[u"y"]) + list(pz[u"y_int"] or ())
            ids_z = list(pz[u"z"]) + list(pz[u"z_int"] or ())
            piani_y = [p for p in self.ris[u"piani_y"] if p[u"id"] in ids_y]
            piani_z = [p for p in self.ris[u"piani"] if p[u"id"] in ids_z]
            for faccia in _facce(ext, opt):
                n = faccia.FaceNormal
                if abs(n.Y) > 0.99:
                    pos, candidati, conv, vista = faccia.Origin.Y, piani_y, self.Y, self.pianta
                elif abs(n.Z) > 0.99:
                    pos, candidati, conv, vista = faccia.Origin.Z, piani_z, self.Z, self.vista
                else:
                    continue
                for p in candidati:
                    if abs(conv(p[u"pos"]) - pos) < TOLL:
                        try:
                            al = self.crea.NewAlignment(vista, self.rp[p[u"id"]].GetReference(),
                                                        faccia.Reference)
                            al.IsLocked = True
                        except Exception:
                            self.report[u"aperte"] += 1
                        break

    # --- contorno: mostre, davanzali, soglia, imbotte, foro con la mazzetta ---------------------
    def _contorno(self):
        """Ogni elemento e' un'estrusione disegnata in prospetto sul suo piano parallelo al muro;
        le facce si bloccano ai piani: x/z nel prospetto, y nel prospetto laterale."""
        elementi = self.ris[u"contorno"]
        if not elementi:
            return
        if self.vista_lato is None or self.centro is None:
            self.report[u"contorno"] += len(elementi)
            self.report[u"motivi_contorno"].append(u"manca il prospetto laterale o il piano centro")
            return
        for e in elementi:
            try:
                ext = self._estrusione_contorno(e)
                self._descrivi(ext, e[u"nome"])
                self.contorno.append((ext, e))
            except Exception as ex:
                self.report[u"contorno"] += 1
                self.report[u"motivi_contorno"].append(u"%s: %s" % (e[u"nome"], ex))
        self.doc.Regenerate()
        for ext, e in self.contorno:
            self._allinea_contorno(ext, e)

    def _estrusione_contorno(self, e):
        pos = dict((p[u"id"], p[u"pos"]) for p in self.ris[u"piani"])
        pos_y = dict((p[u"id"], p[u"pos"]) for p in self.ris[u"piani_y"])
        x0, x1 = sorted(pos[k] for k in e[u"x"])
        z0, z1 = sorted(pos[k] for k in e[u"z"])
        ya, yb = pos_y[e[u"y"][0]], pos_y[e[u"y"][1]]
        sp = DB.SketchPlane.Create(self.doc, self.rp[e[u"y"][0]].Id)
        yw = self.Y(ya)
        pts = [DB.XYZ(self.X(x0), yw, self.Z(z0)), DB.XYZ(self.X(x1), yw, self.Z(z0)),
               DB.XYZ(self.X(x1), yw, self.Z(z1)), DB.XYZ(self.X(x0), yw, self.Z(z1))]
        ca = DB.CurveArray()
        for i in range(4):
            ca.Append(DB.Line.CreateBound(pts[i], pts[(i + 1) % 4]))
        profilo = DB.CurveArrArray()
        profilo.Append(ca)
        # l'estrusione va lungo la normale del piano di schizzo: da ya a yb
        off = ft(yb - ya) * (1 if sp.GetPlane().Normal.Y > 0 else -1)
        ext = self.crea.NewExtrusion(True, profilo, sp, abs(off) or ft(1))
        ext.StartOffset = min(0.0, off)
        ext.EndOffset = max(0.0, off)
        for nome, bip in ((e[u"visibile"], DB.BuiltInParameter.IS_VISIBLE_PARAM),
                          (e[u"materiale"], DB.BuiltInParameter.MATERIAL_ID_PARAM)):
            if nome and nome in self.fp:
                try:
                    self.fm.AssociateElementParameterToFamilyParameter(ext.get_Parameter(bip), self.fp[nome])
                except Exception as ex:
                    self.report[u"motivi_contorno"].append(u"%s, %s: %s" % (e[u"nome"], nome, ex))
        sc = _sottocategoria(self.doc, {u"mostra": u"mostre", u"imbotte": u"imbotte", u"mazzetta": u"mazzetta"}
                             .get(e[u"tipo"], u"davanzali"))
        if sc is not None:
            try:
                ext.Subcategory = sc
            except Exception:
                pass
        _visibilita(ext, G.TUTTI)
        return ext

    def _allinea_contorno(self, ext, e):
        """Blocca le facce dell'elemento ai suoi piani: x e z nel prospetto, y nel laterale."""
        opt = DB.Options()
        opt.ComputeReferences = True
        opt.IncludeNonVisibleObjects = True
        piani = dict((p[u"id"], p) for p in self.ris[u"piani"])
        piani_y = dict((p[u"id"], p) for p in self.ris[u"piani_y"])
        candidati = {u"x": [piani[k] for k in e[u"x"]], u"z": [piani[k] for k in e[u"z"]],
                     u"y": [piani_y[k] for k in e[u"y"]]}
        bloccati = 0
        for faccia in _facce(ext, opt):
            n = faccia.FaceNormal
            if abs(n.X) > 0.99:
                asse, pos, conv, vista = u"x", faccia.Origin.X, self.X, self.vista
            elif abs(n.Z) > 0.99:
                asse, pos, conv, vista = u"z", faccia.Origin.Z, self.Z, self.vista
            elif abs(n.Y) > 0.99:
                asse, pos, conv, vista = u"y", faccia.Origin.Y, self.Y, self.vista_lato
            else:
                continue
            for p in candidati[asse]:
                if abs(conv(p[u"pos"]) - pos) < TOLL:
                    try:
                        al = self.crea.NewAlignment(vista, self.rp[p[u"id"]].GetReference(), faccia.Reference)
                        al.IsLocked = True
                        bloccati += 1
                    except Exception as ex:
                        self.report[u"allineamenti"] += 1
                        motivo = u"%s (%s): %s" % (e[u"nome"], asse, ex)
                        if motivo not in self.report[u"motivi_contorno"]:
                            self.report[u"motivi_contorno"].append(motivo)
                    break
        if bloccati < 6:
            self.report[u"motivi_contorno"].append(u"%s: %d facce bloccate su 6" % (e[u"nome"], bloccati))

    def _tipi(self, tipi):
        fm = self.fm
        primo = fm.CurrentType
        for nome, schema_tipo in tipi[1:]:
            parametri = PA.elenco(schema_tipo)
            fm.NewType(nome)
            self._scrivi_valori(parametri)
        if len(tipi) > 1:
            fm.CurrentType = primo
            self.doc.Regenerate()

    def _flex(self):
        """Allarga e alza di 30 cm: telaio, ante, vetri e simboli devono seguire."""
        s2 = S.copia(self.schema)
        s2[u"larghezza"] += FLEX_MM
        s2[u"altezza"] += FLEX_MM
        ris2 = G.calcola(s2, self.spessore_muro)
        st = DB.SubTransaction(self.doc)
        st.Start()
        try:
            self.fm.Set(self.fp[G.LARGHEZZA], ft(s2[u"larghezza"]))
            self.fm.Set(self.fp[G.ALTEZZA], ft(s2[u"altezza"]))
            self.doc.Regenerate()
            x0 = self.rp[u"sx"].BubbleEnd.X
            z0 = self.rp[u"basso"].BubbleEnd.Z
            pezzi_fuori = 0
            for (ext, _pz), pz2 in zip(self.estrusioni, ris2[u"pezzi"]):
                r = G.rettangolo(ris2, pz2[u"esterni"])
                bb = ext.get_BoundingBox(None)
                if bb is None or max(abs(bb.Min.X - (x0 + ft(r[0]))), abs(bb.Max.X - (x0 + ft(r[2]))),
                                     abs(bb.Min.Z - (z0 + ft(r[1]))),
                                     abs(bb.Max.Z - (z0 + ft(r[3])))) > TOLL * 2:
                    pezzi_fuori += 1
            segs2 = [seg for s in ris2[u"simboli"] for seg in s[u"segmenti"]]
            simboli_fuori = 0
            for (curva, _seg), seg2 in zip(self.simboli, segs2):
                c = curva.GeometryCurve
                for i, p in ((0, seg2[u"p0"]), (1, seg2[u"p1"])):
                    q = c.GetEndPoint(i)
                    if abs(q.X - (x0 + ft(p[0]))) > TOLL * 2 or abs(q.Z - (z0 + ft(p[1]))) > TOLL * 2:
                        simboli_fuori += 1
                        self.report[u"linee_fuori"].append(u"%s-%s estremo %d" % (
                            _seg[u"p0"], _seg[u"p1"], i))
                        break
            # contorno: x e z come da geometria
            pos2 = dict((p[u"id"], p[u"pos"]) for p in ris2[u"piani"])
            for (ext, e), e2 in zip(self.contorno, ris2[u"contorno"]):
                bb = ext.get_BoundingBox(None)
                x = sorted(pos2[k] for k in e2[u"x"])
                z = sorted(pos2[k] for k in e2[u"z"])
                if bb is None or max(abs(bb.Min.X - (x0 + ft(x[0]))), abs(bb.Max.X - (x0 + ft(x[1]))),
                                     abs(bb.Min.Z - (z0 + ft(z[0]))), abs(bb.Max.Z - (z0 + ft(z[1])))) > TOLL * 2:
                    pezzi_fuori += 1
                    self.report[u"linee_fuori"].append(e[u"nome"])
            self.report[u"pezzi_fuori"] = pezzi_fuori
            self.report[u"simboli_fuori"] = simboli_fuori
        except Exception as ex:
            self.report[u"flex"] = u"%s" % ex
        finally:
            st.RollBack()


def _facce(elemento, opt):
    for g in elemento.get_Geometry(opt):
        if isinstance(g, DB.Solid):
            for f in g.Faces:
                if isinstance(f, DB.PlanarFace):
                    yield f
        elif isinstance(g, DB.GeometryInstance):
            for g2 in g.GetInstanceGeometry():
                if isinstance(g2, DB.Solid):
                    for f in g2.Faces:
                        if isinstance(f, DB.PlanarFace):
                            yield f


# --- ingresso -------------------------------------------------------------------------
def crea_famiglia(app, modello, schema, percorso_rfa, tipi=None):
    """Crea e salva la famiglia; ritorna (documento famiglia aperto, report).

    tipi: [(nome tipo, schema)] con la stessa struttura; il primo e' quello corrente.
    In caso di errore il documento famiglia viene chiuso e l'errore rilanciato.
    """
    tipi = tipi or [(S.nome_tipo(schema), schema)]
    famdoc = app.NewFamilyDocument(modello)
    if famdoc is None:
        raise FamigliaErrore(u"Non riesco ad aprire il modello famiglia:\n%s" % modello)
    try:
        t = DB.Transaction(famdoc, u"CDV infisso")
        errori = _Errori()
        opz = t.GetFailureHandlingOptions()
        opz.SetFailuresPreprocessor(errori)
        opz.SetClearAfterRollback(True)
        t.SetFailureHandlingOptions(opz)
        t.Start()
        costruttore = None
        try:
            costruttore = _Costruttore(famdoc, schema)
            report = costruttore.esegui(tipi)
            esito = t.Commit()
        except Exception:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            raise
        if esito != DB.TransactionStatus.Committed:
            testo = u"Revit non accetta la famiglia: %s" % (u"; ".join(errori.messaggi)
                                                            or u"motivo sconosciuto")
            if errori.elementi and costruttore is not None:
                testo += u"\nElementi coinvolti: %s" % u", ".join(
                    costruttore.spiega(errori.elementi)[:16])
            raise FamigliaErrore(testo)
        report[u"revit"] = list(errori.messaggi)
        opzioni = DB.SaveAsOptions()
        opzioni.OverwriteExistingFile = True
        famdoc.SaveAs(percorso_rfa, opzioni)
        return famdoc, report
    except Exception:
        famdoc.Close(False)
        raise


def carica(doc, famdoc):
    """Carica (o ricarica sovrascrivendo) la famiglia nel progetto e chiude il documento famiglia."""
    try:
        return famdoc.LoadFamily(doc, OpzioniCaricamento())
    finally:
        famdoc.Close(False)


def problemi(report):
    """Righe di testo dei problemi trovati (vuoto = tutto a posto)."""
    righe = []
    if report.get(u"quote"):
        righe.append(u"%d quote non etichettate" % report[u"quote"])
    if report.get(u"allineamenti"):
        righe.append(u"%d facce non bloccate ai piani" % report[u"allineamenti"])
    if report.get(u"simboli"):
        righe.append(u"%d linee di apertura non bloccate" % report[u"simboli"])
    if report.get(u"pezzi_fuori"):
        righe.append(u"prova flessione: %d pezzi non seguono le misure" % report[u"pezzi_fuori"])
    if report.get(u"simboli_fuori"):
        righe.append(u"prova flessione: %d linee di apertura non seguono le misure"
                     % report[u"simboli_fuori"])
    if report.get(u"flex"):
        righe.append(u"prova flessione non riuscita: %s" % report[u"flex"])
    if report.get(u"pianta"):
        righe.append(u"%d linee in pianta non create o non bloccate" % report[u"pianta"])
    if report.get(u"aperte"):
        righe.append(u"%d pezzi delle ante aperte non creati o non bloccati" % report[u"aperte"])
    if report.get(u"formule"):
        righe.append(u"formule non accettate da Revit: %s" % u", ".join(report[u"formule"]))
    if report.get(u"revit"):
        righe.append(u"Revit ha tolto dei vincoli in conflitto: %s" % u"; ".join(report[u"revit"][:3]))
    if report.get(u"visibilita"):
        righe.append(u"%d pezzi senza visibilità per dettaglio o apertura" % report[u"visibilita"])
    if report.get(u"contorno"):
        righe.append(u"%d elementi del contorno non creati" % report[u"contorno"])
    return righe


# --- lettura dal progetto (Modifica infisso) ----------------------------------------------
def schema_del_tipo(tipo):
    """Schema salvato nel tipo (FamilySymbol), aggiornato con i valori attuali del tipo; None se non e' CDV."""
    p = tipo.LookupParameter(PA.SCHEMA)
    if p is None or not p.AsString():
        return None
    schema = S.from_json(p.AsString())
    valori = {}
    for nomi_bip, chiave in ((_BIP_LARGHEZZA, G.LARGHEZZA), (_BIP_ALTEZZA, G.ALTEZZA)):
        for n in nomi_bip:
            bip = getattr(DB.BuiltInParameter, n, None)
            q = tipo.get_Parameter(bip) if bip is not None else None
            if q is not None and q.HasValue:
                valori[chiave] = q.AsDouble() / MM
                break
    nomi = [e for _k, e, _v, _m in S.PROFILI] + [e for _k, e, _v, _m in S.MISURE_CONTORNO]
    for _perc, div in S.divisioni(schema[u"radice"]):
        for i in range(len(div[u"figli"]) - 1):
            nomi.append(G.nome_misura(div[u"verso"], tuple(_perc) + (i,)))
    for n in nomi:
        q = tipo.LookupParameter(n)
        if q is not None and q.HasValue and q.StorageType == DB.StorageType.Double:
            valori[n] = q.AsDouble() / MM
    return PA.schema_da_valori(schema, valori)
