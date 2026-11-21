# -*- coding: utf-8 -*-
"""Campitura da Polilinea / Offset (CDV Tools)

Crea una campitura (Filled Region) ad offset da linee/polilinee selezionate
(Linee di Dettaglio o Linee di Modello).
Supporta offset su Lato Sinistro, Lato Destro o Entrambi i Lati (spessore totale),
gestione angoli miter puliti, chiusure ortogonali, selezione stile linea dei bordi
e scelta se conservare o eliminare le linee guida originali.
"""

import os
import sys
import re
import math
import clr

clr.AddReference('System')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System.Collections.ObjectModel import ObservableCollection
from System.Collections.Generic import List
from System.Windows import Window, MessageBox, MessageBoxButton, MessageBoxImage, MessageBoxResult

from pyrevit import revit, DB, UI, forms, script, EXEC_PARAMS
import stile_finestre as SF
import memoria_finestre as MF
import avviso_wpf as AVW

# Clic: crea subito la campitura con le ultime impostazioni; Maiusc+clic: finestra.
_MEMORIA = u"campitura_polilinea"
_CONTROLLI = [u"txtOffset", u"rbBoth", u"rbLeft", u"rbRight", u"chkClosedDonut",
              u"cmbFilledRegionType", u"cmbLineStyle", u"rbKeepLines", u"rbDeleteLines",
              u"chkSelectResult"]

# ==============================================================================
# SELECTION FILTER & UTILITIES
# ==============================================================================

class CurveSelectionFilter(UI.Selection.ISelectionFilter):
    """Filtro di selezione per accettare solo elementi geometrici basati su linee/curve."""
    def AllowElement(self, elem):
        if not elem:
            return False
        if isinstance(elem, (DB.DetailCurve, DB.ModelCurve, DB.CurveElement)):
            return True
        cat = elem.Category
        if cat and cat.Id.IntegerValue in (int(DB.BuiltInCategory.OST_Lines), int(DB.BuiltInCategory.OST_SketchLines)):
            return True
        return False

    def AllowReference(self, reference, position):
        return True


def get_id_val(elem_id):
    """Restituisce il valore intero dell'ElementId."""
    if elem_id is None:
        return None
    if hasattr(elem_id, 'Value'):
        return elem_id.Value
    elif hasattr(elem_id, 'IntegerValue'):
        return elem_id.IntegerValue
    try:
        return int(elem_id)
    except Exception:
        return None


def get_element_name(elem):
    """Estrae in modo affidabile il nome da un elemento Revit."""
    if not elem:
        return ""
    try:
        p = elem.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_NAME)
        if p and p.AsString():
            return p.AsString()
    except Exception:
        pass
    try:
        p = elem.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
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


# ==============================================================================
# UNIT PARSER
# ==============================================================================

def parse_offset_to_feet(input_str, default_unit="mm"):
    """Converte una stringa di testo (es. 1500mm, 150cm, 1.50m, 1,5m) in piedi (feet interni Revit).
    
    Restituisce (valore_in_piedi, stringa_formattata_display).
    """
    if not input_str:
        raise ValueError("Valore di offset vuoto.")

    cleaned = input_str.strip().replace(" ", "").replace(",", ".")
    
    match = re.match(r"^([0-9\.]+)\s*([a-zA-Z\"']*)$", cleaned)
    if not match:
        raise ValueError("Formato offset non valido: '{}'.".format(input_str))

    num_str, unit_str = match.groups()
    try:
        val = float(num_str)
    except Exception:
        raise ValueError("Valore numerico non valido: '{}'.".format(num_str))

    if val <= 0:
        raise ValueError("L'offset deve essere maggiore di zero.")

    unit = unit_str.lower()
    if unit in ("mm", "millimetri"):
        feet = val / 304.8
        display = "{} mm ({:.3f} m)".format(int(val) if val.is_integer() else val, val / 1000.0)
    elif unit in ("cm", "centimetri"):
        feet = (val * 10.0) / 304.8
        display = "{} cm ({:.3f} m)".format(int(val) if val.is_integer() else val, val / 100.0)
    elif unit in ("m", "metri", "mt"):
        feet = (val * 1000.0) / 304.8
        display = "{} m".format(val)
    elif unit in ("in", '"', "inch"):
        feet = val / 12.0
        display = '{}" ({:.1f} mm)'.format(val, val * 25.4)
    elif unit in ("ft", "'", "feet"):
        feet = val
        display = "{} ft".format(val)
    else:
        # Default mm
        feet = val / 304.8
        display = "{} mm (default)".format(val)

    return feet, display


