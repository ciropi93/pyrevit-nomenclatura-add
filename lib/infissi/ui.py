# -*- coding: utf-8 -*-
"""Finestra del configuratore e creazione della famiglia (usata da Configuratore e Modifica infisso).

A sinistra gli schemi (pronti e salvati), al centro l'anteprima in prospetto vista da fuori
(clic su una zona per sceglierla), a destra categoria, nome, misure e profili. "Crea" chiude
la finestra; la famiglia si costruisce dopo, fuori dalla finestra.
"""
import os
import re

import clr
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

from System.Windows import FontWeights, GridLength, HorizontalAlignment, Thickness, VerticalAlignment
from System.Windows.Controls import (Canvas, ColumnDefinition, Grid, ListBoxItem, TextBlock,
                                     TextBox)
from System.Windows.Media import DoubleCollection
from System.Windows.Shapes import Line, Rectangle

from pyrevit import forms

import avviso as AV
import avviso_wpf as AVW
import stile_finestre as SF
from icone_wpf import colore

from infissi import catalogo as C
from infissi import geometria as G
from infissi import schema as S

TITOLO = u"Infissi"
XAML = os.path.join(os.path.dirname(os.path.abspath(__file__)), u"configuratore.xaml")

COLORI = {
    u"telaio": u"#4A5866", u"montante": u"#4A5866", u"anta": u"#5B6B78",
    u"zoccolo": u"#5B6B78", u"vetro": u"#CFE3F4", u"pannello": u"#C9D3DB",
    u"maniglia": u"#2B3640",
}
ARANCIO = u"#E5862A"      # zona scelta
SCURO = u"#2B3640"        # bordi e simboli di apertura
GRIGIO = u"#5B6B78"
BLU = u"#1F6FB2"          # parte che cambia il campo in uso
ORDINE_DISEGNO = (u"telaio", u"montante", u"anta", u"zoccolo", u"vetro", u"pannello", u"maniglia")
MARGINE = 24.0
_VIETATI = re.compile(u'[\\\\/:*?"<>|]')


def numero(testo):
    """Numero da un testo (accetta la virgola); None se non e' un numero."""
    try:
        return float((testo or u"").strip().replace(u",", u"."))
    except ValueError:
        return None


def cartella_predefinita():
    return os.path.join(os.path.expanduser(u"~"), u"Documents", u"CDV Infissi")


