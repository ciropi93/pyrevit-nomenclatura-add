# -*- coding: utf-8 -*-
"""Azioni della palette fatte con le API di Revit: blocca, selezione rapida, visibilita'.

Ogni modifica al modello o alla vista sta in una transazione (annullabile con Ctrl+Z).
Le funzioni ricevono l'UIDocument e gli id selezionati e ritornano un messaggio breve
per l'utente; se l'azione non si puo' fare sollevano AzioneErrore con la spiegazione.
I comandi nativi di Revit (Sposta, Copia, ...) non passano da qui: li lancia l'overlay
con PostCommand.
"""
import clr
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

from System.Collections.Generic import List
from Autodesk.Revit import DB
from Autodesk.Revit.Exceptions import OperationCanceledException
from Autodesk.Revit.UI.Selection import ObjectType

import allinea_oggetti as AO


class AzioneErrore(Exception):
    pass


def _id_val(eid):
    v = getattr(eid, "Value", None)
    return v if v is not None else eid.IntegerValue


def _lista(ids):
    out = List[DB.ElementId]()
    for i in ids:
        out.Add(i)
    return out


def _transazione(doc, nome, fn):
    t = DB.Transaction(doc, nome)
    t.Start()
    try:
        risultato = fn()
        t.Commit()
        return risultato
    except Exception:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        raise


def angoli_ingombro(el, vista):
    """Gli 8 angoli (XYZ, coordinate del modello) dell'ingombro di un elemento nella vista;
    lista vuota se l'elemento non ha ingombro in quella vista."""
    bb = el.get_BoundingBox(vista)
    if bb is None:
        return []
    return [bb.Transform.OfPoint(DB.XYZ(x, y, z))
            for x in (bb.Min.X, bb.Max.X)
            for y in (bb.Min.Y, bb.Max.Y)
            for z in (bb.Min.Z, bb.Max.Z)]


def _elementi(doc, ids):
    return [e for e in (doc.GetElement(i) for i in ids) if e is not None]


def _categorie(elementi):
    visti = {}
    for e in elementi:
        if e.Category is not None:
            visti[_id_val(e.Category.Id)] = e.Category.Id
    return list(visti.values())


def _vista(doc):
    vista = doc.ActiveView
    if vista is None:
        raise AzioneErrore(u"Nessuna vista attiva.")
    return vista


# ==============================================================================
# MODIFICA
# ==============================================================================

def blocca(uidoc, ids):
    doc = uidoc.Document
    elementi = _elementi(doc, ids)
    tutti_bloccati = bool(elementi) and all(e.Pinned for e in elementi)
    nuovo = not tutti_bloccati

    def fn():
        n = 0
        for e in elementi:
            try:
                if e.Pinned != nuovo:
                    e.Pinned = nuovo
                n += 1
            except Exception:
                pass
        return n

    n = _transazione(doc, u"Palette: blocca/sblocca", fn)
    return u"%d elementi %s." % (n, u"bloccati" if nuovo else u"sbloccati")


# ==============================================================================
# SELEZIONE RAPIDA
# ==============================================================================

def _seleziona(uidoc, trovati):
    uidoc.Selection.SetElementIds(_lista(trovati))
    return u"%d elementi selezionati." % len(trovati)


def _raccolta(doc, elementi, solo_vista):
    coll = (DB.FilteredElementCollector(doc, doc.ActiveView.Id) if solo_vista
            else DB.FilteredElementCollector(doc))
    coll = coll.WhereElementIsNotElementType()
    cats = _categorie(elementi)
    if cats:
        coll = coll.WherePasses(DB.ElementMulticategoryFilter(_lista(cats)))
    return coll


def sel_tipo(uidoc, ids, solo_vista):
    doc = uidoc.Document
    elementi = _elementi(doc, ids)
    tipi = set()
    for e in elementi:
        t = e.GetTypeId()
        if t is not None and t != DB.ElementId.InvalidElementId:
            tipi.add(_id_val(t))
    if not tipi:
        raise AzioneErrore(u"Gli elementi selezionati non hanno un tipo.")
    trovati = [e.Id for e in _raccolta(doc, elementi, solo_vista)
               if _id_val(e.GetTypeId()) in tipi]
    return _seleziona(uidoc, trovati)


def sel_categoria_vista(uidoc, ids):
    doc = uidoc.Document
    elementi = _elementi(doc, ids)
    if not _categorie(elementi):
        raise AzioneErrore(u"Gli elementi selezionati non hanno una categoria.")
    trovati = [e.Id for e in _raccolta(doc, elementi, True)]
    return _seleziona(uidoc, trovati)


# ==============================================================================
# VISIBILITA' NELLA VISTA ATTIVA
# ==============================================================================

_MSG_MODELLO = (u"Non si può cambiare la visibilità in questa vista: probabilmente "
                u"è controllata da un modello di vista.")


