# -*- coding: utf-8 -*-
"""Controllo della nomenclatura BIM ADD."""
from pyrevit import forms, revit, script

from nomenclatura import revit_dati as RD
from nomenclatura import ui

doc = revit.doc
ctx = ui.contesto(doc)
ambiti = ui.scegli_ambiti()
if not ambiti:
    script.exit()

voci = RD.raccogli(doc, ambiti, ctx)
problemi = ui.mostra_report(voci, doc, ctx)

if problemi and forms.alert(u"Trovati %d nomi da sistemare.\nVuoi esportare l'elenco in CSV "
                            u"(da modificare in Excel e reimportare)?" % len(problemi),
                            yes=True, no=True):
    percorso = ui.esporta_csv(voci, RD.nome_file_modello(doc))
    if percorso:
        script.get_output().print_md(u"CSV salvato in `%s`" % percorso)
