# -*- coding: utf-8 -*-
"""Allineamento e distribuzione di riquadri di vista e titoli nella stessa tavola."""

try:
    from Autodesk.Revit import DB
    from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
    from Autodesk.Revit.Exceptions import OperationCanceledException
except ImportError:
    DB = None
    ObjectType = None
    ISelectionFilter = object
    OperationCanceledException = Exception

import profondita_sezione as PS

try:
    import avviso_wpf as AVW
except ImportError:   # fuori da Revit (test): niente WPF
    AVW = None


def _id_val(eid):
    if eid is None:
        return -1
    return getattr(eid, "Value", getattr(eid, "IntegerValue", -1))


# ==============================================================================
# FUNZIONI PURE (senza API Revit, testabili con pytest)
# ==============================================================================

def calcola_delta_box(ref_box, tgt_box, modo_x=u"nessuno", modo_y=u"nessuno",
                      ref_model_xy=None, tgt_model_xy=None):
    """Calcola (dx, dy) in piedi da applicare al riquadro target rispetto al riferimento.

    ref_box / tgt_box: (min_x, min_y, max_x, max_y)
    """
    r_min_x, r_min_y, r_max_x, r_max_y = [float(v) for v in ref_box]
    t_min_x, t_min_y, t_max_x, t_max_y = [float(v) for v in tgt_box]

    if modo_x == u"nessuno":
        dx = 0.0
    elif modo_x == u"sinistra":
        dx = r_min_x - t_min_x
    elif modo_x == u"centro":
        dx = 0.5 * (r_min_x + r_max_x) - 0.5 * (t_min_x + t_max_x)
    elif modo_x == u"destra":
        dx = r_max_x - t_max_x
    elif modo_x == u"modello":
        if ref_model_xy is not None and tgt_model_xy is not None:
            dx = float(ref_model_xy[0]) - float(tgt_model_xy[0])
        else:
            dx = 0.5 * (r_min_x + r_max_x) - 0.5 * (t_min_x + t_max_x)
    else:
        raise ValueError(u"Modalita' allineamento X non valida: %s" % modo_x)

    if modo_y == u"nessuno":
        dy = 0.0
    elif modo_y == u"basso":
        dy = r_min_y - t_min_y
    elif modo_y == u"centro":
        dy = 0.5 * (r_min_y + r_max_y) - 0.5 * (t_min_y + t_max_y)
    elif modo_y == u"alto":
        dy = r_max_y - t_max_y
    elif modo_y == u"modello":
        if ref_model_xy is not None and tgt_model_xy is not None:
            dy = float(ref_model_xy[1]) - float(tgt_model_xy[1])
        else:
            dy = 0.5 * (r_min_y + r_max_y) - 0.5 * (t_min_y + t_max_y)
    else:
        raise ValueError(u"Modalita' allineamento Y non valida: %s" % modo_y)

    return dx, dy


def calcola_nuovo_label_offset(ref_box_min, ref_label_off, tgt_box_min, tgt_label_off,
                               modo_titolo_x=u"nessuno", modo_titolo_y=u"nessuno",
                               ref_crop_min=None, tgt_crop_min=None):
    """Calcola il nuovo (LabelOffset.X, LabelOffset.Y) in piedi per il viewport target.

    LabelOffset in Revit e' relativo a GetBoxOutline().MinimumPoint (*_box_min).
    Per le modalita' relative al ritaglio (bordo_sinistro, relativo) si compensa rispetto a *_crop_min.
    """
    if ref_crop_min is None:
        ref_crop_min = ref_box_min
    if tgt_crop_min is None:
        tgt_crop_min = tgt_box_min

    ref_abs_x = float(ref_box_min[0]) + float(ref_label_off[0])
    ref_abs_y = float(ref_box_min[1]) + float(ref_label_off[1])

    if modo_titolo_x == u"nessuno":
        new_ox = float(tgt_label_off[0])
    elif modo_titolo_x == u"foglio":
        new_ox = ref_abs_x - float(tgt_box_min[0])
    elif modo_titolo_x == u"relativo":
        new_ox = (float(tgt_crop_min[0]) + (ref_abs_x - float(ref_crop_min[0]))) - float(tgt_box_min[0])
    elif modo_titolo_x == u"bordo_sinistro":
        new_ox = float(tgt_crop_min[0]) - float(tgt_box_min[0])
    else:
        raise ValueError(u"Modalita' titolo X non valida: %s" % modo_titolo_x)

    if modo_titolo_y == u"nessuno":
        new_oy = float(tgt_label_off[1])
    elif modo_titolo_y == u"foglio":
        new_oy = ref_abs_y - float(tgt_box_min[1])
    elif modo_titolo_y == u"relativo":
        new_oy = (float(tgt_crop_min[1]) + (ref_abs_y - float(ref_crop_min[1]))) - float(tgt_box_min[1])
    else:
        raise ValueError(u"Modalita' titolo Y non valida: %s" % modo_titolo_y)

    return new_ox, new_oy


