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
class _SoloAvvisi(DB.IFailuresPreprocessor):
    """Toglie gli avvisi (non gli errori) mentre si costruisce la famiglia."""

    def PreprocessFailures(self, accessor):
        for f in accessor.GetFailureMessages():
            if f.GetSeverity() == DB.FailureSeverity.Warning:
                accessor.DeleteWarning(f)
        return DB.FailureProcessingResult.Continue


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


def _visibilita(elemento, dettaglio, modello=True, pianta=True):
    """Livelli di dettaglio (e pianta si'/no) in cui l'elemento della famiglia si vede."""
    try:
        tipo = DB.FamilyElementVisibilityType.Model if modello else DB.FamilyElementVisibilityType.ViewSpecific
        vis = DB.FamilyElementVisibility(tipo)
        vis.IsShownInCoarse = G.BASSO in dettaglio
        vis.IsShownInMedium = G.MEDIO in dettaglio
        vis.IsShownInFine = G.ALTO in dettaglio
        if modello:
            vis.IsShownInPlanRCP = pianta
        elemento.SetVisibility(vis)
        return True
    except Exception:
        return False


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
    if cv is None or co is None:
        raise FamigliaErrore(u"Nel modello famiglia non trovo i piani di riferimento di "
                             u"larghezza e altezza.")
    out = {u"sx": cv[1], u"dx": cv[2], u"basso": co[1], u"alto": co[2], u"centro": None}
    for y, rp in front:
        if abs(y) < TOLL:
            out[u"centro"] = rp
    return out


