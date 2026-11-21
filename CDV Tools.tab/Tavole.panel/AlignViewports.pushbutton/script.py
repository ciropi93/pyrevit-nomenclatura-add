# -*- coding: utf-8 -*-
"""Allinea una vista in tavola sulle altre tavole.

La vista di riferimento e' quella selezionata in tavola (se nella tavola ce n'e' una sola,
quella). Si spuntano le tavole che contengono una vista dello stesso tipo: le viste
vengono spostate perche' il modello (fabbricato, griglie) cada nello stesso punto del
foglio. Opzioni (Maiusc+clic): centro del riquadro invece del modello, titolo, tipo.
"""
import clr

clr.AddReference('RevitAPI')
clr.AddReference('RevitAPIUI')

from Autodesk.Revit.DB import (
    FailureProcessingResult,
    FailureSeverity,
    FilteredElementCollector,
    IFailuresPreprocessor,
    Transaction,
    Viewport,
    ViewSheet,
    XYZ,
)
from Autodesk.Revit.UI.Selection import ISelectionFilter, ObjectType

from pyrevit import revit, EXEC_PARAMS
import avviso as AV
import avviso_wpf as AVW
import scelta_wpf as SCW

OPZIONI = [
    (u"chkAlignTitle", u"Porta il titolo nella stessa posizione", True),
    (u"chkAlignTitleLength", u"Stessa lunghezza della linea del titolo", True),
    (u"chkApplyType", u"Stesso tipo di vista in tavola (stile del titolo)", False),
    (u"chkAlignBoxCenter", u"Allinea il centro del riquadro invece delle coordinate del modello", False),
]


class WarningSwallower(IFailuresPreprocessor):
    def PreprocessFailures(self, failuresAccessor):
        for f in failuresAccessor.GetFailureMessages():
            if f.GetSeverity() == FailureSeverity.Warning:
                failuresAccessor.DeleteWarning(f)
        return FailureProcessingResult.Continue


class _SoloViste(ISelectionFilter):
    def AllowElement(self, el):
        return isinstance(el, Viewport)

    def AllowReference(self, ref, pos):
        return False


def vista_riferimento(doc, uidoc):
    for eid in uidoc.Selection.GetElementIds():
        el = doc.GetElement(eid)
        if isinstance(el, Viewport):
            return el
    tavola = doc.ActiveView
    if not isinstance(tavola, ViewSheet):
        return None
    ids = list(tavola.GetAllViewports())
    if len(ids) == 1:
        return doc.GetElement(ids[0])
    if not ids:
        return None
    try:
        ref = uidoc.Selection.PickObject(ObjectType.Element, _SoloViste(),
                                         u"Clicca la vista da usare come riferimento")
        return doc.GetElement(ref)
    except Exception:
        return None


def allinea(doc, src_vp, tgt_vp, opz):
    if not opz[u"chkAlignBoxCenter"] and src_vp.HasViewportTransforms() and tgt_vp.HasViewportTransforms():
        # stesso punto del modello nello stesso punto del foglio
        o_src = src_vp.GetProjectionToSheetTransform().Origin
        o_tgt = tgt_vp.GetProjectionToSheetTransform().Origin
        tgt_vp.SetBoxCenter(tgt_vp.GetBoxCenter() + XYZ(o_src.X - o_tgt.X, o_src.Y - o_tgt.Y, 0.0))
    else:
        c_src = src_vp.GetBoxCenter()
        tgt_vp.SetBoxCenter(XYZ(c_src.X, c_src.Y, tgt_vp.GetBoxCenter().Z))
    doc.Regenerate()
    if opz[u"chkAlignTitle"]:
        try:
            tgt_vp.LabelOffset = src_vp.LabelOffset
        except Exception:
            pass
    if opz[u"chkAlignTitleLength"]:
        try:
            tgt_vp.LabelLineLength = src_vp.LabelLineLength
        except Exception:
            pass
    if opz[u"chkApplyType"]:
        try:
            tgt_vp.ChangeTypeId(src_vp.GetTypeId())
        except Exception:
            pass


def main():
    doc = revit.doc
    uidoc = revit.uidoc
    src_vp = vista_riferimento(doc, uidoc)
    if src_vp is None:
        AVW.errore(u"Apri una tavola e seleziona la vista da usare come riferimento")
        return
    src_v = doc.GetElement(src_vp.ViewId)
    src_s = doc.GetElement(src_vp.SheetId)

    voci = []
    for s in FilteredElementCollector(doc).OfClass(ViewSheet):
        if s.Id == src_s.Id:
            continue
        for vpid in s.GetAllViewports():
            vp = doc.GetElement(vpid)
            v = doc.GetElement(vp.ViewId)
            if v is not None and v.ViewType == src_v.ViewType:
                voci.append((vp, u"%s - %s" % (s.SheetNumber, s.Name), v.Name))
    if not voci:
        AVW.errore(u"Nessun'altra tavola ha una vista dello stesso tipo")
        return
    voci.sort(key=lambda x: x[1])

    ris = SCW.scegli(
        titolo=u"Allinea viste su tavole",
        sottotitolo=u"come %s in %s" % (src_v.Name, src_s.SheetNumber),
        voci=voci,
        pulsante=(u"Allinea 1 vista", u"Allinea %d viste", u"Scegli le tavole"),
        opzioni=OPZIONI, memoria=u"allinea_viste_tavole", apri_opzioni=EXEC_PARAMS.config_mode,
        nota=u"Il modello (fabbricato, griglie) cade nello stesso punto del foglio.")
    if not ris:
        return
    viste, opz = ris

    t = Transaction(doc, u"Allinea viste su tavole")
    o = t.GetFailureHandlingOptions()
    o.SetFailuresPreprocessor(WarningSwallower())
    t.SetFailureHandlingOptions(o)
    fatte, errori = 0, []
    t.Start()
    try:
        for vp in viste:
            try:
                allinea(doc, src_vp, vp, opz)
                fatte += 1
            except Exception as ex:
                errori.append(u"%s: %s" % (doc.GetElement(vp.SheetId).SheetNumber, ex))
        t.Commit()
    except Exception as ex:
        t.RollBack()
        AVW.errore(u"Allineamento non riuscito: %s" % ex)
        return

    msg = u"Allineata 1 vista" if fatte == 1 else u"Allineate %d viste" % fatte
    if fatte and errori:
        AVW.attenzione(AV.con_errori(msg, errori))
    elif fatte:
        AVW.mostra(msg)
    else:
        AVW.errore(AV.con_errori(u"Nessuna vista allineata", errori))


if __name__ == "__main__":
    main()