def calcola_distribuzione(boxes, asse=u"x"):
    """Calcola gli spostamenti {id_key: delta} per distribuire >= 3 riquadri.

    boxes: lista di (id_key, min_x, min_y, max_x, max_y).
    Mantiene fissi il primo e l'ultimo elemento lungo l'asse scelto.
    """
    n = len(boxes)
    if n < 3:
        return {}

    idx_min, idx_max = (1, 3) if asse == u"x" else (2, 4)
    ordinati = sorted(boxes, key=lambda b: 0.5 * (float(b[idx_min]) + float(b[idx_max])))

    b_first = ordinati[0]
    b_last = ordinati[-1]
    first_min = float(b_first[idx_min])
    first_max = float(b_first[idx_max])
    last_min = float(b_last[idx_min])
    last_max = float(b_last[idx_max])

    sizes = [float(b[idx_max]) - float(b[idx_min]) for b in ordinati]
    span = last_max - first_min
    sum_sizes = sum(sizes)

    deltas = {b_first[0]: 0.0, b_last[0]: 0.0}
    if span > sum_sizes:
        gap = (span - sum_sizes) / float(n - 1)
        cursor = first_min + sizes[0] + gap
        for i in range(1, n - 1):
            b = ordinati[i]
            deltas[b[0]] = cursor - float(b[idx_min])
            cursor += sizes[i] + gap
    else:
        c_first = 0.5 * (first_min + first_max)
        c_last = 0.5 * (last_min + last_max)
        step = (c_last - c_first) / float(n - 1)
        for i in range(1, n - 1):
            b = ordinati[i]
            c_cur = 0.5 * (float(b[idx_min]) + float(b[idx_max]))
            deltas[b[0]] = (c_first + i * step) - c_cur

    return deltas


def scegli_indice_riferimento(boxes, comando):
    """Sceglie l'indice del viewport di riferimento tra quelli pre-selezionati."""
    if not boxes:
        return 0
    if comando in (u"box_sinistra", u"titolo_colonna", u"titolo_bordo_sinistro"):
        return min(range(len(boxes)), key=lambda i: boxes[i][0])
    if comando == u"box_destra":
        return max(range(len(boxes)), key=lambda i: boxes[i][2])
    if comando == u"box_alto":
        return max(range(len(boxes)), key=lambda i: boxes[i][3])
    if comando in (u"box_basso", u"titolo_riga", u"titolo_distanza_y"):
        return min(range(len(boxes)), key=lambda i: boxes[i][1])
    return 0


# ==============================================================================
# FUNZIONI REVIT API
# ==============================================================================

def _coordinate_modello_su_foglio(vp, view):
    """Restituisce la proiezione (X, Y) di riferimento del modello sul foglio."""
    if vp is None or not vp.HasViewportTransforms():
        return None
    t = vp.GetProjectionToSheetTransform()
    if view is not None and view.ViewType in (DB.ViewType.Section, DB.ViewType.Elevation):
        try:
            scale = float(max(view.Scale, 1))
            z_off = view.CropBox.Transform.Origin.Z / scale
            return (t.Origin.X, t.Origin.Y - z_off)
        except Exception:
            pass
    return (t.Origin.X, t.Origin.Y)


def _box_tuple(vp):
    out = vp.GetBoxOutline()
    return (
        out.MinimumPoint.X,
        out.MinimumPoint.Y,
        out.MaximumPoint.X,
        out.MaximumPoint.Y,
    )


