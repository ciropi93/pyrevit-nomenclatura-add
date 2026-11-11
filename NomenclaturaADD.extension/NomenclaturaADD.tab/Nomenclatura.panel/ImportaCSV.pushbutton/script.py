# -*- coding: utf-8 -*-
"""Rinomina in blocco dal CSV modificato in Excel."""
from pyrevit import forms, revit, script

from nomenclatura import regole as R
from nomenclatura import revit_dati as RD
from nomenclatura import tabella as T
from nomenclatura import ui

doc = revit.doc
out = script.get_output()

ctx = ui.contesto(doc)
percorso = forms.pick_file(file_ext="csv")
if not percorso:
    script.exit()

try:
    righe_csv = T.leggi_csv(percorso)
except Exception as ex:
    forms.alert(u"Impossibile leggere il CSV:\n%s" % ex)
    script.exit()

# Il CSV deve venire da questo modello: gli Id di un altro modello puntano ad altri elementi
modello = RD.nome_file_modello(doc)
altri_modelli = sorted(set((r.get(u"Modello") or u"").strip() for r in righe_csv) - set([u"", modello]))
if altri_modelli and not forms.alert(
        u"Il CSV e' stato esportato da:\n%s\n\nIl modello aperto e':\n%s\n\n"
        u"Gli Id potrebbero indicare elementi diversi. Le righe il cui valore attuale non coincide "
        u"verranno comunque scartate.\nContinuare?" % (u"\n".join(altri_modelli), modello),
        yes=True, no=True):
    script.exit()

modifiche, scartate = [], []
for riga in righe_csv:
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
    nel_modello = RD.leggi_valore(el, campo)
    if nel_modello is None:
        scartate.append((out.linkify(el.Id), campo, nuovo,
                         u"l'Id non corrisponde a un elemento di tipo '%s' (CSV di un altro modello?)" % campo))
        continue
    if nel_modello != attuale:
        scartate.append((out.linkify(el.Id), campo, nuovo,
                         u"nel modello il valore e' '%s', nel CSV '%s': riesporta il CSV" % (nel_modello, attuale)))
        continue
    if not RD.valido_per_revit(nuovo):
        scartate.append((out.linkify(el.Id), campo, nuovo, u"caratteri non accettati da Revit"))
        continue
    livello, esito = RD.ricontrolla(campo, nuovo, el, ctx)
    modifiche.append((el, campo, nuovo, attuale, livello, esito))

if not modifiche:
    msg = u"Nel CSV non ci sono valori nuovi da applicare (colonna NuovoValore)."
    if scartate:
        msg = u"Nessuna riga applicabile: %d scartate (vedi elenco nella finestra di output)." % len(scartate)
        out.print_table([list(x) for x in scartate], columns=[u"Id", u"Campo", u"Valore", u"Motivo"])
    forms.alert(msg)
    script.exit()

conflitti = RD.conflitti_nomi(doc, [(m[0], m[1], m[2]) for m in modifiche])
righe = []
for m, conflitto in zip(modifiche, conflitti):
    el, campo, nuovo, attuale, livello, esito = m
    testo = u"[%s] %s  ->  %s   (%s%s)" % (campo, attuale, nuovo, esito,
                                           u"; " + conflitto if conflitto else u"")
    # Non spuntate: valori che restano in errore o in conflitto con altri nomi
    righe.append((m, testo, livello != R.ERRORE and not conflitto))
scelte = ui.scegli_righe(righe, u"Rinomina da CSV: quelle non spuntate sono da verificare", u"Applica")
if not scelte:
    script.exit()

ok, errori = RD.applica_lista(doc, [(m[0], m[1], m[2]) for m in scelte],
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
