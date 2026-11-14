# -*- coding: utf-8 -*-
"""Tasti in sovraimpressione che cambiano con la selezione.

Sul bordo superiore della selezione compare una fila di tastini con icona
(il nome completo e' nel suggerimento al passaggio del mouse):
  - linea di sezione (in pianta) o riquadro di una sezione con Profondita' attiva:
    "Profondita' sezione" e "Sincronizza sfondo"; se non e' ancora attiva, solo
    "Attiva profondita' sezione" (apre la finestra per creare lo sfondo);
  - una vista in tavola: allineamento del suo titolo;
  - due o piu' viste/titoli in tavola: allineamento di titoli e riquadri;
  - tre o piu': anche distribuzione.
Quali tasti mostrare lo decide tasti_contestuali.py (senza API Revit).

Viene attivato da startup.py dell'estensione. Usa l'evento SelectionChanged
(Revit 2023+) e l'evento Idling, che rilegge la selezione nelle versioni precedenti
e rimette i tasti sul bordo dopo zoom e pan. La posizione si ricava da
UIView.GetZoomCorners / GetWindowRectangle. I tasti lavorano tramite ExternalEvent.
"""
import os
import imp

import clr
clr.AddReference("System")
clr.AddReference("System.Drawing")
clr.AddReference("System.Windows.Forms")
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")
clr.AddReference("RevitAPI")
clr.AddReference("RevitAPIUI")

import System
from System import Double, EventHandler, IntPtr
from System.Windows import Size, Thickness, Visibility
from System.Windows.Controls import Border, Button
from System.Windows.Interop import WindowInteropHelper
from System.Windows.Markup import XamlReader
from System.Windows.Media import BrushConverter, Geometry, Stretch
from System.Windows.Shapes import Path
from Autodesk.Revit import DB, UI

# Import qui, all'avvio: quando poi scatta l'ExternalEvent la cartella lib
# dell'estensione non e' piu' nel sys.path e un import li' fallirebbe.
import allinea_in_tavola as AIT
import profondita_sezione as PS
import tasti_contestuali as TC


# Stessa chiave della prima versione: al Reload spegne anche il vecchio pannello
CHIAVE_APPDOMAIN = "CDVTools.SezioneOverlay.Spegni"
TITOLO = u"CDV Tools"
SCRIPT_PROFONDITA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    u"CDV Tools.tab", u"Grafica e Filtri.panel", u"SectionDepth.pushbutton", u"script.py",
)
DIM_TASTO = 22
DIM_ICONA = 14

XAML = u"""
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        WindowStyle="None" AllowsTransparency="True" Background="Transparent"
        ShowInTaskbar="False" ShowActivated="False" ResizeMode="NoResize"
        SizeToContent="WidthAndHeight" FontFamily="Segoe UI" FontSize="11">
  <Window.Resources>
    <Style TargetType="Button">
      <Setter Property="Width" Value="22"/>
      <Setter Property="Height" Value="22"/>
      <Setter Property="Margin" Value="1,0,1,0"/>
      <Setter Property="Cursor" Value="Hand"/>
      <Setter Property="Focusable" Value="False"/>
      <Setter Property="Background" Value="Transparent"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="Button">
            <Border x:Name="sfondo" Background="{TemplateBinding Background}" CornerRadius="3">
              <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property="IsMouseOver" Value="True">
                <Setter TargetName="sfondo" Property="Background" Value="#E0F2FE"/>
              </Trigger>
              <Trigger Property="IsPressed" Value="True">
                <Setter TargetName="sfondo" Property="Background" Value="#BAE6FD"/>
              </Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>
  </Window.Resources>
  <Border Margin="0,0,3,3" CornerRadius="4" Background="#F2FFFFFF" BorderBrush="#CBD5E1"
          BorderThickness="1" Padding="2">
    <Border.Effect>
      <DropShadowEffect BlurRadius="4" ShadowDepth="1" Opacity="0.2"/>
    </Border.Effect>
    <StackPanel x:Name="pnlTasti" Orientation="Horizontal"/>
  </Border>
</Window>
"""

_PENNELLI = BrushConverter()


def _colore(hex_):
    return _PENNELLI.ConvertFromString(hex_)