def nascondi_elementi(uidoc, ids):
    doc = uidoc.Document
    vista = _vista(doc)
    nascondibili = [e.Id for e in _elementi(doc, ids) if e.CanBeHidden(vista)]
    if not nascondibili:
        raise AzioneErrore(u"Questi elementi non si possono nascondere in questa vista.")
    _transazione(doc, u"Palette: nascondi elementi",
                 lambda: vista.HideElements(_lista(nascondibili)))
    return u"%d elementi nascosti nella vista." % len(nascondibili)


def nascondi_categoria(uidoc, ids):
    doc = uidoc.Document
    vista = _vista(doc)
    cats = [c for c in _categorie(_elementi(doc, ids)) if vista.CanCategoryBeHidden(c)]
    if not cats:
        raise AzioneErrore(u"Questa categoria non si può nascondere in questa vista.")

    def fn():
        for c in cats:
            vista.SetCategoryHidden(c, True)

    try:
        _transazione(doc, u"Palette: nascondi categoria", fn)
    except Exception:
        raise AzioneErrore(_MSG_MODELLO)
    return u"Categoria nascosta nella vista." if len(cats) == 1 else \
        u"%d categorie nascoste nella vista." % len(cats)


def isola_elementi(uidoc, ids):
    doc = uidoc.Document
    vista = _vista(doc)
    _transazione(doc, u"Palette: isola elementi",
                 lambda: vista.IsolateElementsTemporary(_lista(list(ids))))
    return u"Elementi isolati (temporaneo)."


def isola_categoria(uidoc, ids):
    doc = uidoc.Document
    vista = _vista(doc)
    cats = _categorie(_elementi(doc, ids))
    if not cats:
        raise AzioneErrore(u"Gli elementi selezionati non hanno una categoria.")
    _transazione(doc, u"Palette: isola categoria",
                 lambda: vista.IsolateCategoriesTemporary(_lista(cats)))
    return u"Categorie isolate (temporaneo)."


def ripristina_temporaneo(uidoc, ids):
    doc = uidoc.Document
    vista = _vista(doc)
    _transazione(doc, u"Palette: ripristina nascondi/isola",
                 lambda: vista.DisableTemporaryViewMode(DB.TemporaryViewMode.TemporaryHideIsolate))
    return u"Nascondi/isola temporaneo tolto."


def mezzitoni(uidoc, ids):
    doc = uidoc.Document
    vista = _vista(doc)
    elementi = _elementi(doc, ids)
    if not elementi:
        raise AzioneErrore(u"Nessun elemento selezionato.")
    tutti = all(vista.GetElementOverrides(e.Id).Halftone for e in elementi)

    def fn():
        for e in elementi:
            ogs = vista.GetElementOverrides(e.Id)
            ogs.SetHalftone(not tutti)
            vista.SetElementOverrides(e.Id, ogs)

    try:
        _transazione(doc, u"Palette: mezzitoni", fn)
    except Exception:
        raise AzioneErrore(_MSG_MODELLO)
    return u"Mezzitoni tolti." if tutti else u"Mezzitoni attivati."


def _scegli(uidoc, messaggio):
    """Elemento cliccato dall'utente nella vista, o None con Esc."""
    try:
        ref = uidoc.Selection.PickObject(ObjectType.Element, messaggio)
    except OperationCanceledException:
        return None
    return uidoc.Document.GetElement(ref.ElementId)


def _applica_grafica(doc, vista, ids, ogs):
    def fn():
        for i in ids:
            vista.SetElementOverrides(i, ogs)
    try:
        _transazione(doc, u"Palette: copia grafica", fn)
    except Exception:
        raise AzioneErrore(_MSG_MODELLO)


def copia_grafica(uidoc, ids):
    """Come il matchprop di AutoCAD, per la grafica degli elementi nella vista attiva.

    Un elemento selezionato: e' la sorgente, poi si cliccano i destinatari uno alla
    volta (ognuno cambia subito, Esc per finire). Piu' elementi selezionati: si clicca
    la sorgente e la sua grafica va su tutti i selezionati.
    """
    doc = uidoc.Document
    vista = _vista(doc)
    elementi = _elementi(doc, ids)
    if not elementi:
        raise AzioneErrore(u"Nessun elemento selezionato.")
    if len(elementi) == 1:
        sorgente = elementi[0]
        ogs = vista.GetElementOverrides(sorgente.Id)
        n = 0
        while True:
            el = _scegli(uidoc, u"Copia grafica: clicca gli elementi a cui applicarla (Esc per finire)")
            if el is None:
                break
            if el.Id == sorgente.Id:
                continue
            _applica_grafica(doc, vista, [el.Id], ogs)
            n += 1
        return (u"Grafica copiata su %d elementi." % n) if n else None
    sorgente = _scegli(uidoc, u"Copia grafica: clicca l'elemento da cui copiarla (Esc per annullare)")
    if sorgente is None:
        return None
    ogs = vista.GetElementOverrides(sorgente.Id)
    destinatari = [e.Id for e in elementi if e.Id != sorgente.Id]
    _applica_grafica(doc, vista, destinatari, ogs)
    return u"Grafica copiata su %d elementi." % len(destinatari)


