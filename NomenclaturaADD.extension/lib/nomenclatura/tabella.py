# -*- coding: utf-8 -*-
"""Esportazione/importazione CSV (separatore ';', UTF-8 con BOM: si apre bene in Excel italiano).

Scritto a mano perche' il modulo csv di IronPython 2.7 non gestisce l'unicode.
"""
import io

COLONNE = [u"Id", u"Ambito", u"Campo", u"Categoria", u"Contesto", u"ValoreAttuale",
           u"Esito", u"Messaggio", u"Proposta", u"NuovoValore"]


def _cella(v):
    v = u"" if v is None else (v if isinstance(v, type(u"")) else u"%s" % v)
    return u'"' + v.replace(u'"', u'""') + u'"'


def scrivi_csv(percorso, righe):
    """righe: lista di dict con le chiavi di COLONNE."""
    with io.open(percorso, "w", encoding="utf-8-sig", newline=u"") as f:
        f.write(u";".join(COLONNE) + u"\r\n")
        for r in righe:
            f.write(u";".join(_cella(r.get(c)) for c in COLONNE) + u"\r\n")


def _dividi(testo, sep=u";"):
    righe, riga, cella, virg, i = [], [], [], False, 0
    n = len(testo)
    while i < n:
        c = testo[i]
        if virg:
            if c == u'"':
                if i + 1 < n and testo[i + 1] == u'"':
                    cella.append(u'"')
                    i += 1
                else:
                    virg = False
            else:
                cella.append(c)
        else:
            if c == u'"':
                virg = True
            elif c == sep:
                riga.append(u"".join(cella))
                cella = []
            elif c in u"\r\n":
                if c == u"\r" and i + 1 < n and testo[i + 1] == u"\n":
                    i += 1
                riga.append(u"".join(cella))
                cella = []
                if any(x for x in riga):
                    righe.append(riga)
                riga = []
            else:
                cella.append(c)
        i += 1
    if cella or riga:
        riga.append(u"".join(cella))
        if any(x for x in riga):
            righe.append(riga)
    return righe


def leggi_csv(percorso):
    with io.open(percorso, "r", encoding="utf-8-sig") as f:
        testo = f.read()
    sep = u";" if testo.split(u"\n", 1)[0].count(u";") >= testo.split(u"\n", 1)[0].count(u",") else u","
    righe = _dividi(testo, sep)
    if not righe:
        return []
    intest = [h.strip() for h in righe[0]]
    out = []
    for r in righe[1:]:
        out.append(dict((intest[i], r[i] if i < len(r) else u"") for i in range(len(intest))))
    return out
