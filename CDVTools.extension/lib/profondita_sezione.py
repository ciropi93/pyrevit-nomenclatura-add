# -*- coding: utf-8 -*-
"""Gestione della profondita' di sezione vettoriale (primo piano + sfondo grigio/halftone).

Replica l'Area distante marcata di ArchiCAD in 100% vettoriale tramite una seconda
sezione collegata che parte esattamente alla fine della sezione madre (d1) e si
estende fino a d2, con linee grigie/mezzitoni e sincronizzazione automatica nel
modello e sulle tavole.
"""
import json
import math

try:
    from System import Guid
    from Autodesk.Revit import DB
except ImportError:
    Guid = None
    DB = None


METRI_PER_PIEDE = 0.3048
SUFFISSO_SFONDO = u" (Sfondo)"
SCHEMA_NAME = "CDVSectionDepthJson"
SCHEMA_GUID_STR = "8C5E0D32-6B9F-4A20-8F43-D9E2B3C4F5A6"


# ==============================================================================
# FUNZIONI PURE (senza API Revit, testabili con pytest)
# ==============================================================================

def _id_val(eid):
    if eid is None:
        return -1
    return getattr(eid, "Value", getattr(eid, "IntegerValue", -1))


def metri_a_piedi(metri):
    return float(metri) / METRI_PER_PIEDE


def piedi_a_metri(piedi):
    return float(piedi) * METRI_PER_PIEDE


def calcola_profondita_sfondo(d1_m, valore_m, modalita=u"totale"):
    """Calcola (spessore_sfondo_m, profondita_totale_m) a partire da d1_m.

    modalita:
      - "totale": valore_m e' d2 (distanza totale dal piano della sezione madre)
      - "aggiuntiva": valore_m e' delta (estensione oltre d1)
    """
    d1 = float(d1_m)
    val = float(valore_m)
    if modalita == u"totale":
        spessore = val - d1
        totale = val
        if spessore <= 1e-4:
            raise ValueError(
                u"La profondita' totale dello sfondo (%.2f m) deve essere maggiore "
                u"della profondita' della sezione madre (%.2f m)." % (val, d1)
            )
    elif modalita == u"aggiuntiva":
        spessore = val
        totale = d1 + val
        if spessore <= 1e-4:
            raise ValueError(u"L'estensione aggiuntiva dello sfondo deve essere maggiore di zero.")
    else:
        raise ValueError(u"Modalita' profondita' non valida: %s" % modalita)
    return spessore, totale


def origine_piano_sfondo(origine, dir_vista, offset_d1_ft):
    """Origine del piano di taglio dello sfondo (spostato indietro di d1 lungo -ViewDirection)."""
    ox, oy, oz = float(origine[0]), float(origine[1]), float(origine[2])
    vx, vy, vz = float(dir_vista[0]), float(dir_vista[1]), float(dir_vista[2])
    d = float(offset_d1_ft)
    return (ox - d * vx, oy - d * vy, oz - d * vz)


def angolo_rotazione_xy(dir_attuale, dir_target):
    """Angolo firmato in radianti nel piano XY da dir_attuale a dir_target."""
    ax, ay = float(dir_attuale[0]), float(dir_attuale[1])
    tx, ty = float(dir_target[0]), float(dir_target[1])
    la = math.hypot(ax, ay)
    lt = math.hypot(tx, ty)
    if la < 1e-9 or lt < 1e-9:
        return 0.0
    ax, ay = ax / la, ay / la
    tx, ty = tx / lt, ty / lt
    return math.atan2(ax * ty - ay * tx, ax * tx + ay * ty)


def nome_vista_sfondo(nome_madre, suffisso=SUFFISSO_SFONDO):
    """Restituisce il nome della vista di sfondo evitando duplicazioni del suffisso."""
    base = nome_madre or u"Sezione"
    if base.endswith(suffisso):
        return base
    return base + suffisso


# ==============================================================================
# METADATI EXTENSIBLE STORAGE
# ==============================================================================

