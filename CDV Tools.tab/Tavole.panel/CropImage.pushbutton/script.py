# -*- coding: utf-8 -*-
"""Ritaglia Immagine - CDV Tools

Ritaglia un'immagine raster (in tavola o in vista) come in Word: trascini un
rettangolo sull'anteprima, oppure ne sposti i bordi. La parte tenuta resta nella
stessa posizione. Il tipo immagine ritagliato ricorda l'originale e il riquadro
(Extensible Storage): riaprendo si vede l'immagine intera e si puo' allargare.
"""

import os
import tempfile
import clr

clr.AddReference('System.Drawing')
clr.AddReference('PresentationFramework')
clr.AddReference('PresentationCore')
clr.AddReference('WindowsBase')

from System import Guid, Int32
from System.IO import MemoryStream
from System.Drawing import Rectangle as DRect
from System.Drawing.Imaging import ImageFormat
from System.Windows.Controls import Canvas
from System.Windows.Media import BrushConverter
from System.Windows.Media.Imaging import BitmapImage, BitmapCacheOption
from Autodesk.Revit.Exceptions import OperationCanceledException
from pyrevit import revit, DB, UI, forms
import stile_finestre as SF

import avviso_wpf as AVW
import ritaglio_immagine as RI

MAX_W = 860.0
MAX_H = 540.0
PRESA = 8.0  # distanza in pixel schermo per "agganciare" un bordo
SCHEMA_GUID = Guid("6f1c2a4e-8b3d-4c5a-9e71-2d0b7a3c5f18")
CAMPI_RETT = ("X", "Y", "W", "H")


def _schema(crea=False):
    s = DB.ExtensibleStorage.Schema.Lookup(SCHEMA_GUID)
    if s is not None or not crea:
        return s
    sb = DB.ExtensibleStorage.SchemaBuilder(SCHEMA_GUID)
    sb.SetSchemaName("CDVRitaglioImmagine")
    sb.SetReadAccessLevel(DB.ExtensibleStorage.AccessLevel.Public)
    sb.SetWriteAccessLevel(DB.ExtensibleStorage.AccessLevel.Public)
    sb.AddSimpleField("TipoOriginale", clr.GetClrType(DB.ElementId))
    for nome in CAMPI_RETT:
        sb.AddSimpleField(nome, clr.GetClrType(Int32))
    return sb.Finish()


def _leggi_dati(doc, tipo):
    """(tipo originale, rett) se tipo e' un ritaglio fatto da questo pulsante."""
    s = _schema()
    if s is None:
        return None
    ent = tipo.GetEntity(s)
    if not ent.IsValid():
        return None
    orig = doc.GetElement(ent.Get[DB.ElementId]("TipoOriginale"))
    if not isinstance(orig, DB.ImageType):
        return None  # originale eliminato (es. "Elimina inutilizzati")
    return orig, tuple(ent.Get[Int32](n) for n in CAMPI_RETT)


def _scrivi_dati(tipo, orig_id, rett):
    ent = DB.ExtensibleStorage.Entity(_schema(crea=True))
    ent.Set[DB.ElementId]("TipoOriginale", orig_id)
    for nome, val in zip(CAMPI_RETT, rett):
        ent.Set[Int32](nome, Int32(val))
    tipo.SetEntity(ent)


class FiltroImmagini(UI.Selection.ISelectionFilter):
    def AllowElement(self, el):
        return isinstance(el, DB.ImageInstance)

    def AllowReference(self, ref, pt):
        return False


def _scegli_immagine(doc, uidoc):
    for eid in uidoc.Selection.GetElementIds():
        el = doc.GetElement(eid)
        if isinstance(el, DB.ImageInstance):
            return el
    try:
        ref = uidoc.Selection.PickObject(
            UI.Selection.ObjectType.Element, FiltroImmagini(),
            u"Seleziona l'immagine da ritagliare (ESC per annullare)")
    except OperationCanceledException:
        return None
    return doc.GetElement(ref)


def _bitmap_wpf(bmp):
    ms = MemoryStream()
    bmp.Save(ms, ImageFormat.Png)
    ms.Position = 0
    bi = BitmapImage()
    bi.BeginInit()
    bi.CacheOption = BitmapCacheOption.OnLoad
    bi.StreamSource = ms
    bi.EndInit()
    return bi


