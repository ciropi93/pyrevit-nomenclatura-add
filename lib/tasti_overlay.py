# -*- coding: utf-8 -*-
"""Palette contestuale (stile ArchiCAD) e tasti in sovraimpressione.

Selezionando qualcosa nella vista, accanto al cursore compare una palette di icone
(il nome completo e' nel suggerimento al passaggio del mouse), una riga per gruppo:
  - Modifica / Selezione / Visibilita': comandi scelti per categoria in palette.py
    (configurabili, file personale in %APPDATA%); Sposta, Copia, ... sono i comandi
    di Revit lanciati con PostCommand, gli altri stanno in palette_azioni.py;
  - strumenti CDV legati al contesto (tasti_contestuali.py):
  - linea di sezione (in pianta) o riquadro di una sezione con Profondita' attiva:
    "Profondita' sezione" e "Sincronizza sfondo"; se non e' ancora attiva, solo
    "Attiva profondita' sezione" (apre la finestra per creare lo sfondo);
  - una vista in tavola: allineamento del suo titolo;
  - due o piu' viste/titoli in tavola: allineamento di titoli e riquadri;
  - tre o piu': anche distribuzione;
  - uno o piu' muri: "Inverti muro sul centro", e accanto a ogni muro le lettere
    E (esterno) e I (interno) sui due lati, in pianta e in sezione.
Se la selezione arriva dal browser di progetto (cursore fuori dalla vista) la palette
sta sul bordo superiore della selezione. Il pulsante "Palette On/Off" la spegne tutta.

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
from System import Double, EventHandler, IntPtr, TimeSpan
from System.Windows import Point, Size, SystemParameters, Thickness, Visibility
from System.Windows import CornerRadius, FontWeights, HorizontalAlignment, VerticalAlignment
from System.Windows.Controls import Border, Button, Canvas, Orientation, StackPanel, TextBlock
from System.Windows.Input import Keyboard, ModifierKeys
from System.Windows.Interop import WindowInteropHelper
from System.Windows.Markup import XamlReader
from System.Windows.Media import BrushConverter, Geometry, Stretch
from System.Windows.Shapes import Path
from System.Windows.Threading import DispatcherTimer
from System.Windows.Forms import Control, MouseButtons
from Autodesk.Revit import DB, UI

# Import qui, all'avvio: quando poi scatta l'ExternalEvent la cartella lib
# dell'estensione non e' piu' nel sys.path e un import li' fallirebbe.
import allinea_in_tavola as AIT
import profondita_sezione as PS
import tasti_contestuali as TC
import palette as PAL
import palette_azioni as PA


# Stessa chiave della prima versione: al Reload spegne anche il vecchio pannello
CHIAVE_APPDOMAIN = "CDVTools.SezioneOverlay.Spegni"
TITOLO = u"CDV Tools"
SCRIPT_PROFONDITA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    u"CDV Tools.tab", u"Grafica e Filtri.panel", u"SectionDepth.pushbutton", u"script.py",
)
SCRIPT_INVERTI_MURO = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    u"CDV Tools.tab", u"Modellazione.panel", u"FlipWallCenter.pushbutton", u"script.py",
)
DIM_TASTO = 22
DIM_ICONA = 14
DIM_LETTERA = 14          # cerchietto della lettera E / I
DISTACCO_LETTERA = 10     # pixel tra la faccia del muro e il centro della lettera
CONTROLLO_MOUSE_MS = 40   # ogni quanto si guarda se la vista si sta spostando
MAX_MURI_LETTERE = 150    # oltre, niente lettere (troppe per leggerle)
COLORE_ESTERNO = "#DC2626"
COLORE_INTERNO = "#2563EB"

_STILI = u"""
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
            <Border x:Name="sfondo" Background="{TemplateBinding Background}" CornerRadius="3"
                    Padding="{TemplateBinding Padding}">
              <ContentPresenter HorizontalAlignment="{TemplateBinding HorizontalContentAlignment}"
                                VerticalAlignment="Center"/>
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
    <!-- strumento CDV della categoria: blu pieno -->
    <Style x:Key="Primario" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
      <Setter Property="Background" Value="#0369A1"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="Button">
            <Border x:Name="sfondo" Background="{TemplateBinding Background}" CornerRadius="3">
              <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property="IsMouseOver" Value="True">
                <Setter TargetName="sfondo" Property="Background" Value="#075985"/>
              </Trigger>
              <Trigger Property="IsPressed" Value="True">
                <Setter TargetName="sfondo" Property="Background" Value="#0C4A6E"/>
              </Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>
    <!-- fila fissa: tasti piccoli -->
    <Style x:Key="Piccolo" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
      <Setter Property="Width" Value="18"/>
      <Setter Property="Height" Value="18"/>
    </Style>
    <!-- voce del menu "..." -->
    <Style x:Key="Voce" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
      <Setter Property="Width" Value="NaN"/>
      <Setter Property="Height" Value="24"/>
      <Setter Property="Margin" Value="0"/>
      <Setter Property="Padding" Value="10,0,14,0"/>
      <Setter Property="HorizontalContentAlignment" Value="Left"/>
    </Style>
  </Window.Resources>
"""

_FINESTRA = u"""
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        WindowStyle="None" AllowsTransparency="True" Background="Transparent"
        ShowInTaskbar="False" ShowActivated="False" ResizeMode="NoResize"
        SizeToContent="WidthAndHeight" FontFamily="Segoe UI" FontSize="12">