def _get_schema():
    if DB is None or Guid is None:
        return None
    guid = Guid(SCHEMA_GUID_STR)
    schema = DB.ExtensibleStorage.Schema.Lookup(guid)
    if schema is not None:
        return schema
    sb = DB.ExtensibleStorage.SchemaBuilder(guid)
    sb.SetSchemaName(SCHEMA_NAME)
    sb.SetReadAccessLevel(DB.ExtensibleStorage.AccessLevel.Public)
    sb.SetWriteAccessLevel(DB.ExtensibleStorage.AccessLevel.Public)
    sb.AddSimpleField("ConfigJson", str)
    return sb.Finish()


def salva_config_sfondo(vista_sfondo, cfg):
    """Salva la configurazione di collegamento e grafica sulla vista di sfondo."""
    schema = _get_schema()
    if schema is None:
        return
    payload = {
        "source_uid": u"%s" % cfg.get("source_uid", u""),
        "modalita": u"%s" % cfg.get("modalita", u"totale"),
        "valore_m": float(cfg.get("valore_m", 15.0)),
        "halftone": bool(cfg.get("halftone", True)),
        "grigio": bool(cfg.get("grigio", True)),
        "grigio_rgb": int(cfg.get("grigio_rgb", 140)),
        "nascondi_retini": bool(cfg.get("nascondi_retini", True)),
    }
    ent = DB.ExtensibleStorage.Entity(schema)
    ent.Set("ConfigJson", u"%s" % json.dumps(payload, ensure_ascii=True))
    vista_sfondo.SetEntity(ent)


def leggi_config_sfondo(vista_sfondo):
    """Legge la configurazione salvata sulla vista di sfondo, oppure None."""
    schema = _get_schema()
    if schema is None:
        return None
    ent = vista_sfondo.GetEntity(schema)
    if ent is None or not ent.IsValid():
        return None
    raw = ent.Get[str]("ConfigJson")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    return {
        "source_uid": data.get("source_uid", u""),
        "modalita": data.get("modalita") or u"totale",
        "valore_m": float(data.get("valore_m", 15.0)),
        "halftone": bool(data.get("halftone", True)),
        "grigio": bool(data.get("grigio", True)),
        "grigio_rgb": int(data.get("grigio_rgb", 140)),
        "nascondi_retini": bool(data.get("nascondi_retini", True)),
    }


# ==============================================================================
# RICERCA E LETTURA SEZIONI
# ==============================================================================

def e_vista_supportata(vista):
    if vista is None or vista.IsTemplate:
        return False
    return vista.ViewType in (DB.ViewType.Section, DB.ViewType.Elevation)


def profondita_madre_piedi(vista_madre):
    """Legge il Far Clip Offset (d1) della sezione madre verificando che sia attivo."""
    p_clip = vista_madre.get_Parameter(DB.BuiltInParameter.VIEWER_BOUND_FAR_CLIPPING)
    if p_clip is not None and p_clip.AsInteger() == 0:
        raise ValueError(
            u"La vista '%s' non ha il ritaglio lontano attivo (Far Clipping).\n"
            u"Imposta prima una profondita' sulla sezione madre." % vista_madre.Name
        )
    p_far = vista_madre.get_Parameter(DB.BuiltInParameter.VIEWER_BOUND_OFFSET_FAR)
    if p_far is None:
        raise ValueError(u"La vista '%s' non supporta l'offset di ritaglio lontano." % vista_madre.Name)
    d1_ft = p_far.AsDouble()
    if d1_ft <= 1e-4:
        raise ValueError(
            u"La profondita' della vista '%s' e' nulla. Imposta una profondita' maggiore di 0."
            % vista_madre.Name
        )
    return d1_ft


