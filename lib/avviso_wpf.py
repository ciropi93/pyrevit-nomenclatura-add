# -*- coding: utf-8 -*-
"""Avviso piccolo in basso a destra nella vista attiva (la parte WPF; regole in avviso.py).

Uso: avviso_wpf.mostra(u"Mezzitoni attivati.")  oppure  mostra(testo, avviso.ERRORE)

Una sola finestra per tutto CDV Tools: ogni pulsante pyRevit gira in un motore Python suo,
quindi finestra e stato (ultimo testo, contatore) stanno nell'AppDomain di Revit e
vengono riusati da chi mostra il messaggio successivo. La finestra non prende il focus e
lascia passare i clic; dopo qualche secondo sfuma (animazione WPF, nessun timer Python).
Se qualcosa va storto ripiega sulla notifica di pyRevit.
"""
import clr
clr.AddReference("System")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

import System
from System import DateTime, Double, TimeSpan
from System.Collections import Hashtable
from System.Windows import Duration, Size, UIElement
from System.Windows.Interop import WindowInteropHelper
from System.Windows.Markup import XamlReader
from System.Windows.Media.Animation import DoubleAnimation

import avviso as AV
import finestre_wpf as FW

# Cambiare il numero se cambia lo XAML: al Reload si crea una finestra nuova
CHIAVE_APPDOMAIN = "CDVTools.Avviso.v1"
TITOLO = u"CDV Tools"

XAML = u"""
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        WindowStyle="None" AllowsTransparency="True" Background="Transparent"
        ShowInTaskbar="False" ShowActivated="False" ResizeMode="NoResize"
        SizeToContent="WidthAndHeight" IsHitTestVisible="False"
        FontFamily="Segoe UI" FontSize="11">
  <StackPanel Orientation="Horizontal" Margin="4,3,4,3">
    <StackPanel.Effect>
      <DropShadowEffect Color="White" ShadowDepth="0" BlurRadius="5" Opacity="1"/>
    </StackPanel.Effect>
    <TextBlock x:Name="txtSimbolo" FontWeight="Bold" Margin="0,0,5,0"
               VerticalAlignment="Center"/>
    <TextBlock x:Name="txtTesto" MaxWidth="%d" TextTrimming="CharacterEllipsis"
               Foreground="%s" VerticalAlignment="Center"/>
  </StackPanel>
</Window>
""" % (AV.LARGHEZZA_MAX, AV.COLORE_TESTO)


def _uiapp_pyrevit():
    try:
        from pyrevit import HOST_APP
        return HOST_APP.uiapp
    except Exception:
        return None


def _rett_vista(uiapp):
    """(sinistra, alto, destra, basso) in pixel fisici: la vista attiva, se no Revit intero."""
    try:
        uidoc = uiapp.ActiveUIDocument
        vista = uidoc.ActiveView if uidoc is not None else None
        if vista is not None:
            for v in uidoc.GetOpenUIViews():
                if v.ViewId.Equals(vista.Id):
                    r = v.GetWindowRectangle()
                    return (float(r.Left), float(r.Top), float(r.Right), float(r.Bottom))
    except Exception:
        pass
    try:
        r = uiapp.MainWindowExtents
        return (float(r.Left), float(r.Top), float(r.Right), float(r.Bottom))
    except Exception:
        pass
    from System.Windows.Forms import Screen
    a = Screen.PrimaryScreen.WorkingArea
    return (float(a.Left), float(a.Top), float(a.Right), float(a.Bottom))


def _stato():
    dominio = System.AppDomain.CurrentDomain
    stato = dominio.GetData(CHIAVE_APPDOMAIN)
    if stato is None:
        stato = Hashtable()
        dominio.SetData(CHIAVE_APPDOMAIN, stato)
    return stato


def _nuova_finestra(uiapp):
    win = XamlReader.Parse(XAML)
    try:
        WindowInteropHelper(win).Owner = uiapp.MainWindowHandle
    except Exception:
        win.Topmost = True
    FW.non_attivabile(win, trasparente_ai_clic=True)
    return win


def _colore(hex_):
    from System.Windows.Media import BrushConverter
    return BrushConverter().ConvertFromString(hex_)


def _prepara(win, testo, livello):
    simbolo, colore = AV.STILI[livello]
    s = win.FindName("txtSimbolo")
    s.Text = simbolo
    s.Foreground = _colore(colore)
    win.FindName("txtTesto").Text = testo


def _mostra(testo, livello, uiapp):
    testo = AV.una_riga(testo)
    if not testo:
        return
    livello = AV.livello_valido(livello)
    uiapp = uiapp or _uiapp_pyrevit()
    stato = _stato()
    adesso = DateTime.Now

    # stesso messaggio mentre il precedente si vede ancora: contatore
    fine = stato["fine"]
    if (stato["testo"] == testo and stato["livello"] == livello
            and fine is not None and adesso < fine):
        conta = (stato["conta"] or 1) + 1
    else:
        conta = 1

    win = stato["win"]
    if win is None:
        win = _nuova_finestra(uiapp)
        stato["win"] = win
    _prepara(win, AV.testo_con_contatore(testo, conta), livello)

    # posizione: in basso a destra nella vista attiva (unita' WPF)
    k = FW.scala_dpi() or 1.0
    sx, alto, dx, basso = _rett_vista(uiapp)
    win.Content.Measure(Size(Double.PositiveInfinity, Double.PositiveInfinity))
    dim = win.Content.DesiredSize
    x, y = AV.posizione_avviso((sx / k, alto / k, dx / k, basso / k), dim.Width, dim.Height)
    win.Left = x
    win.Top = y

    # pieno per un po', poi sfuma (resta a opacita' 0, trasparente ai clic)
    durata = AV.durata_avviso(livello)
    win.BeginAnimation(UIElement.OpacityProperty, None)
    win.Opacity = 1.0
    anim = DoubleAnimation(1.0, 0.0, Duration(TimeSpan.FromMilliseconds(AV.DISSOLVENZA_MS)))
    anim.BeginTime = TimeSpan.FromMilliseconds(durata)
    if not win.IsVisible:
        win.Show()
    win.BeginAnimation(UIElement.OpacityProperty, anim)

    stato["testo"] = testo
    stato["livello"] = livello
    stato["conta"] = conta
    stato["fine"] = adesso.AddMilliseconds(durata + AV.DISSOLVENZA_MS)


def mostra(testo, livello=AV.INFO, uiapp=None):
    """Mostra l'avviso; non solleva mai eccezioni."""
    try:
        _mostra(testo, livello, uiapp)
        return
    except Exception:
        # finestra rovinata (es. chiusa da un caricamento precedente): una nuova
        try:
            _stato()["win"] = None
            _mostra(testo, livello, uiapp)
            return
        except Exception:
            pass
    try:
        from pyrevit import forms
        forms.toast(AV.una_riga(testo), title=TITOLO)
    except Exception:
        pass


def errore(testo, uiapp=None):
    mostra(testo, AV.ERRORE, uiapp)


def attenzione(testo, uiapp=None):
    mostra(testo, AV.ATTENZIONE, uiapp)
