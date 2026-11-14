# -*- coding: utf-8 -*-
"""Disegna in WPF le icone della palette (usato dall'overlay e da Personalizza Palette).

Un'icona e' una lista di livelli in un quadrato 16x16 (palette.ICONE):
  ("f", colore, tracciato)                     riempimento
  ("s", colore, tracciato, spessore[, trattino]) contorno (trattino in unita' 16x16)
oppure un solo tracciato (tasti_contestuali.ICONE), riempito con 'colore'.
Il quadrato viene scalato alla dimensione voluta con un Viewbox.
"""
import clr
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

from System.Windows.Controls import Canvas, Viewbox
from System.Windows.Media import BrushConverter, DoubleCollection, Geometry, PenLineCap
from System.Windows.Shapes import Path

_PENNELLI = BrushConverter()
_TESTO = (type(u""), type(""))


def colore(hex_):
    return _PENNELLI.ConvertFromString(hex_)


def _livelli(icona, colore_singolo):
    if isinstance(icona, _TESTO):
        return [(u"t", colore_singolo, icona)]
    return icona or []


def crea_icona(icona, dim, colore_singolo=u"#1F6FB2"):
    """Viewbox di lato 'dim' con l'icona disegnata."""
    tela = Canvas()
    tela.Width = 16
    tela.Height = 16
    for liv in _livelli(icona, colore_singolo):
        tipo, col, tracciato = liv[0], liv[1], liv[2]
        p = Path()
        if tipo == u"s":
            p.Data = Geometry.Parse(tracciato)
            p.Stroke = colore(col)
            spessore = float(liv[3]) if len(liv) > 3 else 1.0
            p.StrokeThickness = spessore
            p.StrokeStartLineCap = PenLineCap.Flat
            p.StrokeEndLineCap = PenLineCap.Flat
            if len(liv) > 4 and liv[4]:
                # in WPF il tratteggio si misura in spessori della linea
                tratti = DoubleCollection()
                for v in liv[4]:
                    tratti.Add(float(v) / spessore)
                p.StrokeDashArray = tratti
        else:
            # "f": riempimento pieno anche dove le forme si sovrappongono (come in SVG);
            # "t": tracciato singolo, la regola la decide il tracciato stesso (F1 o no)
            p.Data = Geometry.Parse(tracciato if tipo == u"t" or tracciato.startswith(u"F")
                                    else u"F1 " + tracciato)
            p.Fill = colore(col)
        tela.Children.Add(p)
    vb = Viewbox()
    vb.Width = dim
    vb.Height = dim
    vb.Child = tela
    return vb