# ==============================================================================
# GEOMETRIC ALGORITHMS & OFFSET ENGINE
# ==============================================================================

def get_curve_from_element(elem):
    """Estrae la curva geometrica da un elemento di linea/curva di Revit."""
    if hasattr(elem, "GeometryCurve") and elem.GeometryCurve is not None:
        return elem.GeometryCurve
    return None


def sort_and_chain_curves(curves, tolerance=0.002):
    """Ordina una lista di curve in una o piu catene connesse e coerentemente orientate.
    
    Restituisce una lista di catene, dove ogni catena e (curves_list, is_closed).
    """
    if not curves:
        return []

    remaining = list(curves)
    chains = []

    while remaining:
        current_chain = [remaining.pop(0)]
        
        # Estendi in avanti
        extended = True
        while extended:
            extended = False
            last_pt = current_chain[-1].GetEndPoint(1)
            
            for i, c in enumerate(remaining):
                p0 = c.GetEndPoint(0)
                p1 = c.GetEndPoint(1)
                
                if last_pt.DistanceTo(p0) <= tolerance:
                    current_chain.append(c)
                    remaining.pop(i)
                    extended = True
                    break
                elif last_pt.DistanceTo(p1) <= tolerance:
                    current_chain.append(c.CreateReversed())
                    remaining.pop(i)
                    extended = True
                    break
        
        # Estendi all'indietro
        extended = True
        while extended:
            extended = False
            first_pt = current_chain[0].GetEndPoint(0)
            
            for i, c in enumerate(remaining):
                p0 = c.GetEndPoint(0)
                p1 = c.GetEndPoint(1)
                
                if first_pt.DistanceTo(p1) <= tolerance:
                    current_chain.insert(0, c)
                    remaining.pop(i)
                    extended = True
                    break
                elif first_pt.DistanceTo(p0) <= tolerance:
                    current_chain.insert(0, c.CreateReversed())
                    remaining.pop(i)
                    extended = True
                    break

        # Controlla se la catena e chiusa
        p_start = current_chain[0].GetEndPoint(0)
        p_end = current_chain[-1].GetEndPoint(1)
        is_closed = (p_start.DistanceTo(p_end) <= tolerance and len(current_chain) >= 3)

        chains.append((current_chain, is_closed))

    return chains


def compute_miter_point(p_prev, p_curr, p_next, d, view_dir):
    """Calcola il punto di intersezione miter 2D per il vertice p_curr tra due segmenti."""
    v1 = (p_curr - p_prev).Normalize()
    v2 = (p_next - p_curr).Normalize()

    n1 = view_dir.CrossProduct(v1).Normalize()
    n2 = view_dir.CrossProduct(v2).Normalize()

    # Rette traslate di d
    a1 = p_curr + d * n1
    a2 = p_curr + d * n2

    det = (v1.CrossProduct(v2)).DotProduct(view_dir)

    if abs(det) > 1e-5:
        t = ((a2 - a1).CrossProduct(v2)).DotProduct(view_dir) / det
        miter_pt = a1 + t * v1
        
        # Protezione miter eccessivo (angoli molto acuti)
        dist = miter_pt.DistanceTo(p_curr)
        if dist > 5.0 * abs(d):
            bisector = (n1 + n2).Normalize()
            miter_pt = p_curr + d * bisector
        return miter_pt
    else:
        # Segmenti paralleli/collineari
        return p_curr + d * n1