%s
  <Border Margin="0,0,4,4" CornerRadius="%d" Background="#FAFFFFFF" BorderBrush="#CBD5E1"
          BorderThickness="1" Padding="%s">
    <Border.Effect>
      <DropShadowEffect BlurRadius="%d" ShadowDepth="1" Opacity="0.2"/>
    </Border.Effect>
    <StackPanel x:Name="pnlTasti" Orientation="Vertical"/>
  </Border>
</Window>
"""

XAML = _FINESTRA % (_STILI, 5, u"2", 4)
XAML_MENU = _FINESTRA % (_STILI, 6, u"0,4,0,4", 8)

# Icona del tasto "..." (tre punti)
ICONA_ALTRO = (u"M3,6.5 A1.5,1.5 0 1 1 3,9.5 A1.5,1.5 0 1 1 3,6.5 Z "
               u"M8,6.5 A1.5,1.5 0 1 1 8,9.5 A1.5,1.5 0 1 1 8,6.5 Z "
               u"M13,6.5 A1.5,1.5 0 1 1 13,9.5 A1.5,1.5 0 1 1 13,6.5 Z")

# Finestra trasparente sopra la vista per le lettere E / I: non riceve clic
XAML_LETTERE = u"""
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        WindowStyle="None" AllowsTransparency="True" Background="Transparent"
        ShowInTaskbar="False" ShowActivated="False" ResizeMode="NoResize"
        IsHitTestVisible="False" FontFamily="Segoe UI">
  <Canvas x:Name="tela"/>
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


def _non_attivabile(win, trasparente_ai_clic=False):
    """Il pannello non prende il focus: Revit resta attivo (Esc, scorciatoie, ExternalEvent).

    trasparente_ai_clic: mouse e clic passano alla vista di Revit sotto (lettere E / I).
    """
    try:
        import ctypes
        hwnd = WindowInteropHelper(win).EnsureHandle().ToInt64()
        user32 = ctypes.windll.user32
        GWL_EXSTYLE = -20
        WS_EX_NOACTIVATE = 0x08000000
        WS_EX_TOOLWINDOW = 0x00000080
        WS_EX_TRANSPARENT = 0x00000020
        stile = user32.GetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
        stile = stile | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
        if trasparente_ai_clic:
            stile = stile | WS_EX_TRANSPARENT
        user32.SetWindowLongW(ctypes.c_void_p(hwnd), GWL_EXSTYLE, stile)
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


_NOMI_OST = {}


def _nome_ost(el):
    """Nome OST_* della categoria dell'elemento (None se non e' una categoria di Revit)."""
    cat = el.Category
    if cat is None:
        return None
    v = PS._id_val(cat.Id)
    if v not in _NOMI_OST:
        nome = None
        try:
            tipo = clr.GetClrType(DB.BuiltInCategory)
            bic = System.Enum.ToObject(tipo, v)
            if System.Enum.IsDefined(tipo, bic):
                nome = str(bic)
        except Exception:
            nome = None
        _NOMI_OST[v] = nome
    return _NOMI_OST[v]


def _gruppi_cdv(doc, elementi):
    """Strumenti CDV legati al contesto: (gruppi, madre_uid).

    Muri: Inverti sul centro. Soli riquadri di vista (in tavola) o una sola linea di
    sezione/prospetto: Profondita' Sezione e allineamenti in tavola.
    """
    muri = [e for e in elementi if isinstance(e, DB.Wall)]
    if muri and len(muri) == len(elementi):
        return TC.comandi_per_selezione(0, in_tavola=False, n_muri=len(muri)), None
    viewports = [e for e in elementi if isinstance(e, DB.Viewport)]
    viewers = [e for e in elementi if _e_viewer(e)]

    if len(viewports) == len(elementi):
        voci = None
    elif len(viewers) == 1 and len(elementi) == 1:
        voci = [(u"viewer", viewers[0].Name)]
    else:
        return [], None

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
    if madre is None:
        madre = da_attivare
    return gruppi, (madre.UniqueId if madre is not None else None)


def _analizza_selezione(doc, ids, cfg, disponibili):
    """Ritorna (struttura, madre_uid) oppure None se non c'e' nulla da proporre.

    struttura: vedi palette.struttura_palette (strumenti CDV del contesto, comandi
    in vista, menu "...", fila fissa).
    """
    if doc is None or doc.IsFamilyDocument or not ids or not cfg.get(u"attiva", True):
        return None
    elementi = [e for e in (doc.GetElement(i) for i in ids) if e is not None]
    if not elementi:
        return None
    chiavi = set(PAL.chiave_categoria(_nome_ost(e), e.GetType().Name) for e in elementi)
    cdv, madre_uid = _gruppi_cdv(doc, elementi)
    struttura = PAL.struttura_palette(chiavi, len(elementi), cfg, disponibili, cdv)
    if struttura is None:
        return None
    return struttura, madre_uid


# ==============================================================================
# AZIONI (eseguite in contesto API tramite ExternalEvent)
# ==============================================================================

def _apri_profondita(madre_uid):
    modulo = imp.load_source("cdv_sectiondepth_script", SCRIPT_PROFONDITA)
    modulo.main(madre_uid=madre_uid)


