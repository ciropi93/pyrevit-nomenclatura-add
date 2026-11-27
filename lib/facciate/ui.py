# -*- coding: utf-8 -*-
"""Finestra "Ritmo facciata" (usata da Ritmo facciata, Aggiorna facciata con Maiusc e palette).

Cinque passi a sinistra (1 schema, 2 colonne, 3 righe, 4 classi di celle e linee, 5 tipi di
Revit e nome), a destra il prospetto della facciata selezionata visto da fuori, con le misure
vere. La finestra non usa le API Revit: riceve le misure della facciata e i nomi dei tipi e
ritorna lo schema; lo applica revit_facciata.
"""
import os

import clr
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

from System.Windows import (FontWeights, GridLength, HorizontalAlignment, TextAlignment, Thickness,
                            VerticalAlignment, Visibility)
from System.Windows.Controls import (Button, Canvas, CheckBox, ColumnDefinition, ComboBox, Grid,
                                     ListBoxItem, Orientation, StackPanel, TextBlock, TextBox)
from System.Windows.Input import Key, Keyboard, ModifierKeys
from System.Windows.Media import DoubleCollection
from System.Windows.Shapes import Line, Rectangle

from pyrevit import forms

import stile_finestre as SF
from icone_wpf import colore

from facciate import anteprima as AN
from facciate import catalogo as C
from facciate import ritmo as R
from facciate import schema as S

TITOLO = u"Ritmo facciata"
XAML = os.path.join(os.path.dirname(os.path.abspath(__file__)), u"facciata.xaml")
PASSI = 5
ARANCIO = u"#E5862A"
SCURO = u"#2B3640"
GRIGIO = u"#5B6B78"
CHIARO = u"#C5CED6"
LIVELLO = u"#1F6FB2"
TOLLERANZA_PX = 6.0
TIPO_FACCIATA = u"(tipo della facciata)"
FACCIATA_PROVA = {u"lunghezza": 12000.0, u"altezza": 7000.0, u"quote_livelli": [0.0, 3500.0, 7000.0]}
AIUTO_PASSO = {
    1: u"Scegli lo schema più vicino a quello che ti serve: lo cambi nei passi dopo.",
    2: u"Scrivi la sequenza con le lettere dei moduli (es. A A B): è il motivo che si ripete.",
    3: u"Come per le colonne, dal basso; con i livelli il motivo riparte a ogni piano.",
    4: u"Clicca una cella o una linea; Maiusc+clic aggiunge celle da unire.",
    5: u"Le classi senza tipo usano quello del tipo di facciata.",
}


def numero(testo):
    """Numero da un testo (accetta la virgola); None se non e' un numero."""
    try:
        return float((testo or u"").strip().replace(u",", u"."))
    except ValueError:
        return None


def _tratteggio():
    d = DoubleCollection()
    d.Add(6)
    d.Add(4)
    return d