# ==============================================================================
# ALLINEA / DISTRIBUISCI OGGETTI NELLA VISTA
# ==============================================================================

MAX_GIRI_ALLINEA = 3


def _ingombri(doc, vista, per_id):
    """[(chiave, u_min, v_min, u_max, v_max)] nel piano della vista."""
    destra, alto = vista.RightDirection, vista.UpDirection
    out = []
    for k, eid in per_id.items():
        el = doc.GetElement(eid)
        punti = angoli_ingombro(el, vista) if el is not None else []
        if punti:
            us = [p.DotProduct(destra) for p in punti]
            vs = [p.DotProduct(alto) for p in punti]
            out.append((k, min(us), min(vs), max(us), max(vs)))
    return out


def allinea_oggetti(uidoc, comando):
    """Allinea o distribuisce gli oggetti selezionati nella vista attiva (annullabile).

    Un oggetto ne puo' trascinare altri selezionati (il muro la sua porta, l'elemento la
    sua etichetta): dopo il primo giro si rileggono gli ingombri e si corregge chi non e'
    arrivato al suo bersaglio, per al massimo MAX_GIRI_ALLINEA giri.
    """
    doc = uidoc.Document
    vista = _vista(doc)
    if not AO.vista_ammessa(str(vista.ViewType)):
        raise AzioneErrore(u"Allinea e Distribuisci funzionano in pianta, sezione, prospetto "
                           u"e viste di dettaglio, non in questa vista.")
    destra, alto = vista.RightDirection, vista.UpDirection
    per_id, saltati = {}, 0
    for eid in uidoc.Selection.GetElementIds():
        el = doc.GetElement(eid)
        if el is None:
            continue
        if el.Pinned or el.GroupId != DB.ElementId.InvalidElementId:
            saltati += 1
            continue
        per_id[_id_val(eid)] = eid
    iniziali = _ingombri(doc, vista, per_id)
    obiettivi = AO.bersagli(iniziali, comando)
    mosse = AO.spostamenti(iniziali, comando)
    spostati, falliti = set(), set()

    def fn():
        da_fare = mosse
        for _giro in range(MAX_GIRI_ALLINEA):
            if not da_fare:
                break
            for k, (du, dv) in da_fare.items():
                if k in falliti:
                    continue
                try:
                    DB.ElementTransformUtils.MoveElement(
                        doc, per_id[k], destra.Multiply(du).Add(alto.Multiply(dv)))
                    spostati.add(k)
                except Exception:
                    falliti.add(k)      # es. una porta non puo' uscire dal suo muro
            doc.Regenerate()
            da_fare = AO.residui(_ingombri(doc, vista, per_id), obiettivi, comando)

    if mosse:
        _transazione(doc, u"Palette: allinea oggetti", fn)
    spostati -= falliti
    if spostati:
        msg = u"%d oggetti spostati." % len(spostati)
    elif falliti:
        msg = u"Nessun oggetto spostato."
    else:
        msg = u"Gli oggetti erano già allineati."
    if falliti:
        msg += u"\n(%d non si possono spostare così)" % len(falliti)
    if saltati:
        msg += u"\n(%d bloccati o in gruppi: saltati)" % saltati
    return msg


AZIONI = {
    u"blocca": blocca,
    u"sel_tipo_vista": lambda uidoc, ids: sel_tipo(uidoc, ids, True),
    u"sel_tipo_progetto": lambda uidoc, ids: sel_tipo(uidoc, ids, False),
    u"sel_categoria_vista": sel_categoria_vista,
    u"nascondi_elementi": nascondi_elementi,
    u"nascondi_categoria": nascondi_categoria,
    u"isola_elementi": isola_elementi,
    u"isola_categoria": isola_categoria,
    u"ripristina_temporaneo": ripristina_temporaneo,
    u"mezzitoni": mezzitoni,
    u"copia_grafica": copia_grafica,
}


def esegui(uidoc, comando):
    """Esegue l'azione sulla selezione corrente; ritorna il messaggio per l'utente."""
    azione = AZIONI.get(comando)
    if azione is None:
        raise AzioneErrore(u"Comando sconosciuto: %s" % comando)
    ids = list(uidoc.Selection.GetElementIds())
    if not ids and comando != u"ripristina_temporaneo":
        raise AzioneErrore(u"Nessun elemento selezionato.")
    return azione(uidoc, ids)