def trova_coppie_sezioni(doc):
    """Restituisce (coppie, mappa_madre_a_sfondo, mappa_sfondo_a_madre).

    coppie: lista di dict {"madre": View, "sfondo": View, "cfg": dict}
    """
    viste = [
        v for v in DB.FilteredElementCollector(doc).OfClass(DB.View).ToElements()
        if e_vista_supportata(v)
    ]
    by_uid = dict((v.UniqueId, v) for v in viste)
    by_name = dict((v.Name, v) for v in viste)

    coppie = []
    madre_to_sfondo = {}
    sfondo_to_madre = {}

    for v in viste:
        cfg = leggi_config_sfondo(v)
        madre = None
        if cfg and cfg.get("source_uid"):
            madre = by_uid.get(cfg["source_uid"])
        if madre is None and v.Name.endswith(SUFFISSO_SFONDO):
            nome_base = v.Name[:-len(SUFFISSO_SFONDO)]
            madre = by_name.get(nome_base)
            if cfg is None and madre is not None:
                d1_m = piedi_a_metri(
                    madre.get_Parameter(DB.BuiltInParameter.VIEWER_BOUND_OFFSET_FAR).AsDouble()
                )
                d_sf_m = piedi_a_metri(
                    v.get_Parameter(DB.BuiltInParameter.VIEWER_BOUND_OFFSET_FAR).AsDouble()
                )
                cfg = {
                    "source_uid": madre.UniqueId,
                    "modalita": u"totale",
                    "valore_m": round(d1_m + max(d_sf_m, 1.0), 3),
                    "halftone": True,
                    "grigio": True,
                    "grigio_rgb": 140,
                    "nascondi_retini": True,
                }
        if madre is not None and _id_val(madre.Id) != _id_val(v.Id):
            coppie.append({"madre": madre, "sfondo": v, "cfg": cfg})
            madre_to_sfondo[_id_val(madre.Id)] = v
            sfondo_to_madre[_id_val(v.Id)] = madre

    return coppie, madre_to_sfondo, sfondo_to_madre


def _trova_viewer(doc, vista):
    """Trova l'elemento OST_Viewers associato alla vista di sezione/prospetto."""
    try:
        filtro = DB.ElementCategoryFilter(DB.BuiltInCategory.OST_Viewers)
        deps = list(vista.GetDependentElements(filtro))
        for eid in deps:
            el = doc.GetElement(eid)
            if el is not None and el.Name == vista.Name:
                return eid
        if deps:
            return deps[0]
    except Exception:
        pass
    col = DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Viewers).ToElements()
    for el in col:
        if el.Name == vista.Name:
            return el.Id
    return None


# ==============================================================================
# SINCRONIZZAZIONE VISTA E GRAFICA
# ==============================================================================

def _copia_parametro_se_possibile(src, dst, bip):
    ps = src.get_Parameter(bip)
    pd = dst.get_Parameter(bip)
    if ps is None or pd is None or pd.IsReadOnly:
        return
    st = ps.StorageType
    if st == DB.StorageType.ElementId:
        pd.Set(ps.AsElementId())
    elif st == DB.StorageType.Integer:
        pd.Set(ps.AsInteger())
    elif st == DB.StorageType.Double:
        pd.Set(ps.AsDouble())
    elif st == DB.StorageType.String:
        pd.Set(ps.AsString() or u"")