def _avvisa(msg):
    try:
        from pyrevit import forms
        forms.alert(msg, title=TITOLO)
    except Exception:
        UI.TaskDialog.Show(TITOLO, msg)


def _toast(msg):
    try:
        from pyrevit import forms
        forms.toast(msg, title=TITOLO)
    except Exception:
        pass


def _non_attivabile(win):
    """Il pannello non prende il focus: Revit resta attivo (Esc, scorciatoie, ExternalEvent)."""
    try:
        import ctypes
        hwnd = WindowInteropHelper(win).EnsureHandle().ToInt64()
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080
        stile = user32.GetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
        user32.SetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE,
                              stile | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW)
    except Exception:
        pass


class _IgnoraAvvisi(DB.IFailuresPreprocessor):
    def PreprocessFailures(self, failuresAccessor):
        for f in failuresAccessor.GetFailureMessages():
            if f.GetSeverity() == DB.FailureSeverity.Warning:
                failuresAccessor.DeleteWarning(f)
        return DB.FailureProcessingResult.Continue


# ==============================================================================
# LETTURA SELEZIONE
# ==============================================================================

def _e_viewer(el):
    cat = el.Category if el is not None else None
    return cat is not None and PS._id_val(cat.Id) == int(DB.BuiltInCategory.OST_Viewers)


def _vista_da_attivare(doc, voce, viewports):
    """Sezione o prospetto (senza sfondo) indicato dalla voce di selezione, oppure None."""
    tipo, valore = voce
    if tipo == u"viewport":
        for vp in viewports:
            if PS._id_val(vp.ViewId) == valore:
                vista = doc.GetElement(vp.ViewId)
                return vista if PS.e_vista_supportata(vista) else None
        return None
    if tipo == u"viewer":
        for vista in DB.FilteredElementCollector(doc).OfClass(DB.View):
            if vista.Name == valore and PS.e_vista_supportata(vista):
                return vista
    return None


def _analizza_selezione(doc, ids):
    """Ritorna (titolo, gruppi, madre_uid) oppure None se non c'e' nulla da proporre.

    Considera solo selezioni fatte di soli riquadri di vista (in tavola) oppure di
    una sola linea di sezione/prospetto.
    """
    if doc is None or doc.IsFamilyDocument or not ids:
        return None
    elementi = [doc.GetElement(i) for i in ids]
    viewports = [e for e in elementi if isinstance(e, DB.Viewport)]
    viewers = [e for e in elementi if _e_viewer(e)]

    if len(viewports) == len(elementi):
        voci = None
    elif len(viewers) == 1 and len(elementi) == 1:
        voci = [(u"viewer", viewers[0].Name)]
    else:
        return None

    coppie, _, sfondo_to_madre = PS.trova_coppie_sezioni(doc)
    madri = dict((PS._id_val(c["madre"].Id), c["madre"]) for c in coppie)
    righe = [
        (PS._id_val(c["madre"].Id), c["madre"].Name, PS._id_val(c["sfondo"].Id), c["sfondo"].Name)
        for c in coppie
    ]

    if voci is None:
        sfondo_a_madre = dict((k, PS._id_val(m.Id)) for k, m in sfondo_to_madre.items())
        viste = TC.viste_distinte([PS._id_val(vp.ViewId) for vp in viewports], sfondo_a_madre)
        n = len(viste)
        voci = [(u"viewport", viste[0])] if n == 1 else []
        in_tavola = isinstance(doc.ActiveView, DB.ViewSheet)
    else:
        n = 1
        in_tavola = False

    id_madre = PS.madre_da_selezione(voci, righe) if voci else None
    madre = madri.get(id_madre) if id_madre is not None else None
    # Sezione/prospetto senza sfondo: il tasto apre Profondita' Sezione per crearlo
    da_attivare = _vista_da_attivare(doc, voci[0], viewports) if (madre is None and voci) else None

    gruppi = TC.comandi_per_selezione(n, in_tavola=in_tavola, sezione_con_sfondo=madre is not None,
                                      sezione_senza_sfondo=da_attivare is not None)
    if not gruppi:
        return None
    if madre is None:
        madre = da_attivare
    if n == 1:
        if madre is not None:
            titolo = madre.Name
        else:
            vista = doc.GetElement(viewports[0].ViewId)
            titolo = vista.Name if vista is not None else u"Vista"
    else:
        titolo = u"%d viste selezionate" % n
    return titolo, gruppi, (madre.UniqueId if madre is not None else None)