def offset_straight_line_chain(chain_curves, d, view_dir, is_closed):
    """Genera la catena di linee offset con raccordi angolari miter puliti."""
    pts = [chain_curves[0].GetEndPoint(0)]
    for c in chain_curves:
        pts.append(c.GetEndPoint(1))

    num_pts = len(pts)
    offset_pts = []

    if is_closed:
        # Catena chiusa
        pts_unique = pts[:-1]
        n = len(pts_unique)
        for i in range(n):
            p_prev = pts_unique[(i - 1 + n) % n]
            p_curr = pts_unique[i]
            p_next = pts_unique[(i + 1) % n]
            q = compute_miter_point(p_prev, p_curr, p_next, d, view_dir)
            offset_pts.append(q)
        offset_pts.append(offset_pts[0])
    else:
        # Catena aperta
        v0 = (pts[1] - pts[0]).Normalize()
        n0 = view_dir.CrossProduct(v0).Normalize()
        offset_pts.append(pts[0] + d * n0)

        for i in range(1, num_pts - 1):
            q = compute_miter_point(pts[i - 1], pts[i], pts[i + 1], d, view_dir)
            offset_pts.append(q)

        vend = (pts[-1] - pts[-2]).Normalize()
        nend = view_dir.CrossProduct(vend).Normalize()
        offset_pts.append(pts[-1] + d * nend)

    offset_curves = []
    for i in range(len(offset_pts) - 1):
        p_start = offset_pts[i]
        p_end = offset_pts[i + 1]
        if p_start.DistanceTo(p_end) > 0.001:
            offset_curves.append(DB.Line.CreateBound(p_start, p_end))

    return offset_curves


def offset_general_curve_chain(chain_curves, d, view_dir, is_closed):
    """Esegue l'offset su catene generiche (comprese curve/archi)."""
    all_lines = all(isinstance(c, DB.Line) for c in chain_curves)
    if all_lines:
        return offset_straight_line_chain(chain_curves, d, view_dir, is_closed)

    offset_curves = []
    for c in chain_curves:
        try:
            oc = c.CreateOffset(d, view_dir)
            if oc:
                offset_curves.append(oc)
            else:
                if isinstance(c, DB.Line):
                    v = (c.GetEndPoint(1) - c.GetEndPoint(0)).Normalize()
                    n = view_dir.CrossProduct(v).Normalize()
                    offset_curves.append(DB.Line.CreateBound(c.GetEndPoint(0) + d * n, c.GetEndPoint(1) + d * n))
        except Exception:
            if isinstance(c, DB.Line):
                v = (c.GetEndPoint(1) - c.GetEndPoint(0)).Normalize()
                n = view_dir.CrossProduct(v).Normalize()
                offset_curves.append(DB.Line.CreateBound(c.GetEndPoint(0) + d * n, c.GetEndPoint(1) + d * n))

    connected_curves = []
    for i in range(len(offset_curves)):
        c_curr = offset_curves[i]
        connected_curves.append(c_curr)
        if i < len(offset_curves) - 1:
            c_next = offset_curves[i + 1]
            p_end = c_curr.GetEndPoint(1)
            p_start_next = c_next.GetEndPoint(0)
            gap = p_end.DistanceTo(p_start_next)
            if 0.001 < gap < 1.0:
                connected_curves.append(DB.Line.CreateBound(p_end, p_start_next))

    return connected_curves