def _inverti_muri(maiuscolo):
    """Lancia "Inverti Muro sul Centro" sui muri selezionati (con Maiusc: su Asse del muro)."""
    modulo = imp.load_source("cdv_flipwallcenter_script", SCRIPT_INVERTI_MURO)
    modulo.__shiftclick__ = bool(maiuscolo)
    modulo.main()


def _comandi_disponibili():
    """Id della palette utilizzabili in questa versione di Revit."""
    out = set()
    for c in PAL.CATALOGO:
        if c.esecuzione != PAL.REVIT or getattr(UI.PostableCommand, c.postable, None) is not None:
            out.add(c.id)
    return out


def _posta_comando(uiapp, nome):
    """Lancia un comando nativo di Revit: parte dopo l'ExternalEvent, con la selezione attuale."""
    pc = getattr(UI.PostableCommand, nome, None)
    cid = UI.RevitCommandId.LookupPostableCommandId(pc) if pc is not None else None
    if cid is None or not uiapp.CanPostCommand(cid):
        _avvisa(u"Il comando di Revit non si può avviare adesso.")
        return
    uiapp.PostCommand(cid)


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
        self.maiuscolo = False
        self.al_termine = None   # chiamata a fine azione (la palette torna)

    def Execute(self, uiapp):
        comando, uid = self.comando, self.madre_uid
        self.comando = None
        try:
            uidoc = uiapp.ActiveUIDocument
            if uidoc is None or not comando:
                return
            cmd = PAL.PER_ID.get(comando)
            if cmd is not None and cmd.esecuzione == PAL.REVIT:
                _posta_comando(uiapp, cmd.postable)
            elif cmd is not None:
                try:
                    msg = PA.esegui(uidoc, comando)
                except PA.AzioneErrore as ex:
                    _avvisa(u"%s" % ex)
                    return
                if msg:
                    _toast(msg)
            elif comando == TC.SEZIONE_APRI:
                _apri_profondita(uid)
            elif comando == TC.SEZIONE_SINCRONIZZA:
                _sincronizza(uidoc.Document, uid)
            elif comando == TC.MURO_INVERTI:
                _inverti_muri(self.maiuscolo)
            else:
                # Allineamenti: lavorano sulla selezione corrente della tavola attiva
                AIT.esegui_da_ribbon(comando)
        except Exception as ex:
            _avvisa(u"Errore: %s" % ex)
        finally:
            if self.al_termine is not None:
                try:
                    self.al_termine(comando)
                except Exception:
                    pass

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


def _tasti_premuti():
    """(centrale, sinistro): tasti del mouse premuti in questo momento (senza API Revit)."""
    b = Control.MouseButtons
    return ((b & MouseButtons.Middle) == MouseButtons.Middle,
            (b & MouseButtons.Left) == MouseButtons.Left)


class _GancioMouse(object):
    """Hook WH_MOUSE sul thread di Revit: avvisa appena arriva un clic o la rotellina.

    Serve per togliere tasti e lettere all'istante quando parte un pan o uno zoom:
    durante il ridisegno Revit non manda Idling e un timer non fa in tempo.
    su_messaggio(msg) riceve il codice del messaggio (WM_MBUTTONDOWN, ...).
    """
    WH_MOUSE = 7
    WM_LBUTTONDOWN = 0x0201
    WM_MBUTTONDOWN = 0x0207
    WM_MOUSEWHEEL = 0x020A
    WM_MOUSEHWHEEL = 0x020E
    _MESSAGGI = (WM_LBUTTONDOWN, WM_MBUTTONDOWN, WM_MOUSEWHEEL, WM_MOUSEHWHEEL)

    def __init__(self, su_messaggio):
        self.su_messaggio = su_messaggio
        self.hhook = None
        self._proc = None
        self._user32 = None

    def attacca(self):
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_longlong, ctypes.c_int,
                                      ctypes.c_ulonglong, ctypes.c_longlong)
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p,
                                             ctypes.c_uint]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                          ctypes.c_ulonglong, ctypes.c_longlong]
        user32.CallNextHookEx.restype = ctypes.c_longlong
        user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
        self._user32 = user32
        messaggi = self._MESSAGGI

        def proc(n_code, w_param, l_param):
            if n_code >= 0 and w_param in messaggi:
                try:
                    self.su_messaggio(w_param)
                except Exception:
                    pass
            return user32.CallNextHookEx(self.hhook, n_code, w_param, l_param)

        self._proc = HOOKPROC(proc)   # tenuto in vita finche' l'hook e' attivo
        self.hhook = user32.SetWindowsHookExW(self.WH_MOUSE, self._proc, None,
                                              kernel32.GetCurrentThreadId())
        return bool(self.hhook)

    def stacca(self):
        if self.hhook and self._user32 is not None:
            try:
                self._user32.UnhookWindowsHookEx(self.hhook)
            except Exception:
                pass
        self.hhook = None
        self._proc = None