def _applica_grafica_sfondo(doc, vista_madre, vista_sfondo, cfg):
    """Copia visibilita' categorie/filtri dalla madre e applica mezzitoni/grigio."""
    vista_sfondo.AreAnnotationCategoriesHidden = True

    # Copia filtri
    for fid in list(vista_sfondo.GetFilters()):
        try:
            vista_sfondo.RemoveFilter(fid)
        except Exception:
            pass
    for fid in list(vista_madre.GetFilters()):
        try:
            vista_sfondo.AddFilter(fid)
            vista_sfondo.SetFilterVisibility(fid, vista_madre.GetFilterVisibility(fid))
        except Exception:
            pass

    use_halftone = bool(cfg.get("halftone", True))
    use_grey = bool(cfg.get("grigio", True))
    g_val = max(0, min(255, int(cfg.get("grigio_rgb", 140))))
    hide_cut = bool(cfg.get("nascondi_retini", True))

    ogs = DB.OverrideGraphicSettings()
    ogs.SetHalftone(use_halftone)
    if use_grey:
        colore = DB.Color(g_val, g_val, g_val)
        ogs.SetProjectionLineColor(colore)
        ogs.SetProjectionLineWeight(1)
        ogs.SetCutLineColor(colore)
        ogs.SetCutLineWeight(1)
    if hide_cut:
        ogs.SetCutForegroundPatternVisible(False)
        ogs.SetCutBackgroundPatternVisible(False)
        ogs.SetSurfaceForegroundPatternVisible(False)
        ogs.SetSurfaceBackgroundPatternVisible(False)

    for cat in doc.Settings.Categories:
        if cat is None or cat.CategoryType != DB.CategoryType.Model:
            continue
        cid = cat.Id
        try:
            if vista_madre.CanCategoryBeHidden(cid) and vista_sfondo.CanCategoryBeHidden(cid):
                vista_sfondo.SetCategoryHidden(cid, vista_madre.GetCategoryHidden(cid))
        except Exception:
            pass
        try:
            vista_sfondo.SetCategoryOverrides(cid, ogs)
        except Exception:
            pass

    # Riallinea i modelli collegati (Revit Link) alle sostituzioni della vista ospite
    for link_inst in DB.FilteredElementCollector(doc).OfClass(DB.RevitLinkInstance).ToElements():
        if hasattr(vista_sfondo, "GetLinkOverrides"):
            for target_id in (link_inst.Id, link_inst.GetTypeId()):
                try:
                    lo = vista_sfondo.GetLinkOverrides(target_id)
                    if lo is not None and lo.LinkVisibilityType == DB.LinkVisibility.Custom:
                        lo.LinkedViewId = DB.ElementId.InvalidElementId
                        lo.ObjectStyles = DB.LinkVisibility.ByHostView
                        vista_sfondo.SetLinkOverrides(target_id, lo)
                except Exception:
                    pass
        try:
            vista_sfondo.SetElementOverrides(link_inst.Id, ogs)
        except Exception:
            pass


def _copia_ritaglio(doc, vista_madre, vista_sfondo, spessore_ft):
    """Allinea CropBox e eventuale forma sagomata (CurveLoop) dalla madre allo sfondo."""
    scope_p = vista_sfondo.get_Parameter(DB.BuiltInParameter.VIEWER_VOLUME_OF_INTEREST_CROP)
    if scope_p is not None and not scope_p.IsReadOnly and scope_p.AsElementId() != DB.ElementId.InvalidElementId:
        scope_p.Set(DB.ElementId.InvalidElementId)
        doc.Regenerate()

    vista_sfondo.CropBoxActive = True
    doc.Regenerate()

    src_mgr = vista_madre.GetCropRegionShapeManager()
    tgt_mgr = vista_sfondo.GetCropRegionShapeManager()

    if src_mgr.CanHaveShape and src_mgr.ShapeSet:
        shapes = src_mgr.GetCropShape()
        if shapes and shapes.Count > 0:
            delta = vista_sfondo.Origin - vista_madre.Origin
            trans = DB.Transform.CreateTranslation(delta)
            tgt_loop = DB.CurveLoop()
            for c in shapes[0]:
                tgt_loop.Append(c.CreateTransformed(trans))
            if tgt_mgr.IsCropRegionShapeValid(tgt_loop):
                tgt_mgr.SetCropShape(tgt_loop)
                doc.Regenerate()
    else:
        if tgt_mgr.CanHaveShape and tgt_mgr.ShapeSet:
            tgt_mgr.RemoveCropRegionShape()
            doc.Regenerate()

        src_box = vista_madre.CropBox
        tgt_box = vista_sfondo.CropBox
        tgt_inv = tgt_box.Transform.Inverse
        p_min = tgt_inv.OfPoint(src_box.Transform.OfPoint(src_box.Min))
        p_max = tgt_inv.OfPoint(src_box.Transform.OfPoint(src_box.Max))
        new_box = DB.BoundingBoxXYZ()
        new_box.Transform = tgt_box.Transform
        new_box.Min = DB.XYZ(min(p_min.X, p_max.X), min(p_min.Y, p_max.Y), -float(spessore_ft))
        new_box.Max = DB.XYZ(max(p_min.X, p_max.X), max(p_min.Y, p_max.Y), 0.0)
        vista_sfondo.CropBox = new_box
        doc.Regenerate()

    vista_sfondo.CropBoxActive = vista_madre.CropBoxActive
    vista_sfondo.CropBoxVisible = False


