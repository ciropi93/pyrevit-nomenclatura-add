# -*- coding: utf-8 -*-
"""Prova: palette con le icone originali di Revit (prese dal ribbon, nessun file copiato).

Mostra una finestra con:
  - un'anteprima della palette per un muro (fila fissa sopra, famiglie sotto, griglia
    "Trasforma" aperta) usando le icone di Revit dove ci sono;
  - per ogni strumento la nostra icona, quella di Revit e come e' stata trovata.
Non modifica il modello.
"""
from System.Windows import (CornerRadius, FontWeights, HorizontalAlignment, Thickness,
                            VerticalAlignment, Window, WindowStartupLocation)
from System.Windows.Controls import (Border, Image, Orientation, ScrollViewer, ScrollBarVisibility,
                                     StackPanel, TextBlock, WrapPanel)
from System.Windows.Media import BrushConverter, FontFamily, Geometry, Stretch
from System.Windows.Shapes import Path

from pyrevit import forms

import palette as PAL
import tasti_contestuali as TC
import icone_revit as IR

_PENNELLI = BrushConverter()

FISSA = [u"nascondi_elementi", u"nascondi_categoria", u"mezzitoni", u"copia_grafica", u"blocca"]
FAMIGLIE = [
    (u"Trasforma", [u"sposta", u"copia", u"ruota", u"specchia", u"serie", u"scala"]),
    (u"Forma", [u"allinea", u"offset", u"dividi", u"taglia_estendi", u"crea_simile"]),
    (u"Seleziona", [u"sel_tipo_vista", u"sel_tipo_progetto", u"sel_categoria_vista"]),
    (u"Isola", [u"isola_elementi", u"isola_categoria", u"ripristina_temporaneo"]),
]


def _colore(hex_):
    return _PENNELLI.ConvertFromString(hex_)


def _icona_nostra(cid, dim, colore="#0369A1"):
    p = Path()
    tracciato = PAL.PER_ID[cid].icona if cid in PAL.PER_ID else TC.ICONE.get(cid)
    p.Data = Geometry.Parse(tracciato or u"M2,2 H14 V14 H2 Z")
    p.Fill = _colore(colore)
    p.Width = dim
    p.Height = dim
    p.Stretch = Stretch.Uniform
    return p


def _icona(cid, revit, dim, grande=False, colore="#0369A1"):
    """Icona di Revit se trovata, altrimenti la nostra."""
    if cid in revit:
        img = Image()
        img.Source = revit[cid][1 if grande else 0]
        img.Width = dim
        img.Height = dim
        return img
    return _icona_nostra(cid, dim, colore)


def _testo(t, dim=11, colore="#0F172A", grassetto=False):
    tb = TextBlock()
    tb.Text = t
    tb.FontSize = dim
    tb.Foreground = _colore(colore)
    if grassetto:
        tb.FontWeight = FontWeights.SemiBold
    return tb


def _riquadro(figlio, sfondo="#FFFFFF", bordo="#CBD5E1", raggio=6, pad=4):
    b = Border()
    b.Child = figlio
    b.Background = _colore(sfondo)
    b.BorderBrush = _colore(bordo)
    b.BorderThickness = Thickness(1)
    b.CornerRadius = CornerRadius(raggio)
    b.Padding = Thickness(pad)
    b.HorizontalAlignment = HorizontalAlignment.Left
    return b


def _cella(contenuto, w, h, sfondo=None):
    b = Border()
    b.Width = w
    b.Height = h
    b.Margin = Thickness(1)
    b.CornerRadius = CornerRadius(4)
    if sfondo:
        b.Background = _colore(sfondo)
    contenuto.HorizontalAlignment = HorizontalAlignment.Center
    contenuto.VerticalAlignment = VerticalAlignment.Center
    b.Child = contenuto
    return b