def _contesto_vista(uidoc):
    """(vista, uv, zoom, finestra) della vista attiva, oppure None.

    uv(XYZ) -> coordinate nel piano della vista; zoom: angoli visibili in uv;
    finestra: area della vista sullo schermo in pixel fisici.
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
    return vista, uv, zoom, finestra


def _riquadro_selezione(uidoc, ids):
    """(riquadro, finestra) in pixel fisici, oppure None.

    riquadro: ingombro sullo schermo degli elementi selezionati (riquadri di vista
    in tavola, linea di sezione o muri); finestra: area della vista attiva.
    """
    ctx = _contesto_vista(uidoc)
    if ctx is None:
        return None
    vista, uv, zoom, finestra = ctx
    doc = uidoc.Document

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


def _asse_muro(wall):
    """(punto a meta' muro, versore orizzontale verso l'esterno) oppure None."""
    curva = getattr(wall.Location, "Curve", None)
    if curva is None:
        return None
    if isinstance(curva, DB.Line):
        medio = curva.Evaluate(0.5, True)
        n = wall.Orientation
    else:
        der = curva.ComputeDerivatives(0.5, True)
        medio = der.Origin
        n = DB.XYZ.BasisZ.CrossProduct(der.BasisX)
        if wall.Flipped:
            n = n.Negate()
    n = DB.XYZ(n.X, n.Y, 0.0)
    if n.GetLength() < 1e-9:
        return None
    # in sezione le lettere stanno a meta' altezza del muro
    bb = wall.get_BoundingBox(None)
    if bb is not None:
        medio = DB.XYZ(medio.X, medio.Y, (bb.Min.Z + bb.Max.Z) / 2.0)
    return medio, n.Normalize()


def _su_faccia(faccia, p):
    """Punto della faccia piu' vicino a p (sul piano della faccia se p cade in un foro)."""
    try:
        r = faccia.Project(p)
    except Exception:
        r = None
    if r is not None:
        return r.XYZPoint
    if isinstance(faccia, DB.PlanarFace):
        n = faccia.FaceNormal
        return p + n.Multiply((faccia.Origin - p).DotProduct(n))
    return None


def _punto_faccia(wall, tipo, p):
    migliore = None
    for ref in DB.HostObjectUtils.GetSideFaces(wall, tipo):
        faccia = wall.GetGeometryObjectFromReference(ref)
        if not isinstance(faccia, DB.Face):
            continue
        q = _su_faccia(faccia, p)
        if q is not None and (migliore is None or q.DistanceTo(p) < migliore.DistanceTo(p)):
            migliore = q
    return migliore


def _facce_muro(wall):
    """(punto faccia esterna, punto faccia interna, centro, versore esterno) oppure None.

    I punti sono presi sulla geometria vera del muro (facce laterali di Revit), cosi'
    non dipendono da linea di ubicazione, stratigrafia o Flip.
    """
    asse = _asse_muro(wall)
    if asse is None:
        return None
    medio, n = asse
    try:
        est = _punto_faccia(wall, DB.ShellLayerType.Exterior, medio)
        int_ = _punto_faccia(wall, DB.ShellLayerType.Interior, medio)
    except Exception:
        est = int_ = None
    if est is None or int_ is None:
        # es. muro sovrapposto: si stima dalla linea di ubicazione
        codice = 0
        p = wall.get_Parameter(DB.BuiltInParameter.WALL_KEY_REF_PARAM)
        if p is not None:
            codice = p.AsInteger()
        strati, primo, ultimo = None, -1, -1
        try:
            cs = wall.WallType.GetCompoundStructure()
        except Exception:
            cs = None
        if cs is not None:
            strati = [cs.GetLayerWidth(i) for i in range(cs.LayerCount)]
            primo, ultimo = cs.GetFirstCoreLayerIndex(), cs.GetLastCoreLayerIndex()
        spessore = wall.Width
        off = TC.offset_linea_ubicazione(codice, spessore, strati, primo, ultimo)
        mezzo = (sum(strati) if strati and sum(strati) > 0 else spessore) / 2.0
        centro = medio - n.Multiply(off)
        est = centro + n.Multiply(mezzo)
        int_ = centro - n.Multiply(mezzo)
    centro = (est + int_).Divide(2.0)
    return est, int_, centro, n


def _chiave_muro(wall):
    """Cambia quando il muro viene spostato, invertito o cambia tipo/spessore."""
    curva = getattr(wall.Location, "Curve", None)
    estremi = ()
    if curva is not None:
        for k in (0, 1):
            q = curva.GetEndPoint(k)
            estremi += (round(q.X, 6), round(q.Y, 6), round(q.Z, 6))
    p = wall.get_Parameter(DB.BuiltInParameter.WALL_KEY_REF_PARAM)
    return (wall.Flipped, estremi, round(wall.Width, 6),
            p.AsInteger() if p is not None else 0, PS._id_val(wall.GetTypeId()))