def _box_ritaglio_foglio(doc, vp):
    """Restituisce (min_x, min_y, max_x, max_y) del puro ritaglio di vista (CropBox) sul foglio,
    ignorando le annotazioni sporgenti. Ripiega su GetBoxOutline() solo se la vista non ha CropBox."""
    try:
        view = doc.GetElement(vp.ViewId) if doc is not None else None
        if view is not None and vp.HasViewportTransforms() and getattr(view, "CropBox", None) is not None:
            t = vp.GetProjectionToSheetTransform()
            cb = view.CropBox
            s = float(max(getattr(view, "Scale", 1), 1))
            pts = [
                t.OfPoint(DB.XYZ(cb.Min.X / s, cb.Min.Y / s, 0.0)),
                t.OfPoint(DB.XYZ(cb.Max.X / s, cb.Min.Y / s, 0.0)),
                t.OfPoint(DB.XYZ(cb.Min.X / s, cb.Max.Y / s, 0.0)),
                t.OfPoint(DB.XYZ(cb.Max.X / s, cb.Max.Y / s, 0.0)),
            ]
            xs = [p.X for p in pts]
            ys = [p.Y for p in pts]
            return (min(xs), min(ys), max(xs), max(ys))
    except Exception:
        pass
    return _box_tuple(vp)


def _sposta_viewport_con_sfondo(doc, vp, delta_xyz, madre_to_sfondo, vps_in_sheet):
    """Sposta un viewport e l'eventuale vista (Sfondo) associata sulla stessa tavola."""
    vp.SetBoxCenter(vp.GetBoxCenter() + delta_xyz)
    sfondo_view = madre_to_sfondo.get(_id_val(vp.ViewId))
    if sfondo_view is not None:
        sfondo_vp = vps_in_sheet.get(_id_val(sfondo_view.Id))
        if sfondo_vp is not None:
            sfondo_vp.SetBoxCenter(sfondo_vp.GetBoxCenter() + delta_xyz)


def allinea_viewports_in_tavola(doc, sheet, ref_vp, target_vps, opz):
    """Allinea riquadri e titoli dei viewport target rispetto al riferimento nella stessa tavola."""
    _, madre_to_sfondo, _ = PS.trova_coppie_sezioni(doc)

    vps_in_sheet = {}
    for vpid in sheet.GetAllViewports():
        vp = doc.GetElement(vpid)
        if vp is not None:
            vps_in_sheet[_id_val(vp.ViewId)] = vp

    ref_view = doc.GetElement(ref_vp.ViewId)
    ref_model_xy = _coordinate_modello_su_foglio(ref_vp, ref_view)

    modo_x = opz.get("modo_x", u"nessuno")
    modo_y = opz.get("modo_y", u"nessuno")
    modo_tx = opz.get("modo_titolo_x", u"nessuno")
    modo_ty = opz.get("modo_titolo_y", u"nessuno")
    modo_linea = opz.get("modo_linea", u"nessuno")
    copia_tipo = bool(opz.get("copia_tipo", False))

    allineati = 0
    for tgt_vp in target_vps:
        if _id_val(tgt_vp.Id) == _id_val(ref_vp.Id):
            continue

        tgt_view = doc.GetElement(tgt_vp.ViewId)
        tgt_model_xy = _coordinate_modello_su_foglio(tgt_vp, tgt_view)
        ref_box_t = _box_ritaglio_foglio(doc, ref_vp)
        tgt_box_t = _box_ritaglio_foglio(doc, tgt_vp)

        dx, dy = calcola_delta_box(
            ref_box_t, tgt_box_t,
            modo_x=modo_x, modo_y=modo_y,
            ref_model_xy=ref_model_xy, tgt_model_xy=tgt_model_xy,
        )

        if abs(dx) > 1e-6 or abs(dy) > 1e-6:
            _sposta_viewport_con_sfondo(doc, tgt_vp, DB.XYZ(dx, dy, 0.0), madre_to_sfondo, vps_in_sheet)
            doc.Regenerate()

        ref_box = ref_vp.GetBoxOutline()
        tgt_box = tgt_vp.GetBoxOutline()

        if copia_tipo:
            try:
                tgt_vp.ChangeTypeId(ref_vp.GetTypeId())
                doc.Regenerate()
                tgt_box = tgt_vp.GetBoxOutline()
            except Exception:
                pass

        ref_crop = _box_ritaglio_foglio(doc, ref_vp)
        tgt_crop = _box_ritaglio_foglio(doc, tgt_vp)

        try:
            ref_off = ref_vp.LabelOffset
            tgt_off = tgt_vp.LabelOffset
            new_ox, new_oy = calcola_nuovo_label_offset(
                (ref_box.MinimumPoint.X, ref_box.MinimumPoint.Y),
                (ref_off.X, ref_off.Y),
                (tgt_box.MinimumPoint.X, tgt_box.MinimumPoint.Y),
                (tgt_off.X, tgt_off.Y),
                modo_titolo_x=modo_tx,
                modo_titolo_y=modo_ty,
                ref_crop_min=(ref_crop[0], ref_crop[1]),
                tgt_crop_min=(tgt_crop[0], tgt_crop[1]),
            )
            tgt_vp.LabelOffset = DB.XYZ(new_ox, new_oy, tgt_off.Z)
        except Exception:
            pass

        try:
            if modo_linea == u"riferimento":
                tgt_vp.LabelLineLength = ref_vp.LabelLineLength
            elif modo_linea == u"larghezza_vista":
                w = max(0.01, tgt_crop[2] - tgt_crop[0])
                tgt_vp.LabelLineLength = w
        except Exception:
            pass

        allineati += 1

    return allineati


