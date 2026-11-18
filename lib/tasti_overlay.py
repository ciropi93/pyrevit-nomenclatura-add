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
    E (esterno) e I (interno) sui due lati, in pianta e in sezione;
  - una immagine raster: "Ritaglia immagine".
Doppio clic dove non c'e' nulla (selezione vuota): palette per creare annotazioni
(quote, campiture, testo, etichette); un clic altrove la chiude.
Se la selezione arriva dal browser di progetto (cursore fuori dalla vista) la palette
sta sul bordo superiore della selezione. Il pulsante "Palette On/Off" la spegne tutta.

Viene attivato da startup.py dell'estensione. Usa l'evento SelectionChanged
(Revit 2023+) e l'evento Idling, che rilegge la selezione nelle versioni precedenti
e rimette i tasti sul bordo dopo zoom e pan. La posizione si ricava da
UIView.GetZoomCorners / GetWindowRectangle. I tasti lavorano tramite ExternalEvent.
"""
import os
import imp
import sys
import time

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
from System import Double, EventHandler, TimeSpan
from System.Windows import Point, Size, Thickness, Visibility
from System.Windows import CornerRadius, FontWeights, HorizontalAlignment, VerticalAlignment
from System.Windows import TextAlignment, TextWrapping
from System.Windows.Controls import (Border, Button, Canvas, Grid, Orientation, StackPanel,
                                     TextBlock, WrapPanel)
from System.Windows.Input import Keyboard, ModifierKeys
from System.Windows.Interop import WindowInteropHelper
from System.Windows.Markup import XamlReader
from System.Windows.Media import Geometry
from System.Windows.Shapes import Path
from System.Windows.Threading import DispatcherTimer
from System.Windows.Forms import Control, MouseButtons, Screen, SystemInformation
from System.Drawing import Point as PuntoSchermo
from Autodesk.Revit import DB, UI

# Import qui, all'avvio: quando poi scatta l'ExternalEvent la cartella lib
# dell'estensione non e' piu' nel sys.path e un import li' fallirebbe.
import allinea_in_tavola as AIT
import profondita_sezione as PS
import tasti_contestuali as TC
import palette as PAL
import palette_azioni as PA
import allinea_oggetti as AO
import icone_wpf as IW
import finestre_wpf as FW
import avviso as AV
import avviso_wpf as AVW


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
SCRIPT_RITAGLIA = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    u"CDV Tools.tab", u"Tavole.panel", u"CropImage.pushbutton", u"script.py",
)
_LIB = os.path.dirname(os.path.abspath(__file__))
ATTESA_DOPPIO_CLIC_S = 0.8   # oltre, il doppio clic non apre piu' la palette annotazioni
DIM_TASTO = 22
DIM_LETTERA = 14          # cerchietto della lettera E / I
DISTACCO_LETTERA = 10     # pixel tra la faccia del muro e il centro della lettera
CONTROLLO_MOUSE_MS = 40   # timer di riserva (solo se l'hook del mouse non parte)
CONTROLLO_CONFIG_S = 1.0  # ogni quanto, al massimo, si guarda se palette.json e' cambiato
DURATA_CACHE_SEZIONI_S = 20.0  # oltre, le coppie sezione/sfondo si rileggono comunque
ATTESA_COMANDO_S = 0.4    # dopo aver lanciato un comando di Revit, prima di credere che sia finito
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
    <!-- tasto famiglia (riga sotto) -->
    <Style x:Key="Famiglia" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
      <Setter Property="Width" Value="28"/>
      <Setter Property="Height" Value="26"/>
    </Style>
    <!-- famiglia di strumenti CDV della categoria: sfondo azzurro con bordo blu -->
    <Style x:Key="FamigliaCdv" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
      <Setter Property="Width" Value="28"/>
      <Setter Property="Height" Value="26"/>
      <Setter Property="Template">
        <Setter.Value>
          <ControlTemplate TargetType="Button">
            <Border x:Name="sfondo" Background="#E5EEF7" BorderBrush="#1F6FB2" BorderThickness="1"
                    CornerRadius="3">
              <ContentPresenter HorizontalAlignment="Center" VerticalAlignment="Center"/>
            </Border>
            <ControlTemplate.Triggers>
              <Trigger Property="IsMouseOver" Value="True">
                <Setter TargetName="sfondo" Property="Background" Value="#CFE3F4"/>
              </Trigger>
              <Trigger Property="IsPressed" Value="True">
                <Setter TargetName="sfondo" Property="Background" Value="#BAE6FD"/>
              </Trigger>
            </ControlTemplate.Triggers>
          </ControlTemplate>
        </Setter.Value>
      </Setter>
    </Style>
    <!-- fila fissa: tasti piccoli -->
    <Style x:Key="Piccolo" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
      <Setter Property="Width" Value="19"/>
      <Setter Property="Height" Value="19"/>
    </Style>
    <!-- casella della griglia che si apre sopra una famiglia: icona e nome -->
    <Style x:Key="Casella" TargetType="Button" BasedOn="{StaticResource {x:Type Button}}">
      <Setter Property="Width" Value="68"/>
      <Setter Property="Height" Value="56"/>
      <Setter Property="Margin" Value="1"/>
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
XAML_MENU = _FINESTRA % (_STILI, 8, u"6", 8)

# Famiglie CDV che non dipendono dalle viste del modello (le altre: sezioni, titoli, viste)
NOMI_CDV_OGGETTI = frozenset([u"Muri", u"Allinea oggetti", u"Distribuisci oggetti", u"Immagine"])
TEMPO_APERTURA_MS = 250   # mouse fermo su una famiglia: si apre la griglia
TEMPO_CHIUSURA_MS = 350   # mouse fuori da famiglia e griglia: si chiude
CASELLE_PER_RIGA = 3

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

_colore = IW.colore


def _avvisa(msg):
    try:
        from pyrevit import forms
        forms.alert(msg, title=TITOLO)
    except Exception:
        UI.TaskDialog.Show(TITOLO, msg)


_UIAPP = [None]   # impostato da attiva(): serve all'avviso per trovare la vista attiva


def _toast(msg):
    """Esito: avviso piccolo in basso a destra nella vista (vedi avviso_wpf.py)."""
    AVW.mostra(msg, AV.INFO, _UIAPP[0])


def _errore(msg):
    """Errore semplice (azione non possibile): avviso rosso, senza finestra da chiudere."""
    AVW.mostra(msg, AV.ERRORE, _UIAPP[0])


_non_attivabile = FW.non_attivabile


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


def _coppie_valide(valore):
    try:
        return all(c["madre"].IsValidObject and c["sfondo"].IsValidObject for c in valore[0])
    except Exception:
        return False


def _coppie_sezioni(doc, cache):
    """PS.trova_coppie_sezioni scorre tutte le viste: si rifa' solo quando serve.

    cache: {"versione", "chiave", "valore", "quando"} dell'overlay. Si rilegge se:
      - "versione" e' salita (una vista o un riquadro e' cambiato in questo Revit);
      - sono passati DURATA_CACHE_SEZIONI_S (modifiche che non passano da DocumentChanged:
        Ricarica ultimi / sincronizzazione di un modello condiviso);
      - una vista in cache non e' piu' valida.
    La cache si svuota quando un documento si chiude.
    """
    if cache is None:
        return PS.trova_coppie_sezioni(doc)
    chiave = (doc.PathName or doc.Title, cache.get(u"versione", 0))
    adesso = time.time()
    if (cache.get(u"chiave") != chiave
            or adesso - cache.get(u"quando", 0.0) > DURATA_CACHE_SEZIONI_S
            or not _coppie_valide(cache.get(u"valore"))):
        cache[u"valore"] = PS.trova_coppie_sezioni(doc)
        cache[u"chiave"] = chiave
        cache[u"quando"] = adesso
    return cache[u"valore"]


def _gruppi_cdv(doc, elementi, cache=None):
    """Strumenti CDV legati al contesto: (gruppi, madre_uid).

    Muri: Inverti sul centro. Soli riquadri di vista (in tavola) o una sola linea di
    sezione/prospetto: Profondita' Sezione e allineamenti in tavola. Altri oggetti
    (2 o piu'): allinea e distribuisci nella vista (non in 3D).
    """
    # Allinea/Distribuisci oggetti: non nelle viste 3D (li' "alto" e' una direzione obliqua)
    vista = doc.ActiveView
    n_allinea = len(elementi) if (vista is not None
                                  and AO.vista_ammessa(str(vista.ViewType))) else 0
    muri = [e for e in elementi if isinstance(e, DB.Wall)]
    if muri and len(muri) == len(elementi):
        return TC.comandi_per_selezione(0, in_tavola=False, n_muri=len(muri),
                                        n_oggetti=n_allinea), None
    viewports = [e for e in elementi if isinstance(e, DB.Viewport)]
    viewers = [e for e in elementi if _e_viewer(e)]

    if len(viewports) == len(elementi):
        voci = None
    elif len(viewers) == 1 and len(elementi) == 1:
        voci = [(u"viewer", viewers[0].Name)]
    elif not viewports:
        # oggetti del modello o di dettaglio: allinea / distribuisci da 2 in su;
        # solo immagini raster: Ritaglia (con una)
        immagini = [e for e in elementi if isinstance(e, DB.ImageInstance)]
        n_immagini = len(immagini) if len(immagini) == len(elementi) else 0
        return TC.comandi_per_selezione(0, in_tavola=False, n_oggetti=n_allinea,
                                        n_immagini=n_immagini), None
    else:
        return [], None

    coppie, _, sfondo_to_madre = _coppie_sezioni(doc, cache)
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


def _analizza_selezione(doc, ids, cfg, disponibili, cache=None):
    """Ritorna (struttura, madre_uid) oppure None se non c'e' nulla da proporre.

    struttura: vedi palette.struttura_palette (fila fissa e famiglie, prima quelle CDV).
    cache: cache delle coppie sezione/sfondo dell'overlay (vedi _coppie_sezioni).
    """
    if doc is None or doc.IsFamilyDocument or not ids or not cfg.get(u"attiva", True):
        return None
    elementi = [e for e in (doc.GetElement(i) for i in ids) if e is not None]
    if not elementi:
        return None
    chiavi = set(PAL.chiave_categoria(_nome_ost(e), e.GetType().Name) for e in elementi)
    cdv, madre_uid = _gruppi_cdv(doc, elementi, cache)
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


def _ritaglia_immagine():
    """Apre Ritaglia Immagine sull'immagine selezionata."""
    # lo script importa ritaglio_immagine: dentro l'ExternalEvent la cartella lib
    # dell'estensione non e' piu' nel sys.path
    if _LIB not in sys.path:
        sys.path.append(_LIB)
    modulo = imp.load_source("cdv_cropimage_script", SCRIPT_RITAGLIA)
    modulo.main()


def _comandi_disponibili():
    """Id della palette utilizzabili in questa versione di Revit."""
    out = set()
    for c in PAL.CATALOGO + PAL.ANNOTAZIONI:
        if c.esecuzione != PAL.REVIT or getattr(UI.PostableCommand, c.postable, None) is not None:
            out.add(c.id)
    return out


def _posta_comando(uiapp, nome):
    """Lancia un comando nativo di Revit: parte dopo l'ExternalEvent, con la selezione attuale.
    Ritorna True se il comando e' stato lanciato."""
    pc = getattr(UI.PostableCommand, nome, None)
    cid = UI.RevitCommandId.LookupPostableCommandId(pc) if pc is not None else None
    if cid is None or not uiapp.CanPostCommand(cid):
        _errore(u"Il comando di Revit non si può avviare adesso.")
        return False
    uiapp.PostCommand(cid)
    return True


def _sincronizza(doc, madre_uid):
    madre = doc.GetElement(madre_uid)
    if madre is None:
        _errore(u"Sezione non trovata nel documento attivo.")
        return
    coppie, _, _ = PS.trova_coppie_sezioni(doc)
    coppia = None
    for c in coppie:
        if c["madre"].UniqueId == madre_uid:
            coppia = c
            break
    if coppia is None:
        _errore(u"La sezione '%s' non ha uno sfondo collegato." % madre.Name)
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
        self.al_termine = None   # al_termine(comando, avviato): a fine azione

    def Execute(self, uiapp):
        comando, uid = self.comando, self.madre_uid
        self.comando = None
        avviato = False          # un comando di Revit e' stato lanciato davvero
        try:
            uidoc = uiapp.ActiveUIDocument
            if uidoc is None or not comando:
                return
            cmd = PAL.PER_ID.get(comando)
            if cmd is not None and cmd.esecuzione == PAL.REVIT:
                avviato = _posta_comando(uiapp, cmd.postable)
            elif cmd is not None:
                try:
                    msg = PA.esegui(uidoc, comando)
                except PA.AzioneErrore as ex:
                    _errore(u"%s" % ex)
                    return
                if msg:
                    _toast(msg)
            elif comando in AO.COMANDI:
                try:
                    _toast(PA.allinea_oggetti(uidoc, comando))
                except PA.AzioneErrore as ex:
                    _errore(u"%s" % ex)
            elif comando == TC.SEZIONE_APRI:
                _apri_profondita(uid)
            elif comando == TC.SEZIONE_SINCRONIZZA:
                _sincronizza(uidoc.Document, uid)
            elif comando == TC.MURO_INVERTI:
                _inverti_muri(self.maiuscolo)
            elif comando == TC.IMMAGINE_RITAGLIA:
                _ritaglia_immagine()
            else:
                # Allineamenti: lavorano sulla selezione corrente della tavola attiva
                AIT.esegui_da_ribbon(comando)
        except Exception as ex:
            _avvisa(u"Errore: %s" % ex)
        finally:
            if self.al_termine is not None:
                try:
                    self.al_termine(comando, avviato)
                except Exception:
                    pass

    def GetName(self):
        return u"CDV Tools - Tasti in sovraimpressione"


# ==============================================================================
# POSIZIONE SULLO SCHERMO
# ==============================================================================

_scala_dpi = FW.scala_dpi


def _tasti_premuti():
    """(centrale, sinistro): tasti del mouse premuti in questo momento (senza API Revit)."""
    b = Control.MouseButtons
    return ((b & MouseButtons.Middle) == MouseButtons.Middle,
            (b & MouseButtons.Left) == MouseButtons.Left)


class _Gancio(object):
    """Hook di Windows sul thread di Revit.

    filtro(w_param, l_param) ritorna l'evento da passare a su_evento, o None per
    ignorare il messaggio. Il filtro deve essere velocissimo: gira a ogni messaggio.
    """
    TIPO = None

    def __init__(self, filtro, su_evento):
        self.filtro = filtro
        self.su_evento = su_evento
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
        filtro, su_evento = self.filtro, self.su_evento

        def proc(n_code, w_param, l_param):
            # solo HC_ACTION (0): con HC_NOREMOVE (3) lo stesso messaggio arriverebbe due volte
            if n_code == 0:
                try:
                    evento = filtro(w_param, l_param)
                    if evento is not None:
                        su_evento(evento)
                except Exception:
                    pass
            return user32.CallNextHookEx(self.hhook, n_code, w_param, l_param)

        self._proc = HOOKPROC(proc)   # tenuto in vita finche' l'hook e' attivo
        self.hhook = user32.SetWindowsHookExW(self.TIPO, self._proc, None,
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


class _GancioMouse(_Gancio):
    """Clic, rotellina e movimento del mouse sulle finestre di Revit (e sulle nostre).

    Rotellina premuta o girata = pan/zoom: via subito tasti e lettere (durante il
    ridisegno Revit non manda Idling). Movimento = trasparenza "alla Office".
    """
    TIPO = 7                      # WH_MOUSE
    WM_MOUSEMOVE = 0x0200
    WM_LBUTTONDOWN = 0x0201
    WM_LBUTTONDBLCLK = 0x0203     # solo per le finestre che chiedono i doppi clic
    WM_MBUTTONDOWN = 0x0207
    WM_MOUSEWHEEL = 0x020A
    WM_MOUSEHWHEEL = 0x020E
    MESSAGGI = frozenset([WM_MOUSEMOVE, WM_LBUTTONDOWN, WM_LBUTTONDBLCLK, WM_MBUTTONDOWN,
                          WM_MOUSEWHEEL, WM_MOUSEHWHEEL])

    def __init__(self, su_evento):
        # segui_movimento: il movimento serve solo con la palette accanto al cursore;
        # altrimenti si scarta subito, senza chiamare l'overlay.
        self.segui_movimento = False
        messaggi = self.MESSAGGI
        mossa = self.WM_MOUSEMOVE

        def filtro(w, l):
            if w == mossa:
                return w if self.segui_movimento else None
            return w if w in messaggi else None

        _Gancio.__init__(self, filtro, su_evento)


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


def _firma_vista(ctx):
    """Cambia solo se la vista attiva, il suo zoom/pan o la sua finestra cambiano."""
    if ctx is None:
        return None
    vista, _uv, zoom, finestra = ctx
    (u0, v0), (u1, v1) = zoom
    return (PS._id_val(vista.Id), round(u0, 6), round(v0, 6), round(u1, 6), round(v1, 6), finestra)


def _riquadro_selezione(uidoc, ids, ctx=None):
    """(riquadro, finestra) in pixel fisici, oppure None.

    riquadro: ingombro sullo schermo degli elementi selezionati (riquadri di vista
    in tavola, linea di sezione o muri); finestra: area della vista attiva.
    """
    ctx = ctx or _contesto_vista(uidoc)
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
            punti.extend(uv(p) for p in PA.angoli_ingombro(el, vista))
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


def _posizioni_lettere(uidoc, ids, distacco, cache, ctx=None):
    """Lista di (lettera, x, y) in pixel fisici per i muri selezionati, dentro la vista.

    cache: {id muro: (chiave, facce)}: la geometria si rilegge solo se il muro cambia.
    """
    ctx = ctx or _contesto_vista(uidoc)
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

def _doc_vista(doc):
    vista = doc.ActiveView
    return (doc.PathName or doc.Title, PS._id_val(vista.Id) if vista is not None else None)


def _firma_struttura(st):
    """Uguale per due palette con gli stessi tasti (es. un muro dopo l'altro)."""
    return (tuple(v[0] for v in st[u"fissa"]),
            tuple((f[u"id"], tuple(v[0] for v in f[u"voci"])) for f in st[u"famiglie"]))


# Le coppie sezione/sfondo dipendono solo dalle viste (nome e parametri), non dalle tavole
# ne' dai riquadri: spostare una vista in tavola non le cambia.
_FILTRO_VISTE = DB.LogicalAndFilter(DB.ElementClassFilter(DB.View),
                                    DB.ElementClassFilter(DB.ViewSheet, True))


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
        self.comando_lanciato = None     # quando Revit ha ricevuto il comando (time.time)
        self.win_menu = None        # griglia della famiglia sotto il mouse
        self.menu_da = None         # tasto famiglia che l'ha aperta
        self.da_aprire = None
        self.t_apri = None
        self.t_chiudi = None
        self.famiglie = {}          # id famiglia -> (tasto, famiglia)
        self.fam_di = {}            # comando -> id famiglia
        self.ultimi = {}            # id famiglia -> ultimo strumento usato (in questa sessione)
        self.ha_evento_selezione = False   # Revit 2023+: la selezione arriva con l'evento
        self.doc_vista = None       # (documento, vista) dell'ultima selezione letta
        self.cfg_letta = 0.0        # quando si e' guardato l'ultima volta palette.json
        self.firma = None           # ultima vista/zoom su cui si e' posizionato tutto
        self.sporco = True          # qualcosa e' cambiato: riposizionare anche a vista ferma
        self.firma_struttura = None # palette uguale alla precedente: niente ricostruzione
        self.rett_palette = None    # dove sta la palette sullo schermo (pixel fisici)
        self.sparita = False        # allontanandosi col mouse la palette sparisce
        self.in_movimento = False   # pan/zoom in corso: niente da mostrare fino al prossimo Idling
        self.forza_analisi = False  # modello cambiato: rianalizzare la selezione corrente
        self.ids_val = frozenset()  # id (interi) degli elementi selezionati
        self.con_viste = False      # la selezione contiene riquadri di vista o linee di sezione
        self.cache_coppie = {}      # coppie sezione/sfondo (vedi _coppie_sezioni)
        self.modo_annotazioni = False   # palette del doppio clic (annotazioni) aperta
        self.ultimo_clic = None     # (secondi, x, y) dell'ultimo clic sinistro
        self.doppio_clic = None     # doppio clic da controllare al prossimo Idling

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
        clic = messaggio in (_GancioMouse.WM_LBUTTONDOWN, _GancioMouse.WM_LBUTTONDBLCLK)
        if clic:
            self._clic_sinistro(messaggio)
        if not self.attivo:
            return
        if messaggio == _GancioMouse.WM_MOUSEMOVE:
            self._su_movimento()
        elif clic:
            self._nascondi_lettere()
            self.sporco = True
            # clic fuori da palette e menu: il menu si chiude
            if not (self._sotto_cursore(self.win_menu) or self._sotto_cursore(self.win)):
                self._chiudi_menu()
        else:
            self._vista_in_movimento()

    def _clic_sinistro(self, messaggio):
        """Dall'hook. Un clic fuori dalle nostre finestre chiude la palette annotazioni;
        un doppio clic si segna e si controlla al prossimo Idling (_controlla_doppio_clic),
        quando Revit ha gia' aggiornato la selezione."""
        if self._sotto_cursore(self.win) or self._sotto_cursore(self.win_menu):
            self.ultimo_clic = None
            return
        if self.modo_annotazioni:
            self.nascondi()
        mp = Control.MousePosition
        clic = (time.time(), mp.X, mp.Y)
        if messaggio == _GancioMouse.WM_LBUTTONDBLCLK or PAL.doppio_clic(
                self.ultimo_clic, clic, SystemInformation.DoubleClickTime / 1000.0,
                max(SystemInformation.DoubleClickSize.Width, SystemInformation.DoubleClickSize.Height)):
            self.doppio_clic = clic
            self.ultimo_clic = None
        else:
            self.ultimo_clic = clic

    def _controlla_doppio_clic(self, uidoc):
        """Doppio clic nella vista dove non c'e' nulla: palette per creare annotazioni."""
        clic, self.doppio_clic = self.doppio_clic, None
        if clic is None or time.time() - clic[0] > ATTESA_DOPPIO_CLIC_S:
            return
        doc = uidoc.Document
        vista = doc.ActiveView
        if (not self.cfg.get(u"attiva", True) or doc.IsFamilyDocument or vista is None
                or str(vista.ViewType) not in PAL.VISTE_ANNOTAZIONI
                or uidoc.Selection.GetElementIds().Count):
            return      # doppio clic su un elemento (o in una vista senza annotazioni)
        ctx = _contesto_vista(uidoc)
        if ctx is None or not PAL.dentro((clic[1], clic[2]), ctx[3]):
            return      # doppio clic fuori dalla vista (es. browser di progetto)
        st = PAL.struttura_annotazioni(self.disponibili)
        if st is not None:
            self.mostra(uidoc, [], st, None)
            self.modo_annotazioni = True

    def _vista_in_movimento(self):
        """Pan o zoom: via palette, griglia e lettere; tornano al prossimo Idling."""
        self.in_movimento = True
        self._chiudi_menu()
        self._nascondi_finestra()
        self._nascondi_lettere()
        self.sporco = True

    def _su_movimento(self):
        """Trasparenza "alla Office": piena sopra, sbiadita lontano, sparisce oltre."""
        if (self.win is None or not self.attivo or self.sospesa or self.ancora is None
                or self.rett_palette is None or self.in_movimento):
            # durante pan/zoom rett_palette e' vecchio: la palette torna con l'Idling
            return
        mp = Control.MousePosition
        if self._sotto_cursore(self.win_menu):
            distanza = 0
        else:
            distanza = PAL.distanza_da_rettangolo((mp.X, mp.Y), self.rett_palette)
        opacita, sparita = PAL.opacita_palette(distanza, self.sparita)
        if sparita != self.sparita:
            self.sparita = sparita
            if sparita:
                self._chiudi_menu()
                self._nascondi_finestra()
            else:
                self.win.Show()
        if not sparita and abs(self.win.Opacity - opacita) > 0.01:
            self.win.Opacity = opacita

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
                self._vista_in_movimento()
            elif sinistro:
                # trascinamento (es. muro spostato): via le lettere, i tasti restano cliccabili
                self._nascondi_lettere()
                self.sporco = True
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

    def _aggiorna_segui(self):
        """Il movimento del mouse serve solo con la palette ancorata al cursore e visibile
        (o sparita allontanandosi, per farla tornare)."""
        if self.gancio is not None:
            self.gancio.segui_movimento = bool(
                self.attivo and not self.sospesa and self.ancora is not None
                and self.rett_palette is not None)

    def _aggiorna_lettere(self, uidoc, ctx=None):
        """Lettere E / I ai lati dei muri selezionati (seguono zoom, pan e inversioni)."""
        if not (self.attivo and self.muri) or uidoc is None:
            self._nascondi_lettere()
            return
        if any(_tasti_premuti()):
            self._nascondi_lettere()
            self.sporco = True
            return
        finestra, lettere = _posizioni_lettere(uidoc, self.ids, DISTACCO_LETTERA * self.scala,
                                               self.cache_muri, ctx)
        if finestra is None or not lettere:
            self._nascondi_lettere()
            return
        k = self.scala
        stato = tuple((l, round(x / k), round(y / k)) for l, x, y in lettere)
        if self.win_lettere is None:
            self._crea_finestra_lettere()
        if stato != self.ultime_lettere:
            self.ultime_lettere = stato
            # La finestra trasparente copre solo le lettere, non tutta la vista:
            # Windows ridisegna molto meno a ogni spostamento.
            meta = DIM_LETTERA / 2.0 + 1
            xs = [x / k for _, x, _ in lettere]
            ys = [y / k for _, _, y in lettere]
            sx, alto = min(xs) - meta, min(ys) - meta
            w = self.win_lettere
            w.Left, w.Top = sx, alto
            w.Width, w.Height = max(xs) + meta - sx, max(ys) + meta - alto
            tela = w.FindName("tela")
            tela.Children.Clear()
            for lettera, x, y in lettere:
                el = self._lettera(lettera)
                Canvas.SetLeft(el, x / k - sx - DIM_LETTERA / 2.0)
                Canvas.SetTop(el, y / k - alto - DIM_LETTERA / 2.0)
                tela.Children.Add(el)
        if self.win_lettere.Visibility != Visibility.Visible:
            self.win_lettere.Show()

    # --- costruzione della palette -------------------------------------------
    def _icona(self, comando, dim, colore_singolo="#1F6FB2"):
        dati = PAL.ICONE.get(comando) or TC.ICONE.get(comando)
        return IW.crea_icona(dati, dim, colore_singolo)

    def _tasto(self, comando, etichetta, suggerimento, stile, dim):
        b = Button()
        b.Style = self.win.FindResource(stile)
        b.Content = self._icona(comando, dim, "#475569" if stile == u"Piccolo" else "#1F6FB2")
        b.ToolTip = u"%s\n%s" % (etichetta, suggerimento)
        b.Click += lambda s, a: self._esegui(comando)
        return b

    def _contenuto_famiglia(self, fam):
        """Icona dell'ultimo strumento usato, con il triangolino se ce ne sono altri."""
        voci = fam[u"voci"]
        corrente = self.ultimi.get(fam[u"id"])
        if corrente not in [v[0] for v in voci]:
            corrente = voci[0][0]
        g = Grid()
        g.Width = 26
        g.Height = 24
        icona = self._icona(corrente, 16)
        icona.HorizontalAlignment = HorizontalAlignment.Center
        icona.VerticalAlignment = VerticalAlignment.Center
        g.Children.Add(icona)
        if len(voci) > 1:
            tri = Path()
            tri.Data = Geometry.Parse(u"M5,0 V5 H0 Z")
            tri.Fill = _colore("#94A3B8")
            tri.HorizontalAlignment = HorizontalAlignment.Right
            tri.VerticalAlignment = VerticalAlignment.Bottom
            tri.Margin = Thickness(0, 0, 2, 2)
            g.Children.Add(tri)
        return g, corrente

    def _tasto_famiglia(self, fam):
        b = Button()
        b.Style = self.win.FindResource(u"FamigliaCdv" if fam[u"cdv"] else u"Famiglia")
        self._aggiorna_famiglia(b, fam)
        b.Click += lambda s, a: self._esegui(b.Tag)
        b.MouseEnter += lambda s, a: self._entra_famiglia(b, fam)
        b.MouseLeave += lambda s, a: self._esci()
        return b

    def _aggiorna_famiglia(self, b, fam):
        contenuto, corrente = self._contenuto_famiglia(fam)
        b.Content = contenuto
        b.Tag = corrente
        nome = [v[1] for v in fam[u"voci"] if v[0] == corrente][0]
        b.ToolTip = None if len(fam[u"voci"]) > 1 else u"%s\n%s" % (nome, fam[u"voci"][0][2])

    def _riempi(self, st):
        """Sopra la fila fissa (piccola), sotto una riga di tasti famiglia."""
        self._chiudi_menu()
        pnl = self.win.FindName("pnlTasti")
        pnl.Children.Clear()
        self.famiglie = {}
        self.fam_di = {}
        if st[u"fissa"]:
            fila = StackPanel()
            fila.Orientation = Orientation.Horizontal
            for comando, etichetta, suggerimento in st[u"fissa"]:
                fila.Children.Add(self._tasto(comando, etichetta, suggerimento, u"Piccolo", 13))
            fondo = Border()
            fondo.Child = fila
            fondo.Background = _colore("#F1F5F9")
            fondo.CornerRadius = CornerRadius(4)
            fondo.Padding = Thickness(1)
            fondo.HorizontalAlignment = HorizontalAlignment.Left
            pnl.Children.Add(fondo)
        if st[u"famiglie"]:
            riga = StackPanel()
            riga.Orientation = Orientation.Horizontal
            if st[u"fissa"]:
                riga.Margin = Thickness(0, 2, 0, 0)
            for fam in st[u"famiglie"]:
                b = self._tasto_famiglia(fam)
                self.famiglie[fam[u"id"]] = (b, fam)
                for v in fam[u"voci"]:
                    self.fam_di[v[0]] = fam[u"id"]
                riga.Children.Add(b)
            pnl.Children.Add(riga)
        self.win.Content.Measure(Size(Double.PositiveInfinity, Double.PositiveInfinity))
        self.ultima_pos = None

    # --- griglia che si apre sopra una famiglia --------------------------------
    def _crea_menu(self):
        win = XamlReader.Parse(XAML_MENU)
        try:
            WindowInteropHelper(win).Owner = self.uiapp.MainWindowHandle
        except Exception:
            win.Topmost = True
        _non_attivabile(win)
        win.MouseEnter += lambda s, a: self.t_chiudi.Stop()
        win.MouseLeave += lambda s, a: self._esci()
        self.win_menu = win
        self.t_apri = DispatcherTimer()
        self.t_apri.Interval = TimeSpan.FromMilliseconds(TEMPO_APERTURA_MS)
        self.t_apri.Tick += self._su_t_apri
        self.t_chiudi = DispatcherTimer()
        self.t_chiudi.Interval = TimeSpan.FromMilliseconds(TEMPO_CHIUSURA_MS)
        self.t_chiudi.Tick += self._su_t_chiudi

    def _entra_famiglia(self, tasto, fam):
        if self.win_menu is None:
            self._crea_menu()
        self.t_chiudi.Stop()
        if len(fam[u"voci"]) < 2:
            self._chiudi_menu()
            return
        self.da_aprire = (tasto, fam)
        if self.win_menu.Visibility == Visibility.Visible:
            self._apri_menu(tasto, fam)      # gia' aperta su un'altra famiglia: cambia subito
        else:
            self.t_apri.Stop()
            self.t_apri.Start()

    def _esci(self):
        if self.win_menu is None:
            return
        self.t_apri.Stop()
        self.t_chiudi.Stop()
        self.t_chiudi.Start()

    def _su_t_apri(self, sender, args):
        self.t_apri.Stop()
        if self.da_aprire is not None and self.da_aprire[0].IsMouseOver:
            self._apri_menu(*self.da_aprire)

    def _su_t_chiudi(self, sender, args):
        self.t_chiudi.Stop()
        if self.win_menu is not None and self.win_menu.IsMouseOver:
            return
        if self.menu_da is not None and self.menu_da.IsMouseOver:
            return
        self._chiudi_menu()

    def _casella(self, fam_id, comando, etichetta, suggerimento):
        b = Button()
        b.Style = self.win_menu.FindResource(u"Casella")
        cella = StackPanel()
        icona = self._icona(comando, 22)
        icona.HorizontalAlignment = HorizontalAlignment.Center
        cella.Children.Add(icona)
        t = TextBlock()
        t.Text = etichetta
        t.FontSize = 10.5
        t.Foreground = _colore("#1E293B")
        t.TextAlignment = TextAlignment.Center
        t.TextWrapping = TextWrapping.Wrap
        t.MaxWidth = 64
        t.Margin = Thickness(0, 3, 0, 0)
        cella.Children.Add(t)
        b.Content = cella
        b.ToolTip = suggerimento
        b.Click += lambda s, a: self._esegui(comando)
        if comando == self.ultimi.get(fam_id):
            b.Background = _colore("#F0F9FF")
        return b

    def _apri_menu(self, tasto, fam):
        if self.win_menu is None:
            self._crea_menu()
        pnl = self.win_menu.FindName("pnlTasti")
        pnl.Children.Clear()
        t = TextBlock()
        t.Text = fam[u"nome"].upper()
        t.FontSize = 10
        t.FontWeight = FontWeights.SemiBold
        t.Foreground = _colore("#64748B")
        t.Margin = Thickness(4, 0, 4, 4)
        pnl.Children.Add(t)
        griglia = WrapPanel()
        griglia.Width = CASELLE_PER_RIGA * 70
        for comando, etichetta, suggerimento in fam[u"voci"]:
            griglia.Children.Add(self._casella(fam[u"id"], comando, etichetta, suggerimento))
        pnl.Children.Add(griglia)
        self.win_menu.Content.Measure(Size(Double.PositiveInfinity, Double.PositiveInfinity))
        dim = self.win_menu.Content.DesiredSize
        # sotto la palette, allineata al suo bordo sinistro; sopra se in basso non c'e' posto
        # (dentro il monitor dove sta la palette, non quello principale: se finisse su un
        # altro schermo il mouse non ci arriverebbe prima che si richiuda)
        k = self.scala
        alto = self.win.PointToScreen(Point(0, 0))
        basso = tasto.PointToScreen(Point(0, tasto.ActualHeight))
        a = Screen.FromPoint(PuntoSchermo(int(alto.X), int(alto.Y))).WorkingArea
        x, y = PAL.posizione_griglia(alto.X / k, basso.Y / k, alto.Y / k, dim.Width, dim.Height,
                                     (a.Left / k, a.Top / k, a.Right / k, a.Bottom / k))
        self.win_menu.Left, self.win_menu.Top = x, y
        self.menu_da = tasto
        if self.win_menu.Visibility != Visibility.Visible:
            self.win_menu.Show()

    def _chiudi_menu(self):
        self.menu_da = None
        self.da_aprire = None
        if self.win_menu is not None:
            self.t_apri.Stop()
            self.t_chiudi.Stop()
            if self.win_menu.Visibility == Visibility.Visible:
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
        if _tasti_premuti()[0]:
            # vista in movimento: si rimettono a posto quando si rilascia
            self._vista_in_movimento()
            return
        ctx = _contesto_vista(uidoc) if uidoc is not None else None
        firma = _firma_vista(ctx)
        if firma == self.firma and not self.sporco:
            return      # vista ferma e niente di nuovo: nessun calcolo
        # La firma si salva solo a lavoro riuscito: se qualcosa fallisce si riprova al
        # prossimo Idling (sporco resta vero), invece di restare nascosti per sempre.
        self.sporco = False
        try:
            self._posiziona(uidoc, ctx)
        except Exception:
            self.sporco = True
            raise
        self.firma = firma
        self.in_movimento = False
        self._aggiorna_segui()

    def _posiziona(self, uidoc, ctx):
        """Lettere E/I e palette per la vista 'ctx' (chiamata da riposiziona)."""
        try:
            self._aggiorna_lettere(uidoc, ctx)
        except Exception:
            self._nascondi_lettere()
            self.sporco = True      # si riprova al prossimo Idling
        pos = None
        dim = self.win.Content.DesiredSize
        larg, alt = dim.Width * self.scala, dim.Height * self.scala
        if ctx is not None and self.ancora is not None:
            _vista, _uv, zoom, finestra = ctx
            punto = TC.proietta(self.ancora, zoom, finestra)
            pos = PAL.posizione_palette(punto, finestra, larg, alt)
        elif ctx is not None:
            esito = _riquadro_selezione(uidoc, self.ids, ctx)
            if esito is not None:
                riquadro, finestra = esito
                pos = TC.posizione_striscia(riquadro, finestra, larg, alt)
        if pos is None:
            self.rett_palette = None
            self._nascondi_finestra()
            return
        self.rett_palette = (pos[0], pos[1], pos[0] + larg, pos[1] + alt)
        pos = (round(pos[0] / self.scala), round(pos[1] / self.scala))
        if pos != self.ultima_pos:
            if self.ultima_pos is not None:
                self._chiudi_menu()
            self.win.Left, self.win.Top = pos
            self.ultima_pos = pos
        if self.sparita:
            self._nascondi_finestra()
            return
        if self.ancora is None:
            self.win.Opacity = 1.0      # palette sul bordo della selezione: sempre piena
        if self.win.Visibility != Visibility.Visible:
            self.win.Show()

    def mostra(self, uidoc, ids, struttura, madre_uid, stessa=False):
        if self.win is None:
            self._crea_finestra()
        self.modo_annotazioni = False
        self.madre_uid = madre_uid
        self.ids = list(ids)
        self.ids_val = frozenset(PS._id_val(i) for i in self.ids)
        self.con_viste = any(f[u"cdv"] and f[u"nome"] not in NOMI_CDV_OGGETTI
                             for f in struttura[u"famiglie"])
        self.muri = any(v[0] == TC.MURO_INVERTI for f in struttura[u"famiglie"] for v in f[u"voci"])
        self.ultime_lettere = None
        self.attivo = True
        self.sporco = True
        if not stessa:
            # selezione nuova: palette accanto al cursore, semitrasparente
            self.cache_muri = {}
            self.ancora = self._ancora_cursore(uidoc)
            self.sparita = False
        # il timer serve solo se l'hook del mouse non e' partito
        if self.gancio is None and self.timer is not None and not self.timer.IsEnabled:
            self.timer.Start()
        firma = _firma_struttura(struttura)
        if firma != self.firma_struttura:
            self._riempi(struttura)
            self.firma_struttura = firma
        else:
            self._chiudi_menu()       # stessa palette di prima: si sposta e basta
        if self.ancora is not None and not stessa:
            # comparsa semitrasparente, poi la regola il movimento del mouse
            self.win.Opacity = PAL.OPACITA_COMPARSA
        self._aggiorna_segui()
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
        self.modo_annotazioni = False
        self.ids_val = frozenset()
        self.con_viste = False
        self.rett_palette = None
        self._aggiorna_segui()
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
        fam_id = self.fam_di.get(comando)
        if fam_id is not None:
            self.ultimi[fam_id] = comando
            if fam_id in self.famiglie:
                b, fam = self.famiglie[fam_id]
                self._aggiorna_famiglia(b, fam)
        cmd = PAL.PER_ID.get(comando)
        if self.modo_annotazioni:
            # palette del doppio clic: si chiude, il comando di Revit fa il resto
            self.nascondi()
        elif cmd is not None and (cmd.esecuzione == PAL.REVIT or cmd.interattivo):
            # Sposta, Copia, Copia grafica...: la palette si toglie e torna a comando
            # finito (vedi _su_idling per i comandi di Revit, _fine_azione per i nostri)
            # o quando cambia la selezione.
            self.sospesa = True
            self.sospesa_revit = cmd.esecuzione == PAL.REVIT
            self.comando_lanciato = None
            self._nascondi_finestra()
            self._nascondi_lettere()
            self._aggiorna_segui()
        elif comando in (TC.SEZIONE_APRI, TC.IMMAGINE_RITAGLIA):
            # Si apre una finestra: i tasti si tolgono di mezzo e tornano dopo
            # (chiave azzerata = la selezione viene riletta al prossimo Idling).
            self.nascondi()
            self.chiave_sel = None
        self.evento.Raise()

    # --- selezione ------------------------------------------------------------
    def _rileggi_config(self):
        """Rilegge palette.json solo se e' cambiato (es. Palette On/Off), al massimo 1 volta al secondo."""
        adesso = time.time()
        if adesso - self.cfg_letta < CONTROLLO_CONFIG_S:
            return
        self.cfg_letta = adesso
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
            ids = list(ids)
            doc = uidoc.Document if uidoc is not None else None
            if doc is None:
                chiave = None
            else:
                self.doc_vista = _doc_vista(doc)
                chiave = self.doc_vista + (tuple(sorted(PS._id_val(i) for i in ids)),)
            stessa = chiave == self.chiave_sel
            if stessa and (self.sospesa or not self.forza_analisi):
                # niente di nuovo; durante un comando la rianalisi chiesta da una modifica
                # resta in attesa e si fa quando la palette torna
                return
            self.forza_analisi = False
            self.chiave_sel = chiave
            if not stessa:
                # selezione nuova: un eventuale comando in corso non la riguarda piu'
                self.sospesa = False
                self.sospesa_revit = False
                self.comando_lanciato = None
            esito = _analizza_selezione(doc, ids, self.cfg, self.disponibili, self.cache_coppie)
            if esito is None:
                self.nascondi()
            else:
                struttura, madre_uid = esito
                self.mostra(uidoc, ids, struttura, madre_uid, stessa=stessa)
        except Exception:
            # Un errore qui non deve mai disturbare il lavoro in Revit
            self.nascondi()

    def _su_selezione(self, sender, args):
        self._rileggi_config()
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
            if self._comando_revit_finito():
                self._riprendi()
            self._rileggi_config()
            # Revit 2023+: la selezione arriva con SelectionChanged; qui si rilegge solo
            # se serve (configurazione o modello cambiati, altro documento o altra vista).
            if (not self.ha_evento_selezione or self.chiave_sel is None or self.forza_analisi
                    or _doc_vista(uidoc.Document) != self.doc_vista):
                self.aggiorna(uidoc, uidoc.Selection.GetElementIds())
            if self.doppio_clic is not None:
                self._controlla_doppio_clic(uidoc)
            self.riposiziona(uidoc)
        except Exception:
            self._nascondi_finestra()
            self._nascondi_lettere()

    def _su_chiusura(self, sender, args):
        self.chiave_sel = None
        self.cache_coppie.clear()   # niente riferimenti a elementi di un documento chiuso
        self.nascondi()

    def _su_modifica(self, sender, args):
        """Il modello e' cambiato: si rifa' solo quello che la modifica tocca."""
        self.sporco = True          # oggetti spostati o invertiti: palette e lettere da rimettere
        try:
            eliminati = args.GetDeletedElementIds()
            # Viste aggiunte/cambiate, oppure qualcosa eliminato (non si puo' piu' sapere
            # cosa fosse): le coppie sezione/sfondo vanno rilette.
            if (eliminati.Count or args.GetAddedElementIds(_FILTRO_VISTE).Count
                    or args.GetModifiedElementIds(_FILTRO_VISTE).Count):
                self.cache_coppie[u"versione"] = self.cache_coppie.get(u"versione", 0) + 1
                # la palette si rilegge solo se la modifica la riguarda: selezione con
                # viste/sezioni (tasti CDV) o elementi selezionati eliminati
                if self.madre_uid is not None or self.con_viste \
                        or any(PS._id_val(i) in self.ids_val for i in eliminati):
                    self.forza_analisi = True
        except Exception:
            # nel dubbio si rilegge tutto
            self.cache_coppie[u"versione"] = self.cache_coppie.get(u"versione", 0) + 1
            self.forza_analisi = True

    def _fine_azione(self, comando, avviato):
        """Dall'ExternalEvent, a fine azione."""
        if not self.sospesa:
            return
        if self.sospesa_revit and avviato:
            # Il comando di Revit e' partito: finisce quando Revit torna a mandare Idling
            # (vedi _su_idling). Da adesso si conta l'attesa minima.
            self.comando_lanciato = time.time()
        else:
            # Azione nostra finita (es. Copia grafica dopo Esc), oppure il comando di
            # Revit non e' partito (non disponibile per questa selezione): la palette torna.
            self._riprendi()

    def _comando_revit_finito(self):
        """Revit manda Idling solo fuori da strumenti e transazioni: il primo Idling dopo
        che il comando e' partito vuol dire che e' finito, comunque sia finito (operazione
        fatta, Esc, clic su Modifica, Annulla dal tasto destro...)."""
        return (self.sospesa and self.sospesa_revit and self.comando_lanciato is not None
                and time.time() - self.comando_lanciato >= ATTESA_COMANDO_S)

    def _riprendi(self):
        # Torna sul bordo della selezione: gli elementi possono essersi spostati
        self.sospesa = False
        self.sospesa_revit = False
        self.comando_lanciato = None
        self.ancora = None
        self.ultima_pos = None
        self.sporco = True
        self.sparita = False
        self._aggiorna_segui()

    # --- attivazione ----------------------------------------------------------
    def accendi(self):
        tipo_args = getattr(UI.Events, "SelectionChangedEventArgs", None)
        if tipo_args is not None and clr.GetClrType(UI.UIApplication).GetEvent("SelectionChanged"):
            d = EventHandler[tipo_args](self._su_selezione)
            self.uiapp.SelectionChanged += d
            self.delegati.append(("SelectionChanged", d))
            self.ha_evento_selezione = True
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
        self.cache_coppie.clear()


def attiva(uiapp):
    """Accende palette e tasti in sovraimpressione (spegne quelli di un caricamento precedente)."""
    dominio = System.AppDomain.CurrentDomain
    vecchio = dominio.GetData(CHIAVE_APPDOMAIN)
    if vecchio is not None:
        try:
            vecchio.Invoke()
        except Exception:
            pass
    _UIAPP[0] = uiapp
    overlay = TastiOverlay(uiapp)
    overlay.accendi()
    dominio.SetData(CHIAVE_APPDOMAIN, System.Action(overlay.spegni))
    return overlay