class FinestraFacciata(forms.WPFWindow):
    def __init__(self, schema=None, facciata=None, tipi=None, n_muri=1):
        forms.WPFWindow.__init__(self, SF.xaml(XAML), literal_string=True)
        self.risultato = None
        self._errore = False     # in basso c'e' un errore del calcolo (sparisce quando torna giusto)
        self._carico = True
        self.passo = 1
        self.ris = None
        self._scala = None
        self.sel = None          # {"tipo": "celle", "punti": [(x, y)]} o {"tipo": verso, "pos": mm}
        self._ctrl = {}          # controlli degli editor di colonne e righe
        self.facciata = facciata or FACCIATA_PROVA
        self.tipi = tipi or {u"pannelli": [], u"montanti": []}
        self.voci = []
        self.riempi_schemi()
        self.btnEliminaSchema.IsEnabled = False
        self.schema = S.normalizza(S.copia(schema)) if schema else S.copia(self.voci[0][1])
        f = self.facciata
        testo = u"Facciata %d x %d mm, vista da fuori" % (round(f[u"lunghezza"]), round(f[u"altezza"]))
        if n_muri > 1:
            testo += u" (la prima di %d selezionate: il ritmo si adatta a ognuna)" % n_muri
        self.txtFacciata.Text = testo
        self.pannelli = [self.pnlPasso1, self.pnlPasso2, self.pnlPasso3, self.pnlPasso4, self.pnlPasso5]
        self.tasti_passo = [self.btnPasso1, self.btnPasso2, self.btnPasso3, self.btnPasso4, self.btnPasso5]

        self.lstSchemi.SelectionChanged += self.su_schema
        self.btnSalvaSchema.Click += self.su_salva_schema
        self.btnEliminaSchema.Click += self.su_elimina_schema
        self.chkLivelli.Click += self.su_livelli
        self.txtOffsetLivelli.TextChanged += self.su_offset_livelli
        self.cnvAnteprima.MouseLeftButtonDown += self.su_clic_anteprima
        self.cnvAnteprima.SizeChanged += lambda s, a: self.ridisegna()
        self.btnAssegna.Click += lambda s, a: self.assegna()
        self.cmbClasse.SelectionChanged += self.su_classe_scelta
        self.cmbClasse.KeyDown += self.su_tasto_classe
        self.btnUnisci.Click += self.su_unisci
        self.btnSepara.Click += self.su_separa
        self.txtNome.TextChanged += self.su_nome
        self.btnAnnulla.Click += lambda s, a: self.Close()
        self.btnApplica.Click += self.su_applica
        for i, tasto in enumerate(self.tasti_passo):
            tasto.Click += lambda s, a, n=i + 1: self.vai_al_passo(n)
        self.btnIndietro.Click += lambda s, a: self.vai_al_passo(self.passo - 1)
        self.btnAvanti.Click += lambda s, a: self.vai_al_passo(self.passo + 1)
        self.carica_schema()
        self.vai_al_passo(2 if schema else 1)

    # --- passi ---------------------------------------------------------------------------
    def vai_al_passo(self, n):
        n = max(1, min(PASSI, n))
        self.passo = n
        primario = self.FindResource(u"Primario")
        for i, (pannello, tasto) in enumerate(zip(self.pannelli, self.tasti_passo)):
            pannello.Visibility = Visibility.Visible if i + 1 == n else Visibility.Collapsed
            if i + 1 == n:
                tasto.Style = primario
            else:
                tasto.ClearValue(Button.StyleProperty)
        self.btnIndietro.IsEnabled = n > 1
        self.btnAvanti.Visibility = Visibility.Visible if n < PASSI else Visibility.Collapsed
        if n == 5:
            self.riempi_tipi()
        self.aggiorna_scelta()
        self.ridisegna()

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
                    vecchio = self._carico
                    self._carico = True
                    self.lstSchemi.SelectedIndex = i
                    self._carico = vecchio

    def su_schema(self, sender, args):
        if self._carico or self.lstSchemi.SelectedIndex < 0:
            return
        percorso, nuovo = self.voci[self.lstSchemi.SelectedIndex]
        vecchie = self.schema.get(u"classi") or {}
        self.schema = S.copia(nuovo)
        # i tipi gia' scelti per classi con lo stesso nome restano
        for gruppo in (u"pannelli", u"montanti"):
            for k in self.schema[u"classi"][gruppo]:
                if not self.schema[u"classi"][gruppo][k] and (vecchie.get(gruppo) or {}).get(k):
                    self.schema[u"classi"][gruppo][k] = vecchie[gruppo][k]
        self.btnEliminaSchema.IsEnabled = bool(percorso)
        self.sel = None
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
        self._imposta(self.txtNome, nome)
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

    # --- aiuti -----------------------------------------------------------------------------
    def _stato(self, testo, errore=False):
        self._errore = errore
        self.txtErrori.Text = testo
        self.txtErrori.Foreground = colore(u"#DC2626" if errore else GRIGIO)

    def _imposta(self, ctrl, testo):
        vecchio = self._carico
        self._carico = True
        ctrl.Text = testo
        self._carico = vecchio

    def _etichetta(self, pannello, testo, sopra=10):
        tb = TextBlock()
        tb.Text = testo
        tb.Style = self.FindResource(u"Etichetta")
        tb.Margin = Thickness(0, sopra, 0, 4)
        pannello.Children.Add(tb)
        return tb

    def _riga(self, pannello, etichetta, controllo, aiuto=None, larghezza=110):
        g = Grid()
        g.Margin = Thickness(0, 0, 0, 4)
        c0, c1 = ColumnDefinition(), ColumnDefinition()
        c1.Width = GridLength(larghezza)
        g.ColumnDefinitions.Add(c0)
        g.ColumnDefinitions.Add(c1)
        tb = TextBlock()
        tb.Text = etichetta
        tb.VerticalAlignment = VerticalAlignment.Center
        if aiuto:
            tb.ToolTip = aiuto
        Grid.SetColumn(controllo, 1)
        g.Children.Add(tb)
        g.Children.Add(controllo)
        pannello.Children.Add(g)
        return g

    def _casella(self, valore, gestore):
        box = TextBox()
        box.Text = valore
        box.TextChanged += gestore
        return box

    def _combo(self, voci, indice, gestore, modificabile=False):
        cmb = ComboBox()
        cmb.IsEditable = modificabile
        cmb.IsTextSearchEnabled = False     # niente completamento: scrivendo non si sceglie da solo
        cmb.ItemsSource = list(voci)
        cmb.SelectedIndex = indice
        if modificabile:
            cmb.LostFocus += gestore
        cmb.SelectionChanged += gestore
        return cmb

    # --- schema nei campi ----------------------------------------------------------------
    def carica_schema(self):
        self._carico = True
        try:
            self.txtNome.Text = self.schema.get(u"nome") or u""
            liv = self.schema[u"righe"].get(u"livelli") or {}
            self.chkLivelli.IsChecked = bool(liv.get(u"attivo"))
            self.txtOffsetLivelli.Text = u"%g" % (liv.get(u"offset") or 0)
            self.grdLivelli.IsEnabled = bool(liv.get(u"attivo"))
            self.editor_regola(u"colonne")
            self.editor_regola(u"righe")
            if self.passo == 5:
                self.riempi_tipi()
        finally:
            self._carico = False
        self.aggiorna_scelta()
        self.ridisegna()

    def editor_regola(self, chiave):
        """Moduli, sequenza e modo di colonne o righe (si rifa' quando cambia la struttura)."""
        vecchio = self._carico
        self._carico = True
        try:
            self._editor_regola(chiave)
        finally:
            self._carico = vecchio

    def _editor_regola(self, chiave):
        pannello = self.pnlColonne if chiave == u"colonne" else self.pnlRighe
        regola = self.schema[chiave]
        pannello.Children.Clear()
        ctrl = self._ctrl[chiave] = {}
        self._etichetta(pannello, u"MODULI (MM)", 0)
        for m in regola[u"moduli"]:
            g = Grid()
            g.Margin = Thickness(0, 0, 0, 4)
            for w in (36, 90, None, 30):
                cd = ColumnDefinition()
                if w:
                    cd.Width = GridLength(w)
                g.ColumnDefinitions.Add(cd)
            nome = TextBlock()
            nome.Text = m[u"id"]
            nome.FontWeight = FontWeights.Bold
            nome.VerticalAlignment = VerticalAlignment.Center
            box = self._casella(u"%g" % m[u"misura"],
                                lambda s, a, k=chiave, i=m[u"id"]: self.su_misura_modulo(k, i, s))
            blocco = CheckBox()
            blocco.Content = u"bloccato"
            blocco.IsChecked = bool(m[u"bloccato"])
            blocco.Margin = Thickness(10, 0, 0, 0)
            blocco.VerticalAlignment = VerticalAlignment.Center
            blocco.ToolTip = u"La misura resta questa: si adattano solo i moduli non bloccati"
            blocco.Click += lambda s, a, k=chiave, i=m[u"id"]: self.su_blocco(k, i, s)
            togli = Button()
            togli.Content = u"×"
            togli.ToolTip = u"Togli il modulo"
            togli.IsEnabled = len(regola[u"moduli"]) > 1
            togli.Click += lambda s, a, k=chiave, i=m[u"id"]: self.su_togli_modulo(k, i)
            for col, el in enumerate((nome, box, blocco, togli)):
                Grid.SetColumn(el, col)
                g.Children.Add(el)
            pannello.Children.Add(g)
        nuovo = Button()
        nuovo.Content = u"+ Modulo"
        nuovo.HorizontalAlignment = HorizontalAlignment.Left
        nuovo.Click += lambda s, a, k=chiave: self.su_aggiungi_modulo(k)
        pannello.Children.Add(nuovo)

        self._etichetta(pannello, u"SEQUENZA DEL MOTIVO")
        seq = self._casella(S.scrivi_sequenza(regola[u"sequenza"]),
                            lambda s, a, k=chiave: self.su_sequenza(k, s))
        seq.ToolTip = u"Le lettere dei moduli nell'ordine del motivo, es. A A B"
        pannello.Children.Add(seq)
        self._etichetta(pannello, u"COME SI RIPETE")
        modi = [k for k, _e in R.MODI]
        cmb = self._combo([e for _k, e in R.MODI], modi.index(regola[u"modo"]),
                          lambda s, a, k=chiave: self.su_modo(k, s))
        cmb.ToolTip = (u"Divisione migliore: il motivo finisce esatto sul bordo, i moduli liberi si adattano.\n"
                       u"Misura fissa: misure vere, il motivo si taglia ai bordi (ritagli).\n"
                       u"Numero di ripetizioni: il motivo n volte, i moduli liberi si adattano.")
        pannello.Children.Add(cmb)
        ctrl[u"modo"] = StackPanel()
        ctrl[u"modo"].Margin = Thickness(0, 6, 0, 0)
        pannello.Children.Add(ctrl[u"modo"])
        self._riempi_modo(chiave)

    def _riempi_modo(self, chiave):
        regola = self.schema[chiave]
        pnl = self._ctrl[chiave][u"modo"]
        pnl.Children.Clear()
        modo = regola[u"modo"]
        if modo == R.MIGLIORE:
            voci = [u"Motivo intero"] + [u"%d · %s" % (i + 1, mid) for i, mid in enumerate(regola[u"sequenza"])]
            fine = regola.get(u"finisci_con")
            indice = 0 if fine is None or fine >= len(regola[u"sequenza"]) - 1 else fine + 1
            cmb = self._combo(voci, indice, lambda s, a, k=chiave: self.su_fine(k, s))
            self._riga(pnl, u"Finisci con", cmb,
                       u"Con quale posto del motivo finisce la facciata (es. A per A B A B A)")
        elif modo == R.RIPETIZIONI:
            self._riga(pnl, u"Quante volte", self._casella(
                u"%d" % regola[u"ripetizioni"], lambda s, a, k=chiave: self.su_valore(k, u"ripetizioni", s, intero=True)))
        else:
            origini = [k for k, _e in R.ORIGINI]
            self._riga(pnl, u"Il motivo parte", self._combo(
                [e for _k, e in R.ORIGINI], origini.index(regola[u"origine"]),
                lambda s, a, k=chiave: self.su_origine(k, s)))
            self._riga(pnl, u"Spostato di (mm)", self._casella(
                u"%g" % regola[u"scarto"], lambda s, a, k=chiave: self.su_valore(k, u"scarto", s)),
                u"Sposta il motivo verso destra (o verso l'alto)")
            self._riga(pnl, u"Unisci ritagli sotto (mm)", self._casella(
                u"%g" % regola[u"resto_minimo"], lambda s, a, k=chiave: self.su_valore(k, u"resto_minimo", s)),
                u"I ritagli ai bordi più corti di questa misura si uniscono al modulo vicino")
            classi = [u""] + self._classi_pannelli()
            resto = regola.get(u"resto") or u""
            cmb = self._combo(classi, classi.index(resto) if resto in classi else 0,
                              lambda s, a, k=chiave: self.su_resto(k, s, a), modificabile=True)
            cmb.Text = resto
            self._riga(pnl, u"Classe dei ritagli", cmb, u"Vuoto = come il motivo")

    # --- gestori degli editor -------------------------------------------------------------
    def _modulo(self, chiave, mid):
        for m in self.schema[chiave][u"moduli"]:
            if m[u"id"] == mid:
                return m
        return None

    def su_misura_modulo(self, chiave, mid, box):
        if self._carico:
            return
        v = numero(box.Text)
        m = self._modulo(chiave, mid)
        if v is not None and m is not None:
            m[u"misura"] = v
            self.ridisegna()

    def su_blocco(self, chiave, mid, cb):
        if self._carico:
            return
        m = self._modulo(chiave, mid)
        if m is not None:
            m[u"bloccato"] = bool(cb.IsChecked)
            self.ridisegna()

    def su_aggiungi_modulo(self, chiave):
        S.aggiungi_modulo(self.schema[chiave])
        self.editor_regola(chiave)
        self.ridisegna()

    def su_togli_modulo(self, chiave, mid):
        try:
            S.togli_modulo(self.schema[chiave], mid)
        except S.SchemaErrore as ex:
            self._stato(u"%s" % ex, errore=True)
            return
        self.editor_regola(chiave)
        self.ridisegna()

    def su_sequenza(self, chiave, box):
        if self._carico:
            return
        S.imposta_sequenza(self.schema[chiave], box.Text)
        vecchio = self._carico
        self._carico = True
        try:
            self._riempi_modo(chiave)     # "Finisci con" elenca i posti del motivo
        finally:
            self._carico = vecchio
        self.ridisegna()

    def su_modo(self, chiave, cmb):
        if self._carico or cmb.SelectedIndex < 0:
            return
        self.schema[chiave][u"modo"] = R.MODI[cmb.SelectedIndex][0]
        self.editor_regola(chiave)
        self.ridisegna()

    def su_fine(self, chiave, cmb):
        if self._carico or cmb.SelectedIndex < 0:
            return
        self.schema[chiave][u"finisci_con"] = None if cmb.SelectedIndex == 0 else cmb.SelectedIndex - 1
        self.ridisegna()

    def su_origine(self, chiave, cmb):
        if self._carico or cmb.SelectedIndex < 0:
            return
        self.schema[chiave][u"origine"] = R.ORIGINI[cmb.SelectedIndex][0]
        self.ridisegna()

    def su_valore(self, chiave, campo, box, intero=False):
        if self._carico:
            return
        v = numero(box.Text)
        if v is None:
            return
        self.schema[chiave][campo] = max(1, int(v)) if intero else v
        self.ridisegna()

    def su_resto(self, chiave, cmb, args):
        if self._carico:
            return
        aggiunte = getattr(args, u"AddedItems", None)       # scelta dall'elenco o testo scritto
        testo = aggiunte[0] if aggiunte is not None and aggiunte.Count else (cmb.Text or u"").strip()
        self.schema[chiave][u"resto"] = testo or None
        S.aggiorna_classi(self.schema)
        self.ridisegna()

    def su_livelli(self, sender, args):
        if self._carico:
            return
        liv = self.schema[u"righe"].setdefault(u"livelli", S.livelli(False))
        liv[u"attivo"] = bool(self.chkLivelli.IsChecked)
        self.grdLivelli.IsEnabled = liv[u"attivo"]
        S.aggiorna_classi(self.schema)
        self.ridisegna()

    def su_offset_livelli(self, sender, args):
        if self._carico:
            return
        v = numero(self.txtOffsetLivelli.Text)
        if v is not None:
            self.schema[u"righe"].setdefault(u"livelli", S.livelli(False))[u"offset"] = v
            self.ridisegna()

    def su_nome(self, sender, args):
        if not self._carico:
            self.schema[u"nome"] = (self.txtNome.Text or u"").strip()

    # --- passo 4: classi ------------------------------------------------------------------
    def _classi_pannelli(self):
        pan, _mon = S.classi_usate(self.schema)
        return pan + [k for k in S.CLASSI_PANNELLI if k not in pan]

    def _classi_montanti(self):
        _pan, mon = S.classi_usate(self.schema)
        return mon + [k for k in S.CLASSI_MONTANTI if k not in mon]

    def celle_scelte(self):
        if not self.sel or self.sel[u"tipo"] != u"celle" or not self.ris:
            return []
        out = []
        for x, y in self.sel[u"punti"]:
            c = R.trova_cella(self.ris[u"celle"], self.ris[u"colonne"], self.ris[u"righe"], x, y)
            if c is not None and c not in out:
                out.append(c)
        return out

    def linea_scelta(self):
        if not self.sel or self.sel[u"tipo"] == u"celle" or not self.ris:
            return None
        linee = self.ris[u"linee_v"] if self.sel[u"tipo"] == u"verticale" else self.ris[u"linee_o"]
        vicine = [l for l in linee if abs(l[u"pos"] - self.sel[u"pos"]) < 1.0]
        return vicine[0] if vicine else None

    def aggiorna_scelta(self):
        """Il riquadro del passo 4 secondo cio' che e' scelto nel disegno."""
        vecchio = self._carico
        self._carico = True
        try:
            self._aggiorna_scelta()
        finally:
            self._carico = vecchio

    def _aggiorna_scelta(self):
        celle = self.celle_scelte()
        linea = self.linea_scelta()
        self.pnlAmbito.Visibility = Visibility.Visible if len(celle) == 1 else Visibility.Collapsed
        self.btnUnisci.IsEnabled = len(celle) > 1
        self.btnSepara.IsEnabled = any(c[u"col"][0] != c[u"col"][1] or c[u"riga"][0] != c[u"riga"][1]
                                       for c in celle)
        self.btnAssegna.IsEnabled = bool(celle) or linea is not None
        self.cmbClasse.IsEnabled = self.btnAssegna.IsEnabled
        if celle:
            if len(celle) == 1:
                self.txtScelta.Text = AN.descrizione_cella(self.ris, celle[0])
            else:
                self.txtScelta.Text = u"%d celle scelte" % len(celle)
            self.cmbClasse.ItemsSource = self._classi_pannelli()
            self.cmbClasse.Text = celle[0][u"classe"]
        elif linea is not None:
            self.txtScelta.Text = AN.descrizione_linea(self.ris, self.sel[u"tipo"], linea)
            self.cmbClasse.ItemsSource = self._classi_montanti()
            self.cmbClasse.Text = linea[u"classe"]
        else:
            self.txtScelta.Text = u"Niente di scelto: clicca una cella o una linea nel disegno"
            self.cmbClasse.ItemsSource = []
            self.cmbClasse.Text = u""

    def su_clic_anteprima(self, sender, args):
        if self._scala is None or not self.ris:
            return
        p = args.GetPosition(self.cnvAnteprima)
        sc, ox, oy = self._scala
        x, y = (p.X - ox) / sc, (oy - p.Y) / sc
        el = AN.elemento_in_punto(self.ris, x, y, TOLLERANZA_PX / sc)
        aggiungi = (Keyboard.Modifiers & ModifierKeys.Shift) == ModifierKeys.Shift
        if el is None:
            self.sel = None
        elif el[0] == u"cella":
            if aggiungi and self.sel and self.sel[u"tipo"] == u"celle":
                scelte = self.celle_scelte()
                if el[1] in scelte:          # Maiusc+clic su una cella gia' scelta la toglie
                    self.sel[u"punti"] = [pt for pt, c in zip(self.sel[u"punti"], scelte) if c != el[1]]
                else:
                    self.sel[u"punti"].append((x, y))
            else:
                self.sel = {u"tipo": u"celle", u"punti": [(x, y)]}
        else:
            self.sel = {u"tipo": el[0], u"pos": el[1][u"pos"]}
        if self.passo != 4:
            self.vai_al_passo(4)
        else:
            self.aggiorna_scelta()
            self.ridisegna()

    def _ambito(self):
        if self.rbColonna.IsChecked:
            return S.COLONNA
        if self.rbRiga.IsChecked:
            return S.RIGA
        return S.CELLA

    def assegna(self, classe=None):
        classe = (classe or self.cmbClasse.Text or u"").strip()
        if not classe:
            return
        celle = self.celle_scelte()
        linea = self.linea_scelta()
        if celle:
            ambito = self._ambito() if len(celle) == 1 else S.CELLA
            for c in celle:
                tc, tr = self.ris[u"colonne"][c[u"col"][0]], self.ris[u"righe"][c[u"riga"][0]]
                if tc[u"resto"] and self.schema[u"colonne"][u"modo"] == R.FISSO:
                    self.schema[u"colonne"][u"resto"] = classe     # ritaglio delle colonne
                elif tr[u"resto"] and self.schema[u"righe"][u"modo"] == R.FISSO:
                    self.schema[u"righe"][u"resto"] = classe
                else:
                    S.imposta_classe_cella(self.schema, tc[u"pos"], tr[u"pos"], classe, ambito)
            S.aggiorna_classi(self.schema)
        elif linea is not None:
            if self.sel[u"tipo"] == u"orizzontale" and AN.sul_livello(self.ris, linea):
                self.schema[u"righe"][u"livelli"][u"classe"] = classe
                S.aggiorna_classi(self.schema)
            else:
                verso = u"colonne" if self.sel[u"tipo"] == u"verticale" else u"righe"
                tratti = self.ris[verso]
                S.imposta_classe_linea(self.schema, verso, tratti[linea[u"indice"]][u"pos"], classe)
        else:
            return
        self.ridisegna()
        self.aggiorna_scelta()
        self._stato(u"Classe \"%s\" assegnata" % classe)

    def su_classe_scelta(self, sender, args):
        if self._carico or self.cmbClasse.SelectedItem is None:
            return
        self.assegna(self.cmbClasse.SelectedItem)

    def su_tasto_classe(self, sender, args):
        if args.Key == Key.Enter:
            self.assegna()

    def su_unisci(self, sender, args):
        celle = self.celle_scelte()
        rq = AN.riquadro_selezione(self.ris, celle)
        if rq is None:
            self._stato(u"Si uniscono solo celle della stessa ripetizione del motivo (e dello stesso piano)",
                        errore=True)
            return
        S.unisci(self.schema, rq[0], rq[1])
        self.sel = {u"tipo": u"celle", u"punti": self.sel[u"punti"][:1]}
        self.ridisegna()
        self.aggiorna_scelta()
        self._stato(u"Celle unite in ogni ripetizione del motivo")

    def su_separa(self, sender, args):
        for c in self.celle_scelte():
            pc, pr = AN.posizioni_cella(self.ris, c)
            S.separa(self.schema, pc, pr)
        self.ridisegna()
        self.aggiorna_scelta()

    # --- passo 5: tipi --------------------------------------------------------------------
    def riempi_tipi(self):
        vecchio = self._carico
        self._carico = True
        try:
            S.aggiorna_classi(self.schema)
            pan, mon = S.classi_usate(self.schema)
            for pannello, gruppo, classi, extra, disponibili in (
                    (self.pnlTipiPannelli, u"pannelli", pan, [TIPO_FACCIATA], self.tipi[u"pannelli"]),
                    (self.pnlTipiMontanti, u"montanti", mon, [TIPO_FACCIATA, S.NESSUNO], self.tipi[u"montanti"])):
                pannello.Children.Clear()
                for k in classi:
                    scelto = self.schema[u"classi"][gruppo].get(k) or u""
                    voci = extra + sorted(disponibili)
                    if scelto and scelto not in voci:
                        voci.append(scelto)          # tipo di un altro progetto: resta scritto
                    indice = voci.index(scelto) if scelto else 0
                    cmb = self._combo(voci, indice, lambda s, a, g=gruppo, c=k: self.su_tipo(g, c, s))
                    self._riga(pannello, k, cmb, larghezza=210)
                if not disponibili:
                    nota = TextBlock()
                    nota.Text = u"(nessun tipo letto dal progetto)"
                    nota.Foreground = colore(u"#8C9AA6")
                    pannello.Children.Add(nota)
        finally:
            self._carico = vecchio

    def su_tipo(self, gruppo, classe, cmb):
        if self._carico or cmb.SelectedItem is None:
            return
        v = cmb.SelectedItem
        self.schema[u"classi"][gruppo][classe] = u"" if v == TIPO_FACCIATA else v

    # --- disegno ---------------------------------------------------------------------------
    def calcola(self):
        f = self.facciata
        errori = S.errori(self.schema)
        if errori:
            return None, errori
        try:
            return R.calcola(self.schema, f[u"lunghezza"], f[u"altezza"], f[u"quote_livelli"]), []
        except R.RitmoErrore as ex:
            return None, [u"%s" % ex]

    def ridisegna(self):
        self.ris, errori = self.calcola()
        self.btnApplica.IsEnabled = not errori
        if errori:
            self._stato(u"\n".join(errori), errore=True)
        elif self._errore:
            self._stato(u"")
        self.txtAiuto.Text = AIUTO_PASSO.get(self.passo, u"")
        cnv = self.cnvAnteprima
        cnv.Children.Clear()
        self.pnlLegenda.Children.Clear()
        self._scala = None
        if self.ris is None:
            return
        f = self.facciata
        w = cnv.ActualWidth or 600.0
        h = cnv.ActualHeight or 460.0
        scala = AN.scala(f[u"lunghezza"], f[u"altezza"], w, h, (64.0, 40.0, 90.0, 24.0))
        if scala is None:
            return
        self._scala = scala
        sc, ox, oy = scala
        ris = self.ris
        L, H = ris[u"lunghezza"], ris[u"altezza"]
        pan, mon = S.classi_usate(self.schema)

        def X(x):
            return ox + x * sc

        def Y(y):
            return oy - y * sc

        for c in ris[u"celle"]:
            x0, x1 = ris[u"colonne"][c[u"col"][0]][u"da"], ris[u"colonne"][c[u"col"][1]][u"a"]
            y0, y1 = ris[u"righe"][c[u"riga"][0]][u"da"], ris[u"righe"][c[u"riga"][1]][u"a"]
            self._rett(X(x0), Y(y1), (x1 - x0) * sc, (y1 - y0) * sc, AN.colore_pannello(c[u"classe"], pan),
                       u"#FFFFFF", 0.6)
        for verso, linee in ((u"verticale", ris[u"linee_v"]), (u"orizzontale", ris[u"linee_o"])):
            for l in linee:
                if not AN.linea_esiste(ris, verso, l):
                    continue
                tinta = AN.colore_montante(l[u"classe"], mon)
                sp = AN.spessore_montante(l[u"classe"])
                for a, b in AN.segmenti(ris, verso, l):
                    if verso == u"verticale":
                        self._linea(X(l[u"pos"]), Y(a), X(l[u"pos"]), Y(b), tinta, sp)
                    else:
                        self._linea(X(a), Y(l[u"pos"]), X(b), Y(l[u"pos"]), tinta, sp)
        self._rett(X(0), Y(H), L * sc, H * sc, None, SCURO, 2.0)          # bordo del tipo
        # livelli del progetto
        for q in f[u"quote_livelli"]:
            if R.TOLLERANZA < q < H - R.TOLLERANZA:
                self._linea(X(0) - 8, Y(q), X(L) + 8, Y(q), LIVELLO, 0.8, True)
                self._testo(u"livello +%d" % round(q), X(L) + 10, Y(q) - 8, LIVELLO)
        # quote dei tratti: colonne sopra, righe a sinistra
        for a, b, testo in AN.quote(ris[u"colonne"], sc):
            self._linea(X(a), Y(H) - 14, X(b), Y(H) - 14, CHIARO, 0.8)
            self._testo(testo, (X(a) + X(b)) / 2.0 - 25, Y(H) - 30, GRIGIO, larghezza=50)
        for a, b, testo in AN.quote(ris[u"righe"], sc, 18.0):
            self._linea(X(0) - 14, Y(a), X(0) - 14, Y(b), CHIARO, 0.8)
            self._testo(testo, X(0) - 62, (Y(a) + Y(b)) / 2.0 - 8, GRIGIO, larghezza=44, destra=True)
        # cio' che e' scelto
        for c in self.celle_scelte():
            x0, x1 = ris[u"colonne"][c[u"col"][0]][u"da"], ris[u"colonne"][c[u"col"][1]][u"a"]
            y0, y1 = ris[u"righe"][c[u"riga"][0]][u"da"], ris[u"righe"][c[u"riga"][1]][u"a"]
            self._rett(X(x0), Y(y1), (x1 - x0) * sc, (y1 - y0) * sc, u"#33E5862A", ARANCIO, 2.5)
        l = self.linea_scelta()
        if l is not None:
            if self.sel[u"tipo"] == u"verticale":
                self._linea(X(l[u"pos"]), Y(0), X(l[u"pos"]), Y(H), ARANCIO, 4.0)
            else:
                self._linea(X(0), Y(l[u"pos"]), X(L), Y(l[u"pos"]), ARANCIO, 4.0)
        self._legenda(pan, mon)

    def _legenda(self, pan, mon):
        for k in pan:
            self._voce_legenda(k, AN.colore_pannello(k, pan), True)
        for k in mon:
            self._voce_legenda(k, AN.colore_montante(k, mon), False)

    def _voce_legenda(self, testo, tinta, pannello):
        sp = StackPanel()
        sp.Orientation = Orientation.Horizontal
        sp.Margin = Thickness(0, 0, 14, 0)
        r = Rectangle()
        r.Width = 14
        r.Height = 10 if pannello else 3
        r.Fill = colore(tinta)
        if pannello:
            r.Stroke = colore(CHIARO)
        r.Margin = Thickness(0, 0, 4, 0)
        r.VerticalAlignment = VerticalAlignment.Center
        tb = TextBlock()
        tb.Text = testo
        tb.Foreground = colore(GRIGIO)
        sp.Children.Add(r)
        sp.Children.Add(tb)
        self.pnlLegenda.Children.Add(sp)

    def _rett(self, px, py, larg, alt, riempi, bordo=SCURO, spessore=0.8):
        el = Rectangle()
        el.Width = max(larg, 0.5)
        el.Height = max(alt, 0.5)
        if riempi:
            el.Fill = colore(riempi)
        el.Stroke = colore(bordo)
        el.StrokeThickness = spessore
        Canvas.SetLeft(el, px)
        Canvas.SetTop(el, py)
        self.cnvAnteprima.Children.Add(el)

    def _linea(self, x1, y1, x2, y2, tinta=SCURO, spessore=1.0, tratteggio=False):
        ln = Line()
        ln.X1, ln.Y1, ln.X2, ln.Y2 = x1, y1, x2, y2
        ln.Stroke = colore(tinta)
        ln.StrokeThickness = spessore
        if tratteggio:
            ln.StrokeDashArray = _tratteggio()
        self.cnvAnteprima.Children.Add(ln)

    def _testo(self, testo, x, y, tinta=GRIGIO, larghezza=None, destra=False):
        tb = TextBlock()
        tb.Text = testo
        tb.Foreground = colore(tinta)
        tb.FontSize = 11
        if larghezza:
            tb.Width = larghezza
            tb.TextAlignment = TextAlignment.Right if destra else TextAlignment.Center
        Canvas.SetLeft(tb, x)
        Canvas.SetTop(tb, y)
        self.cnvAnteprima.Children.Add(tb)

    # --- fine ----------------------------------------------------------------------------
    def su_applica(self, sender, args):
        if self.ris is None:
            return
        S.aggiorna_classi(self.schema)
        self.risultato = S.copia(self.schema)
        self.Close()


def apri(schema=None, facciata=None, tipi=None, n_muri=1):
    """Mostra la finestra; ritorna lo schema scelto o None se annullata."""
    win = FinestraFacciata(schema=schema, facciata=facciata, tipi=tipi, n_muri=n_muri)
    win.ShowDialog()
    return win.risultato