def build_filled_region_curveloops(chain_curves, is_closed, offset_dist, side_mode, view_dir, closed_donut=True, tolerance=0.002):
    """Costruisce i CurveLoop chiusi per la creazione della FilledRegion."""
    loops = List[DB.CurveLoop]()

    if is_closed:
        if side_mode == "both":
            half_w = offset_dist / 2.0
            outer_curves = offset_general_curve_chain(chain_curves, half_w, view_dir, True)
            inner_curves = offset_general_curve_chain(chain_curves, -half_w, view_dir, True)
            
            loop_outer = sanitize_and_create_curveloop(outer_curves, tolerance)
            loop_inner = sanitize_and_create_curveloop(inner_curves, tolerance)
            
            if closed_donut and loop_outer and loop_inner:
                loops.Add(loop_outer)
                loops.Add(loop_inner)
            elif loop_outer:
                loops.Add(loop_outer)
        elif side_mode == "left":
            offset_curves = offset_general_curve_chain(chain_curves, offset_dist, view_dir, True)
            loop_offset = sanitize_and_create_curveloop(offset_curves, tolerance)
            loop_orig = sanitize_and_create_curveloop(chain_curves, tolerance)
            if closed_donut and loop_offset and loop_orig:
                loops.Add(loop_offset)
                loops.Add(loop_orig)
            elif loop_offset:
                loops.Add(loop_offset)
        else: # right
            offset_curves = offset_general_curve_chain(chain_curves, -offset_dist, view_dir, True)
            loop_offset = sanitize_and_create_curveloop(offset_curves, tolerance)
            loop_orig = sanitize_and_create_curveloop(chain_curves, tolerance)
            if closed_donut and loop_offset and loop_orig:
                loops.Add(loop_orig)
                loops.Add(loop_offset)
            elif loop_offset:
                loops.Add(loop_offset)

    else:
        all_loop_curves = []

        if side_mode == "both":
            half_w = offset_dist / 2.0
            left_curves = offset_general_curve_chain(chain_curves, half_w, view_dir, False)
            right_curves = offset_general_curve_chain(chain_curves, -half_w, view_dir, False)

            if not left_curves or not right_curves:
                return []

            # 1. Catena sinistra
            all_loop_curves.extend(left_curves)

            # 2. Testata finale
            pt_left_end = left_curves[-1].GetEndPoint(1)
            pt_right_end = right_curves[-1].GetEndPoint(1)
            if pt_left_end.DistanceTo(pt_right_end) > 0.001:
                all_loop_curves.append(DB.Line.CreateBound(pt_left_end, pt_right_end))

            # 3. Catena destra invertita
            for c in reversed(right_curves):
                all_loop_curves.append(c.CreateReversed())

            # 4. Testata iniziale
            pt_right_start = right_curves[0].GetEndPoint(0)
            pt_left_start = left_curves[0].GetEndPoint(0)
            if pt_right_start.DistanceTo(pt_left_start) > 0.001:
                all_loop_curves.append(DB.Line.CreateBound(pt_right_start, pt_left_start))

        elif side_mode == "left":
            left_curves = offset_general_curve_chain(chain_curves, offset_dist, view_dir, False)
            if not left_curves:
                return []

            all_loop_curves.extend(chain_curves)

            pt_orig_end = chain_curves[-1].GetEndPoint(1)
            pt_off_end = left_curves[-1].GetEndPoint(1)
            if pt_orig_end.DistanceTo(pt_off_end) > 0.001:
                all_loop_curves.append(DB.Line.CreateBound(pt_orig_end, pt_off_end))

            for c in reversed(left_curves):
                all_loop_curves.append(c.CreateReversed())

            pt_off_start = left_curves[0].GetEndPoint(0)
            pt_orig_start = chain_curves[0].GetEndPoint(0)
            if pt_off_start.DistanceTo(pt_orig_start) > 0.001:
                all_loop_curves.append(DB.Line.CreateBound(pt_off_start, pt_orig_start))

        else: # right
            right_curves = offset_general_curve_chain(chain_curves, -offset_dist, view_dir, False)
            if not right_curves:
                return []

            all_loop_curves.extend(chain_curves)

            pt_orig_end = chain_curves[-1].GetEndPoint(1)
            pt_off_end = right_curves[-1].GetEndPoint(1)
            if pt_orig_end.DistanceTo(pt_off_end) > 0.001:
                all_loop_curves.append(DB.Line.CreateBound(pt_orig_end, pt_off_end))

            for c in reversed(right_curves):
                all_loop_curves.append(c.CreateReversed())

            pt_off_start = right_curves[0].GetEndPoint(0)
            pt_orig_start = chain_curves[0].GetEndPoint(0)
            if pt_off_start.DistanceTo(pt_orig_start) > 0.001:
                all_loop_curves.append(DB.Line.CreateBound(pt_off_start, pt_orig_start))

        loop = sanitize_and_create_curveloop(all_loop_curves, tolerance)
        if loop:
            loops.Add(loop)

    return loops


def sanitize_and_create_curveloop(curve_list, tolerance=0.002):
    """Sanitizza una lista di curve consecutive per creare un CurveLoop valido e continuo in Revit."""
    if not curve_list or len(curve_list) < 3:
        return None

    doc = revit.doc
    min_len = doc.Application.ShortCurveTolerance if doc else 0.00256

    valid_curves = []
    for c in curve_list:
        if c.Length >= min_len:
            valid_curves.append(c)

    if len(valid_curves) < 3:
        return None

    sanitized = []
    num = len(valid_curves)
    for i in range(num):
        c_curr = valid_curves[i]
        c_next = valid_curves[(i + 1) % num]

        p_start = c_curr.GetEndPoint(0)
        p_end = c_curr.GetEndPoint(1)
        p_next_start = c_next.GetEndPoint(0)

        if p_end.DistanceTo(p_next_start) > 1e-7:
            if isinstance(c_curr, DB.Line):
                p_prev_end = sanitized[-1].GetEndPoint(1) if sanitized else p_start
                if p_prev_end.DistanceTo(p_next_start) >= min_len:
                    c_curr = DB.Line.CreateBound(p_prev_end, p_next_start)

        sanitized.append(c_curr)

    loop = DB.CurveLoop()
    for c in sanitized:
        if c.Length >= min_len:
            try:
                loop.Append(c)
            except Exception:
                pass

    if loop.IsOpen():
        try:
            first_pt = sanitized[0].GetEndPoint(0)
            last_pt = sanitized[-1].GetEndPoint(1)
            if first_pt.DistanceTo(last_pt) >= min_len:
                closing_line = DB.Line.CreateBound(last_pt, first_pt)
                loop.Append(closing_line)
        except Exception:
            pass

    return loop


