# -*- coding: utf-8 -*-
"""Crea automaticamente una campitura (es. TERRENO) a partire dal bordo inferiore o superiore di uno o piu elementi 3D sezionati nella vista (pavimenti inclinati, tetti, fondazioni, link RVT), chiudendola con fondo orizzontale (da punto min/max o da Livello) o parallelo alla pendenza."""

import re
import math
import clr

clr.AddReference("System")
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Collections.Generic import List
from System.Windows.Media import BrushConverter

from pyrevit import revit, DB, UI, forms, script, EXEC_PARAMS
import stile_finestre as SF
import memoria_finestre as MF
import avviso_wpf as AVW

# Clic: crea subito la campitura con le ultime impostazioni; Maiusc+clic: finestra.
_MEMORIA = u"campitura_sezione"
_CONTROLLI = [u"rbEdgeBottom", u"rbEdgeTop", u"rbDirDown", u"rbDirUp", u"rbModeMinMax",
              u"rbRefLowest", u"rbRefHighest", u"rbModeLevel", u"cmbLevel", u"rbModeParallel",
              u"rbParVertical", u"rbParNormal", u"txtHeight", u"cmbFilledRegionType",
              u"cmbTopLineStyle", u"cmbSideBottomLineStyle", u"chkSelectResult"]


def get_id_val(elem_id):
    """Restituisce il valore intero di un ElementId."""
    if elem_id is None:
        return None
    if hasattr(elem_id, "Value"):
        return elem_id.Value
    if hasattr(elem_id, "IntegerValue"):
        return elem_id.IntegerValue
    try:
        return int(elem_id)
    except Exception:
        return None


def get_element_name(elem):
    """Estrae in modo sicuro il nome leggibile di un elemento Revit."""
    if not elem:
        return ""
    for bp in (DB.BuiltInParameter.ALL_MODEL_TYPE_NAME, DB.BuiltInParameter.SYMBOL_NAME_PARAM, DB.BuiltInParameter.DATUM_TEXT):
        try:
            p = elem.get_Parameter(bp)
            if p and p.AsString():
                return p.AsString()
        except Exception:
            pass
    try:
        if hasattr(elem, "Name") and elem.Name:
            return elem.Name
    except Exception:
        pass
    try:
        return DB.Element.Name.__get__(elem)
    except Exception:
        pass
    return "Elemento {}".format(get_id_val(elem.Id))


def parse_signed_length_to_feet(input_str):
    """Converte una stringa con unita (anche negativa o zero, es. -150cm, 100cm, 1.2m, 0mm) in piedi."""
    if input_str is None or not input_str.strip():
        raise ValueError("Inserisci un valore numerico valido.")

    cleaned = input_str.strip().replace(" ", "").replace(",", ".")
    match = re.match(r"^([+-]?[0-9]*\.?[0-9]+)\s*([a-zA-Z\"']*)$", cleaned)
    if not match:
        raise ValueError("Formato misura non valido: '{}'.".format(input_str))

    num_str, unit_str = match.groups()
    val = float(num_str)
    unit = unit_str.lower()

    if unit in ("mm", "millimetri", ""):
        feet = val / 304.8
        disp = "{} mm".format(int(val) if val.is_integer() else val)
    elif unit in ("cm", "centimetri"):
        feet = (val * 10.0) / 304.8
        disp = "{} cm".format(int(val) if val.is_integer() else val)
    elif unit in ("m", "metri", "mt"):
        feet = (val * 1000.0) / 304.8
        disp = "{} m".format(val)
    elif unit in ("ft", "'", "feet"):
        feet = val
        disp = "{} ft".format(val)
    else:
        feet = val / 304.8
        disp = "{} mm".format(val)

    return feet, disp


def collect_solids_from_geometry(geom_elem, transform=None):
    """Estrae ricorsivamente tutti i Solid con volume positivo da un GeometryElement."""
    solids = []
    if not geom_elem:
        return solids

    for g in geom_elem:
        if isinstance(g, DB.Solid):
            if g.Volume > 1e-6 and g.Faces.Size > 0:
                s = DB.SolidUtils.CreateTransformed(g, transform) if transform else g
                solids.append(s)
        elif isinstance(g, DB.GeometryInstance):
            inst_geom = g.GetInstanceGeometry()
            if inst_geom:
                for sg in inst_geom:
                    if isinstance(sg, DB.Solid) and sg.Volume > 1e-6 and sg.Faces.Size > 0:
                        s = DB.SolidUtils.CreateTransformed(sg, transform) if transform else sg
                        solids.append(s)
    return solids


