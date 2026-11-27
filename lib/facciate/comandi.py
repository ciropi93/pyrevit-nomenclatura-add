# -*- coding: utf-8 -*-
"""I due comandi delle facciate, usati dai pulsanti e dalla palette.

- ritmo: sulle curtain wall selezionate apre la finestra (con lo schema gia' applicato alla
  prima, se c'e', o l'ultimo usato) e applica lo schema a tutte;
- aggiorna: riapplica a ogni curtain wall selezionata il suo schema salvato (dopo averla
  stirata o cambiati i livelli); con Maiusc apre la finestra.
"""
import avviso as AV
import avviso_wpf as AVW
import memoria_finestre as MF

from facciate import revit_facciata as RV
from facciate import schema as S

MEMORIA = u"facciate"
ULTIMO = u"ultimo_schema"


def _selezione(uidoc):
    """Le curtain wall selezionate; None (con l'avviso) se non ce ne sono."""
    doc = uidoc.Document if uidoc is not None else None
    if doc is None or doc.IsFamilyDocument:
        AVW.errore(u"Apri un progetto (non una famiglia)")
        return None
    muri = RV.facciate_selezionate(uidoc)
    if not muri:
        AVW.errore(u"Seleziona una o più facciate continue (curtain wall), poi clicca")
        return None
    return muri


def _ultimo_schema():
    dati = MF.valore(MEMORIA, ULTIMO)
    if not dati:
        return None
    try:
        return S.normalizza(dati)
    except Exception:
        return None


def _mostra_esito(esito, titolo, saltati=()):
    voci = esito[u"muri"]
    ok = [v for v in voci if u"errore" not in v]
    problemi = [u"facciata %s: %s" % (v[u"muro"], v[u"errore"]) for v in voci if u"errore" in v]
    problemi += list(saltati)
    avvisi = sum(len(v[u"report"][u"avvisi"]) for v in ok)
    msg = u"%s: %d facciat%s" % (titolo, len(ok), u"a" if len(ok) == 1 else u"e")
    if avvisi:
        msg += u" (%d avvisi)" % avvisi
    if problemi:
        AVW.attenzione(AV.con_errori(msg, problemi))
    else:
        AVW.mostra(msg + u" (annullabile)", AV.INFO)


def ritmo(uidoc):
    """Finestra del ritmo sulle facciate selezionate; Applica le aggiorna tutte."""
    from facciate import ui as UI
    muri = _selezione(uidoc)
    if not muri:
        return
    doc = uidoc.Document
    validi, saltati = [], []
    for m in muri:
        try:
            validi.append((m, RV.leggi(doc, m)))
        except RV.FacciataErrore as ex:
            saltati.append(u"facciata %s: %s" % (RV.chiave_id(m.Id), ex))
    if not validi:
        AVW.errore(u"; ".join(saltati))
        return
    schema = RV.schema_salvato(validi[0][0]) or _ultimo_schema()
    nuovo = UI.apri(schema=schema, facciata=RV.dati_facciata(validi[0][1]),
                    tipi=RV.nomi_tipi(doc), n_muri=len(validi))
    if not nuovo:
        return
    MF.imposta_valore(MEMORIA, ULTIMO, nuovo)
    try:
        esito = RV.applica(doc, [m for m, _f in validi], nuovo)
    except Exception as ex:
        AVW.errore(u"Ritmo non applicato: %s" % ex)
        return
    _mostra_esito(esito, u"Ritmo \"%s\" applicato" % (nuovo.get(u"nome") or u"facciata"), saltati)


def aggiorna(uidoc, finestra=False):
    """Riapplica lo schema salvato su ogni facciata selezionata; finestra=True (Maiusc) apre
    la finestra del ritmo."""
    if finestra:
        return ritmo(uidoc)
    muri = _selezione(uidoc)
    if not muri:
        return
    coppie, saltati = [], []
    for m in muri:
        s = RV.schema_salvato(m)
        if s is None:
            saltati.append(u"facciata %s senza ritmo CDV" % RV.chiave_id(m.Id))
        else:
            coppie.append((m, s))
    if not coppie:
        AVW.errore(u"Nessuna facciata selezionata ha un ritmo CDV: usa Ritmo facciata")
        return
    try:
        esito = RV.applica_coppie(uidoc.Document, coppie, u"CDV Aggiorna facciata")
    except Exception as ex:
        AVW.errore(u"Facciate non aggiornate: %s" % ex)
        return
    _mostra_esito(esito, u"Facciate aggiornate", saltati)
