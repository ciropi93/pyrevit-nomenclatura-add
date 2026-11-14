# -*- coding: utf-8 -*-
"""Tasto in sovraimpressione per le sezioni con Profondita' (sfondo) attiva.

Quando selezioni la linea di sezione (in pianta) o il riquadro in tavola di una
sezione che ha lo sfondo vettoriale, vicino al cursore compare un piccolo pannello:
  - "Profondita' sezione": apre la finestra del pulsante gia' su quella sezione;
  - "Sincronizza": riallinea subito sfondo e tavole (una transazione, annullabile).

Viene attivato da startup.py dell'estensione. Usa l'evento SelectionChanged
(Revit 2023+) oppure, nelle versioni precedenti, il controllo della selezione
nell'evento Idling.
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
from System import EventHandler, IntPtr
from System.Windows import Visibility
from System.Windows.Interop import WindowInteropHelper
from System.Windows.Markup import XamlReader
from Autodesk.Revit import DB, UI

import profondita_sezione as PS


CHIAVE_APPDOMAIN = "CDVTools.SezioneOverlay.Spegni"
TITOLO = u"CDV Tools"
SCRIPT_PULSANTE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    u"CDV Tools.tab", u"Grafica e Filtri.panel", u"SectionDepth.pushbutton", u"script.py",
)

XAML = u"""
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
        WindowStyle="None" AllowsTransparency="True" Background="Transparent"
        ShowInTaskbar="False" ShowActivated="False" ResizeMode="NoResize"
        SizeToContent="WidthAndHeight" FontFamily="Segoe UI" FontSize="12">
  <Border Margin="8" CornerRadius="6" Background="#FFFFFF" BorderBrush="#CBD5E1"
          BorderThickness="1" Padding="4">
    <Border.Effect>
      <DropShadowEffect BlurRadius="10" ShadowDepth="2" Opacity="0.25"/>
    </Border.Effect>
    <StackPanel Orientation="Horizontal">
      <Button x:Name="btnApri" Padding="10,3" Margin="0,0,4,0" Cursor="Hand"
              Background="#0369A1" Foreground="White" BorderThickness="0"
              ToolTip="Apri Profondità Sezione su questa sezione">
        <StackPanel>
          <TextBlock Text="Profondità sezione" FontWeight="SemiBold"/>
          <TextBlock x:Name="lblNome" FontSize="10" Opacity="0.85"/>
        </StackPanel>
      </Button>
      <Button x:Name="btnSync" Content="Sincronizza" Padding="8,3" Margin="0,0,4,0"
              Cursor="Hand" Background="#E0F2FE" Foreground="#0369A1" BorderThickness="0"
              ToolTip="Riallinea sfondo e tavole alla sezione madre (annullabile)"/>
      <Button x:Name="btnChiudi" Content="×" Width="22" Cursor="Hand" FontSize="14"
              Background="Transparent" Foreground="#64748B" BorderThickness="0"
              ToolTip="Nascondi"/>
    </StackPanel>
  </Border>
</Window>
"""


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


class _IgnoraAvvisi(DB.IFailuresPreprocessor):
    def PreprocessFailures(self, failuresAccessor):
        for f in failuresAccessor.GetFailureMessages():
            if f.GetSeverity() == DB.FailureSeverity.Warning:
                failuresAccessor.DeleteWarning(f)
        return DB.FailureProcessingResult.Continue


# ==============================================================================
# LETTURA SELEZIONE
# ==============================================================================

def _voce_elemento(el):
    """Voce per PS.madre_da_selezione, oppure None se l'elemento non interessa."""
    if el is None:
        return None
    if isinstance(el, DB.Viewport):
        return (u"viewport", PS._id_val(el.ViewId))
    cat = el.Category
    if cat is not None and PS._id_val(cat.Id) == int(DB.BuiltInCategory.OST_Viewers):
        return (u"viewer", el.Name)
    return None


def _madre_selezionata(doc, ids):
    """Sezione madre (View) indicata dalla selezione, oppure None."""
    if doc is None or doc.IsFamilyDocument or len(ids) != 1:
        return None
    voce = _voce_elemento(doc.GetElement(ids[0]))
    if voce is None:
        return None
    coppie, _, _ = PS.trova_coppie_sezioni(doc)
    if not coppie:
        return None
    per_id = dict((PS._id_val(c["madre"].Id), c["madre"]) for c in coppie)
    righe = [
        (PS._id_val(c["madre"].Id), c["madre"].Name, PS._id_val(c["sfondo"].Id), c["sfondo"].Name)
        for c in coppie
    ]
    id_madre = PS.madre_da_selezione([voce], righe)
    return per_id.get(id_madre) if id_madre is not None else None


# ==============================================================================
# AZIONI (eseguite in contesto API tramite ExternalEvent)
# ==============================================================================