# ==============================================================================
# AZIONI (eseguite in contesto API tramite ExternalEvent)
# ==============================================================================

def _apri_profondita(madre_uid):
    modulo = imp.load_source("cdv_sectiondepth_script", SCRIPT_PROFONDITA)
    modulo.main(madre_uid=madre_uid)


def _sincronizza(doc, madre_uid):
    madre = doc.GetElement(madre_uid)
    if madre is None:
        _avvisa(u"Sezione non trovata nel documento attivo.")
        return
    coppie, _, _ = PS.trova_coppie_sezioni(doc)
    coppia = None
    for c in coppie:
        if c["madre"].UniqueId == madre_uid:
            coppia = c
            break
    if coppia is None:
        _avvisa(u"La sezione '%s' non ha uno sfondo collegato." % madre.Name)
        return
    cfg = coppia["cfg"] or {
        "modalita": u"totale", "valore_m": 20.0, "halftone": True,
        "grigio": True, "grigio_rgb": 140, "nascondi_retini": True,
    }

    t = DB.Transaction(doc, u"Sincronizza Profondita' Sezione")
    opts = t.GetFailureHandlingOptions()
    opts.SetFailuresPreprocessor(_IgnoraAvvisi())
    t.SetFailureHandlingOptions(opts)
    t.Start()
    try:
        PS.sincronizza_vista_sfondo(doc, madre, coppia["sfondo"], cfg)
        tavole = PS.sincronizza_in_tavola(doc, madre, coppia["sfondo"], crea_se_manca=True)
        t.Commit()
    except Exception as ex:
        if t.HasStarted() and not t.HasEnded():
            t.RollBack()
        _avvisa(u"Errore durante la sincronizzazione:\n%s" % ex)
        return
    msg = u"Sfondo di '%s' sincronizzato." % madre.Name
    if tavole > 0:
        msg += u"\nTavole allineate: %d." % tavole
    _toast(msg)


class _GestoreAzione(UI.IExternalEventHandler):
    def __init__(self):
        self.comando = None
        self.madre_uid = None

    def Execute(self, uiapp):
        comando, uid = self.comando, self.madre_uid
        self.comando = None
        try:
            uidoc = uiapp.ActiveUIDocument
            if uidoc is None or not comando:
                return
            if comando == TC.SEZIONE_APRI:
                _apri_profondita(uid)
            elif comando == TC.SEZIONE_SINCRONIZZA:
                _sincronizza(uidoc.Document, uid)
            else:
                # Allineamenti: lavorano sulla selezione corrente della tavola attiva
                AIT.esegui_da_ribbon(comando)
        except Exception as ex:
            _avvisa(u"Errore: %s" % ex)

    def GetName(self):
        return u"CDV Tools - Tasti in sovraimpressione"


# ==============================================================================
# POSIZIONE SULLO SCHERMO
# ==============================================================================

def _scala_dpi():
    """Pixel fisici per unita' WPF (1.0 a 96 dpi)."""
    from System.Drawing import Graphics
    g = Graphics.FromHwnd(IntPtr.Zero)
    try:
        return g.DpiX / 96.0
    finally:
        g.Dispose()