def extract_element_solids(elem, transform=None):
    """Restituisce i solidi 3D di un elemento (applicando eventuale trasformazione da Link RVT)."""
    if not elem:
        return []
    opts = DB.Options()
    opts.ComputeReferences = False
    opts.DetailLevel = DB.ViewDetailLevel.Fine
    try:
        ge = elem.get_Geometry(opts)
        return collect_solids_from_geometry(ge, transform)
    except Exception:
        return []


def extract_section_cut_segments(solids, view, pick_top_edge=False):
    """Taglia una lista di Solid con il piano della vista di sezione e restituisce i segmenti 2D (u0, v0, u1, v1) del bordo superiore o inferiore."""
    origin = view.Origin
    view_dir = view.ViewDirection
    right = view.RightDirection
    up = view.UpDirection
    plane = DB.Plane.CreateByNormalAndOrigin(view_dir, origin)

    extracted_segments = []

    for s in solids:
        try:
            s_copy = DB.SolidUtils.Clone(s)
            DB.BooleanOperationsUtils.CutWithHalfSpaceModifyingOriginalSolid(s_copy, plane)
        except Exception:
            continue

        for face in s_copy.Faces:
            if not isinstance(face, DB.PlanarFace):
                continue
            if abs(face.FaceNormal.DotProduct(view_dir)) < 0.999:
                continue
            if abs((face.Origin - origin).DotProduct(view_dir)) > 1e-3:
                continue

            for loop in face.GetEdgesAsCurveLoops():
                loop_segs = []
                for c in loop:
                    p0 = c.GetEndPoint(0) - origin
                    p1 = c.GetEndPoint(1) - origin
                    u0, v0 = p0.DotProduct(right), p0.DotProduct(up)
                    u1, v1 = p1.DotProduct(right), p1.DotProduct(up)
                    du = abs(u1 - u0)
                    dv = abs(v1 - v0)
                    if du > 1e-4 and dv <= 8.0 * du:
                        if u0 > u1:
                            u0, v0, u1, v1 = u1, v1, u0, v0
                        loop_segs.append((u0, v0, u1, v1))

                for s_cand in loop_segs:
                    u_mid = 0.5 * (s_cand[0] + s_cand[2])
                    v_mid = 0.5 * (s_cand[1] + s_cand[3])
                    keep = True
                    for s_other in loop_segs:
                        if s_other is s_cand:
                            continue
                        if s_other[0] - 1e-4 <= u_mid <= s_other[2] + 1e-4:
                            denom = s_other[2] - s_other[0]
                            if denom > 1e-5:
                                t_val = (u_mid - s_other[0]) / denom
                                v_other = s_other[1] + t_val * (s_other[3] - s_other[1])
                                if pick_top_edge:
                                    if v_other > v_mid + 1e-4:
                                        keep = False
                                        break
                                else:
                                    if v_other < v_mid - 1e-4:
                                        keep = False
                                        break
                    if keep:
                        extracted_segments.append(s_cand)

    return extracted_segments


def get_view_crop_u_limits(view):
    """Restituisce (u_min, u_max) del Riquadro di Taglio della vista in coordinate (u, v) rispetto a view.Origin."""
    if not view.CropBoxActive:
        return None
    crop_bb = view.CropBox
    t_crop = crop_bb.Transform
    origin = view.Origin
    right = view.RightDirection
    pts = [
        t_crop.OfPoint(DB.XYZ(crop_bb.Min.X, crop_bb.Min.Y, 0.0)),
        t_crop.OfPoint(DB.XYZ(crop_bb.Max.X, crop_bb.Min.Y, 0.0)),
        t_crop.OfPoint(DB.XYZ(crop_bb.Max.X, crop_bb.Max.Y, 0.0)),
        t_crop.OfPoint(DB.XYZ(crop_bb.Min.X, crop_bb.Max.Y, 0.0)),
    ]
    us = [(p - origin).DotProduct(right) for p in pts]
    return min(us), max(us)


