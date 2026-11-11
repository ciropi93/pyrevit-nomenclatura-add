# -*- coding: utf-8 -*-
"""Rinomina in blocco dal CSV modificato in Excel."""
from pyrevit import forms, revit, script

from nomenclatura import regole as R
from nomenclatura import revit_dati as RD
from nomenclatura import tabella as T
from nomenclatura import ui

doc = revit.doc
out = script.get_output()

percorso = forms.pick_file(file_ext="csv")
if not percorso:
    script.exit()

ctx = R.Contesto()
modifiche, scartate = [], []
for riga in T.leggi_csv(percorso):
    nuovo = (riga.get(u"NuovoValore") or u"").strip()
    campo = (riga.get(u"Campo") or u"").strip()
    attuale = riga.get(u"ValoreAttuale") or u""
    if not nuovo or nuovo == attuale:
        continue
    if campo == RD.CAMPO_FILE:
        scartate.append((u"-", campo, nuovo, u"il file si rinomina con 'Salva con nome'"))
        continue
    try:
        el = doc.GetElement(RD.nuovo_id(riga.get(u"Id")))
    except Exception:
        el = None
    if el is None:
        scartate.append((riga.get(u"Id"), campo, nuovo, u"elemento non trovato in questo modello"))
        continue
    if not RD.valido_per_revit(nuovo):
        scartate.append((riga.get(u"Id"), campo, nuovo, u"caratteri non accettati da Revit"))
        continue
    esito = RD.ricontrolla(campo, nuovo, el, ctx)
    modifiche.append((el, campo, nuovo, attuale, esito))

if not modifiche:
    forms.alert(u"Nel CSV non ci sono valori nuovi da applicare (colonna NuovoValore).")
    script.exit()

righe = []
for m in modifiche:
    el, campo, nuovo, attuale, esito = m
    righe.append((m, u"[%s] %s  ->  %s   (%s)" % (campo, attuale, nuovo, esito)))
scelte = ui.scegli_righe(righe, u"Rinomina da CSV: controlla l'elenco", u"Applica")
if not scelte:
    script.exit()

ok, errori = RD.applica_lista(doc, [(el, campo, nuovo) for el, campo, nuovo, _, _ in scelte],
                              titolo=u"Rinomina da CSV (nomenclatura ADD)")
out.print_md(u"# Rinominati: %d" % len(ok))
if ok:
    out.print_table([[out.linkify(el.Id), campo, val] for el, campo, val in ok],
                    columns=[u"Id", u"Campo", u"Nuovo valore"])
tutte = [(out.linkify(el.Id), c, v, msg) for el, c, v, msg in errori] + scartate
if tutte:
    out.print_md(u"## Non applicate: %d" % len(tutte))
    out.print_table([list(x) for x in tutte], columns=[u"Id", u"Campo", u"Valore", u"Motivo"])
out.print_md(u"Per annullare tutto: **Ctrl+Z**.")