class Configuratore(forms.WPFWindow):
    def __init__(self, schema=None, nome_famiglia=None, cartella=u"", modifica=False):
        forms.WPFWindow.__init__(self, SF.xaml(XAML), literal_string=True)
        self.risultato = None
        self.modifica = modifica
        self._carico = True
        self.sel = None
        self.ris = None
        self._scala = None
        self._nome_manuale = bool(nome_famiglia)
        self.evid = None          # campo in uso: cosa illuminare nel disegno

        self.voci = []
        self.riempi_schemi()
        self.btnEliminaSchema.IsEnabled = False   # si attiva sugli schemi salvati da te
        self.cmbAnta.ItemsSource = [e for _k, e in S.ANTE]
        self.cmbChiusura.ItemsSource = [e for _k, e in S.RIEMPIMENTI]
        self.cmbPianta.ItemsSource = [e for _k, e in S.SIMBOLI_PIANTA]

        self.schema = S.copia(schema) if schema else S.copia(self.voci[0][1])
        self.txtNome.Text = nome_famiglia or S.nome_famiglia(self.schema)
        self.txtCartella.Text = cartella or cartella_predefinita()
        if modifica:
            self.rbFinestre.IsEnabled = self.rbPorte.IsEnabled = False
            self.txtNome.IsEnabled = False
            self.lstSchemi.IsEnabled = self.btnEliminaSchema.IsEnabled = False
            self.btnCrea.Content = u"Aggiorna famiglia"
            self.lblTitolo.Text = u"Modifica infisso"

        self.lstSchemi.SelectionChanged += self.su_schema
        self.btnSalvaSchema.Click += self.su_salva_schema
        self.btnEliminaSchema.Click += self.su_elimina_schema
        self.cnvAnteprima.MouseLeftButtonDown += self.su_clic_anteprima
        self.cnvAnteprima.SizeChanged += lambda s, a: self.ridisegna()
        self.cmbAnta.SelectionChanged += self.su_anta
        self.cmbChiusura.SelectionChanged += self.su_chiusura
        self.chkSoglia.Click += self.su_soglia
        self.chkManiglie.Click += self.su_maniglie
        self.cmbPianta.SelectionChanged += self.su_pianta
        for box, chiave in ((self.txtLarghezza, (u"larghezza",)), (self.txtAltezza, (u"altezza",))):
            self._aggancia_evidenza(box, chiave)
        self.btnDividiV.Click += lambda s, a: self.dividi(u"v")
        self.btnDividiO.Click += lambda s, a: self.dividi(u"o")
        self.btnTogli.Click += self.su_togli
        self.chkMontante.Click += self.su_montante
        self.rbFinestre.Checked += self.su_categoria
        self.rbPorte.Checked += self.su_categoria
        self.txtNome.TextChanged += self.su_nome
        self.txtLarghezza.TextChanged += self.su_dimensione
        self.txtAltezza.TextChanged += self.su_dimensione
        self.btnCartella.Click += self.su_cartella
        self.txtCartella.TextChanged += lambda s, a: self.aggiorna_file()
        self.btnAnnulla.Click += lambda s, a: self.Close()
        self.btnCrea.Click += self.su_crea
        self.carica_schema()
        self.aggiorna_file()

    # --- messaggi nella finestra (niente popup) ----------------------------------------
    def _stato(self, testo, errore=False):
        self.txtErrori.Text = testo
        self.txtErrori.Foreground = colore(u"#DC2626" if errore else GRIGIO)

    def aggiorna_file(self):
        """Sotto i pulsanti: dove finisce la famiglia e se sovrascrive un file."""
        nome = (self.txtNome.Text or u"").strip()
        cartella = (self.txtCartella.Text or u"").strip() or cartella_predefinita()
        percorso = os.path.join(cartella, nome + u".rfa")
        if nome and os.path.exists(percorso) and not self.modifica:
            self.lblFile.Text = u"%s esiste già: verrà sovrascritto" % percorso
            self.lblFile.Foreground = colore(ARANCIO)
        else:
            self.lblFile.Text = u"Salvata in %s" % cartella
            self.lblFile.Foreground = colore(GRIGIO)

    # --- catalogo --------------------------------------------------------------------
    def riempi_schemi(self, seleziona=None):
        self.voci = [(None, s) for s in C.preimpostati()] + list(C.schemi_utente())
        self.lstSchemi.Items.Clear()
        for percorso, s in self.voci:
            voce = ListBoxItem()
            voce.Content = (u"★ " if percorso else u"") + (s.get(u"nome") or u"(senza nome)")
            voce.ToolTip = S.descrizione(s)
            self.lstSchemi.Items.Add(voce)
        if seleziona is not None:
            for i, (percorso, _s) in enumerate(self.voci):
                if percorso == seleziona:
                    self._carico = True
                    self.lstSchemi.SelectedIndex = i
                    self._carico = False

    def su_schema(self, sender, args):
        if self._carico or self.lstSchemi.SelectedIndex < 0:
            return
        self.schema = S.copia(self.voci[self.lstSchemi.SelectedIndex][1])
        self.btnEliminaSchema.IsEnabled = bool(self.voci[self.lstSchemi.SelectedIndex][0])
        self.sel = None
        if not self._nome_manuale:
            self._imposta_nome(S.nome_famiglia(self.schema))
        self.carica_schema()

    def su_salva_schema(self, sender, args):
        nome = forms.ask_for_string(default=self.schema.get(u"nome") or u"", prompt=u"Nome dello schema:",
                                    title=TITOLO)
        if not nome:
            return
        self.schema[u"nome"] = nome
        try:
            percorso = C.salva_schema(self.schema)
        except Exception as ex:
            self._stato(u"Schema non salvato: %s" % ex, errore=True)
            return
        self.riempi_schemi(seleziona=percorso)
        self._stato(u"Schema \"%s\" salvato" % nome)

    def su_elimina_schema(self, sender, args):
        i = self.lstSchemi.SelectedIndex
        if i < 0 or not self.voci[i][0]:
            return
        nome = self.voci[i][1].get(u"nome")
        # cancella un file e non si annulla: questa domanda resta
        if not forms.alert(u"Elimino lo schema \"%s\"?" % nome, title=TITOLO, yes=True, no=True):
            return
        C.elimina_schema(self.voci[i][0])
        self.riempi_schemi()
        self.btnEliminaSchema.IsEnabled = False
        self._stato(u"Schema \"%s\" eliminato" % nome)

    # --- campi -------------------------------------------------------------------------
    def _imposta_nome(self, nome):
        vecchio = self._carico
        self._carico = True
        self.txtNome.Text = nome
        self._carico = vecchio

    def carica_schema(self):
        """Riempie tutti i campi dallo schema corrente."""
        self._carico = True
        try:
            self.rbFinestre.IsChecked = self.schema[u"categoria"] != S.PORTE
            self.rbPorte.IsChecked = self.schema[u"categoria"] == S.PORTE
            self.txtLarghezza.Text = u"%g" % self.schema[u"larghezza"]
            self.txtAltezza.Text = u"%g" % self.schema[u"altezza"]
            self.chkSoglia.IsChecked = bool(self.schema.get(u"soglia", True))
            self.chkManiglie.IsChecked = bool(self.schema.get(u"maniglie", False))
            self.cmbPianta.SelectedIndex = [k for k, _e in S.SIMBOLI_PIANTA].index(
                self.schema.get(u"simbolo_pianta", u"nessuno"))
            self.riempi_profili()
            self.riempi_misure()
        finally:
            self._carico = False
        self.aggiorna_selezione()
        self.ridisegna()

    def _aggancia_evidenza(self, box, chiave):
        box.GotFocus += lambda s, a, k=chiave: self._evidenzia(k)
        box.LostFocus += lambda s, a: self._evidenzia(None)

    def _evidenzia(self, chiave):
        self.evid = chiave
        self.ridisegna()

    def _riga(self, pannello, etichetta, valore, tag, gestore, aiuto=None, evidenza=None):
        g = Grid()
        g.Margin = Thickness(0, 0, 0, 4)
        c0, c1 = ColumnDefinition(), ColumnDefinition()
        c1.Width = GridLength(90)
        g.ColumnDefinitions.Add(c0)
        g.ColumnDefinitions.Add(c1)
        tb = TextBlock()
        tb.Text = etichetta
        tb.VerticalAlignment = VerticalAlignment.Center
        if aiuto:
            tb.ToolTip = aiuto
        box = TextBox()
        box.Text = u"%g" % valore
        box.Tag = tag
        box.Width = 90
        box.HorizontalAlignment = HorizontalAlignment.Right
        box.TextChanged += gestore
        if evidenza is not None:
            self._aggancia_evidenza(box, evidenza)
        Grid.SetColumn(box, 1)
        g.Children.Add(tb)
        g.Children.Add(box)
        pannello.Children.Add(g)

    def riempi_profili(self):
        self.pnlProfili.Children.Clear()
        for k, etichetta, _v, minimo in S.PROFILI:
            aiuto = (u"Minimo %g mm" % minimo) if minimo is not None else None
            self._riga(self.pnlProfili, etichetta, self.schema[u"profili"][k], k, self.su_profilo, aiuto,
                       evidenza=(u"profilo", k))

    def riempi_misure(self):
        self.pnlMisure.Children.Clear()
        for perc, div in S.divisioni(self.schema[u"radice"]):
            for i in range(len(div[u"figli"]) - 1):
                nome = G.nome_misura(div[u"verso"], tuple(perc) + (i,))
                self._riga(self.pnlMisure, nome, div[u"misure"][i], (tuple(perc), i), self.su_misura,
                           u"Dal bordo esterno o dall'asse precedente all'asse seguente",
                           evidenza=(u"misura", tuple(perc), i))
        if not self.pnlMisure.Children.Count:
            tb = TextBlock()
            tb.Text = u"(nessuna divisione)"
            tb.Foreground = colore(u"#8C9AA6")
            self.pnlMisure.Children.Add(tb)

    def su_nome(self, sender, args):
        if not self._carico:
            self._nome_manuale = True
        self.aggiorna_file()

    def su_categoria(self, sender, args):
        if self._carico:
            return
        self.schema[u"categoria"] = S.PORTE if self.rbPorte.IsChecked else S.FINESTRE
        if not self._nome_manuale:
            self._imposta_nome(S.nome_famiglia(self.schema))
        self.ridisegna()

    def su_dimensione(self, sender, args):
        if self._carico:
            return
        v = numero(sender.Text)
        if v is None:
            return
        self.schema[u"larghezza" if sender is self.txtLarghezza else u"altezza"] = v
        self.ridisegna()

    def su_profilo(self, sender, args):
        if self._carico:
            return
        v = numero(sender.Text)
        if v is not None:
            self.schema[u"profili"][sender.Tag] = v
            self.ridisegna()

    def su_misura(self, sender, args):
        if self._carico:
            return
        v = numero(sender.Text)
        if v is not None:
            perc, i = sender.Tag
            self.schema = S.imposta_misura(self.schema, perc, i, v)
            self.ridisegna()

    def su_cartella(self, sender, args):
        scelta = forms.pick_folder(title=u"Cartella delle famiglie")
        if scelta:
            self.txtCartella.Text = scelta

    # --- zone --------------------------------------------------------------------------
    def aggiorna_selezione(self):
        c = S.nodo_in(self.schema[u"radice"], self.sel) if self.sel is not None else None
        attiva = c is not None and c[u"tipo"] == u"cella"
        if not attiva:
            self.sel = None
        for ctl in (self.cmbAnta, self.cmbChiusura, self.btnDividiV, self.btnDividiO):
            ctl.IsEnabled = attiva
        ha_padre = attiva and len(self.sel) > 0
        self.btnTogli.IsEnabled = ha_padre
        self.chkMontante.IsEnabled = ha_padre
        vecchio = self._carico
        self._carico = True
        try:
            if attiva:
                self.cmbAnta.SelectedIndex = [k for k, _e in S.ANTE].index(c[u"anta"])
                self.cmbChiusura.SelectedIndex = [k for k, _e in S.RIEMPIMENTI].index(
                    S.riempimento_valido(c[u"anta"], c.get(u"riempimento", S.VETRO)))
            else:
                self.cmbAnta.SelectedIndex = -1
                self.cmbChiusura.SelectedIndex = -1
            if ha_padre:
                self.chkMontante.IsChecked = S.nodo_in(self.schema[u"radice"], self.sel[:-1])[u"montante"]
        finally:
            self._carico = vecchio

    def su_anta(self, sender, args):
        if self._carico or self.sel is None or self.cmbAnta.SelectedIndex < 0:
            return
        self.schema = S.imposta_anta(self.schema, self.sel, S.ANTE[self.cmbAnta.SelectedIndex][0])
        self._dopo_modifica(struttura=False)

    def su_chiusura(self, sender, args):
        if self._carico or self.sel is None or self.cmbChiusura.SelectedIndex < 0:
            return
        scelta = S.RIEMPIMENTI[self.cmbChiusura.SelectedIndex][0]
        anta = S.nodo_in(self.schema[u"radice"], self.sel)[u"anta"]
        self.schema = S.imposta_riempimento(self.schema, self.sel, scelta)
        self._dopo_modifica(struttura=False)
        if scelta == S.ZOCCOLO and not S.porta(anta):
            self._stato(u"Lo zoccolo si mette solo sulle ante-porta: resta vetrata", errore=True)

    def su_soglia(self, sender, args):
        if not self._carico:
            self.schema[u"soglia"] = bool(self.chkSoglia.IsChecked)
            self.ridisegna()

    def su_maniglie(self, sender, args):
        if not self._carico:
            self.schema[u"maniglie"] = bool(self.chkManiglie.IsChecked)
            self.ridisegna()

    def su_pianta(self, sender, args):
        if not self._carico and self.cmbPianta.SelectedIndex >= 0:
            self.schema[u"simbolo_pianta"] = S.SIMBOLI_PIANTA[self.cmbPianta.SelectedIndex][0]

    def dividi(self, verso):
        if self.sel is None or not self.ris or not self.ris[u"celle"]:
            return
        cella = [c for c in self.ris[u"celle"] if c[u"percorso"] == self.sel]
        if not cella:
            return
        x0, y0, x1, y1 = G.rettangolo(self.ris, cella[0][u"regione"])
        meta = ((x1 - x0) if verso == u"v" else (y1 - y0)) / 2.0
        misura = max(round(meta / 10.0) * 10.0, 10.0)
        self.schema = S.dividi(self.schema, self.sel, verso, misura, montante=True)
        self.sel = tuple(self.sel) + (0,)
        self._dopo_modifica(struttura=True)

    def su_togli(self, sender, args):
        if self.sel is None or not self.sel:
            return
        self.schema = S.togli_divisione(self.schema, self.sel)
        self.sel = tuple(self.sel[:-1])
        self._dopo_modifica(struttura=True)

    def su_montante(self, sender, args):
        if self._carico or self.sel is None or not self.sel:
            return
        self.schema = S.imposta_montante(self.schema, self.sel[:-1], bool(self.chkMontante.IsChecked))
        self._dopo_modifica(struttura=False)

    def _dopo_modifica(self, struttura):
        if not self._nome_manuale:
            self._imposta_nome(S.nome_famiglia(self.schema))
        if struttura:
            self._carico = True
            try:
                self.riempi_misure()
            finally:
                self._carico = False
        self.aggiorna_selezione()
        self.ridisegna()

    def su_clic_anteprima(self, sender, args):
        if self._scala is None or not self.ris:
            return
        p = args.GetPosition(self.cnvAnteprima)
        sc, ox, oy = self._scala
        self.sel = G.cella_in_punto(self.ris, (p.X - ox) / sc, (oy - p.Y) / sc)
        self.aggiorna_selezione()
        self.ridisegna()

    # --- anteprima ---------------------------------------------------------------------
    def ridisegna(self):
        self.ris = G.calcola(self.schema)
        errori = self.ris[u"errori"]
        self.txtErrori.Text = u"\n".join(errori)
        self.btnCrea.IsEnabled = not errori
        cnv = self.cnvAnteprima
        cnv.Children.Clear()
        self._scala = None
        L, H = self.schema[u"larghezza"], self.schema[u"altezza"]
        w = cnv.ActualWidth or 460.0
        h = cnv.ActualHeight or 460.0
        if L <= 0 or H <= 0 or not self.ris[u"piani"]:
            return
        sc = min((w - 2 * MARGINE) / L, (h - 2 * MARGINE - 16) / H)
        if sc <= 0:
            return
        ox = (w - L * sc) / 2.0
        oy = (h - 16 + H * sc) / 2.0
        self._scala = (sc, ox, oy)

        def rett(r, riempi, bordo=SCURO, spessore=0.8):
            x0, y0, x1, y1 = r
            el = Rectangle()
            el.Width = max((x1 - x0) * sc, 0.5)
            el.Height = max((y1 - y0) * sc, 0.5)
            el.Fill = colore(riempi)
            el.Stroke = colore(bordo)
            el.StrokeThickness = spessore
            Canvas.SetLeft(el, ox + x0 * sc)
            Canvas.SetTop(el, oy - y1 * sc)
            cnv.Children.Add(el)

        for tipo in ORDINE_DISEGNO:
            for pz in self.ris[u"pezzi"]:
                if pz[u"tipo"] == tipo:
                    rett(G.rettangolo(self.ris, pz[u"esterni"]), COLORI[tipo])
        tratteggio = DoubleCollection()
        tratteggio.Add(5)
        tratteggio.Add(3)
        for s in self.ris[u"simboli"]:
            for seg in s[u"segmenti"]:
                ln = Line()
                ln.X1, ln.Y1 = ox + seg[u"p0"][0] * sc, oy - seg[u"p0"][1] * sc
                ln.X2, ln.Y2 = ox + seg[u"p1"][0] * sc, oy - seg[u"p1"][1] * sc
                ln.Stroke = colore(SCURO)
                ln.StrokeThickness = 1
                ln.StrokeDashArray = tratteggio
                cnv.Children.Add(ln)
        if self.sel is not None:
            for c in self.ris[u"celle"]:
                if c[u"percorso"] == self.sel:
                    rett(G.rettangolo(self.ris, c[u"luce"]), u"#33E5862A", ARANCIO, 2.5)
        if self.evid is not None:
            try:
                ev = G.evidenzia(self.ris, self.schema, self.evid)
            except (IndexError, KeyError, TypeError):
                ev = {u"rettangoli": [], u"quota": None}   # zona appena tolta: niente da illuminare
            for r in ev[u"rettangoli"]:
                rett(r, u"#661F6FB2", BLU, 2)
            if ev[u"quota"] is not None:
                self._disegna_quota(cnv, ev[u"quota"], sc, ox, oy)
        quota = TextBlock()
        quota.Text = u"%g x %g mm   ·   %s" % (L, H, S.descrizione(self.schema))
        quota.Foreground = colore(GRIGIO)
        Canvas.SetLeft(quota, ox)
        Canvas.SetTop(quota, oy + 4)
        cnv.Children.Add(quota)

    def _disegna_quota(self, cnv, q, sc, ox, oy):
        """Linea di quota blu, poco fuori dal disegno, con la misura scritta."""
        x0, y0, x1, y1 = q
        orizzontale = abs(y1 - y0) < 1e-6
        scost = 10.0
        if orizzontale:
            px0, px1 = ox + x0 * sc, ox + x1 * sc
            py = oy - y0 * sc - scost
            punti = ((px0, py, px1, py), (px0, py - 4, px0, py + 4), (px1, py - 4, px1, py + 4))
            valore = x1 - x0
            tx, ty = (px0 + px1) / 2.0 - 16, py - 18
        else:
            py0, py1 = oy - y0 * sc, oy - y1 * sc
            px = ox + x0 * sc + scost
            punti = ((px, py0, px, py1), (px - 4, py0, px + 4, py0), (px - 4, py1, px + 4, py1))
            valore = y1 - y0
            tx, ty = px + 4, (py0 + py1) / 2.0 - 8
        for a, b, c, d in punti:
            ln = Line()
            ln.X1, ln.Y1, ln.X2, ln.Y2 = a, b, c, d
            ln.Stroke = colore(BLU)
            ln.StrokeThickness = 1.5
            cnv.Children.Add(ln)
        tb = TextBlock()
        tb.Text = u"%g" % valore
        tb.Foreground = colore(BLU)
        tb.FontWeight = FontWeights.Bold
        tb.Background = colore(u"#FFFFFF")
        Canvas.SetLeft(tb, tx)
        Canvas.SetTop(tb, ty)
        cnv.Children.Add(tb)

    # --- fine ----------------------------------------------------------------------------
    def su_crea(self, sender, args):
        if self.ris is None or self.ris[u"errori"]:
            return
        nome = (self.txtNome.Text or u"").strip()
        if not nome or _VIETATI.search(nome):
            self._stato(u"Nome della famiglia non valido: non usare \\ / : * ? \" < > |", errore=True)
            self.txtNome.Focus()
            return
        cartella = (self.txtCartella.Text or u"").strip() or cartella_predefinita()
        self.risultato = {u"schema": S.copia(self.schema), u"nome": nome, u"cartella": cartella}
        self.Close()