def clip_segments_to_u_range(segments, u_min, u_max):
    """Ritaglia i segmenti 2D (u0, v0, u1, v1) entro [u_min, u_max]."""
    clipped = []
    for u0, v0, u1, v1 in segments:
        if u1 <= u_min + 1e-5 or u0 >= u_max - 1e-5:
            continue
        cu0 = max(u0, u_min)
        cu1 = min(u1, u_max)
        if cu1 - cu0 > 1e-4:
            cv0 = v0 + (cu0 - u0) / (u1 - u0) * (v1 - v0)
            cv1 = v0 + (cu1 - u0) / (u1 - u0) * (v1 - v0)
            clipped.append((cu0, cv0, cu1, cv1))
    return clipped


def build_profile_islands(segments, max_join_gap_ft=0.984):
    """Unisce i segmenti in polilinee continue (inserendo gradini verticali dove contigui entro 30 cm) e separa le isole distanti."""
    if not segments:
        return []

    sorted_segs = sorted(segments, key=lambda s: (round(s[0], 4), round(s[2], 4)))

    cleaned = []
    for seg in sorted_segs:
        u0, v0, u1, v1 = seg
        if not cleaned:
            cleaned.append([u0, v0, u1, v1])
            continue
        prev = cleaned[-1]
        if u1 <= prev[2] + 1e-4:
            continue
        if u0 < prev[2] - 1e-4:
            u_new = prev[2]
            if u1 - u_new > 1e-4:
                v_new = v0 + (u_new - u0) / (u1 - u0) * (v1 - v0)
                cleaned.append([u_new, v_new, u1, v1])
        else:
            cleaned.append([u0, v0, u1, v1])

    islands = []
    current_pts = [(cleaned[0][0], cleaned[0][1]), (cleaned[0][2], cleaned[0][3])]

    for i in range(1, len(cleaned)):
        u0, v0, u1, v1 = cleaned[i]
        last_u, last_v = current_pts[-1]
        gap_u = u0 - last_u

        if gap_u <= max_join_gap_ft:
            dist = math.hypot(u0 - last_u, v0 - last_v)
            if dist > 0.003:
                current_pts.append((u0, v0))
            current_pts.append((u1, v1))
        else:
            islands.append(current_pts)
            current_pts = [(u0, v0), (u1, v1)]

    if current_pts:
        islands.append(current_pts)

    return islands


def uv_to_xyz(u, v, origin, right, up):
    """Converte coordinate 2D (u, v) della sezione in punto 3D sul piano della vista."""
    return origin + u * right + v * up


def compute_parallel_offset_points(pts_uv, h_signed, is_normal_offset):
    """Calcola la polilinea inferiore traslata verticalmente o perpendicolarmente di h_signed."""
    if not is_normal_offset:
        return [(u, v + h_signed) for (u, v) in pts_uv]

    n_seg = len(pts_uv) - 1
    normals = []
    for i in range(n_seg):
        du = pts_uv[i + 1][0] - pts_uv[i][0]
        dv = pts_uv[i + 1][1] - pts_uv[i][1]
        length = math.hypot(du, dv)
        if length < 1e-6:
            normals.append((0.0, 1.0 if h_signed >= 0 else -1.0))
        else:
            nx = -dv / length
            ny = du / length
            normals.append((nx, ny))

    out_pts = []
    for i in range(len(pts_uv)):
        u, v = pts_uv[i]
        if i == 0:
            nx, ny = normals[0]
        elif i == n_seg:
            nx, ny = normals[-1]
        else:
            nx0, ny0 = normals[i - 1]
            nx1, ny1 = normals[i]
            bx = nx0 + nx1
            by = ny0 + ny1
            blen = math.hypot(bx, by)
            if blen < 1e-5:
                nx, ny = nx0, ny0
            else:
                nx, ny = bx / blen, by / blen
                dot = nx * nx0 + ny * ny0
                if abs(dot) > 0.25:
                    nx /= dot
                    ny /= dot
        out_pts.append((u + h_signed * nx, v + h_signed * ny))

    return out_pts


