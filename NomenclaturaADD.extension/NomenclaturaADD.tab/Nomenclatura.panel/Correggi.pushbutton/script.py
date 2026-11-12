# -*- coding: utf-8 -*-
"""Correzioni automatiche della nomenclatura BIM ADD (con conferma)."""
from pyrevit import forms, revit, script

from nomenclatura import regole as R
from nomenclatura import revit_dati as RD
from nomenclatura import ui

doc = revit.doc
out = script.get_output()

ctx = ui.contesto(doc)
ambiti = ui.scegli_ambiti(u"Cosa vuoi correggere?", escludi=("file",))
if not ambiti:
    script.exit()

voci = [v for v in RD.raccogli(doc, ambiti, ctx) if v.proposta and v.elemento is not None]
if not voci:
    forms.alert(u"Nessuna correzione automatica disponibile.\n"
                u"I nomi da rifare a mano si vedono con 'Controlla' (e si correggono in blocco con 'Importa CSV').")
    script.exit()

# Nomi gia' usati da altri elementi o proposti due volte: Revit li rifiuterebbe
# (o, per numeri locale e contrassegni, la codifica non sarebbe piu' univoca).
conflitti = RD.conflitti_nomi(doc, [(v.elemento, v.campo, v.proposta) for v in voci])

righe = []
for v, conflitto in zip(voci, conflitti):
    avviso = v.risultato.livello == R.AVVISO
    note = [n for n in (conflitto, u"da AVVISO: verifica" if avviso else u"") if n]
    testo = u"[%s] %s  ->  %s%s" % (v.ambito, v.valore, v.proposta,
                                     u"   (%s)" % u"; ".join(note) if note else u"")
    # Spuntate solo le correzioni di errori senza conflitti
    righe.append((v, testo, not conflitto and not avviso))

scelte = ui.scegli_righe(righe, u"Correzioni proposte: quelle non spuntate sono da verificare",
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