def apri(schema=None, nome_famiglia=None, modifica=False):
    """Mostra il configuratore; ritorna {schema, nome, cartella} o None se annullato."""
    imp = C.carica_impostazioni()
    win = Configuratore(schema=schema, nome_famiglia=nome_famiglia,
                        cartella=imp.get(u"cartella") or u"", modifica=modifica)
    win.ShowDialog()
    return win.risultato


# --- creazione nel progetto ---------------------------------------------------------------
def _modello(app, categoria, imp):
    modello = C.trova_modello(categoria, [app.FamilyTemplatePath], imp)
    if modello:
        return modello
    tipo = u"Porta" if categoria == S.PORTE else u"Finestra"
    AVW.attenzione(u"Non trovo il modello famiglia %s: sceglilo, lo ricordo per le prossime volte" % tipo)
    modello = forms.pick_file(file_ext=u"rft", init_dir=app.FamilyTemplatePath or u"",
                              title=u"Modello famiglia %s (%s)" % (tipo, u", ".join(C.MODELLI[categoria][:2])))
    if modello:
        imp[u"modello_" + categoria] = modello
    return modello


def crea_e_carica(uidoc, risultato, tipi=None, posiziona=True):
    """Costruisce la famiglia, la salva e la carica nel progetto (dopo conferma).

    tipi: [(nome tipo, schema)] (Modifica infisso); di base un tipo solo dallo schema.
    """
    from infissi import revit_famiglia as RF

    doc = uidoc.Document
    app = doc.Application
    schema = risultato[u"schema"]
    imp = C.carica_impostazioni()
    modello = _modello(app, schema[u"categoria"], imp)
    if not modello:
        return None
    cartella = risultato[u"cartella"]
    percorso = os.path.join(cartella, risultato[u"nome"] + u".rfa")
    tipi = tipi or [(S.nome_tipo(schema), schema)]
    # la finestra ha gia' detto dove va il file e se ne sovrascrive uno: nessuna conferma
    try:
        if not os.path.isdir(cartella):
            os.makedirs(cartella)
        imp[u"cartella"] = cartella
        C.salva_impostazioni(imp)
    except Exception as ex:
        AVW.errore(u"Non riesco a usare la cartella %s: %s" % (cartella, ex))
        return None
    try:
        famdoc, report = RF.crea_famiglia(app, modello, schema, percorso, tipi)
        famiglia = RF.carica(doc, famdoc)
    except Exception as ex:
        AVW.errore(u"Famiglia non creata: %s" % ex)
        return None
    problemi = RF.problemi(report)
    if problemi:
        AVW.attenzione(AV.con_errori(u"Famiglia \"%s\" caricata, da controllare" % risultato[u"nome"], problemi))
    else:
        AVW.mostra(u"Famiglia \"%s\" creata e caricata" % risultato[u"nome"], AV.INFO)
    if famiglia is not None and posiziona:
        try:
            ids = list(famiglia.GetFamilySymbolIds())
            if ids:
                uidoc.PostRequestForElementTypePlacement(doc.GetElement(ids[0]))
        except Exception:
            pass
    return famiglia
