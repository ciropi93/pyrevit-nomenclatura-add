# -*- coding: utf-8 -*-
"""Prova in Revit di tutti i preset del configuratore (per lo sviluppo).

La chiama l'indirizzo di pyRevit Routes registrato in startup.py:
http://localhost:48884/cdv-tools/infissi/prova/  (?nome=2 ante per uno solo)
Crea ogni famiglia in una cartella temporanea senza caricarla nel progetto e ritorna,
preset per preset, i problemi trovati e i messaggi di Revit. Ricarica i moduli degli
infissi a ogni chiamata, cosi' le modifiche al codice valgono senza ricaricare pyRevit.
"""
import os
import tempfile
import traceback

_MODULI = (u"schema", u"geometria", u"parametri", u"catalogo", u"revit_famiglia")


def _ricarica():
    import sys
    try:
        from importlib import reload as ricarica
    except ImportError:                     # IronPython 2.7
        import __builtin__
        ricarica = __builtin__.reload
    for nome in _MODULI:
        m = sys.modules.get(u"infissi." + nome)
        if m is not None:
            ricarica(m)


def prova(app, nomi=None, varianti=True):
    """[{nome, variante, esito, problemi, report|errore}] per ogni preset (e variante)."""
    _ricarica()
    from infissi import catalogo as C
    from infissi import revit_famiglia as RF
    from infissi import schema as S

    cartella = os.path.join(tempfile.gettempdir(), u"CDV infissi prova")
    if not os.path.isdir(cartella):
        os.makedirs(cartella)
    imp = C.carica_impostazioni()
    out = []
    for base in C.preimpostati():
        if nomi and base[u"nome"] not in nomi:
            continue
        prove = [(u"base", S.copia(base))]
        if varianti:
            s = S.copia(base)
            s[u"maniglie"] = True
            s[u"simbolo_pianta"] = u"continuo"
            prove.append((u"maniglie+pianta", s))
        for variante, schema in prove:
            voce = {u"nome": base[u"nome"], u"variante": variante}
            modello = C.trova_modello(schema[u"categoria"], [app.FamilyTemplatePath], imp)
            if not modello:
                voce.update(esito=u"errore", errore=u"modello famiglia non trovato")
                out.append(voce)
                continue
            percorso = os.path.join(cartella, u"%s %s.rfa" % (base[u"nome"], variante))
            try:
                famdoc, report = RF.crea_famiglia(app, modello, schema, percorso)
                famdoc.Close(False)
                problemi = RF.problemi(report)
                voce.update(esito=u"da controllare" if problemi else u"ok", problemi=problemi,
                            report=dict((k, v) for k, v in report.items() if v))
            except Exception as ex:
                voce.update(esito=u"errore", errore=u"%s" % ex, traccia=traceback.format_exc())
            out.append(voce)
    return out