def anteprima_palette(revit):
    """Fila fissa sopra, famiglie sotto (prima famiglia evidenziata) e griglia aperta."""
    pnl = StackPanel()
    fissa = StackPanel()
    fissa.Orientation = Orientation.Horizontal
    for cid in FISSA:
        fissa.Children.Add(_cella(_icona(cid, revit, 14, colore="#475569"), 20, 20))
    pnl.Children.Add(_riquadro(fissa, "#F1F5F9", "#F1F5F9", 4, 1))
    riga = StackPanel()
    riga.Orientation = Orientation.Horizontal
    riga.Margin = Thickness(0, 2, 0, 0)
    riga.Children.Add(_cella(_icona_nostra(TC.MURO_INVERTI, 16, "#FFFFFF"), 28, 26, "#0369A1"))
    for n, (_, ids) in enumerate(FAMIGLIE):
        riga.Children.Add(_cella(_icona(ids[0], revit, 16), 28, 26, "#E0F2FE" if n == 0 else None))
    pnl.Children.Add(riga)
    palette = _riquadro(pnl)

    griglia = WrapPanel()
    griglia.Width = 3 * 70
    for cid in FAMIGLIE[0][1]:
        cella = StackPanel()
        cella.Children.Add(_icona(cid, revit, 24, grande=True))
        t = _testo(PAL.PER_ID[cid].etichetta, 10.5)
        t.HorizontalAlignment = HorizontalAlignment.Center
        t.Margin = Thickness(0, 4, 0, 0)
        cella.Children.Add(t)
        griglia.Children.Add(_cella(cella, 68, 56))
    menu = StackPanel()
    menu.Children.Add(_testo(u"TRASFORMA", 10, "#64748B", True))
    menu.Children.Add(griglia)
    menu_b = _riquadro(menu, raggio=8, pad=6)
    menu_b.Margin = Thickness(0, 4, 0, 0)

    out = StackPanel()
    out.Children.Add(palette)
    out.Children.Add(menu_b)
    return out


def confronto(revit):
    wrap = WrapPanel()
    for c in PAL.CATALOGO:
        riga = StackPanel()
        riga.Orientation = Orientation.Horizontal
        riga.Children.Add(_cella(_icona_nostra(c.id, 18), 26, 26))
        if c.id in revit:
            riga.Children.Add(_cella(_icona(c.id, revit, 20, grande=True), 26, 26, "#F1F5F9"))
        else:
            riga.Children.Add(_cella(_testo(u"—", 12, "#94A3B8"), 26, 26, "#F1F5F9"))
        nomi = StackPanel()
        nomi.Margin = Thickness(6, 0, 0, 0)
        nomi.VerticalAlignment = VerticalAlignment.Center
        nomi.Children.Add(_testo(c.etichetta, 11.5))
        nomi.Children.Add(_testo(revit[c.id][2] if c.id in revit else u"icona di Revit non trovata",
                                 9.5, "#16A34A" if c.id in revit else "#94A3B8"))
        riga.Children.Add(nomi)
        b = Border()
        b.Width = 300
        b.Margin = Thickness(0, 2, 8, 2)
        b.Child = riga
        wrap.Children.Add(b)
    return wrap


def main():
    try:
        revit = IR.icone_dal_ribbon()
    except Exception as ex:
        forms.alert(u"Non riesco a leggere le icone dal ribbon di Revit:\n%s" % ex, title=u"CDV Tools")
        return
    corpo = StackPanel()
    corpo.Margin = Thickness(16)
    corpo.Children.Add(_testo(u"Prova icone Revit", 16, grassetto=True))
    sotto = _testo(u"Trovate %d icone di Revit su %d strumenti che esistono anche in Revit. "
                   u"Dove manca resta la nostra." % (len(revit), len(PAL.ICONE_REVIT)), 12, "#475569")
    sotto.Margin = Thickness(0, 2, 0, 12)
    corpo.Children.Add(sotto)
    corpo.Children.Add(_testo(u"Anteprima: muro selezionato, mouse su Trasforma", 12, "#334155", True))
    ant = anteprima_palette(revit)
    ant.Margin = Thickness(0, 6, 0, 16)
    corpo.Children.Add(ant)
    corpo.Children.Add(_testo(u"Confronto: nostra | Revit", 12, "#334155", True))
    conf = confronto(revit)
    conf.Margin = Thickness(0, 6, 0, 0)
    corpo.Children.Add(conf)

    scorri = ScrollViewer()
    scorri.VerticalScrollBarVisibility = ScrollBarVisibility.Auto
    scorri.Content = corpo
    w = Window()
    w.Title = u"Prova icone Revit - CDV Tools"
    w.Width = 960
    w.Height = 720
    w.Background = _colore("#F8FAFC")
    w.FontFamily = FontFamily(u"Segoe UI")
    w.WindowStartupLocation = WindowStartupLocation.CenterScreen
    w.Content = scorri
    w.ShowDialog()


if __name__ == "__main__":
    main()