# ==============================================================================
# ENTRYPOINT INTERATTIVO DA RIBBON (SmartAlign.stack)
# ==============================================================================

_COMANDO_TO_OPZ = {
    u"box_sinistra": {"modo_x": u"sinistra"},
    u"box_centro_x": {"modo_x": u"centro"},
    u"box_destra": {"modo_x": u"destra"},
    u"box_modello_x": {"modo_x": u"modello"},
    u"box_alto": {"modo_y": u"alto"},
    u"box_centro_y": {"modo_y": u"centro"},
    u"box_basso": {"modo_y": u"basso"},
    u"box_modello_y": {"modo_y": u"modello"},
    u"titolo_colonna": {"modo_titolo_x": u"foglio"},
    u"titolo_bordo_sinistro": {"modo_titolo_x": u"bordo_sinistro"},
    u"titolo_riga": {"modo_titolo_y": u"foglio"},
    u"titolo_distanza_y": {"modo_titolo_y": u"relativo"},
    u"titolo_lunghezza_rif": {"modo_linea": u"riferimento"},
}


class _ViewportFilter(ISelectionFilter):
    def __init__(self, sfondo_ids, sheet_id):
        self.sfondo_ids = sfondo_ids
        self.sheet_id_val = _id_val(sheet_id)

    def AllowElement(self, el):
        return (
            isinstance(el, DB.Viewport)
            and _id_val(el.SheetId) == self.sheet_id_val
            and _id_val(el.ViewId) not in self.sfondo_ids
        )

    def AllowReference(self, ref, point):
        return False


def _errore(msg):
    """Avviso rosso piccolo nella vista; senza WPF (es. nei test) la finestra di pyRevit."""
    if AVW is not None:
        AVW.errore(msg)
        return
    from pyrevit import forms
    forms.alert(msg, title=u"CDV Tools")