def _posizioni_lettere(uidoc, ids, distacco, cache):
    """Lista di (lettera, x, y) in pixel fisici per i muri selezionati, dentro la vista.

    cache: {id muro: (chiave, facce)}: la geometria si rilegge solo se il muro cambia.
    """
    ctx = _contesto_vista(uidoc)
    if ctx is None:
        return None, []
    vista, uv, zoom, finestra = ctx
    if not isinstance(vista, (DB.ViewPlan, DB.ViewSection)):
        return finestra, []
    doc = uidoc.Document
    f_sx, f_alto, f_dx, f_basso = finestra
    out = []
    for eid in list(ids)[:MAX_MURI_LETTERE]:
        wall = doc.GetElement(eid)
        if not isinstance(wall, DB.Wall):
            continue
        try:
            chiave = _chiave_muro(wall)
            voce = cache.get(PS._id_val(eid))
            if voce is None or voce[0] != chiave:
                voce = (chiave, _facce_muro(wall))
                cache[PS._id_val(eid)] = voce
            facce = voce[1]
        except Exception:
            facce = None
        if facce is None:
            continue
        est, int_, centro, n = facce
        pr = lambda q: TC.proietta(uv(q), zoom, finestra)
        pos = TC.posizioni_da_facce(pr(est), pr(int_), (pr(centro), pr(centro + n)), distacco)
        if pos is None:
            continue
        for lettera, (x, y) in zip((u"E", u"I"), pos):
            if f_sx <= x <= f_dx and f_alto <= y <= f_basso:
                out.append((lettera, x, y))
    return finestra, out


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
        self.win_lettere = None
        self.muri = False
        self.ultime_lettere = None
        self.cache_muri = {}
        self.timer = None
        self.gancio = None
        self.cfg = PAL.config_predefinita()
        self.cfg_data = -1          # data del file palette.json letto (None = non esiste)
        self.disponibili = None
        self.ancora = None          # punto del clic, in coordinate della vista
        self.sospesa = False        # comando in corso: palette via fino alla fine
        self.sospesa_revit = False  # ... ed e' un comando di Revit (torna con DocumentChanged)
        self.win_menu = None        # menu "..." (o di un gruppo CDV)
        self.menu_da = None         # tasto che ha aperto il menu

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
        self.gestore.al_termine = self._fine_azione
        self.evento = UI.ExternalEvent.Create(self.gestore)
        # Durante pan e zoom Revit non manda Idling: i tasti resterebbero fermi mentre
        # il disegno si sposta. Un timer guarda il mouse e li toglie finche' ci si muove.
        self.timer = DispatcherTimer()
        self.timer.Interval = TimeSpan.FromMilliseconds(CONTROLLO_MOUSE_MS)
        self.timer.Tick += self._su_timer

    def _su_mouse(self, messaggio):
        """Dall'hook: rotellina premuta o girata = la vista si muove, via subito tutto.
        Clic sinistro = forse si trascina un muro, via le lettere.
        Tornano al prossimo Idling, gia' nella posizione nuova."""
        if not self.attivo:
            return
        if messaggio == _GancioMouse.WM_LBUTTONDOWN:
            self._nascondi_lettere()
            # clic fuori da palette e menu: il menu si chiude
            if not (self._sotto_cursore(self.win_menu) or self._sotto_cursore(self.win)):
                self._chiudi_menu()
        else:
            self._chiudi_menu()
            self._nascondi_finestra()
            self._nascondi_lettere()

    def _sotto_cursore(self, win):
        if win is None or win.Visibility != Visibility.Visible:
            return False
        try:
            mp = Control.MousePosition
            k = self.scala
            return (win.Left * k <= mp.X <= (win.Left + win.ActualWidth) * k
                    and win.Top * k <= mp.Y <= (win.Top + win.ActualHeight) * k)
        except Exception:
            return False

    def _su_timer(self, sender, args):
        try:
            if not self.attivo:
                self.timer.Stop()
                return
            centrale, sinistro = _tasti_premuti()
            if centrale:
                # pan con la rotellina premuta: via tasti e lettere fino al rilascio
                self._nascondi_finestra()
                self._nascondi_lettere()
            elif sinistro:
                # trascinamento (es. muro spostato): via le lettere, i tasti restano cliccabili
                self._nascondi_lettere()
        except Exception:
            pass

    def _crea_finestra_lettere(self):
        win = XamlReader.Parse(XAML_LETTERE)
        try:
            WindowInteropHelper(win).Owner = self.uiapp.MainWindowHandle
        except Exception:
            win.Topmost = True
        _non_attivabile(win, trasparente_ai_clic=True)
        self.win_lettere = win

    def _lettera(self, testo):
        t = TextBlock()
        t.Text = testo
        t.FontSize = 9
        t.FontWeight = FontWeights.Bold
        t.Foreground = _colore("#FFFFFF")
        t.HorizontalAlignment = HorizontalAlignment.Center
        t.VerticalAlignment = VerticalAlignment.Center
        b = Border()
        b.Width = DIM_LETTERA
        b.Height = DIM_LETTERA
        b.CornerRadius = CornerRadius(DIM_LETTERA / 2.0)
        b.Background = _colore(COLORE_ESTERNO if testo == u"E" else COLORE_INTERNO)
        b.BorderBrush = _colore("#FFFFFF")
        b.BorderThickness = Thickness(1)
        b.Child = t
        return b

    def _nascondi_lettere(self):
        self.ultime_lettere = None
        if self.win_lettere is not None and self.win_lettere.Visibility == Visibility.Visible:
            self.win_lettere.Hide()

    def _aggiorna_lettere(self, uidoc):
        """Lettere E / I ai lati dei muri selezionati (seguono zoom, pan e inversioni)."""
        if not (self.attivo and self.muri) or uidoc is None:
            self._nascondi_lettere()
            return
        if any(_tasti_premuti()):
            self._nascondi_lettere()
            return
        finestra, lettere = _posizioni_lettere(uidoc, self.ids, DISTACCO_LETTERA * self.scala,
                                               self.cache_muri)
        if finestra is None or not lettere:
            self._nascondi_lettere()
            return
        k = self.scala
        f_sx, f_alto, f_dx, f_basso = finestra
        stato = (tuple(round(v / k) for v in finestra),
                 tuple((l, round(x / k), round(y / k)) for l, x, y in lettere))
        if self.win_lettere is None:
            self._crea_finestra_lettere()
        if stato != self.ultime_lettere:
            self.ultime_lettere = stato
            w = self.win_lettere
            w.Left, w.Top = f_sx / k, f_alto / k
            w.Width, w.Height = max((f_dx - f_sx) / k, 1), max((f_basso - f_alto) / k, 1)
            tela = w.FindName("tela")
            tela.Children.Clear()
            meta = DIM_LETTERA / 2.0
            for lettera, x, y in lettere:
                el = self._lettera(lettera)
                Canvas.SetLeft(el, (x - f_sx) / k - meta)
                Canvas.SetTop(el, (y - f_alto) / k - meta)
                tela.Children.Add(el)
        if self.win_lettere.Visibility != Visibility.Visible:
            self.win_lettere.Show()

    # --- costruzione della palette -------------------------------------------
    def _icona(self, tracciato, colore, dim=DIM_ICONA):
        icona = Path()
        icona.Data = Geometry.Parse(tracciato or u"M2,2 H14 V14 H2 Z")
        icona.Fill = _colore(colore)
        icona.Width = dim
        icona.Height = dim
        icona.Stretch = Stretch.Uniform
        return icona

    def _tracciato(self, comando):
        cmd = PAL.PER_ID.get(comando)
        return cmd.icona if cmd is not None else TC.ICONE.get(comando)

    def _tasto(self, comando, etichetta, suggerimento, stile=None, colore="#0369A1", dim=DIM_ICONA):
        b = Button()
        if stile:
            b.Style = self.win.FindResource(stile)
        b.Content = self._icona(self._tracciato(comando), colore, dim)
        b.ToolTip = u"%s\n%s" % (etichetta, suggerimento)
        b.Click += lambda s, a: self._esegui(comando)
        return b

    def _tasto_menu(self, tracciato, suggerimento, sezioni, stile=None, colore="#475569"):
        """Tasto che apre un menu (il "..." o un gruppo di strumenti CDV)."""
        b = Button()
        if stile:
            b.Style = self.win.FindResource(stile)
        riga = StackPanel()
        riga.Orientation = Orientation.Horizontal
        riga.Children.Add(self._icona(tracciato, colore, DIM_ICONA if not stile else 13))
        if stile == u"Primario":
            b.Width = 30
            freccia = self._icona(u"M0,0 H8 L4,5 Z", colore, 5)
            freccia.Margin = Thickness(2, 0, 0, 0)
            riga.Children.Add(freccia)
        b.Content = riga
        b.ToolTip = suggerimento
        b.Click += lambda s, a: self._apri_menu(b, sezioni)
        return b

    def _separatore(self):
        sep = Border()
        sep.Width = 1
        sep.Height = 16
        sep.Margin = Thickness(3, 0, 3, 0)
        sep.Background = _colore("#CBD5E1")
        return sep

    def _riempi(self, st):
        """Riga principale (CDV in blu | comandi in vista | ...) e sotto la fila fissa."""
        self._chiudi_menu()
        pnl = self.win.FindName("pnlTasti")
        pnl.Children.Clear()
        riga = StackPanel()
        riga.Orientation = Orientation.Horizontal
        for v in st[u"cdv"]:
            if v[0] == u"tasto":
                riga.Children.Add(self._tasto(v[1], v[2], v[3], stile=u"Primario", colore="#FFFFFF"))
            else:
                nome, tasti = v[1], v[2]
                riga.Children.Add(self._tasto_menu(self._tracciato(tasti[0][0]), nome,
                                                   [(nome, tasti)], stile=u"Primario",
                                                   colore="#FFFFFF"))
        if st[u"cdv"] and (st[u"vista"] or st[u"menu"]):
            riga.Children.Add(self._separatore())
        for comando, etichetta, suggerimento in st[u"vista"]:
            riga.Children.Add(self._tasto(comando, etichetta, suggerimento))
        if st[u"menu"]:
            if st[u"vista"]:
                riga.Children.Add(self._separatore())
            riga.Children.Add(self._tasto_menu(ICONA_ALTRO, u"Altri comandi", st[u"menu"]))
        if riga.Children.Count:
            pnl.Children.Add(riga)
        if st[u"fissa"]:
            fila = StackPanel()
            fila.Orientation = Orientation.Horizontal
            for comando, etichetta, suggerimento in st[u"fissa"]:
                fila.Children.Add(self._tasto(comando, etichetta, suggerimento, stile=u"Piccolo",
                                              colore="#475569", dim=12))
            fondo = Border()
            fondo.Child = fila
            fondo.Background = _colore("#F1F5F9")
            fondo.CornerRadius = CornerRadius(3)
            fondo.Padding = Thickness(1)
            fondo.HorizontalAlignment = HorizontalAlignment.Left
            if riga.Children.Count:
                fondo.Margin = Thickness(0, 2, 0, 0)
            pnl.Children.Add(fondo)
        self.win.Content.Measure(Size(Double.PositiveInfinity, Double.PositiveInfinity))
        self.ultima_pos = None

    # --- menu "..." -------------------------------------------------------------
    def _crea_menu(self):
        win = XamlReader.Parse(XAML_MENU)
        try:
            WindowInteropHelper(win).Owner = self.uiapp.MainWindowHandle
        except Exception:
            win.Topmost = True
        _non_attivabile(win)
        self.win_menu = win

    def _voce_menu(self, comando, etichetta, suggerimento):
        b = Button()
        b.Style = self.win_menu.FindResource(u"Voce")
        riga = StackPanel()
        riga.Orientation = Orientation.Horizontal
        riga.Children.Add(self._icona(self._tracciato(comando), "#0369A1"))
        t = TextBlock()
        t.Text = etichetta
        t.Margin = Thickness(8, 0, 0, 0)
        t.Foreground = _colore("#0F172A")
        t.VerticalAlignment = VerticalAlignment.Center
        riga.Children.Add(t)
        b.Content = riga
        b.ToolTip = suggerimento
        b.HorizontalAlignment = HorizontalAlignment.Stretch
        b.Click += lambda s, a: self._esegui(comando)
        return b

    def _apri_menu(self, tasto, sezioni):
        if self.menu_da is tasto and self.win_menu is not None \
                and self.win_menu.Visibility == Visibility.Visible:
            self._chiudi_menu()     # secondo clic sullo stesso tasto: chiude
            return
        if self.win_menu is None:
            self._crea_menu()
        pnl = self.win_menu.FindName("pnlTasti")
        pnl.Children.Clear()
        for titolo, tasti in sezioni:
            t = TextBlock()
            t.Text = titolo.upper()
            t.FontSize = 10
            t.FontWeight = FontWeights.SemiBold
            t.Foreground = _colore("#64748B")
            t.Margin = Thickness(10, 6 if pnl.Children.Count else 2, 10, 2)
            pnl.Children.Add(t)
            for comando, etichetta, suggerimento in tasti:
                pnl.Children.Add(self._voce_menu(comando, etichetta, suggerimento))
        self.win_menu.Content.Measure(Size(Double.PositiveInfinity, Double.PositiveInfinity))
        dim = self.win_menu.Content.DesiredSize
        # sotto il tasto, allineato a sinistra; sopra se in basso non c'e' posto
        k = self.scala
        basso_sx = tasto.PointToScreen(Point(0, tasto.ActualHeight))
        alto_sx = tasto.PointToScreen(Point(0, 0))
        x, y = basso_sx.X / k, basso_sx.Y / k + 2
        schermo = SystemParameters.WorkArea
        if y + dim.Height > schermo.Bottom:
            y = alto_sx.Y / k - dim.Height - 2
        if x + dim.Width > schermo.Right:
            x = schermo.Right - dim.Width
        self.win_menu.Left, self.win_menu.Top = x, y
        self.menu_da = tasto
        self.win_menu.Show()

    def _chiudi_menu(self):
        self.menu_da = None
        if self.win_menu is not None and self.win_menu.Visibility == Visibility.Visible:
            self.win_menu.Hide()

    def riposiziona(self, uidoc):
        """Mette la palette accanto al punto del clic (o sul bordo superiore della selezione
        se e' stata fatta fuori dalla vista); la nasconde se e' fuori vista."""
        if self.win is None or not self.attivo:
            return
        if self.sospesa:
            self._nascondi_finestra()
            self._nascondi_lettere()
            return
        try:
            self._aggiorna_lettere(uidoc)
        except Exception:
            self._nascondi_lettere()
        if _tasti_premuti()[0]:
            # vista in movimento: si rimettono a posto quando si rilascia
            self._nascondi_finestra()
            return
        pos = None
        dim = self.win.Content.DesiredSize
        larg, alt = dim.Width * self.scala, dim.Height * self.scala
        if uidoc is not None and self.ancora is not None:
            ctx = _contesto_vista(uidoc)
            if ctx is not None:
                _vista, _uv, zoom, finestra = ctx
                punto = TC.proietta(self.ancora, zoom, finestra)
                pos = PAL.posizione_palette(punto, finestra, larg, alt)
        elif uidoc is not None:
            esito = _riquadro_selezione(uidoc, self.ids)
            if esito is not None:
                riquadro, finestra = esito
                pos = TC.posizione_striscia(riquadro, finestra, larg, alt)
        if pos is None:
            self._nascondi_finestra()
            return
        pos = (round(pos[0] / self.scala), round(pos[1] / self.scala))
        if pos != self.ultima_pos:
            if self.ultima_pos is not None:
                self._chiudi_menu()
            self.win.Left, self.win.Top = pos
            self.ultima_pos = pos
        if self.win.Visibility != Visibility.Visible:
            self.win.Show()

    def mostra(self, uidoc, ids, struttura, madre_uid):
        if self.win is None:
            self._crea_finestra()
        self.madre_uid = madre_uid
        self.ids = list(ids)
        self.muri = any(v[0] == u"tasto" and v[1] == TC.MURO_INVERTI for v in struttura[u"cdv"])
        self.ultime_lettere = None
        self.cache_muri = {}
        self.ancora = self._ancora_cursore(uidoc)
        self.attivo = True
        if self.timer is not None and not self.timer.IsEnabled:
            self.timer.Start()
        self._riempi(struttura)
        self.riposiziona(uidoc)

    def _ancora_cursore(self, uidoc):
        """Punto del cursore in coordinate della vista, se il cursore e' dentro la vista."""
        try:
            ctx = _contesto_vista(uidoc)
            if ctx is None:
                return None
            _vista, _uv, zoom, finestra = ctx
            mp = Control.MousePosition
            cursore = (float(mp.X), float(mp.Y))
            if not PAL.dentro(cursore, finestra):
                return None
            return PAL.schermo_a_vista(cursore, zoom, finestra)
        except Exception:
            return None

    def _nascondi_finestra(self):
        if self.win is not None and self.win.Visibility == Visibility.Visible:
            self.win.Hide()

    def nascondi(self):
        self._chiudi_menu()
        self.attivo = False
        self.ids = []
        self.muri = False
        if self.timer is not None:
            self.timer.Stop()
        self._nascondi_finestra()
        self._nascondi_lettere()

    def _esegui(self, comando):
        if self.evento is None:
            return
        self.gestore.comando = comando
        self.gestore.madre_uid = self.madre_uid
        try:
            self.gestore.maiuscolo = (Keyboard.Modifiers & ModifierKeys.Shift) == ModifierKeys.Shift
        except Exception:
            self.gestore.maiuscolo = False
        self._chiudi_menu()
        cmd = PAL.PER_ID.get(comando)
        if cmd is not None and (cmd.esecuzione == PAL.REVIT or cmd.interattivo):
            # Sposta, Copia, Copia grafica...: la palette si toglie e torna a comando
            # finito (DocumentChanged per i comandi di Revit, fine azione per i nostri)
            # o quando cambia la selezione.
            self.sospesa = True
            self.sospesa_revit = cmd.esecuzione == PAL.REVIT
            self._nascondi_finestra()
            self._nascondi_lettere()
        elif comando == TC.SEZIONE_APRI:
            # Si apre una finestra: i tasti si tolgono di mezzo e tornano dopo
            # (chiave azzerata = la selezione viene riletta al prossimo Idling).
            self.nascondi()
            self.chiave_sel = None
        self.evento.Raise()

    # --- selezione ------------------------------------------------------------
    def _rileggi_config(self):
        """Rilegge palette.json solo se e' cambiato (es. Palette On/Off)."""
        percorso = PAL.percorso_config()
        try:
            data = os.path.getmtime(percorso) if os.path.exists(percorso) else None
        except Exception:
            data = None
        if data == self.cfg_data:
            return
        self.cfg_data = data
        self.cfg = PAL.carica_config(percorso)
        self.chiave_sel = None   # la selezione si rianalizza con la nuova configurazione

    def aggiorna(self, uidoc, ids):
        try:
            self._rileggi_config()
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
            self.sospesa = False
            self.sospesa_revit = False
            esito = _analizza_selezione(doc, ids, self.cfg, self.disponibili)
            if esito is None:
                self.nascondi()
            else:
                struttura, madre_uid = esito
                self.mostra(uidoc, ids, struttura, madre_uid)
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
            self._nascondi_lettere()

    def _su_chiusura(self, sender, args):
        self.chiave_sel = None
        self.nascondi()

    def _su_modifica(self, sender, args):
        # Comando di Revit finito (es. Sposta): la palette torna, sul bordo della
        # selezione perche' gli elementi si sono spostati dal punto del clic.
        if self.sospesa and self.sospesa_revit:
            self._riprendi()

    def _fine_azione(self, comando):
        # Azione nostra finita (es. Copia grafica dopo Esc): la palette torna
        cmd = PAL.PER_ID.get(comando)
        if self.sospesa and cmd is not None and not self.sospesa_revit:
            self._riprendi()

    def _riprendi(self):
        # Torna sul bordo della selezione: gli elementi possono essersi spostati
        self.sospesa = False
        self.sospesa_revit = False
        self.ancora = None
        self.ultima_pos = None

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
        d = EventHandler[DB.Events.DocumentChangedEventArgs](self._su_modifica)
        self.uiapp.Application.DocumentChanged += d
        self.delegati.append(("DocumentChanged", d))
        try:
            self.disponibili = _comandi_disponibili()
        except Exception:
            self.disponibili = None
        try:
            gancio = _GancioMouse(self._su_mouse)
            if gancio.attacca():
                self.gancio = gancio
        except Exception:
            # senza hook resta il timer (piu' lento con pan veloci)
            self.gancio = None


    def spegni(self):
        for nome, d in self.delegati:
            try:
                if nome == "SelectionChanged":
                    self.uiapp.SelectionChanged -= d
                elif nome == "Idling":
                    self.uiapp.Idling -= d
                elif nome == "DocumentClosing":
                    self.uiapp.Application.DocumentClosing -= d
                elif nome == "DocumentChanged":
                    self.uiapp.Application.DocumentChanged -= d
            except Exception:
                pass
        self.delegati = []
        if self.gancio is not None:
            self.gancio.stacca()
            self.gancio = None
        if self.timer is not None:
            try:
                self.timer.Stop()
            except Exception:
                pass
        for win in (self.win, self.win_lettere, self.win_menu):
            if win is not None:
                try:
                    win.Close()
                except Exception:
                    pass
        self.win = None
        self.win_lettere = None
        self.win_menu = None


def attiva(uiapp):
    """Accende palette e tasti in sovraimpressione (spegne quelli di un caricamento precedente)."""
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
