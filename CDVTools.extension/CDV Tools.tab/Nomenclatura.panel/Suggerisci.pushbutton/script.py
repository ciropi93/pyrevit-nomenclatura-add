# -*- coding: utf-8 -*-
"""Suggerisce i nomi codificati dai dati dei tipi e dei materiali."""
from Autodesk.Revit import DB
from pyrevit import forms, revit, script

from nomenclatura import regole as R
from nomenclatura import revit_dati as RD
from nomenclatura import suggerimenti as SG
from nomenclatura import ui

doc = revit.doc
out = script.get_output()
ctx = ui.contesto(doc)

scelta = forms.CommandSwitchWindow.show(
    [u"Tipi", u"Materiali", u"Tipi e materiali"],
    message=u"Cosa vuoi rinominare? (se hai selezionato elementi, uso solo i loro tipi)")
if not scelta:
    script.exit()

# Tipi: dalla selezione o tutti quelli usati delle categorie note
tipi = []
if u"Tipi" in scelta:
    sel = revit.get_selection().elements
    if sel:
        visti = set()
        for el in sel:
            t = el if isinstance(el, DB.ElementType) else doc.GetElement(el.GetTypeId())
            if t is not None and RD.id_valore(t.Id) not in visti:
                visti.add(RD.id_valore(t.Id))
                tipi.append(t)
    else:
        tipi = [t for t, bic, _ in RD._tipi_modello(doc, ctx) if bic in SG.CODICE_CATEGORIA]

occupati = set(RD.leggi_nome(t) for t in DB.FilteredElementCollector(doc).WhereElementIsElementType())
proposte = []  # (elemento, campo, valore attuale, proposta, nota)
for t in tipi:
    d = RD.dati_tipo(t, doc)
    attuale = d["nome"]
    gia_ok = not R.controlla_elemento(attuale, ctx).ha_errori and SG.controlla_coerenza(d, ctx).ok
    if gia_ok:
        continue
    p = SG.suggerisci_tipo(d, ctx, occupati)
    if p and p != attuale:
        occupati.add(p)
        proposte.append((t, RD.CAMPO_TIPO, attuale, p, t.Category.Name))

if u"ateriali" in scelta:
    nomi_mat = set()
    for m in DB.FilteredElementCollector(doc).OfClass(DB.Material):
        nome = RD.leggi_nome(m)
        if R.materiale_escluso(nome, ctx):
            continue
        p = SG.suggerisci_materiale(nome, RD.classe_materiale(m), ctx)
        if p and p not in nomi_mat:
            nomi_mat.add(p)
            proposte.append((m, RD.CAMPO_MATERIALE, nome, p, u"Materiali"))

if not proposte:
    forms.alert(u"Nessun suggerimento: i nomi sono gia' coerenti o mancano i dati "
                u"(es. strati con materiali non ancora codificati: rinomina prima i materiali).")
    script.exit()

righe = [(x, u"[%s] %s  ->  %s" % (x[4], x[2], x[3])) for x in proposte]
scelte = ui.scegli_righe(righe, u"Nomi suggeriti: togli la spunta a quelli da non usare",
                         u"Rinomina")
if not scelte:
    script.exit()

ok, errori = RD.applica_lista(doc, [(el, campo, p) for el, campo, _, p, _ in scelte],
                              titolo=u"Nomi suggeriti (nomenclatura ADD)")
out.print_md(u"# Rinominati: %d" % len(ok))
if ok:
    out.print_table([[out.linkify(el.Id), campo, val] for el, campo, val in ok],
                    columns=[u"Id", u"Campo", u"Nuovo valore"])
if errori:
    out.print_md(u"## Non applicati: %d" % len(errori))
    out.print_table([[out.linkify(el.Id), c, v, msg] for el, c, v, msg in errori],
                    columns=[u"Id", u"Campo", u"Valore", u"Motivo"])
out.print_md(u"Per annullare tutto: **Ctrl+Z**. Consiglio: rinomina prima i materiali, poi i tipi.")
