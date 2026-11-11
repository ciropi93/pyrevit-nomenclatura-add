# -*- coding: utf-8 -*-
"""Finestre e report comuni ai pulsanti (usa pyRevit)."""
from pyrevit import forms, script

from nomenclatura import regole as R
from nomenclatura import revit_dati as RD
from nomenclatura import tabella as T


class _VoceLista(forms.TemplateListItem):
    """Riga di una lista con casella di spunta e testo personalizzato."""

    def __init__(self, item, testo, checked=True):
        super(_VoceLista, self).__init__(item, checked=checked)
        self._testo = testo

    @property
    def name(self):
        return self._testo


def scegli_ambiti(titolo=u"Cosa vuoi controllare?", escludi=()):
    righe = [_VoceLista(k, etichetta) for k, etichetta in RD.AMBITI if k not in escludi]
    scelti = forms.SelectFromList.show(righe, title=titolo, multiselect=True,
                                       button_name=u"Avvia controllo", width=480, height=420)
    return scelti or []


def scegli_righe(righe_testo, titolo, pulsante):
    """righe_testo: lista di (oggetto, testo). Ritorna gli oggetti spuntati."""
    righe = [_VoceLista(o, t) for o, t in righe_testo]
    scelti = forms.SelectFromList.show(righe, title=titolo, multiselect=True,
                                       button_name=pulsante, width=900, height=600)
    return scelti or []


def riga_csv(v):
    return {
        u"Id": v.id,
        u"Ambito": v.ambito,
        u"Campo": v.campo,
        u"Categoria": v.categoria,
        u"Contesto": v.contesto,
        u"ValoreAttuale": v.valore,
        u"Esito": v.risultato.livello,
        u"Messaggio": v.risultato.messaggio(),
        u"Proposta": v.proposta or u"",
        u"NuovoValore": v.proposta or u"",
    }


def mostra_report(voci, doc):
    out = script.get_output()
    out.set_title(u"Controllo nomenclatura ADD")
    out.print_md(u"# Controllo nomenclatura ADD")
    out.print_md(u"Modello: **%s**" % RD.nome_file_modello(doc))

    # Riepilogo per ambito
    riepilogo = {}
    for v in voci:
        tot, err, avv = riepilogo.get(v.ambito, (0, 0, 0))
        liv = v.risultato.livello
        riepilogo[v.ambito] = (tot + 1, err + (liv == R.ERRORE), avv + (liv == R.AVVISO))
    righe = [[a, t, t - e - w, e, w] for a, (t, e, w) in sorted(riepilogo.items())]
    out.print_table(righe, columns=[u"Ambito", u"Controllati", u"OK", u"Errori", u"Avvisi"],
                    title=u"Riepilogo")

    problemi = [v for v in voci if not v.risultato.ok]
    if not problemi:
        out.print_md(u"**Nessun problema trovato.**")
        return problemi

    ordine = {R.ERRORE: 0, R.AVVISO: 1}
    problemi.sort(key=lambda v: (v.ambito, ordine.get(v.risultato.livello, 2), v.valore))
    tab = []
    for v in problemi:
        link = out.linkify(v.elemento.Id) if v.elemento is not None else u"-"
        tab.append([v.ambito, v.categoria, link, v.valore, v.risultato.livello,
                    v.risultato.messaggio(), v.proposta or u""])
    out.print_table(tab, columns=[u"Ambito", u"Categoria", u"Id", u"Nome attuale", u"Esito",
                                  u"Problema", u"Proposta"],
                    title=u"Nomi da sistemare (%d)" % len(problemi))
    con_proposta = len([v for v in problemi if v.proposta])
    out.print_md(u"Correzioni automatiche disponibili: **%d** (pulsante *Correggi*)." % con_proposta)
    return problemi


def esporta_csv(voci, solo_problemi=True):
    righe = [riga_csv(v) for v in voci if (not solo_problemi or not v.risultato.ok)]
    if not righe:
        return None
    percorso = forms.save_file(file_ext="csv", default_name="nomenclatura_ADD")
    if not percorso:
        return None
    T.scrivi_csv(percorso, righe)
    return percorso
