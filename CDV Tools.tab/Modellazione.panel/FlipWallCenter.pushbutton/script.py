# -*- coding: utf-8 -*-
"""Inverte (specchia) il muro mantenendo immobile il suo asse centrale geometrico.

A differenza delle freccette di default di Revit ("Modifica l'orientamento del muro")
che specchiano l'elemento rispetto alla sua Linea di Ubicazione (spostando il muro
se disegnato su filo esterno, interno o nucleo), questo comando esegue l'inversione
del lato esterno/interno mantenendo il muro perfettamente fisso sul proprio asse centrale.

Funzionalità:
- Clic normale: Inverte il muro sull'asse centrale e ripristina la Linea di Ubicazione originale.
- Shift + Clic: Inverte il muro sull'asse centrale e imposta la Linea di Ubicazione su Asse del Muro.
- Supporta selezione multipla di muri (pre-selezione o selezione interattiva se nessun muro è selezionato).
- Gestione automatica elementi bloccati (Pinned) e silenziamento avvisi Revit sui vincoli.
"""

import clr
clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import *
from Autodesk.Revit.UI import *
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException

from pyrevit import revit, DB, UI, forms

import avviso as AV
import avviso_wpf as AVW


class WarningSwallower(IFailuresPreprocessor):
    """Elimina silenziosamente gli avvisi non critici di Revit (es. rimappatura vincoli)."""
    def PreprocessFailures(self, failuresAccessor):
        failures = failuresAccessor.GetFailureMessages()
        for f in failures:
            if f.GetSeverity() == FailureSeverity.Warning:
                failuresAccessor.DeleteWarning(f)
        return FailureProcessingResult.Continue


class WallSelectionFilter(ISelectionFilter):
    """Filtro di selezione per accettare solo elementi di tipo Wall."""
    def AllowElement(self, elem):
        return isinstance(elem, Wall)

    def AllowReference(self, ref, point):
        return False


def main():
    doc = revit.doc
    uidoc = revit.uidoc

    if not doc or not uidoc:
        AVW.errore("Nessun documento attivo in Revit.")
        return

    # Rileva Shift-Click (per impostare permanentemente su Asse del Muro)
    shift_click = False
    try:
        shift_click = __shiftclick__
    except NameError:
        pass

    # 1. Recupera muri attualmente selezionati
    sel_ids = uidoc.Selection.GetElementIds()
    walls = []
    for el_id in sel_ids:
        el = doc.GetElement(el_id)
        if isinstance(el, Wall):
            walls.append(el)

    # 2. Se nessun muro è pre-selezionato, chiedi all'utente di selezionare uno o più muri
    if not walls:
        try:
            refs = uidoc.Selection.PickObjects(
                ObjectType.Element,
                WallSelectionFilter(),
                "Seleziona uno o più muri da specchiare sull'asse centrale (Esc per annullare)"
            )
            for ref in refs:
                el = doc.GetElement(ref.ElementId)
                if isinstance(el, Wall):
                    walls.append(el)
        except OperationCanceledException:
            return
        except Exception as ex:
            forms.alert("Errore durante la selezione: {}".format(ex), title="CDV Tools")
            return

    if not walls:
        return

    # 3. Esecuzione transazione per invertire i muri sull'asse centrale
    tx_title = "Inverti Muro su Asse Centrale"
    t = Transaction(doc, tx_title)
    opts = t.GetFailureHandlingOptions()
    opts.SetFailuresPreprocessor(WarningSwallower())
    t.SetFailureHandlingOptions(opts)

    success_count = 0
    skipped_groups = 0
    failed_walls = []

    t.Start()
    try:
        for wall in walls:
            try:
                # Se il muro appartiene a un gruppo, non può essere modificato singolarmente
                if wall.GroupId != ElementId.InvalidElementId:
                    skipped_groups += 1
                    continue

                # Gestione elemento bloccato (Pinned)
                was_pinned = wall.Pinned
                if was_pinned:
                    wall.Pinned = False

                loc_param = wall.get_Parameter(BuiltInParameter.WALL_KEY_REF_PARAM)
                has_loc = (loc_param is not None and not loc_param.IsReadOnly)
                orig_val = loc_param.AsInteger() if has_loc else 0

                # 1) Porta temporaneamente la Linea di Ubicazione a 0 (Asse del Muro / Wall Centerline)
                if has_loc and orig_val != 0:
                    loc_param.Set(0)
                    doc.Regenerate()

                # 2) Esegue il Flip sull'asse centrale
                wall.Flip()
                doc.Regenerate()

                # 3) Se non è Shift-Click, ripristina la Linea di Ubicazione originaria del muro
                if not shift_click and has_loc and orig_val != 0:
                    loc_param.Set(orig_val)
                    doc.Regenerate()

                # Ripristina stato Pinned se originariamente bloccato
                if was_pinned:
                    wall.Pinned = True

                success_count += 1
            except Exception as ex:
                wall_id_str = str(getattr(wall.Id, 'Value', getattr(wall.Id, 'IntegerValue', wall.Id)))
                failed_walls.append("ID {}: {}".format(wall_id_str, ex))

        t.Commit()
    except Exception as ex:
        t.RollBack()
        forms.alert("Si è verificato un errore durante l'inversione dei muri:\n{}".format(ex), title="CDV Tools")
        return

    # 4. Feedback finale all'utente
    if success_count > 0:
        if success_count == 1:
            msg = "Muro specchiato sull'asse centrale."
        else:
            msg = "{} muri specchiati sull'asse centrale.".format(success_count)

        if shift_click:
            msg += "\n(Linea di ubicazione impostata su Asse del Muro)"

        if skipped_groups > 0:
            msg += "\n({} muri in gruppi ignorati)".format(skipped_groups)

        if failed_walls:
            AVW.attenzione(AV.con_errori(msg, failed_walls))
        else:
            AVW.mostra(msg)
    elif skipped_groups > 0:
        AVW.errore("I muri selezionati fanno parte di un gruppo e non possono essere modificati singolarmente.")
    elif failed_walls:
        AVW.errore(AV.con_errori("Impossibile invertire i muri selezionati", failed_walls))


if __name__ == "__main__":
    main()
