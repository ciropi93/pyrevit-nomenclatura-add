# -*- coding: utf-8 -*-
"""Correzioni automatiche della nomenclatura BIM ADD (con conferma)."""
from pyrevit import forms, revit, script

from nomenclatura import regole as R
from nomenclatura import revit_dati as RD
from nomenclatura import ui

doc = revit.doc
out = script.get_output()

ambiti = ui.scegli_ambiti(u"Cosa vuoi correggere?", escludi=("file",))
if not ambiti:
    script.exit()

ctx = R.Contesto()
voci = [v for v in RD.raccogli(doc, ambiti, ctx) if v.proposta and v.elemento is not None]
if not voci:
    forms.alert(u"Nessuna correzione automatica disponibile.\n"
                u"I nomi da rifare a mano si vedono con 'Controlla' (e si correggono in blocco con 'Importa CSV').")
    script.exit()

# Evita due proposte identiche nello stesso ambito (Revit rifiuterebbe il nome doppio)
viste = {}
for v in voci:
    viste.setdefault((v.campo, v.categoria, v.proposta), []).append(v)

righe = []
for v in voci:
    doppio = len(viste[(v.campo, v.categoria, v.proposta)]) > 1 and v.campo != RD.CAMPO_NOME_LOCALE
    testo = u"[%s] %s  ->  %s%s" % (v.ambito, v.valore, v.proposta, u"   (NOME DOPPIO)" if doppio else u"")
    righe.append((v, testo))

scelte = ui.scegli_righe(righe, u"Correzioni proposte: togli la spunta a quelle da non applicare",
                         u"Applica correzioni")
if not scelte:
    script.exit()

ok, errori = RD.applica_lista(doc, [(v.elemento, v.campo, v.proposta) for v in scelte])

out.print_md(u"# Correzioni applicate: %d" % len(ok))
if ok:
    out.print_table([[out.linkify(el.Id), campo, val] for el, campo, val in ok],
                    columns=[u"Id", u"Campo", u"Nuovo valore"])
if errori:
    out.print_md(u"## Non applicate: %d" % len(errori))
    out.print_table([[out.linkify(el.Id), campo, val, msg] for el, campo, val, msg in errori],
                    columns=[u"Id", u"Campo", u"Valore", u"Motivo"])
out.print_md(u"Per annullare tutto: **Ctrl+Z** (una sola transazione).")