def build_island_curveloop(pts_uv, view, mode, dir_down, ref_lowest, height_ft, level_v_ft, par_normal, min_len):
    """Costruisce un CurveLoop chiuso per un'isola di profilo e restituisce (loop, closure_midpoints_3d)."""
    if len(pts_uv) < 2:
        return None, []

    origin = view.Origin
    right = view.RightDirection
    up = view.UpDirection

    vs = [p[1] for p in pts_uv]
    v_min = min(vs)
    v_max = max(vs)

    if mode == "minmax":
        base_v = v_min if ref_lowest else v_max
        target_v = (base_v - abs(height_ft)) if dir_down else (base_v + abs(height_ft))
        if dir_down and target_v >= v_min - min_len * 2.0:
            target_v = v_min - max(abs(height_ft), 0.1)
        elif not dir_down and target_v <= v_max + min_len * 2.0:
            target_v = v_max + max(abs(height_ft), 0.1)
        bottom_pts = [(pts_uv[-1][0], target_v), (pts_uv[0][0], target_v)]
    elif mode == "level":
        target_v = (level_v_ft - abs(height_ft)) if dir_down else (level_v_ft + abs(height_ft))
        if dir_down and target_v >= v_min - min_len * 2.0:
            target_v = v_min - max(abs(height_ft), 0.1)
        elif not dir_down and target_v <= v_max + min_len * 2.0:
            target_v = v_max + max(abs(height_ft), 0.1)
        bottom_pts = [(pts_uv[-1][0], target_v), (pts_uv[0][0], target_v)]
    else:
        h_signed = -abs(height_ft) if dir_down else abs(height_ft)
        par_pts = compute_parallel_offset_points(pts_uv, h_signed, par_normal)
        bottom_pts = list(reversed(par_pts))

    top_3d = [uv_to_xyz(u, v, origin, right, up) for (u, v) in pts_uv]
    bot_3d = [uv_to_xyz(u, v, origin, right, up) for (u, v) in bottom_pts]

    filtered_top = [top_3d[0]]
    for pt in top_3d[1:]:
        if pt.DistanceTo(filtered_top[-1]) >= min_len:
            filtered_top.append(pt)

    filtered_bot = [bot_3d[0]]
    for pt in bot_3d[1:]:
        if pt.DistanceTo(filtered_bot[-1]) >= min_len:
            filtered_bot.append(pt)

    if len(filtered_top) < 2 or len(filtered_bot) < 2:
        return None, []

    loop = DB.CurveLoop()
    closure_midpoints = []

    for i in range(len(filtered_top) - 1):
        c = DB.Line.CreateBound(filtered_top[i], filtered_top[i + 1])
        loop.Append(c)

    if filtered_top[-1].DistanceTo(filtered_bot[0]) >= min_len:
        c_right = DB.Line.CreateBound(filtered_top[-1], filtered_bot[0])
        loop.Append(c_right)
        closure_midpoints.append(c_right.Evaluate(0.5, True))

    for i in range(len(filtered_bot) - 1):
        c_bot = DB.Line.CreateBound(filtered_bot[i], filtered_bot[i + 1])
        loop.Append(c_bot)
        closure_midpoints.append(c_bot.Evaluate(0.5, True))

    if filtered_bot[-1].DistanceTo(filtered_top[0]) >= min_len:
        c_left = DB.Line.CreateBound(filtered_bot[-1], filtered_top[0])
        loop.Append(c_left)
        closure_midpoints.append(c_left.Evaluate(0.5, True))

    return loop, closure_midpoints


class CutElementSelectionFilter(UI.Selection.ISelectionFilter):
    """Filtro per selezionare elementi 3D sezionabili nella vista."""

    def AllowElement(self, elem):
        if not elem or not elem.Category:
            return False
        if isinstance(elem, (DB.View, DB.Level, DB.Grid, DB.ReferencePlane)):
            return False
        return True

    def AllowReference(self, reference, position):
        return True


class NamedItem(object):
    def __init__(self, obj, name=None):
        self.Object = obj
        self.Id = obj.Id if hasattr(obj, "Id") else None
        self.Name = name if name is not None else get_element_name(obj)

    def ToString(self):
        return self.Name

    def __str__(self):
        return self.Name