# --- costruzione ------------------------------------------------------------------------
class _Costruttore(object):
    def __init__(self, famdoc, schema):
        self.doc = famdoc
        self.crea = famdoc.FamilyCreate
        self.fm = famdoc.FamilyManager
        self.schema = schema
        self.ris = G.calcola(schema)
        if self.ris[u"errori"]:
            raise FamigliaErrore(u"\n".join(self.ris[u"errori"]))
        self.parametri = PA.elenco(schema, self.ris)
        self.report = {u"quote": 0, u"allineamenti": 0, u"simboli": 0, u"flex": u"",
                       u"pianta": 0, u"aperte": 0, u"visibilita": 0}
        self.fp = {}
        self.rp = {}
        self.estrusioni = []
        self.simboli = []
        self.estrusioni_aperte = []
        self.pianta = None

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
        bordi = _piani_modello(self.doc, ft(self.schema[u"larghezza"]), ft(self.schema[u"altezza"]))
        for k in G.RADICI:
            self.rp[k] = bordi[k]
        self.x0 = bordi[u"sx"].BubbleEnd.X
        self.z0 = bordi[u"basso"].BubbleEnd.Z
        self.y0 = 0.0
        if bordi[u"centro"] is not None:
            self.piano_schizzo = DB.SketchPlane.Create(self.doc, bordi[u"centro"].Id)
        else:
            self.piano_schizzo = DB.SketchPlane.Create(
                self.doc, DB.Plane.CreateByNormalAndOrigin(DB.XYZ.BasisY, DB.XYZ.Zero))

        self._parametri()
        self._piani()
        self._estrusioni()
        self.doc.Regenerate()
        self._allinea()
        self._simboli()
        self._pianta_e_aperte(bordi[u"centro"])
        self._tipi(tipi)
        self._flex()
        return self.report

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
            if p[u"formula"]:
                if p[u"tipo"] == PA.SINO:
                    fm.SetFormula(self.fp[p[u"nome"]], p[u"formula"])     # es. not(Aperta in 3D)
                else:
                    fm.SetFormula(self.fp[p[u"nome"]], PA.rinomina(p[u"formula"], mappa, nomi))

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
            return True
        except Exception:
            self.report[u"quote"] += 1
            return False

    def _piani(self):
        L, H = ft(self.schema[u"larghezza"]), ft(self.schema[u"altezza"])
        sporgenza = ft(300)
        livello_quote = {u"v": self.Z(self.schema[u"altezza"]) + ft(400),
                         u"o": self.X(self.schema[u"larghezza"]) + ft(400)}
        passo = ft(60)
        for i, p in enumerate(self.ris[u"piani"]):
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
        if not _visibilita(ext, pz.get(u"dettaglio", G.TUTTI), pianta=pianta):
            self.report[u"visibilita"] += 1
        nome = {u"chiusa": G.CHIUSA, u"aperta": G.APERTA}.get(pz.get(u"stato"))
        if nome and nome in self.fp:
            try:
                self.fm.AssociateElementParameterToFamilyParameter(
                    ext.get_Parameter(DB.BuiltInParameter.IS_VISIBLE_PARAM), self.fp[nome])
            except Exception:
                self.report[u"visibilita"] += 1

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
                curva = self.crea.NewSymbolicCurve(linea, self.piano_schizzo)
                if stile is not None:
                    try:
                        curva.Subcategory = stile
                    except Exception:
                        pass
                self.simboli.append((curva, seg))
                self._blocca_simbolo(curva, seg)

    def _blocca_simbolo(self, curva, seg):
        """Quota ogni estremo (x e z) dal suo piano base con il suo parametro."""
        ok = True
        cx0, cz0, cx1, cz1 = seg[u"coord"]
        for indice, punto, cx, cz in ((0, seg[u"p0"], cx0, cz0), (1, seg[u"p1"], cx1, cz1)):
            try:
                rif_estremo = curva.GeometryCurve.GetEndPointReference(indice)
            except Exception:
                rif_estremo = None
            if rif_estremo is None:
                ok = False
                continue
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
                    ok = False
        if not ok:
            self.report[u"simboli"] += 1

    # --- pianta e ante aperte --------------------------------------------------------------
    def Y(self, mm):
        return self.yc + ft(mm)

    def _pianta_e_aperte(self, centro):
        """Piani paralleli al muro, simboli in pianta e ante aperte (dove serve)."""
        if not self.ris[u"pianta"] and not self.ris[u"pezzi_aperti"]:
            return
        self.pianta = _vista_pianta(self.doc)
        if self.pianta is None or centro is None:
            self.report[u"pianta"] += len(self.ris[u"pianta"])
            self.report[u"aperte"] += len(self.ris[u"pezzi_aperti"])
            return
        self.yc = centro.BubbleEnd.Y
        self.rp[u"centro"] = centro
        self._piani_y()
        self._simboli_pianta()
        self._aperte()

    def _piani_y(self):
        L = ft(self.schema[u"larghezza"])
        sporg = ft(300)
        x_quote = self.X(self.schema[u"larghezza"]) + ft(400)
        for i, p in enumerate(self.ris[u"piani_y"]):
            if p[u"base"] is None:
                continue
            y = self.Y(p[u"pos"])
            rp = self.crea.NewReferencePlane(DB.XYZ(self.x0 - sporg, y, self.z0),
                                             DB.XYZ(self.x0 + L + sporg, y, self.z0),
                                             DB.XYZ.BasisZ, self.pianta)
            try:
                rp.Name = u"CDV %s" % p[u"id"]
            except Exception:
                pass
            self.rp[p[u"id"]] = rp
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
        piano = self._piano_orizzontale()
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
        for simb in self.ris[u"pianta"]:
            stile = stili.get(SOTTOCATEGORIA_PIANTA[simb[u"stile"]])
            for seg in simb[u"segmenti"]:
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
                if not self._blocca_pianta(curva, seg):
                    self.report[u"pianta"] += 1

    def _blocca_pianta(self, curva, seg):
        """Quota ogni estremo: x da un piano x, y da un piano parallelo al muro (in pianta)."""
        ok = True
        cx0, cy0, cx1, cy1 = seg[u"coord"]
        tutti = dict((p[u"id"], p[u"pos"]) for p in self.ris[u"piani"])
        tutti_y = dict((p[u"id"], p[u"pos"]) for p in self.ris[u"piani_y"])
        for indice, punto, cx, cy in ((0, seg[u"p0"], cx0, cy0), (1, seg[u"p1"], cx1, cy1)):
            try:
                rif = curva.GeometryCurve.GetEndPointReference(indice)
            except Exception:
                rif = None
            if rif is None:
                ok = False
                continue
            for (pid, param, _segno), verso in ((cx, u"x"), (cy, u"y")):
                if verso == u"x":
                    xb, y = self.X(tutti[pid]), self.Y(punto[1])
                    linea = DB.Line.CreateBound(DB.XYZ(xb, y, self.z0), DB.XYZ(self.X(punto[0]), y, self.z0))
                else:
                    x, yb = self.X(punto[0]), self.Y(tutti_y[pid])
                    linea = DB.Line.CreateBound(DB.XYZ(x, yb, self.z0), DB.XYZ(x, self.Y(punto[1]), self.z0))
                if not self._quota(self.rp[pid].GetReference(), rif, linea, param, self.pianta):
                    ok = False
        return ok

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
                # in pianta valgono i simboli: l'anta aperta si vede in 3D, prospetti e sezioni
                self._visibile(ext, pz, pianta=False)
                self.estrusioni_aperte.append((ext, pz))
            except Exception:
                self.report[u"aperte"] += 1
        self.doc.Regenerate()
        self._allinea_aperte()

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
        ris2 = G.calcola(s2)
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
                        break
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
        opz = t.GetFailureHandlingOptions()
        opz.SetFailuresPreprocessor(_SoloAvvisi())
        t.SetFailureHandlingOptions(opz)
        t.Start()
        try:
            report = _Costruttore(famdoc, schema).esegui(tipi)
            t.Commit()
        except Exception:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            raise
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
    if report.get(u"visibilita"):
        righe.append(u"%d pezzi senza visibilità per dettaglio o apertura" % report[u"visibilita"])
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
    nomi = [e for _k, e, _v, _m in S.PROFILI]
    for _perc, div in S.divisioni(schema[u"radice"]):
        for i in range(len(div[u"figli"]) - 1):
            nomi.append(G.nome_misura(div[u"verso"], tuple(_perc) + (i,)))
    for n in nomi:
        q = tipo.LookupParameter(n)
        if q is not None and q.HasValue and q.StorageType == DB.StorageType.Double:
            valori[n] = q.AsDouble() / MM
    return PA.schema_da_valori(schema, valori)