def sincronizza_vista_sfondo(doc, vista_madre, vista_sfondo, cfg):
    """Sincronizza piano di taglio, profondita', ritaglio e grafica dello sfondo."""
    d1_ft = profondita_madre_piedi(vista_madre)
    d1_m = piedi_a_metri(d1_ft)
    spessore_m, _ = calcola_profondita_sfondo(
        d1_m, cfg.get("valore_m", d1_m + 10.0), cfg.get("modalita", u"totale")
    )
    spessore_ft = metri_a_piedi(spessore_m)

    # Sgancia eventuale ViewTemplate sullo sfondo per poter gestire grafica e profondita'
    if vista_sfondo.ViewTemplateId != DB.ElementId.InvalidElementId:
        vista_sfondo.ViewTemplateId = DB.ElementId.InvalidElementId

    # Nome sincronizzato con quello della madre
    nome_desiderato = nome_vista_sfondo(vista_madre.Name)
    if vista_sfondo.Name != nome_desiderato:
        try:
            vista_sfondo.Name = nome_desiderato
        except Exception:
            pass

    # Copia impostazioni base vista
    vista_sfondo.Scale = vista_madre.Scale
    try:
        vista_sfondo.DetailLevel = vista_madre.DetailLevel
    except Exception:
        pass
    # Stile di visualizzazione sempre Linea Nascosta (100% vettoriale, niente ombreggiature materiali)
    try:
        vista_sfondo.DisplayStyle = DB.DisplayStyle.HLR
    except Exception:
        pass
    _copia_parametro_se_possibile(vista_madre, vista_sfondo, DB.BuiltInParameter.VIEW_PHASE)
    _copia_parametro_se_possibile(vista_madre, vista_sfondo, DB.BuiltInParameter.VIEW_PHASE_FILTER)

    # Nasconde simbolo di sezione in tutte le piante (scala piu' grossolana di 1:1)
    p_hide = vista_sfondo.get_Parameter(DB.BuiltInParameter.SECTION_COARSER_SCALE_PULLDOWN_METRIC)
    if p_hide is not None and not p_hide.IsReadOnly:
        p_hide.Set(1)
    doc.Regenerate()

    # Riallinea posizione e rotazione del piano di taglio rispetto alla madre
    viewer_id = _trova_viewer(doc, vista_sfondo)
    if viewer_id is None:
        raise ValueError(u"Impossibile trovare la linea di sezione per '%s'." % vista_sfondo.Name)

    # Allarga temporaneamente il Far Clipping per evitare che il piano di taglio
    # superi il proprio piano lontano durante lo spostamento del viewer
    p_fc = vista_sfondo.get_Parameter(DB.BuiltInParameter.VIEWER_BOUND_FAR_CLIPPING)
    if p_fc is not None and not p_fc.IsReadOnly:
        p_fc.Set(2)
    p_fo = vista_sfondo.get_Parameter(DB.BuiltInParameter.VIEWER_BOUND_OFFSET_FAR)
    if p_fo is not None and not p_fo.IsReadOnly:
        p_fo.Set(d1_ft + spessore_ft)
    doc.Regenerate()

    ang = angolo_rotazione_xy(
        (vista_sfondo.ViewDirection.X, vista_sfondo.ViewDirection.Y),
        (vista_madre.ViewDirection.X, vista_madre.ViewDirection.Y),
    )
    if abs(ang) > 1e-6:
        o_sf = vista_sfondo.Origin
        asse = DB.Line.CreateBound(o_sf, DB.XYZ(o_sf.X, o_sf.Y, o_sf.Z + 10.0))
        DB.ElementTransformUtils.RotateElement(doc, viewer_id, asse, ang)
        doc.Regenerate()

    ox, oy, oz = origine_piano_sfondo(
        (vista_madre.Origin.X, vista_madre.Origin.Y, vista_madre.Origin.Z),
        (vista_madre.ViewDirection.X, vista_madre.ViewDirection.Y, vista_madre.ViewDirection.Z),
        d1_ft,
    )
    o_target = DB.XYZ(ox, oy, oz)
    delta = o_target - vista_sfondo.Origin
    if delta.GetLength() > 1e-6:
        DB.ElementTransformUtils.MoveElement(doc, viewer_id, delta)
        doc.Regenerate()

    # Imposta spessore definitivo dello sfondo
    if p_fo is not None and not p_fo.IsReadOnly:
        p_fo.Set(spessore_ft)
    doc.Regenerate()

    _copia_ritaglio(doc, vista_madre, vista_sfondo, spessore_ft)
    _applica_grafica_sfondo(doc, vista_madre, vista_sfondo, cfg)

    cfg_save = dict(cfg)
    cfg_save["source_uid"] = vista_madre.UniqueId
    salva_config_sfondo(vista_sfondo, cfg_save)