def _apri_finestra(madre_uid):
    modulo = imp.load_source("cdv_sectiondepth_script", SCRIPT_PULSANTE)
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
        self.azione = None
        self.madre_uid = None

    def Execute(self, uiapp):
        azione, uid = self.azione, self.madre_uid
        self.azione = None
        try:
            uidoc = uiapp.ActiveUIDocument
            if uidoc is None or not uid:
                return
            if azione == u"apri":
                _apri_finestra(uid)
            elif azione == u"sincronizza":
                _sincronizza(uidoc.Document, uid)
        except Exception as ex:
            _avvisa(u"Errore: %s" % ex)

    def GetName(self):
        return u"CDV Tools - Profondita' Sezione (sovraimpressione)"


# ==============================================================================
# PANNELLO IN SOVRAIMPRESSIONE
# ==============================================================================

class SezioneOverlay(object):
    def __init__(self, uiapp):
        self.uiapp = uiapp
        self.win = None
        self.gestore = None
        self.evento = None
        self.madre_uid = None
        self.chiave_sel = None
        self.delegati = []

    # --- finestra -------------------------------------------------------------
    def _crea_finestra(self):
        win = XamlReader.Parse(XAML)
        try:
            WindowInteropHelper(win).Owner = self.uiapp.MainWindowHandle
        except Exception:
            win.Topmost = True
        win.FindName("btnApri").Click += lambda s, a: self._esegui(u"apri")
        win.FindName("btnSync").Click += lambda s, a: self._esegui(u"sincronizza")
        win.FindName("btnChiudi").Click += lambda s, a: self.nascondi()
        self.win = win
        # ExternalEvent va creato in contesto API (qui siamo in un evento di Revit)
        self.gestore = _GestoreAzione()
        self.evento = UI.ExternalEvent.Create(self.gestore)

    def _posiziona(self):
        """Mette il pannello in basso a destra del cursore, dentro lo schermo."""
        from System.Drawing import Graphics
        from System.Windows.Forms import Cursor, Screen
        pos = Cursor.Position
        area = Screen.FromPoint(pos).WorkingArea
        g = Graphics.FromHwnd(IntPtr.Zero)
        try:
            scala = g.DpiX / 96.0
        finally:
            g.Dispose()
        w = self.win.ActualWidth or 260.0
        h = self.win.ActualHeight or 60.0
        x = (pos.X + 16) / scala
        y = (pos.Y + 16) / scala
        x = min(x, area.Right / scala - w)
        y = min(y, area.Bottom / scala - h)
        self.win.Left = max(x, area.Left / scala)
        self.win.Top = max(y, area.Top / scala)

    def mostra(self, madre):
        if self.win is None:
            self._crea_finestra()
        self.madre_uid = madre.UniqueId
        self.win.FindName("lblNome").Text = madre.Name
        self._posiziona()
        if self.win.Visibility != Visibility.Visible:
            self.win.Show()
            self.win.UpdateLayout()
            self._posiziona()

    def nascondi(self):
        if self.win is not None and self.win.Visibility == Visibility.Visible:
            self.win.Hide()

    def _esegui(self, azione):
        if not self.madre_uid or self.evento is None:
            return
        self.gestore.azione = azione
        self.gestore.madre_uid = self.madre_uid
        self.nascondi()
        self.evento.Raise()

    # --- selezione ------------------------------------------------------------
    def aggiorna(self, doc, ids):
        try:
            ids = list(ids)
            chiave = (doc.PathName or doc.Title, tuple(sorted(PS._id_val(i) for i in ids))) if doc else None
            if chiave == self.chiave_sel:
                return
            self.chiave_sel = chiave
            madre = _madre_selezionata(doc, ids)
            if madre is None:
                self.nascondi()
            else:
                self.mostra(madre)
        except Exception:
            # Un errore qui non deve mai disturbare il lavoro in Revit
            self.nascondi()

    def _su_selezione(self, sender, args):
        self.aggiorna(args.GetDocument(), args.GetSelectedElements())

    def _su_idling(self, sender, args):
        uidoc = sender.ActiveUIDocument if sender is not None else None
        if uidoc is None:
            self.chiave_sel = None
            self.nascondi()
            return
        self.aggiorna(uidoc.Document, uidoc.Selection.GetElementIds())

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
        else:
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
    """Accende il tasto in sovraimpressione (spegne quello di un caricamento precedente)."""
    dominio = System.AppDomain.CurrentDomain
    vecchio = dominio.GetData(CHIAVE_APPDOMAIN)
    if vecchio is not None:
        try:
            vecchio.Invoke()
        except Exception:
            pass
    overlay = SezioneOverlay(uiapp)
    overlay.accendi()
    dominio.SetData(CHIAVE_APPDOMAIN, System.Action(overlay.spegni))
    return overlay