class SectionFilledRegionWindow(forms.WPFWindow):
    def __init__(self, xaml_file, initial_records):
        forms.WPFWindow.__init__(self, SF.xaml(xaml_file), literal_string=True)
        self.doc = revit.doc
        self.uidoc = revit.uidoc
        self.view = revit.active_view
        self.selected_records = list(initial_records)
        self.esito = False

        self._init_controls()
        self._bind_events()
        self._update_selection_ui()

    def _init_controls(self):
        """Popola tipi campitura, stili linea e livelli del progetto."""
        fr_types = list(DB.FilteredElementCollector(self.doc).OfClass(DB.FilledRegionType).WhereElementIsElementType())
        fr_items = [NamedItem(t) for t in fr_types]
        fr_items.sort(key=lambda x: x.Name.lower())
        self.cmbFilledRegionType.ItemsSource = fr_items

        default_fr_idx = 0
        for i, item in enumerate(fr_items):
            if "terren" in item.Name.lower() or "terra" in item.Name.lower():
                default_fr_idx = i
                break
        if fr_items:
            self.cmbFilledRegionType.SelectedIndex = default_fr_idx

        lines_cat = self.doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Lines)
        ls_items = []
        seen_gs_ids = set()
        if lines_cat and lines_cat.SubCategories:
            for sc in lines_cat.SubCategories:
                try:
                    gs = sc.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
                    if gs:
                        ls_items.append(NamedItem(gs))
                        seen_gs_ids.add(get_id_val(gs.Id))
                except Exception:
                    pass

        inv_cat_id = int(DB.BuiltInCategory.OST_InvisibleLines)
        for gs in DB.FilteredElementCollector(self.doc).OfClass(DB.GraphicsStyle):
            try:
                if gs.GraphicsStyleType == DB.GraphicsStyleType.Projection and gs.GraphicsStyleCategory:
                    if get_id_val(gs.GraphicsStyleCategory.Id) == inv_cat_id and get_id_val(gs.Id) not in seen_gs_ids:
                        ls_items.append(NamedItem(gs))
                        seen_gs_ids.add(get_id_val(gs.Id))
            except Exception:
                pass

        ls_items.sort(key=lambda x: x.Name.lower())
        self.cmbTopLineStyle.ItemsSource = list(ls_items)
        self.cmbSideBottomLineStyle.ItemsSource = list(ls_items)

        inv_idx = 0
        thick_idx = 0
        for i, item in enumerate(ls_items):
            lname = item.Name.lower()
            if "invisibil" in lname or "invisible" in lname:
                inv_idx = i
            if "spess" in lname or "wide" in lname or "medium" in lname or "medi" in lname:
                thick_idx = i

        if ls_items:
            self.cmbTopLineStyle.SelectedIndex = thick_idx
            self.cmbSideBottomLineStyle.SelectedIndex = inv_idx

        levels = list(DB.FilteredElementCollector(self.doc).OfClass(DB.Level).WhereElementIsNotElementType())
        levels.sort(key=lambda l: l.Elevation)
        lvl_items = [
            NamedItem(l, "{} ({:+.2f} m)".format(get_element_name(l), l.Elevation * 0.3048))
            for l in levels
        ]
        self.cmbLevel.ItemsSource = lvl_items

        gf_idx = 0
        for i, item in enumerate(lvl_items):
            if "gf" in item.Name.lower() or abs(item.Object.Elevation) < 0.01:
                gf_idx = i
                break
        if lvl_items:
            self.cmbLevel.SelectedIndex = gf_idx

        self.chkCropToView.IsChecked = bool(self.view.CropBoxActive)

    def _bind_events(self):
        self.btnReselect.Click += self._on_select_host
        self.btnSelectLink.Click += self._on_select_link
        self.btnApply.Click += self._on_apply
        self.btnCancel.Click += lambda s, e: self.Close()

        self.btnPreset0.Click += lambda s, e: self._set_h("0 mm")
        self.btnPreset50cm.Click += lambda s, e: self._set_h("50 cm")
        self.btnPreset100cm.Click += lambda s, e: self._set_h("100 cm")
        self.btnPreset150cm.Click += lambda s, e: self._set_h("150 cm")
        self.btnPreset200cm.Click += lambda s, e: self._set_h("200 cm")

    def _set_h(self, val_str):
        self.txtHeight.Text = val_str

    def _update_selection_ui(self):
        count = len(self.selected_records)
        if count == 0:
            self.lblSelectionInfo.Text = "Nessun elemento 3D selezionato"
            self.lblSelectionDetail.Text = "Usa 'Seleziona...' o '+ Da Link RVT...' per scegliere gli elementi"
            self.lblStatus.Text = "Seleziona almeno un elemento tagliato dalla sezione."
        else:
            names = [r["name"] for r in self.selected_records]
            self.lblSelectionInfo.Text = "{} elementi sezionati selezionati".format(count)
            self.lblSelectionDetail.Text = "Elementi: {}".format(", ".join(names[:4]) + ("..." if len(names) > 4 else ""))
            self.lblStatus.Text = "Pronto per generare la campitura per sezione."

    def _on_select_host(self, sender, e):
        self.Hide()
        try:
            refs = self.uidoc.Selection.PickObjects(
                UI.Selection.ObjectType.Element,
                CutElementSelectionFilter(),
                "Seleziona uno o piu pavimenti/elementi sezionati nella vista (Premi Fine in alto a sinistra al termine)"
            )
            if refs:
                records = []
                for r in refs:
                    el = self.doc.GetElement(r.ElementId)
                    if el:
                        records.append({"elem": el, "transform": None, "name": get_element_name(el)})
                self.selected_records = records
        except Exception:
            pass
        finally:
            self._update_selection_ui()
            self.ShowDialog()

    def _on_select_link(self, sender, e):
        self.Hide()
        try:
            refs = self.uidoc.Selection.PickObjects(
                UI.Selection.ObjectType.LinkedElement,
                "Seleziona gli elementi sezionati dal modello RVT collegato (Premi Fine al termine)"
            )
            if refs:
                for r in refs:
                    link_inst = self.doc.GetElement(r.ElementId)
                    if isinstance(link_inst, DB.RevitLinkInstance):
                        link_doc = link_inst.GetLinkDocument()
                        if link_doc:
                            linked_el = link_doc.GetElement(r.LinkedElementId)
                            if linked_el:
                                self.selected_records.append({
                                    "elem": linked_el,
                                    "transform": link_inst.GetTotalTransform(),
                                    "name": "[Link] " + get_element_name(linked_el)
                                })
        except Exception:
            pass
        finally:
            self._update_selection_ui()
            self.ShowDialog()

    def _problema(self, testo):
        """Qualcosa manca o non va: nella riga di stato (rosso) o, senza finestra, nell'avviso."""
        try:
            self.lblStatus.Text = testo
            self.lblStatus.Foreground = BrushConverter().ConvertFromString("#DC2626")
        except Exception:
            pass
        if not self.IsVisible:
            AVW.attenzione(testo)

    def _on_apply(self, sender, e):
        MF.salva(self, _MEMORIA, _CONTROLLI)
        if not self.selected_records:
            self._problema(u"Seleziona gli elementi tagliati dalla sezione")
            return

        try:
            height_ft, disp_h = parse_signed_length_to_feet(self.txtHeight.Text)
        except ValueError as ex:
            self._problema(str(ex))
            return

        pick_top = bool(self.rbEdgeTop.IsChecked)
        dir_down = bool(self.rbDirDown.IsChecked)
        ref_lowest = bool(self.rbRefLowest.IsChecked)
        par_normal = bool(self.rbParNormal.IsChecked)

        if self.rbModeMinMax.IsChecked:
            mode = "minmax"
        elif self.rbModeLevel.IsChecked:
            mode = "level"
        else:
            mode = "parallel"

        if mode in ("minmax", "parallel") and abs(height_ft) < 0.005:
            self._problema(u"Con questa chiusura l'altezza H deve essere maggiore di zero (es. 100 cm)")
            return

        level_v_ft = 0.0
        if mode == "level":
            sel_lvl = self.cmbLevel.SelectedItem
            if not sel_lvl:
                self._problema(u"Scegli il livello di riferimento")
                return
            lvl_z = sel_lvl.Object.Elevation
            pt_lvl = DB.XYZ(self.view.Origin.X, self.view.Origin.Y, lvl_z)
            level_v_ft = (pt_lvl - self.view.Origin).DotProduct(self.view.UpDirection)

        all_solids = []
        for rec in self.selected_records:
            all_solids.extend(extract_element_solids(rec["elem"], rec["transform"]))

        if not all_solids:
            self._problema(u"Gli elementi selezionati non hanno una geometria 3D da tagliare")
            return

        segments = extract_section_cut_segments(all_solids, self.view, pick_top_edge=pick_top)
        if not segments:
            self._problema(u"Gli elementi non sono tagliati da questa sezione")
            return

        if self.chkCropToView.IsChecked:
            crop_limits = get_view_crop_u_limits(self.view)
            if crop_limits:
                segments = clip_segments_to_u_range(segments, crop_limits[0], crop_limits[1])

        if not segments:
            self._problema(u"La parte tagliata è fuori dal ritaglio della vista")
            return

        islands = build_profile_islands(segments)
        min_len = self.doc.Application.ShortCurveTolerance

        sel_fr = self.cmbFilledRegionType.SelectedItem
        if not sel_fr:
            return
        fr_type_id = sel_fr.Id

        top_ls_item = self.cmbTopLineStyle.SelectedItem
        bot_ls_item = self.cmbSideBottomLineStyle.SelectedItem
        top_gs = top_ls_item.Object if top_ls_item else None
        bot_gs = bot_ls_item.Object if bot_ls_item else None

        created_regions = []

        with revit.Transaction("Campitura per Sezione"):
            for island_pts in islands:
                loop, closure_mids = build_island_curveloop(
                    pts_uv=island_pts,
                    view=self.view,
                    mode=mode,
                    dir_down=dir_down,
                    ref_lowest=ref_lowest,
                    height_ft=height_ft,
                    level_v_ft=level_v_ft,
                    par_normal=par_normal,
                    min_len=min_len
                )
                if not loop:
                    continue

                loops_list = List[DB.CurveLoop]()
                loops_list.Add(loop)

                try:
                    fr = DB.FilledRegion.Create(self.doc, fr_type_id, self.view.Id, loops_list)
                    if fr:
                        created_regions.append(fr)
                        self.doc.Regenerate()
                        dep_sketches = fr.GetDependentElements(DB.ElementClassFilter(DB.Sketch))
                        if dep_sketches:
                            sketch = self.doc.GetElement(dep_sketches[0])
                            for cid in sketch.GetAllElements():
                                ce = self.doc.GetElement(cid)
                                if isinstance(ce, DB.CurveElement) and ce.GeometryCurve:
                                    mid = ce.GeometryCurve.Evaluate(0.5, True)
                                    is_closure = any(mid.DistanceTo(cm) < 0.01 for cm in closure_mids)
                                    if is_closure and bot_gs:
                                        ce.LineStyle = bot_gs
                                    elif not is_closure and top_gs:
                                        ce.LineStyle = top_gs
                except Exception as ex:
                    script.get_logger().error("Errore creazione FilledRegion: {}".format(ex))

        if created_regions:
            if self.chkSelectResult.IsChecked:
                try:
                    self.uidoc.Selection.SetElementIds(List[DB.ElementId]([r.Id for r in created_regions]))
                except Exception:
                    pass
            self.esito = True
            self.Close()
            AVW.mostra(u"Campiture create: %d \u00b7 %s, bordo %s (Maiusc+clic: impostazioni)"
                       % (len(created_regions), sel_fr.Name, u"superiore" if pick_top else u"inferiore"))
        else:
            self._problema(u"Campitura non creata: con queste impostazioni il contorno non si chiude")