class RitaglioWindow(forms.WPFWindow):
    def __init__(self, xaml_file, bmp, iniziale):
        forms.WPFWindow.__init__(self, SF.xaml(xaml_file), literal_string=True)
        self.bmp = bmp
        self.risultato = None
        self.iniziale = iniziale
        self.k = min(MAX_W / bmp.Width, MAX_H / bmp.Height)  # schermo per pixel
        self.dw = bmp.Width * self.k
        self.dh = bmp.Height * self.k
        self.imgPreview.Source = _bitmap_wpf(bmp)
        for el in (self.imgPreview, self.cnv):
            el.Width = self.dw
            el.Height = self.dh
        self.modo = None
        x, y, w, h = iniziale
        k = self.k
        self.rett = [x * k, y * k, (x + w) * k, (y + h) * k]
        self._disegna()

        self.cnv.MouseLeftButtonDown += self.on_down
        self.cnv.MouseMove += self.on_move
        self.cnv.MouseLeftButtonUp += self.on_up
        self.btnReset.Click += self.on_reset
        self.btnCancel.Click += lambda s, a: self.Close()
        self.btnApply.Click += self.on_apply

    # --- rettangolo (coordinate schermo: l, t, r, b) ---
    def _disegna(self):
        l, t, r, b = self.rett
        for rect, x, y, w, h in (
                (self.ombraSu, 0, 0, self.dw, t),
                (self.ombraGiu, 0, b, self.dw, self.dh - b),
                (self.ombraSx, 0, t, l, b - t),
                (self.ombraDx, r, t, self.dw - r, b - t),
                (self.selRect, l, t, r - l, b - t)):
            Canvas.SetLeft(rect, x)
            Canvas.SetTop(rect, y)
            rect.Width = max(0.0, w)
            rect.Height = max(0.0, h)
        try:
            x, y, w, h = RI.rettangolo_pixel(l, t, r, b, 1.0 / self.k, self.bmp.Width, self.bmp.Height)
            self.lblInfo.Text = u"Ritaglio: %d x %d px (originale %d x %d px)" % (w, h, self.bmp.Width, self.bmp.Height)
        except ValueError as ex:
            self.lblInfo.Text = u"%s" % ex

    def on_reset(self, sender, args):
        self.rett = [0.0, 0.0, self.dw, self.dh]
        self._disegna()

    def on_down(self, sender, args):
        p = args.GetPosition(self.cnv)
        l, t, r, b = self.rett
        dentro_y = t - PRESA <= p.Y <= b + PRESA
        dentro_x = l - PRESA <= p.X <= r + PRESA
        bordi = set()
        if dentro_y and abs(p.X - l) <= PRESA:
            bordi.add(0)
        if dentro_y and abs(p.X - r) <= PRESA:
            bordi.add(2)
        if dentro_x and abs(p.Y - t) <= PRESA:
            bordi.add(1)
        if dentro_x and abs(p.Y - b) <= PRESA:
            bordi.add(3)
        if bordi:
            self.modo = ("bordi", bordi)
        elif l < p.X < r and t < p.Y < b and self.rett != [0.0, 0.0, self.dw, self.dh]:
            self.modo = ("sposta", (p.X, p.Y, list(self.rett)))
        else:
            self.modo = ("nuovo", (p.X, p.Y))
        self.cnv.CaptureMouse()

    def on_move(self, sender, args):
        if not self.modo:
            return
        p = args.GetPosition(self.cnv)
        x = min(max(p.X, 0.0), self.dw)
        y = min(max(p.Y, 0.0), self.dh)
        tipo, dati = self.modo
        if tipo == "bordi":
            for i in dati:
                self.rett[i] = x if i in (0, 2) else y
        elif tipo == "sposta":
            x0, y0, (l, t, r, b) = dati
            dx = min(max(p.X - x0, -l), self.dw - r)
            dy = min(max(p.Y - y0, -t), self.dh - b)
            self.rett = [l + dx, t + dy, r + dx, b + dy]
        else:
            x0, y0 = dati
            self.rett = [min(x0, x), min(y0, y), max(x0, x), max(y0, y)]
        l, t, r, b = self.rett
        self.rett = [min(l, r), min(t, b), max(l, r), max(t, b)]
        self._disegna()

    def on_up(self, sender, args):
        self.modo = None
        self.cnv.ReleaseMouseCapture()

    def on_apply(self, sender, args):
        l, t, r, b = self.rett
        try:
            self.risultato = RI.rettangolo_pixel(l, t, r, b, 1.0 / self.k, self.bmp.Width, self.bmp.Height)
        except ValueError as ex:
            self.lblInfo.Text = u"%s" % ex
            self.lblInfo.Foreground = BrushConverter().ConvertFromString("#DC2626")
            return
        if self.risultato == self.iniziale:
            self.risultato = None  # niente da cambiare
        self.Close()