def _riquadro_selezione(uidoc, ids):
    """(riquadro, finestra) in pixel fisici, oppure None.

    riquadro: ingombro sullo schermo degli elementi selezionati (riquadri di vista
    in tavola o linea di sezione in pianta); finestra: area della vista attiva.
    """
    doc = uidoc.Document
    vista = doc.ActiveView
    if vista is None:
        return None
    uiview = None
    for v in uidoc.GetOpenUIViews():
        if PS._id_val(v.ViewId) == PS._id_val(vista.Id):
            uiview = v
            break
    if uiview is None:
        return None
    r = uiview.GetWindowRectangle()
    finestra = (float(r.Left), float(r.Top), float(r.Right), float(r.Bottom))
    destra, alto = vista.RightDirection, vista.UpDirection

    def uv(p):
        return (p.DotProduct(destra), p.DotProduct(alto))

    angoli = list(uiview.GetZoomCorners())
    zoom = (uv(angoli[0]), uv(angoli[1]))

    punti = []
    for eid in ids:
        el = doc.GetElement(eid)
        if el is None:
            continue
        if isinstance(el, DB.Viewport):
            o = el.GetBoxOutline()
            punti.append(uv(o.MinimumPoint))
            punti.append(uv(o.MaximumPoint))
        else:
            bb = el.get_BoundingBox(vista)
            if bb is None:
                continue
            for x in (bb.Min.X, bb.Max.X):
                for y in (bb.Min.Y, bb.Max.Y):
                    for z in (bb.Min.Z, bb.Max.Z):
                        punti.append(uv(bb.Transform.OfPoint(DB.XYZ(x, y, z))))
    riquadro = TC.riquadro_schermo(punti, zoom, finestra)
    if riquadro is None:
        return None
    return riquadro, finestra


# ==============================================================================
# FILA DI TASTINI AI BORDI DELLA SELEZIONE
# ==============================================================================