# ==============================================================================
# SINCRONIZZAZIONE IN TAVOLA
# ==============================================================================

def _trova_tipo_viewport_senza_titolo(doc, tipo_base_id):
    """Restituisce un Viewport Type senza etichetta titolo, creandolo se serve."""
    for vpt in DB.FilteredElementCollector(doc).OfClass(DB.ElementType).ToElements():
        if vpt.FamilyName in (u"Finestra", u"Viewport") or (
            vpt.Category and _id_val(vpt.Category.Id) == int(DB.BuiltInCategory.OST_Viewports)
        ):
            p_lbl = vpt.get_Parameter(DB.BuiltInParameter.VIEWPORT_ATTR_SHOW_LABEL)
            if p_lbl is not None and p_lbl.AsInteger() == 0:
                return vpt.Id

    tipo_base = doc.GetElement(tipo_base_id)
    if tipo_base is None:
        return tipo_base_id
    try:
        nuovo = tipo_base.Duplicate(u"Senza Titolo (Sfondo)")
        p_lbl = nuovo.get_Parameter(DB.BuiltInParameter.VIEWPORT_ATTR_SHOW_LABEL)
        if p_lbl is not None and not p_lbl.IsReadOnly:
            p_lbl.Set(0)
        return nuovo.Id
    except Exception:
        return tipo_base_id


def _centro_puro_viewport(doc, vista_madre, vp_madre):
    """Centro sul foglio del solo ritaglio modello (ignorando annotazioni sporgenti)."""
    st = DB.SubTransaction(doc)
    st.Start()
    try:
        if vista_madre.ViewTemplateId != DB.ElementId.InvalidElementId:
            vista_madre.ViewTemplateId = DB.ElementId.InvalidElementId
        vista_madre.AreAnnotationCategoriesHidden = True
        vista_madre.CropBoxVisible = False
        doc.Regenerate()
        centro = vp_madre.GetBoxCenter()
    finally:
        st.RollBack()
    return centro