# ==============================================================================
# UI ITEM WRAPPERS (WPF Friendly with ToString and Name property)
# ==============================================================================

class FilledRegionTypeItem(object):
    def __init__(self, fr_type):
        self.Type = fr_type
        self.Id = fr_type.Id
        self.Name = get_element_name(fr_type)

    def ToString(self):
        return self.Name

    def __str__(self):
        return self.Name

    def __repr__(self):
        return self.Name


class LineStyleItem(object):
    def __init__(self, gstyle):
        self.GraphicsStyle = gstyle
        self.Id = gstyle.Id
        self.Name = get_element_name(gstyle)

    def ToString(self):
        return self.Name

    def __str__(self):
        return self.Name

    def __repr__(self):
        return self.Name


# ==============================================================================
# MAIN WINDOW CLASS (WPF)
# ==============================================================================

class OffsetFilledRegionWindow(forms.WPFWindow):
    def __init__(self, xaml_file, selected_elements):
        forms.WPFWindow.__init__(self, SF.xaml(xaml_file), literal_string=True)
        self.doc = revit.doc
        self.uidoc = revit.uidoc
        self.view = revit.active_view
        self.selected_elements = list(selected_elements)
        self.esito = False

        self._init_data()
        self._bind_events()
        self._update_selection_summary()

    def _init_data(self):
        """Carica i Tipi di Campitura e gli Stili Linea disponibili nel documento."""
        # 1. Carica FilledRegionTypes
        fr_collector = DB.FilteredElementCollector(self.doc)\
            .OfClass(DB.FilledRegionType)\
            .WhereElementIsElementType()

        fr_items = []
        for frt in fr_collector:
            fr_items.append(FilledRegionTypeItem(frt))
        fr_items.sort(key=lambda x: x.Name.lower())

        self.cmbFilledRegionType.ItemsSource = fr_items
        if fr_items:
            self.cmbFilledRegionType.SelectedIndex = 0

        # 2. Carica Line Styles (Bordi)
        lines_cat = self.doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Lines)
        line_style_items = []
        seen_gs_ids = set()
        default_idx = 0

        if lines_cat and lines_cat.SubCategories:
            for sub_cat in lines_cat.SubCategories:
                try:
                    gs = sub_cat.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
                    if gs:
                        item = LineStyleItem(gs)
                        line_style_items.append(item)
                        seen_gs_ids.add(get_id_val(gs.Id))
                except Exception:
                    pass

        inv_cat_id = int(DB.BuiltInCategory.OST_InvisibleLines)
        for gs in DB.FilteredElementCollector(self.doc).OfClass(DB.GraphicsStyle):
            try:
                if gs.GraphicsStyleType == DB.GraphicsStyleType.Projection and gs.GraphicsStyleCategory:
                    if get_id_val(gs.GraphicsStyleCategory.Id) == inv_cat_id and get_id_val(gs.Id) not in seen_gs_ids:
                        line_style_items.append(LineStyleItem(gs))
                        seen_gs_ids.add(get_id_val(gs.Id))
            except Exception:
                pass

        line_style_items.sort(key=lambda x: x.Name.lower())
        self.cmbLineStyle.ItemsSource = line_style_items

        # Cerca '<Linee invisibili>' o '<Invisible lines>'
        for i, item in enumerate(line_style_items):
            lower_name = item.Name.lower()
            if "invisibil" in lower_name or "invisible" in lower_name:
                default_idx = i
                break
            elif "sottil" in lower_name or "thin" in lower_name:
                default_idx = i

        if line_style_items:
            self.cmbLineStyle.SelectedIndex = default_idx

    def _bind_events(self):
        """Collega i pulsanti e gli eventi dell'interfaccia."""
        self.btnReselect.Click += self._on_reselect_clicked
        self.btnApply.Click += self._on_apply_clicked
        self.btnCancel.Click += self._on_cancel_clicked

        # Preset buttons
        self.btnPreset500mm.Click += lambda s, e: self._set_offset_text("50 cm")
        self.btnPreset100cm.Click += lambda s, e: self._set_offset_text("100 cm")
        self.btnPreset150cm.Click += lambda s, e: self._set_offset_text("150 cm")
        self.btnPreset200cm.Click += lambda s, e: self._set_offset_text("200 cm")

    def _set_offset_text(self, text):
        self.txtOffset.Text = text

    def _update_selection_summary(self):
        """Aggiorna le etichette informative sugli elementi selezionati."""
        curve_elements = [e for e in self.selected_elements if get_curve_from_element(e) is not None]
        total_len = 0.0
        for e in curve_elements:
            c = get_curve_from_element(e)
            if c:
                total_len += c.Length

        total_len_m = total_len * 0.3048

        count = len(curve_elements)
        if count == 0:
            self.lblSelectionInfo.Text = "Nessuna linea valida selezionata"
            self.lblSelectionDetail.Text = "Usa 'Seleziona...' per scegliere le linee"
            self.lblStatus.Text = "Seleziona almeno una linea o polilinea."
        else:
            self.lblSelectionInfo.Text = "{} elementi selezionati (Lungh. tot: {:.2f} m)".format(count, total_len_m)
            types_str = ", ".join(set(e.GetType().Name for e in curve_elements))
            self.lblSelectionDetail.Text = "Tipi: {}".format(types_str)
            self.lblStatus.Text = "Pronto per generare la campitura."

    def _on_reselect_clicked(self, sender, e):
        """Permette all'utente di selezionare interattivamente le linee nel modello."""
        self.Hide()
        try:
            refs = self.uidoc.Selection.PickObjects(
                UI.Selection.ObjectType.Element,
                CurveSelectionFilter(),
                "Seleziona le linee di dettaglio o di modello per la campitura (Premi Fine / Esc al termine)"
            )
            if refs:
                self.selected_elements = [self.doc.GetElement(r.ElementId) for r in refs]
        except Exception:
            pass
        finally:
            self._update_selection_summary()
            self.ShowDialog()

    def _on_cancel_clicked(self, sender, e):
        self.Close()

    def _on_apply_clicked(self, sender, e):
        """Esegue il calcolo dell'offset e la creazione della FilledRegion."""
        MF.salva(self, _MEMORIA, _CONTROLLI)
        # 1. Valida selezione
        curve_elements = [el for el in self.selected_elements if get_curve_from_element(el) is not None]
        if not curve_elements:
            MessageBox.Show(
                "Nessuna linea o curva valida selezionata.\nUsa il pulsante 'Seleziona...' per indicare le linee.",
                "Selezione mancante",
                MessageBoxButton.OK,
                MessageBoxImage.Warning
            )
            return

        # 2. Valida offset
        try:
            offset_feet, display_str = parse_offset_to_feet(self.txtOffset.Text.strip())
        except ValueError as ex:
            MessageBox.Show(
                str(ex),
                "Valore Offset non valido",
                MessageBoxButton.OK,
                MessageBoxImage.Warning
            )
            self.txtOffset.Focus()
            return

        # 3. Determina modalita lato
        if self.rbBoth.IsChecked:
            side_mode = "both"
        elif self.rbLeft.IsChecked:
            side_mode = "left"
        else:
            side_mode = "right"

        closed_donut = bool(self.chkClosedDonut.IsChecked)
        keep_original = bool(self.rbKeepLines.IsChecked)
        select_result = bool(self.chkSelectResult.IsChecked)

        # 4. Tipo campitura e stile linea
        sel_fr_item = self.cmbFilledRegionType.SelectedItem
        if not sel_fr_item:
            MessageBox.Show("Seleziona un Tipo di Campitura (Filled Region Type).", "Attenzione", MessageBoxButton.OK, MessageBoxImage.Warning)
            return
        fr_type_id = sel_fr_item.Id

        sel_ls_item = self.cmbLineStyle.SelectedItem
        line_style_id = sel_ls_item.Id if sel_ls_item else None

        # 5. Geometria vista
        view = self.view
        view_dir = view.ViewDirection

        raw_curves = [get_curve_from_element(el) for el in curve_elements]
        chains = sort_and_chain_curves(raw_curves)

        if not chains:
            MessageBox.Show("Impossibile concatenare le curve selezionate in un percorso valido.", "Errore Geometria", MessageBoxButton.OK, MessageBoxImage.Error)
            return

        created_regions = []

        # 6. Esegui creazione con Transazione
        with revit.Transaction("Crea Campitura da Polilinea"):
            for chain_curves, is_closed in chains:
                loops = build_filled_region_curveloops(
                    chain_curves=chain_curves,
                    is_closed=is_closed,
                    offset_dist=offset_feet,
                    side_mode=side_mode,
                    view_dir=view_dir,
                    closed_donut=closed_donut
                )

                if not loops or loops.Count == 0:
                    continue

                try:
                    filled_region = DB.FilledRegion.Create(self.doc, fr_type_id, view.Id, loops)
                    if filled_region:
                        created_regions.append(filled_region)
                        
                        if line_style_id and line_style_id != DB.ElementId.InvalidElementId:
                            try:
                                filled_region.SetLineStyleId(line_style_id)
                            except Exception:
                                pass
                except Exception as ex:
                    script.get_logger().error("Errore creazione FilledRegion: {}".format(ex))

            # Elimina linee originali se richiesto
            if not keep_original:
                for el in curve_elements:
                    try:
                        self.doc.Delete(el.Id)
                    except Exception:
                        pass

        # 7. Risultato e feedback
        if created_regions:
            if select_result:
                try:
                    new_ids = List[DB.ElementId]([r.Id for r in created_regions])
                    self.uidoc.Selection.SetElementIds(new_ids)
                except Exception:
                    pass

            self.esito = True
            self.Close()
            lato = u"centrata" if side_mode == "both" else (u"a sinistra" if side_mode == "left" else u"a destra")
            AVW.mostra(u"Campiture create: %d · %s, offset %s %s (Maiusc+clic: impostazioni)"
                       % (len(created_regions), sel_fr_item.Name, display_str, lato))
        else:
            MessageBox.Show(
                "Non è stato possibile generare la campitura dalle curve fornite.\n"
                "Verifica che le linee formino un tracciato continuo nel piano della vista.",
                "Errore di Creazione",
                MessageBoxButton.OK,
                MessageBoxImage.Error
            )