def _applica(doc, inst, orig, bmp, larghezza, altezza, centro, rett):
    """larghezza, altezza e centro sono quelli dell'immagine originale intera."""
    vista = doc.GetElement(inst.OwnerViewId)
    vecchio_tipo = doc.GetElement(inst.GetTypeId())
    nuova_w, nuova_h, dx, dy = RI.nuova_geometria(larghezza, altezza, bmp.Width, bmp.Height, rett)
    nuovo_centro = centro + vista.RightDirection.Multiply(dx) + vista.UpDirection.Multiply(dy)
    intera = rett == (0, 0, bmp.Width, bmp.Height)
    percorso = None
    nome = DB.Element.Name.GetValue(orig)
    if not intera:
        x, y, w, h = rett
        ritaglio = bmp.Clone(DRect(x, y, w, h), bmp.PixelFormat)
        base = os.path.splitext(os.path.basename(orig.Path or u""))[0] or u"immagine"
        # i tipi immagine si chiamano come il file (con estensione)
        nomi = [os.path.splitext(DB.Element.Name.GetValue(t))[0] for t in DB.FilteredElementCollector(doc).OfClass(DB.ImageType)]
        nome = RI.nome_univoco(base, nomi)
        # il file temporaneo basta: con ImageTypeSource.Import l'immagine viene incorporata
        percorso = os.path.join(tempfile.gettempdir(), nome + u".png")
        ritaglio.Save(percorso, ImageFormat.Png)

    with revit.Transaction(u"Ritaglia Immagine"):
        if intera:
            tipo_id = orig.Id
        else:
            opts = DB.ImageTypeOptions(percorso, False, DB.ImageTypeSource.Import)
            opts.Resolution = orig.Resolution
            nuovo_tipo = DB.ImageType.Create(doc, opts)
            _scrivi_dati(nuovo_tipo, orig.Id, rett)
            tipo_id = nuovo_tipo.Id
        # Revit non permette ChangeTypeId sulle immagini: nuova istanza al posto della vecchia
        nuova = DB.ImageInstance.Create(
            doc, vista, tipo_id,
            DB.ImagePlacementOptions(nuovo_centro, DB.BoxPlacement.Center))
        nuova.LockProportions = False
        nuova.Width = nuova_w
        nuova.Height = nuova_h
        nuova.LockProportions = inst.LockProportions
        nuova.DrawLayer = inst.DrawLayer
        nuova.SetLocation(nuovo_centro, DB.BoxPlacement.Center)
        doc.Delete(inst.Id)
        # il vecchio ritaglio non serve piu' se nessun'altra immagine lo usa
        if vecchio_tipo.Id != orig.Id and _leggi_dati(doc, vecchio_tipo):
            usato = any(i.GetTypeId() == vecchio_tipo.Id for i in
                        DB.FilteredElementCollector(doc).OfClass(DB.ImageInstance))
            if not usato:
                doc.Delete(vecchio_tipo.Id)
    if percorso:
        try:
            os.remove(percorso)
        except Exception:
            pass
    return nome


def main():
    doc = revit.doc
    uidoc = revit.uidoc
    inst = _scegli_immagine(doc, uidoc)
    if inst is None:
        return
    tipo = doc.GetElement(inst.GetTypeId())
    dati = _leggi_dati(doc, tipo)
    orig, rett_attuale = dati if dati else (tipo, None)
    bmp = orig.GetImage()
    if bmp is None:
        AVW.errore(u"Impossibile leggere l'immagine (file non caricato?).")
        return
    if rett_attuale is None:
        rett_attuale = (0, 0, bmp.Width, bmp.Height)

    # posizione e dimensioni che avrebbe l'originale intero
    vista = doc.GetElement(inst.OwnerViewId)
    larghezza, altezza, dx, dy = RI.geometria_completa(
        inst.Width, inst.Height, bmp.Width, bmp.Height, rett_attuale)
    centro = (inst.GetLocation(DB.BoxPlacement.Center)
              - vista.RightDirection.Multiply(dx) - vista.UpDirection.Multiply(dy))

    xaml = os.path.join(os.path.dirname(__file__), "ui.xaml")
    win = RitaglioWindow(xaml, bmp, rett_attuale)
    win.ShowDialog()
    if not win.risultato:
        return
    try:
        nome = _applica(doc, inst, orig, bmp, larghezza, altezza, centro, win.risultato)
    except Exception as ex:
        AVW.errore(u"Ritaglio non riuscito: %s" % ex)
        return
    AVW.mostra(u"Immagine ritagliata: %s" % nome)


if __name__ == "__main__":
    main()