def main():
    doc = revit.doc
    uidoc = revit.uidoc
    active_view = revit.active_view

    if not doc or not uidoc or doc.IsFamilyDocument:
        AVW.errore(u"Apri una sezione o un prospetto")
        return

    if active_view.ViewType not in (DB.ViewType.Section, DB.ViewType.Elevation, DB.ViewType.Detail):
        AVW.errore(u"Apri una sezione, un prospetto o un dettaglio")
        return

    initial_records = []
    for el_id in uidoc.Selection.GetElementIds():
        el = doc.GetElement(el_id)
        if el and CutElementSelectionFilter().AllowElement(el):
            initial_records.append({"elem": el, "transform": None, "name": get_element_name(el)})

    xaml_path = script.get_bundle_file("ui.xaml")
    diretta = MF.ha_impostazioni(_MEMORIA) and not EXEC_PARAMS.config_mode
    if diretta and not initial_records:
        # prima si seleziona, poi si crea: se manca la selezione la si chiede qui
        try:
            refs = uidoc.Selection.PickObjects(
                UI.Selection.ObjectType.Element, CutElementSelectionFilter(),
                u"Seleziona gli elementi sezionati (Fine per confermare)")
            initial_records = [{"elem": doc.GetElement(r.ElementId), "transform": None,
                                "name": get_element_name(doc.GetElement(r.ElementId))} for r in refs]
        except Exception:
            return
    win = SectionFilledRegionWindow(xaml_path, initial_records)
    MF.ripristina(win, _MEMORIA, _CONTROLLI)
    if diretta and initial_records:
        # esecuzione diretta; se qualcosa non va si apre la finestra per correggere
        win._on_apply(None, None)
        if win.esito:
            return
        win = SectionFilledRegionWindow(xaml_path, initial_records)
        MF.ripristina(win, _MEMORIA, _CONTROLLI)
    win.ShowDialog()


if __name__ == "__main__":
    main()