# ==============================================================================
# ENTRY POINT
# ==============================================================================

def main():
    doc = revit.doc
    uidoc = revit.uidoc
    active_view = revit.active_view

    if active_view.ViewType in (DB.ViewType.ThreeD, DB.ViewType.Schedule, DB.ViewType.DrawingSheet, DB.ViewType.Internal):
        forms.alert(
            "Il comando richiede una vista grafica 2D attiva (Pianta, Prospetto, Sezione, Vista di Dettaglio o Disegno).\n\n"
            "Vista corrente: {} ({})".format(active_view.Name, active_view.ViewType),
            title="Vista non supportata",
            warn_icon=True
        )
        return

    selected_ids = uidoc.Selection.GetElementIds()
    selected_elements = []
    if selected_ids:
        for eid in selected_ids:
            elem = doc.GetElement(eid)
            if elem and get_curve_from_element(elem) is not None:
                selected_elements.append(elem)

    if not selected_elements:
        try:
            refs = uidoc.Selection.PickObjects(
                UI.Selection.ObjectType.Element,
                CurveSelectionFilter(),
                "Seleziona le linee di dettaglio o di modello per la campitura (Premi Fine / Esc al termine)"
            )
            if refs:
                selected_elements = [doc.GetElement(r.ElementId) for r in refs]
        except Exception:
            pass

    xaml_file = os.path.join(os.path.dirname(__file__), 'ui.xaml')
    window = OffsetFilledRegionWindow(xaml_file, selected_elements)
    ricordate = MF.ripristina(window, _MEMORIA, _CONTROLLI)
    if ricordate and selected_elements and not EXEC_PARAMS.config_mode:
        # esecuzione diretta; se qualcosa non va si apre la finestra per correggere
        window._on_apply_clicked(None, None)
        if window.esito:
            return
        window = OffsetFilledRegionWindow(xaml_file, selected_elements)
        MF.ripristina(window, _MEMORIA, _CONTROLLI)
    window.ShowDialog()


if __name__ == '__main__':
    main()
