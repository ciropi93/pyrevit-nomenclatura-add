"""Seleziona una famiglia di simbolo Nord e la ruota automaticamente per allinearla al Nord Reale del progetto (singola istanza o tutte le istanze nel modello)."""

import math
import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit.DB import (
    ElementId,
    ElementTransformUtils,
    FamilyInstance,
    FilteredElementCollector,
    Line,
    Transaction,
    XYZ,
)
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, forms


class FamilyInstanceSelectionFilter(ISelectionFilter):
    """Filtro per consentire la selezione di sole istanze di famiglia."""

    def AllowElement(self, elem):
        return isinstance(elem, FamilyInstance)

    def AllowReference(self, ref, point):
        return False


def get_true_north_vector(doc):
    """Restituisce il vettore unitario del Nord Reale nelle coordinate di modello e l'angolo in gradi."""
    pos = doc.ActiveProjectLocation.GetProjectPosition(XYZ.Zero)
    angle_rad = pos.Angle
    angle_deg = math.degrees(angle_rad) % 360.0
    vec = XYZ(math.sin(angle_rad), math.cos(angle_rad), 0.0)
    return vec, angle_deg


def align_instance_to_vector(doc, fi, target_vec):
    """Ruota un'istanza di famiglia sul piano XY per allineare FacingOrientation a target_vec."""
    if not hasattr(fi, "Location") or not hasattr(fi.Location, "Point") or fi.Location.Point is None:
        return False
    if fi.FacingOrientation is None or fi.FacingOrientation.GetLength() < 1e-9:
        return False

    cur = XYZ(fi.FacingOrientation.X, fi.FacingOrientation.Y, 0.0)
    if cur.GetLength() < 1e-9:
        return False
    cur = cur.Normalize()

    delta = math.atan2(cur.CrossProduct(target_vec).Z, cur.DotProduct(target_vec))
    if abs(delta) < 1e-6:
        return True

    was_pinned = fi.Pinned
    if was_pinned:
        fi.Pinned = False

    pt = fi.Location.Point
    axis = Line.CreateBound(pt, pt + XYZ.BasisZ)
    ElementTransformUtils.RotateElement(doc, fi.Id, axis, delta)

    if was_pinned:
        fi.Pinned = True

    return True


def main():
    doc = revit.doc
    uidoc = revit.uidoc

    if not doc or not uidoc or doc.IsFamilyDocument:
        forms.alert("Apri un documento di progetto per utilizzare questo comando.", title="CDV Tools - Allinea Nord Reale")
        return

    selected_fi = None
    sel_ids = list(uidoc.Selection.GetElementIds())
    for el_id in sel_ids:
        el = doc.GetElement(el_id)
        if isinstance(el, FamilyInstance):
            selected_fi = el
            break

    if selected_fi is None:
        forms.alert(
            "Clicca OK e seleziona nella vista la famiglia (Freccia Nord) da allineare al Nord Reale.",
            title="CDV Tools - Allinea Nord Reale"
        )
        try:
            ref = uidoc.Selection.PickObject(
                ObjectType.Element,
                FamilyInstanceSelectionFilter(),
                "Seleziona la famiglia da allineare al Nord Reale (Esc per annullare)"
            )
            selected_fi = doc.GetElement(ref.ElementId)
        except OperationCanceledException:
            return
        except Exception as ex:
            forms.alert("Errore durante la selezione: {}".format(ex), title="CDV Tools")
            return

    if not selected_fi or not selected_fi.Symbol:
        return

    fam_name = selected_fi.Symbol.Family.Name
    opt_all = "Tutte le istanze di '{}' nel progetto".format(fam_name)
    opt_single = "Solo l'istanza selezionata"

    choice = forms.CommandSwitchWindow.show(
        [opt_all, opt_single],
        message="Quali istanze di '{}' vuoi allineare al Nord Reale?".format(fam_name)
    )
    if not choice:
        return

    if choice == opt_all:
        targets = [
            fi for fi in FilteredElementCollector(doc).OfClass(FamilyInstance)
            if fi.Symbol and fi.Symbol.Family.Name == fam_name
        ]
    else:
        targets = [selected_fi]

    target_vec, angle_deg = get_true_north_vector(doc)

    aligned_count = 0
    t = Transaction(doc, "Allinea Freccia Nord al Nord Reale")
    t.Start()
    try:
        for fi in targets:
            if fi.GroupId != ElementId.InvalidElementId:
                continue
            if align_instance_to_vector(doc, fi, target_vec):
                aligned_count += 1
        t.Commit()
    except Exception as ex:
        t.RollBack()
        forms.alert("Errore durante la rotazione:\n{}".format(ex), title="CDV Tools")
        return

    forms.alert(
        u"Allineate {} istanze di '{}' al Nord Reale ({:.2f}\u00b0).".format(aligned_count, fam_name, angle_deg),
        title="CDV Tools - Allinea Nord Reale"
    )


if __name__ == "__main__":
    main()