def _porta_sopra_madre(doc, sheet, vp_madre, vp_sfondo):
    """Assicura che vp_madre abbia ElementId maggiore (disegnata sopra vp_sfondo)."""
    if _id_val(vp_madre.Id) > _id_val(vp_sfondo.Id):
        return vp_madre

    centro = vp_madre.GetBoxCenter()
    tipo_id = vp_madre.GetTypeId()
    lbl_off = vp_madre.LabelOffset
    lbl_len = vp_madre.LabelLineLength
    p_det = vp_madre.get_Parameter(DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER)
    det_num = p_det.AsString() if p_det is not None else None
    vista_id = vp_madre.ViewId

    doc.Delete(vp_madre.Id)
    doc.Regenerate()

    nuova_vp = DB.Viewport.Create(doc, sheet.Id, vista_id, centro)
    try:
        nuova_vp.ChangeTypeId(tipo_id)
    except Exception:
        pass
    if det_num:
        p_new_det = nuova_vp.get_Parameter(DB.BuiltInParameter.VIEWPORT_DETAIL_NUMBER)
        if p_new_det is not None and not p_new_det.IsReadOnly:
            try:
                p_new_det.Set(det_num)
            except Exception:
                pass
    try:
        nuova_vp.LabelOffset = lbl_off
        nuova_vp.LabelLineLength = lbl_len
    except Exception:
        pass
    return nuova_vp


def _mappa_viewport_per_vista(doc):
    """Mappa view_id_val -> list[(ViewSheet, Viewport)]."""
    mappa = {}
    sheets = DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet).ToElements()
    for s in sheets:
        for vpid in s.GetAllViewports():
            vp = doc.GetElement(vpid)
            if vp is not None:
                mappa.setdefault(_id_val(vp.ViewId), []).append((s, vp))
    return mappa


def sincronizza_in_tavola(doc, vista_madre, vista_sfondo, crea_se_manca=True):
    """Allinea o crea i Viewport di sfondo sovrapposti a quelli della sezione madre.

    Ritorna il numero di tavole aggiornate.
    """
    mappa = _mappa_viewport_per_vista(doc)
    madre_vps = mappa.get(_id_val(vista_madre.Id), [])
    if not madre_vps:
        return 0

    sfondo_by_sheet = dict(
        (_id_val(s.Id), vp) for (s, vp) in mappa.get(_id_val(vista_sfondo.Id), [])
    )

    aggiornate = 0
    for sheet, vp_madre in madre_vps:
        centro_puro = _centro_puro_viewport(doc, vista_madre, vp_madre)
        vp_sfondo = sfondo_by_sheet.get(_id_val(sheet.Id))

        if vp_sfondo is None:
            if not crea_se_manca:
                continue
            if not DB.Viewport.CanAddViewToSheet(doc, sheet.Id, vista_sfondo.Id):
                continue
            vp_sfondo = DB.Viewport.Create(doc, sheet.Id, vista_sfondo.Id, centro_puro)
            no_title_id = _trova_tipo_viewport_senza_titolo(doc, vp_madre.GetTypeId())
            try:
                vp_sfondo.ChangeTypeId(no_title_id)
            except Exception:
                pass
            doc.Regenerate()
        else:
            vp_sfondo.SetBoxCenter(centro_puro)
            doc.Regenerate()

        _porta_sopra_madre(doc, sheet, vp_madre, vp_sfondo)
        aggiornate += 1

    return aggiornate


# ==============================================================================
# ORCHESTRAZIONE PRINCIPALE
# ==============================================================================

def crea_o_aggiorna_sfondo(doc, vista_madre, cfg, impagina_in_tavola=True):
    """Crea (se assente) e sincronizza la vista di sfondo e le eventuali tavole.

    Ritorna (vista_sfondo, creata_nuova, tavole_aggiornate).
    """
    _, madre_to_sfondo, _ = trova_coppie_sezioni(doc)
    vista_sfondo = madre_to_sfondo.get(_id_val(vista_madre.Id))
    creata = False

    if vista_sfondo is None:
        nuovo_id = vista_madre.Duplicate(DB.ViewDuplicateOption.Duplicate)
        vista_sfondo = doc.GetElement(nuovo_id)
        vista_sfondo.Name = nome_vista_sfondo(vista_madre.Name)
        creata = True

    sincronizza_vista_sfondo(doc, vista_madre, vista_sfondo, cfg)
    tavole = sincronizza_in_tavola(doc, vista_madre, vista_sfondo, crea_se_manca=impagina_in_tavola)
    return vista_sfondo, creata, tavole