def esegui_da_ribbon(comando):
    """Esegue un comando Smart Align direttamente sulla tavola attiva."""
    from pyrevit import revit

    doc = revit.doc
    uidoc = revit.uidoc
    if not doc or not uidoc:
        _errore(u"Nessun documento attivo in Revit.")
        return

    if not isinstance(doc.ActiveView, DB.ViewSheet):
        _errore(u"Apri una tavola per usare gli strumenti di allineamento.")
        return

    sheet = doc.ActiveView
    coppie, madre_to_sfondo, sfondo_to_madre = PS.trova_coppie_sezioni(doc)
    sfondo_ids = set(_id_val(item["sfondo"].Id) for item in coppie)
    filtro = _ViewportFilter(sfondo_ids, sheet.Id)

    vp_per_vista = {}
    for vpid in sheet.GetAllViewports():
        vp_s = doc.GetElement(vpid)
        if vp_s is not None:
            vp_per_vista[_id_val(vp_s.ViewId)] = vp_s

    pre_vps = []
    for eid in uidoc.Selection.GetElementIds():
        el = doc.GetElement(eid)
        # Il riquadro di sfondo (sovrapposto) vale come quello della sua sezione madre
        if isinstance(el, DB.Viewport) and _id_val(el.ViewId) in sfondo_ids:
            madre = sfondo_to_madre.get(_id_val(el.ViewId))
            el = vp_per_vista.get(_id_val(madre.Id)) if madre is not None else None
        if filtro.AllowElement(el) and all(_id_val(v.Id) != _id_val(el.Id) for v in pre_vps):
            pre_vps.append(el)

    try:
        if comando in (u"distribuisci_x", u"distribuisci_y"):
            if len(pre_vps) >= 3:
                vps = pre_vps
            else:
                refs = uidoc.Selection.PickObjects(
                    ObjectType.Element, filtro,
                    u"Seleziona almeno 3 viste da distribuire, poi Fine"
                )
                vps = [doc.GetElement(r) for r in refs]
            if len(vps) < 3:
                _errore(u"Seleziona almeno 3 viste nella tavola per distribuirle.")
                return

            asse = u"x" if comando == u"distribuisci_x" else u"y"
            boxes = [(_id_val(vp.Id),) + _box_ritaglio_foglio(doc, vp) for vp in vps]
            deltas = calcola_distribuzione(boxes, asse=asse)

            vps_in_sheet = {}
            for vpid in sheet.GetAllViewports():
                vp_s = doc.GetElement(vpid)
                if vp_s is not None:
                    vps_in_sheet[_id_val(vp_s.ViewId)] = vp_s

            t = DB.Transaction(doc, u"Distribuisci Viste in Tavola")
            t.Start()
            try:
                for vp in vps:
                    d = deltas.get(_id_val(vp.Id), 0.0)
                    if abs(d) > 1e-6:
                        delta_xyz = DB.XYZ(d, 0.0, 0.0) if asse == u"x" else DB.XYZ(0.0, d, 0.0)
                        _sposta_viewport_con_sfondo(doc, vp, delta_xyz, madre_to_sfondo, vps_in_sheet)
                t.Commit()
            except Exception:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                raise
            return

        if comando in (u"titolo_larghezza_vista", u"titolo_bordo_sinistro"):
            prompt_msg = (
                u"Seleziona le viste a cui adattare la linea del titolo, poi Fine"
                if comando == u"titolo_larghezza_vista"
                else u"Seleziona le viste di cui allineare il titolo al ritaglio, poi Fine"
            )
            tx_name = (
                u"Adatta Linea Titolo al Ritaglio"
                if comando == u"titolo_larghezza_vista"
                else u"Allinea Titolo al Bordo Sinistro Ritaglio"
            )
            if len(pre_vps) >= 1:
                target_vps = pre_vps
            else:
                refs = uidoc.Selection.PickObjects(ObjectType.Element, filtro, prompt_msg)
                target_vps = [doc.GetElement(r) for r in refs]
            if not target_vps:
                return

            t = DB.Transaction(doc, tx_name)
            t.Start()
            try:
                for vp in target_vps:
                    crop = _box_ritaglio_foglio(doc, vp)
                    if comando == u"titolo_larghezza_vista":
                        vp.LabelLineLength = max(0.01, crop[2] - crop[0])
                    else:
                        out = vp.GetBoxOutline()
                        off = vp.LabelOffset
                        vp.LabelOffset = DB.XYZ(crop[0] - out.MinimumPoint.X, off.Y, off.Z)
                t.Commit()
            except Exception:
                if t.HasStarted() and not t.HasEnded():
                    t.RollBack()
                raise
            return

        # Comandi di allineamento con riferimento + target
        if len(pre_vps) >= 2:
            boxes = [_box_ritaglio_foglio(doc, vp) for vp in pre_vps]
            idx = scegli_indice_riferimento(boxes, comando)
            ref_vp = pre_vps[idx]
            target_vps = [vp for i, vp in enumerate(pre_vps) if i != idx]
        elif len(pre_vps) == 1:
            ref_vp = pre_vps[0]
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element, filtro,
                u"Seleziona le viste da allineare al riferimento, poi Fine"
            )
            target_vps = [doc.GetElement(r) for r in refs if _id_val(doc.GetElement(r).Id) != _id_val(ref_vp.Id)]
        else:
            ref = uidoc.Selection.PickObject(
                ObjectType.Element, filtro,
                u"Seleziona la vista di RIFERIMENTO"
            )
            ref_vp = doc.GetElement(ref)
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element, filtro,
                u"Seleziona le viste da allineare, poi Fine"
            )
            target_vps = [doc.GetElement(r) for r in refs if _id_val(doc.GetElement(r).Id) != _id_val(ref_vp.Id)]

        if not target_vps:
            return

        opz = _COMANDO_TO_OPZ.get(comando, {})
        t = DB.Transaction(doc, u"Smart Align Tavola")
        t.Start()
        try:
            allinea_viewports_in_tavola(doc, sheet, ref_vp, target_vps, opz)
            t.Commit()
        except Exception:
            if t.HasStarted() and not t.HasEnded():
                t.RollBack()
            raise

    except OperationCanceledException:
        return