class TastiOverlay(object):
    def __init__(self, uiapp):
        self.uiapp = uiapp
        self.win = None
        self.gestore = None
        self.evento = None
        self.madre_uid = None
        self.chiave_sel = None
        self.ids = []
        self.attivo = False
        self.ultima_pos = None
        self.scala = 1.0
        self.delegati = []

    # --- finestra -------------------------------------------------------------
    def _crea_finestra(self):
        win = XamlReader.Parse(XAML)
        try:
            WindowInteropHelper(win).Owner = self.uiapp.MainWindowHandle
        except Exception:
            win.Topmost = True
        _non_attivabile(win)
        self.win = win
        try:
            self.scala = _scala_dpi()
        except Exception:
            self.scala = 1.0
        # ExternalEvent va creato in contesto API (qui siamo in un evento di Revit)
        self.gestore = _GestoreAzione()
        self.evento = UI.ExternalEvent.Create(self.gestore)

    def _tasto(self, comando, etichetta, suggerimento, gruppo):
        icona = Path()
        icona.Data = Geometry.Parse(TC.ICONE.get(comando) or u"M2,2 H14 V14 H2 Z")
        icona.Fill = _colore("#0369A1")
        icona.Width = DIM_ICONA
        icona.Height = DIM_ICONA
        icona.Stretch = Stretch.Uniform
        b = Button()
        b.Content = icona
        b.ToolTip = u"%s: %s\n%s" % (gruppo, etichetta, suggerimento)
        b.Click += lambda s, a: self._esegui(comando)
        return b

    def _riempi(self, gruppi):
        pnl = self.win.FindName("pnlTasti")
        pnl.Children.Clear()
        for n, (nome, tasti) in enumerate(gruppi):
            if n > 0:
                sep = Border()
                sep.Width = 1
                sep.Margin = Thickness(3, 3, 3, 3)
                sep.Background = _colore("#CBD5E1")
                pnl.Children.Add(sep)
            for comando, etichetta, suggerimento in tasti:
                pnl.Children.Add(self._tasto(comando, etichetta, suggerimento, nome))
        self.win.Content.Measure(Size(Double.PositiveInfinity, Double.PositiveInfinity))
        self.ultima_pos = None

    def riposiziona(self, uidoc):
        """Mette la fila sul bordo superiore della selezione (o la nasconde se e' fuori vista)."""
        if self.win is None or not self.attivo:
            return
        pos = None
        if uidoc is not None:
            esito = _riquadro_selezione(uidoc, self.ids)
            if esito is not None:
                riquadro, finestra = esito
                dim = self.win.Content.DesiredSize
                pos = TC.posizione_striscia(riquadro, finestra,
                                            dim.Width * self.scala, dim.Height * self.scala)
        if pos is None:
            self._nascondi_finestra()
            return
        pos = (round(pos[0] / self.scala), round(pos[1] / self.scala))
        if pos != self.ultima_pos:
            self.win.Left, self.win.Top = pos
            self.ultima_pos = pos
        if self.win.Visibility != Visibility.Visible:
            self.win.Show()

    def mostra(self, uidoc, ids, gruppi, madre_uid):
        if self.win is None:
            self._crea_finestra()
        self.madre_uid = madre_uid
        self.ids = list(ids)
        self.attivo = True
        self._riempi(gruppi)
        self.riposiziona(uidoc)

    def _nascondi_finestra(self):
        if self.win is not None and self.win.Visibility == Visibility.Visible:
            self.win.Hide()

    def nascondi(self):
        self.attivo = False
        self.ids = []
        self._nascondi_finestra()

    def _esegui(self, comando):
        if self.evento is None:
            return
        self.gestore.comando = comando
        self.gestore.madre_uid = self.madre_uid
        if comando == TC.SEZIONE_APRI:
            # Si apre una finestra: i tasti si tolgono di mezzo e tornano dopo
            # (chiave azzerata = la selezione viene riletta al prossimo Idling).
            self.nascondi()
            self.chiave_sel = None
        self.evento.Raise()

    # --- selezione ------------------------------------------------------------
    def aggiorna(self, uidoc, ids):
        try:
            ids = list(ids)
            doc = uidoc.Document if uidoc is not None else None
            if doc is None:
                chiave = None
            else:
                chiave = (doc.PathName or doc.Title, PS._id_val(doc.ActiveView.Id),
                          tuple(sorted(PS._id_val(i) for i in ids)))
            if chiave == self.chiave_sel:
                return
            self.chiave_sel = chiave
            esito = _analizza_selezione(doc, ids)
            if esito is None:
                self.nascondi()
            else:
                _titolo, gruppi, madre_uid = esito
                self.mostra(uidoc, ids, gruppi, madre_uid)
        except Exception:
            # Un errore qui non deve mai disturbare il lavoro in Revit
            self.nascondi()

    def _su_selezione(self, sender, args):
        self.aggiorna(self.uiapp.ActiveUIDocument, args.GetSelectedElements())

    def _su_idling(self, sender, args):
        # Rilegge la selezione (Revit < 2023 non ha SelectionChanged) e rimette
        # i tasti al loro posto dopo zoom, pan o spostamento delle viste.
        try:
            uidoc = self.uiapp.ActiveUIDocument
            if uidoc is None:
                self.chiave_sel = None
                self.nascondi()
                return
            self.aggiorna(uidoc, uidoc.Selection.GetElementIds())
            self.riposiziona(uidoc)
        except Exception:
            self._nascondi_finestra()

    def _su_chiusura(self, sender, args):
        self.chiave_sel = None
        self.nascondi()

    # --- attivazione ----------------------------------------------------------
    def accendi(self):
        tipo_args = getattr(UI.Events, "SelectionChangedEventArgs", None)
        if tipo_args is not None and clr.GetClrType(UI.UIApplication).GetEvent("SelectionChanged"):
            d = EventHandler[tipo_args](self._su_selezione)
            self.uiapp.SelectionChanged += d
            self.delegati.append(("SelectionChanged", d))
        d = EventHandler[UI.Events.IdlingEventArgs](self._su_idling)
        self.uiapp.Idling += d
        self.delegati.append(("Idling", d))
        d = EventHandler[DB.Events.DocumentClosingEventArgs](self._su_chiusura)
        self.uiapp.Application.DocumentClosing += d
        self.delegati.append(("DocumentClosing", d))


    def spegni(self):
        for nome, d in self.delegati:
            try:
                if nome == "SelectionChanged":
                    self.uiapp.SelectionChanged -= d
                elif nome == "Idling":
                    self.uiapp.Idling -= d
                elif nome == "DocumentClosing":
                    self.uiapp.Application.DocumentClosing -= d
            except Exception:
                pass
        self.delegati = []
        if self.win is not None:
            try:
                self.win.Close()
            except Exception:
                pass
            self.win = None


def attiva(uiapp):
    """Accende i tasti in sovraimpressione (spegne quelli di un caricamento precedente)."""
    dominio = System.AppDomain.CurrentDomain
    vecchio = dominio.GetData(CHIAVE_APPDOMAIN)
    if vecchio is not None:
        try:
            vecchio.Invoke()
        except Exception:
            pass
    overlay = TastiOverlay(uiapp)
    overlay.accendi()
    dominio.SetData(CHIAVE_APPDOMAIN, System.Action(overlay.spegni))
    return overlay
