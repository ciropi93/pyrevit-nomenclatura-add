# -*- coding: utf-8 -*-
"""Icone originali di Revit per i comandi della palette, prese dal ribbon di Revit.

Non si copia nessun file: mentre Revit gira si cercano nel ribbon (AdWindows) i
pulsanti dei comandi di Revit e se ne usa l'immagine (16 px e 32 px). Il pulsante si
riconosce dall'id del comando (RevitCommandId di PostableCommand) o, in mancanza, dal
testo del pulsante. Se un'icona non si trova si tiene quella di CDV Tools.
"""
import clr
clr.AddReference("AdWindows")
clr.AddReference("RevitAPIUI")

from Autodesk.Revit import UI
from Autodesk.Windows import ComponentManager

import palette as PAL


def _voci_ribbon():
    """Tutti i pulsanti del ribbon (anche dentro split button, righe e pannelli a scomparsa)."""
    out = []

    def visita(item):
        out.append(item)
        figli = getattr(item, "Items", None)
        if figli is not None:
            for f in figli:
                visita(f)

    for tab in ComponentManager.Ribbon.Tabs:
        for pannello in tab.Panels:
            sorgente = getattr(pannello, "Source", None)
            if sorgente is None:
                continue
            for item in sorgente.Items:
                visita(item)
    return out


def _id_comando(nome):
    pc = getattr(UI.PostableCommand, nome, None)
    if pc is None:
        return None
    try:
        cid = UI.RevitCommandId.LookupPostableCommandId(pc)
    except Exception:
        return None
    return cid.Name if cid is not None else None


def _testo(item):
    t = getattr(item, "Text", None) or u""
    return u" ".join(t.split()).lower()


def icone_dal_ribbon():
    """{comando: (immagine piccola, immagine grande, come e' stata trovata)}."""
    voci = [v for v in _voci_ribbon()
            if getattr(v, "Image", None) is not None or getattr(v, "LargeImage", None) is not None]
    out = {}
    for comando, (postable, testi) in PAL.ICONE_REVIT.items():
        trovato, come = None, None
        for nome in postable:
            cid = _id_comando(nome)
            if not cid:
                continue
            cid_m = cid.upper()
            for v in voci:
                vid = (getattr(v, "Id", None) or u"").upper()
                if vid and (vid == cid_m or vid.endswith(cid_m)):
                    trovato, come = v, cid
                    break
            if trovato is not None:
                break
        if trovato is None:
            for t in testi:
                t = t.lower()
                for v in voci:
                    if _testo(v) == t:
                        trovato, come = v, u'testo "%s"' % v.Text
                        break
                if trovato is not None:
                    break
        if trovato is not None:
            piccola = trovato.Image or trovato.LargeImage
            grande = trovato.LargeImage or trovato.Image
            out[comando] = (piccola, grande, come)
    return out
