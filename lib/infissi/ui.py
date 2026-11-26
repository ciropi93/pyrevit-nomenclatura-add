# -*- coding: utf-8 -*-
"""Finestra del configuratore e creazione della famiglia (usata da Configuratore e Modifica infisso).

Quattro passi a sinistra (1 schema e categoria, 2 ante delle zone, 3 misure, 4 dettagli:
opzioni, profili che servono, nome e cartella), a destra il disegno sempre visibile:
prospetto visto da fuori con le quote (clic su una zona per sceglierla) o pianta, al livello
di dettaglio scelto. "Crea" chiude la finestra da qualsiasi passo; la famiglia si costruisce
dopo, fuori dalla finestra.
"""
import math
import os
import re

import clr
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")

from System.Windows import (FontWeights, GridLength, HorizontalAlignment, Point, TextAlignment,
                            Thickness, VerticalAlignment, Visibility)
from System.Windows.Controls import (Button, Canvas, CheckBox, ColumnDefinition, Grid, ListBoxItem,
                                     TextBlock, TextBox)
from System.Windows.Media import DoubleCollection, PointCollection
from System.Windows.Shapes import Line, Polyline, Rectangle

from pyrevit import forms

import avviso as AV
import avviso_wpf as AVW
import stile_finestre as SF
from icone_wpf import colore

from infissi import anteprima as AN
from infissi import catalogo as C
from infissi import geometria as G
from infissi import schema as S

TITOLO = u"Infissi"
XAML = os.path.join(os.path.dirname(os.path.abspath(__file__)), u"configuratore.xaml")

COLORI = {
    u"telaio": u"#4A5866", u"montante": u"#4A5866", u"anta": u"#5B6B78",
    u"zoccolo": u"#5B6B78", u"vetro": u"#CFE3F4", u"pannello": u"#C9D3DB",
    u"maniglia": u"#2B3640",
    u"muro": u"#E3E7EB", u"mostra": u"#C8A47E", u"davanzale": u"#B9B4AE", u"soglia": u"#B9B4AE",
    u"imbotte": u"#D8BE95",
}
# prima davanzali e soglia (in pianta stanno sotto il taglio: il muro li copre dove sono incassati)
ORDINE_CONTORNO = (u"davanzale", u"soglia", u"muro", u"imbotte", u"mostra")
# elementi del contorno a gruppi, nel passo 5 (solo quelli ammessi dalla categoria)
GRUPPI_CONTORNO = ((u"Foro", (u"mazzetta",)), (u"Mostre", (u"mostra_est", u"mostra_int")),
                   (u"Davanzali e soglia", (u"dav_est", u"dav_int", u"soglia_pietra")),
                   (u"Imbotte", (u"imbotte",)))
ARANCIO = u"#E5862A"      # zona scelta
SCURO = u"#2B3640"        # bordi e simboli di apertura
GRIGIO = u"#5B6B78"
BLU = u"#1F6FB2"          # parte che cambia il campo in uso
CHIARO = u"#C5CED6"       # linee di richiamo delle quote, asse del muro
ORDINE_DISEGNO = (u"telaio", u"montante", u"anta", u"zoccolo", u"vetro", u"pannello", u"maniglia")
MARGINE = 24.0
CORSIA = 22.0             # distanza tra le file di quote (pixel)
_VIETATI = re.compile(u'[\\\\/:*?"<>|]')

PASSI = 5
DETTAGLI = ((G.BASSO, u"Basso"), (G.MEDIO, u"Medio"), (G.ALTO, u"Alto"))
AIUTO_PASSO = {
    1: u"Scegli lo schema più vicino a quello che ti serve: lo cambi nei passi dopo.",
    2: u"Clicca una zona del disegno per sceglierla.",
    3: u"Le quote sul disegno sono le misure dei campi: quella del campo in uso è blu.",
    4: u"Il simbolo in pianta si vede con il tasto Pianta qui sopra.",
    5: u"In pianta il muro ha lo spessore dell'anteprima; in Revit conta quello del muro vero.",
}


def numero(testo):
    """Numero da un testo (accetta la virgola); None se non e' un numero."""
    try:
        return float((testo or u"").strip().replace(u",", u"."))
    except ValueError:
        return None


def _tratteggio():
    d = DoubleCollection()
    d.Add(5)
    d.Add(3)
    return d


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
        self.passo = 1
        self.dettaglio = G.ALTO

        self.voci = []
        self.riempi_schemi()
        self.btnEliminaSchema.IsEnabled = False   # si attiva sugli schemi salvati da te
        self.cmbAnta.ItemsSource = [e for _k, e in S.ANTE]
        self.cmbChiusura.ItemsSource = [e for _k, e in S.RIEMPIMENTI]
        self.cmbPianta.ItemsSource = [e for _k, e in S.SIMBOLI_PIANTA]
        self.cmbDettaglio.ItemsSource = [e for _k, e in DETTAGLI]
        self.cmbDettaglio.SelectedIndex = [k for k, _e in DETTAGLI].index(self.dettaglio)

        self.schema = S.copia(schema) if schema else S.copia(self.voci[0][1])
        self.txtNome.Text = nome_famiglia or S.nome_famiglia(self.schema)
        self.txtCartella.Text = cartella or cartella_predefinita()
        self.cmbPosizione.ItemsSource = [e for _k, e in S.POSIZIONI]
        self.pannelli = [self.pnlPasso1, self.pnlPasso2, self.pnlPasso3, self.pnlPasso4, self.pnlPasso5]
        self.tasti_passo = [self.btnPasso1, self.btnPasso2, self.btnPasso3, self.btnPasso4, self.btnPasso5]
        if modifica:
            # schema e categoria sono quelli della famiglia: si parte dalle ante
            self.btnPasso1.IsEnabled = False
            self.txtNome.IsEnabled = False
            self.btnCrea.Content = u"Aggiorna famiglia"
            self.lblTitolo.Text = u"Modifica infisso"
            self.lblSottotitolo.Text = u"Cambia ante, misure o dettagli: la famiglia nel progetto si aggiorna."

        self.lstSchemi.SelectionChanged += self.su_schema
        self.btnSalvaSchema.Click += self.su_salva_schema
        self.btnEliminaSchema.Click += self.su_elimina_schema
        self.cnvAnteprima.MouseLeftButtonDown += self.su_clic_anteprima
        self.cnvAnteprima.SizeChanged += lambda s, a: self.ridisegna()
        self.cmbAnta.SelectionChanged += self.su_anta
        self.cmbChiusura.SelectionChanged += self.su_chiusura
        self.chkSoglia.Click += self.su_soglia
        self.cmbManiglia.SelectionChanged += self.su_maniglia
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
        for i, tasto in enumerate(self.tasti_passo):
            tasto.Click += lambda s, a, n=i + 1: self.vai_al_passo(n)
        self.btnIndietro.Click += lambda s, a: self.vai_al_passo(self.passo - 1)
        self.btnAvanti.Click += lambda s, a: self.vai_al_passo(self.passo + 1)
        self.rbProspetto.Checked += lambda s, a: self.ridisegna()
        self.rbPianta.Checked += lambda s, a: self.ridisegna()
        self.cmbDettaglio.SelectionChanged += self.su_dettaglio
        self.cmbPosizione.SelectionChanged += self.su_posizione
        self.carica_schema()
        self.aggiorna_file()
        self.vai_al_passo(2 if modifica else 1)

    # --- passi ---------------------------------------------------------------------------
    def _primo(self):
        return 2 if self.modifica else 1

    def vai_al_passo(self, n):
        n = max(self._primo(), min(PASSI, n))
        self.passo = n
        primario = self.FindResource(u"Primario")
        for i, (pannello, tasto) in enumerate(zip(self.pannelli, self.tasti_passo)):
            pannello.Visibility = Visibility.Visible if i + 1 == n else Visibility.Collapsed
            if i + 1 == n:
                tasto.Style = primario
            else:
                tasto.ClearValue(Button.StyleProperty)
        self.btnIndietro.IsEnabled = n > self._primo()
        self.btnAvanti.Visibility = Visibility.Visible if n < PASSI else Visibility.Collapsed
        if n == 2 and self.sel is None and self.ris and self.ris[u"celle"]:
            # una zona gia' scelta: si vede subito cosa si puo' fare
            self.sel = tuple(self.ris[u"celle"][0][u"percorso"])
            self.aggiorna_selezione()
        if n in (4, 5):
            self._carico = True
            try:
                self.riempi_profili() if n == 4 else self.riempi_contorno()
            finally:
                self._carico = False
        self.ridisegna()

    def su_dettaglio(self, sender, args):
        if self.cmbDettaglio.SelectedIndex >= 0:
            self.dettaglio = DETTAGLI[self.cmbDettaglio.SelectedIndex][0]
            self.ridisegna()

    def in_pianta(self):
        return bool(self.rbPianta.IsChecked)

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
            self.cmbPianta.SelectedIndex = [k for k, _e in S.SIMBOLI_PIANTA].index(
                self.schema.get(u"simbolo_pianta", u"nessuno"))
            self.riempi_profili()
            self.riempi_misure()
            self.riempi_contorno()
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
        """Solo i profili che servono a questo schema, a gruppi (Telaio, Ante, ...)."""
        self.pnlProfili.Children.Clear()
        dati = dict((k, (etichetta, minimo)) for k, etichetta, _v, minimo in S.PROFILI)
        for n, (titolo, chiavi) in enumerate(AN.profili_per_gruppo(self.schema)):
            tb = TextBlock()
            tb.Text = titolo
            tb.FontWeight = FontWeights.SemiBold
            tb.Margin = Thickness(0, 0 if n == 0 else 8, 0, 4)
            self.pnlProfili.Children.Add(tb)
            for k in chiavi:
                etichetta, minimo = dati[k]
                aiuto = (u"Minimo %g mm" % minimo) if minimo is not None else None
                self._riga(self.pnlProfili, etichetta, self.schema[u"profili"][k], k, self.su_profilo, aiuto,
                           evidenza=(u"profilo", k))

    # --- passo 5: muro e contorno ------------------------------------------------------------
    def _contorno(self):
        if not self.schema.get(u"contorno"):
            self.schema[u"contorno"] = S.contorno_vuoto()
        return self.schema[u"contorno"]

    def riempi_contorno(self):
        """Posizione nel muro, elementi a gruppi; sotto ogni gruppo le misure degli elementi accesi."""
        c = self._contorno()
        misure = dict((k, (e, m)) for k, e, _v, m in S.MISURE_CONTORNO)
        self.cmbPosizione.SelectedIndex = [k for k, _e in S.POSIZIONI].index(c[u"posizione"])
        self.pnlPosizione.Children.Clear()
        chiavi = ([u"posizione"] if c[u"posizione"] != u"centro" else []) + [u"muro"]
        for k in chiavi:
            etichetta, minimo = misure[k]
            if k == u"posizione":
                etichetta = u"Distanza dal filo al telaio"
            self._riga(self.pnlPosizione, etichetta, c[u"misure"][k], k, self.su_misura_contorno,
                       u"Minimo %g mm" % minimo)
        self.pnlContorno.Children.Clear()
        ammessi = S.elementi_ammessi(self.schema[u"categoria"])
        primo = True
        for titolo, elementi in GRUPPI_CONTORNO:
            elementi = [k for k in elementi if k in ammessi]
            if not elementi:
                continue
            tb = TextBlock()
            tb.Text = titolo.upper()
            tb.Style = self.FindResource(u"Etichetta")
            tb.Margin = Thickness(0, 0 if primo else 10, 0, 4)
            primo = False
            self.pnlContorno.Children.Add(tb)
            accese = []
            for k in elementi:
                cb = CheckBox()
                cb.Content = S.NOMI_ELEMENTI_CONTORNO[k]
                cb.IsChecked = bool(c.get(k))
                cb.Tag = k
                cb.Margin = Thickness(0, 0, 0, 4)
                cb.Click += self.su_elemento_contorno
                self.pnlContorno.Children.Add(cb)
                if c.get(k):
                    accese.extend(m for m in S.MISURE_DI[k] if m not in accese)
            for k in accese:
                etichetta, minimo = misure[k]
                self._riga(self.pnlContorno, u"   " + etichetta, c[u"misure"][k], k, self.su_misura_contorno,
                           u"Minimo %g mm" % minimo)

    def _aggiorna_contorno(self):
        vecchio = self._carico
        self._carico = True
        try:
            self.riempi_contorno()
        finally:
            self._carico = vecchio
        self.ridisegna()

    def su_posizione(self, sender, args):
        if self._carico or self.cmbPosizione.SelectedIndex < 0:
            return
        self._contorno()[u"posizione"] = S.POSIZIONI[self.cmbPosizione.SelectedIndex][0]
        self._aggiorna_contorno()

    def su_elemento_contorno(self, sender, args):
        if self._carico:
            return
        self._contorno()[sender.Tag] = bool(sender.IsChecked)
        self._aggiorna_contorno()

    def su_misura_contorno(self, sender, args):
        if self._carico:
            return
        v = numero(sender.Text)
        if v is not None:
            self._contorno()[u"misure"][sender.Tag] = v
            self.ridisegna()

    def _aggiorna_profili(self):
        """Dopo un'opzione che cambia quali profili servono (soglia, maniglie)."""
        vecchio = self._carico
        self._carico = True
        try:
            self.riempi_profili()
        finally:
            self._carico = vecchio

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
        self.aggiorna_selezione()       # le maniglie predefinite cambiano con la categoria
        self._aggiorna_contorno()       # davanzali per le finestre, soglia per le porte

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
        self.txtZona.Text = (u"Zona %s" % G.nome_zona(self.sel)) if attiva else \
            u"Nessuna zona scelta: clicca il disegno"
        vecchio = self._carico
        self._carico = True
        try:
            # maniglie: solo quelle adatte all'anta (l'antipanico sulle ante-porta)
            self.maniglie_cella = S.maniglie_valide(c[u"anta"]) if attiva else []
            self.cmbManiglia.ItemsSource = [S.NOMI_MANIGLIE[k] for k in self.maniglie_cella]
            self.cmbManiglia.IsEnabled = len(self.maniglie_cella) > 1
            if attiva:
                self.cmbAnta.SelectedIndex = [k for k, _e in S.ANTE].index(c[u"anta"])
                self.cmbChiusura.SelectedIndex = [k for k, _e in S.RIEMPIMENTI].index(
                    S.riempimento_valido(c[u"anta"], c.get(u"riempimento", S.VETRO)))
                self.cmbManiglia.SelectedIndex = self.maniglie_cella.index(
                    S.maniglia_di(c, self.schema[u"categoria"]))
            else:
                self.cmbAnta.SelectedIndex = -1
                self.cmbChiusura.SelectedIndex = -1
                self.cmbManiglia.SelectedIndex = -1
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
            self._aggiorna_profili()
            self.ridisegna()

    def su_maniglia(self, sender, args):
        if self._carico or self.sel is None or self.cmbManiglia.SelectedIndex < 0:
            return
        scelta = self.maniglie_cella[self.cmbManiglia.SelectedIndex]
        self.schema = S.imposta_maniglia(self.schema, self.sel, scelta)
        self._dopo_modifica(struttura=False)
        if scelta == S.ANTIPANICO:
            self._stato(u"Maniglione sul lato da cui si spinge: nel progetto gira la porta "
                        u"perché apra verso la via d'uscita")

    def su_pianta(self, sender, args):
        if not self._carico and self.cmbPianta.SelectedIndex >= 0:
            self.schema[u"simbolo_pianta"] = S.SIMBOLI_PIANTA[self.cmbPianta.SelectedIndex][0]
            self.ridisegna()

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
        if self._scala is None or not self.ris or self.in_pianta():
            return
        p = args.GetPosition(self.cnvAnteprima)
        sc, ox, oy = self._scala
        self.sel = G.cella_in_punto(self.ris, (p.X - ox) / sc, (oy - p.Y) / sc)
        self.aggiorna_selezione()
        if self.sel is not None and self.passo != 2:
            self.vai_al_passo(2)        # una zona scelta si cambia al passo Ante
        else:
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
        aiuto = u"Pianta tagliata a metà altezza, vista dall'alto: interno in alto, esterno in basso." \
            if self.in_pianta() else u"Prospetto visto da fuori."
        self.txtAiuto.Text = aiuto + u"  " + AIUTO_PASSO.get(self.passo, u"")
        L, H = self.schema[u"larghezza"], self.schema[u"altezza"]
        if L <= 0 or H <= 0 or not self.ris[u"piani"]:
            return
        w = cnv.ActualWidth or 460.0
        h = cnv.ActualHeight or 460.0
        if self.in_pianta():
            self._disegna_pianta(cnv, w, h, L)
        else:
            self._disegna_prospetto(cnv, w, h, L, H)
        descr = TextBlock()
        descr.Text = u"%g x %g mm   ·   %s" % (L, H, S.descrizione(self.schema))
        descr.Foreground = colore(GRIGIO)
        Canvas.SetLeft(descr, 8)
        Canvas.SetTop(descr, h - 20)
        cnv.Children.Add(descr)

    def _rett(self, cnv, px0, py_alto, larg, alt, riempi, bordo=SCURO, spessore=0.8):
        el = Rectangle()
        el.Width = max(larg, 0.5)
        el.Height = max(alt, 0.5)
        el.Fill = colore(riempi)
        el.Stroke = colore(bordo)
        el.StrokeThickness = spessore
        Canvas.SetLeft(el, px0)
        Canvas.SetTop(el, py_alto)
        cnv.Children.Add(el)

    def _linea(self, cnv, x1, y1, x2, y2, tinta=SCURO, spessore=1.0, tratteggio=False):
        ln = Line()
        ln.X1, ln.Y1, ln.X2, ln.Y2 = x1, y1, x2, y2
        ln.Stroke = colore(tinta)
        ln.StrokeThickness = spessore
        if tratteggio:
            ln.StrokeDashArray = _tratteggio()
        cnv.Children.Add(ln)

    def _testo(self, cnv, testo, x, y, tinta=GRIGIO, grassetto=False, larghezza=None, destra=False):
        tb = TextBlock()
        tb.Text = testo
        tb.Foreground = colore(tinta)
        tb.Background = colore(u"#FFFFFF")
        if grassetto:
            tb.FontWeight = FontWeights.Bold
        if larghezza:
            tb.Width = larghezza
            tb.TextAlignment = TextAlignment.Right if destra else TextAlignment.Center
        Canvas.SetLeft(tb, x)
        Canvas.SetTop(tb, y)
        cnv.Children.Add(tb)

    def _disegna_prospetto(self, cnv, w, h, L, H):
        quote = AN.quote(self.schema, self.ris)
        n_alto = max([q[u"corsia"] + 1 for q in quote if q[u"lato"] == u"alto"] or [0])
        n_destra = max([q[u"corsia"] + 1 for q in quote if q[u"lato"] == u"destra"] or [0])
        contorno = AN.contorno_prospetto(self.ris)
        # ingombro: telaio piu' mostre e davanzali che escono dal foro
        bx0 = min([0.0] + [r[0] for r in contorno])
        bx1 = max([L] + [r[2] for r in contorno])
        bz0 = min([0.0] + [r[1] for r in contorno])
        bz1 = max([H] + [r[3] for r in contorno])
        pad_sx, pad_basso = MARGINE + CORSIA + 40, MARGINE + CORSIA + 22
        pad_alto, pad_dx = MARGINE + n_alto * CORSIA + 6, MARGINE + n_destra * (CORSIA + 26)
        disp_w, disp_h = w - pad_sx - pad_dx, h - pad_alto - pad_basso
        sc = min(disp_w / (bx1 - bx0), disp_h / (bz1 - bz0))
        if sc <= 0:
            return
        ox = pad_sx + (disp_w - (bx1 - bx0) * sc) / 2.0 - bx0 * sc
        oy = pad_alto + (disp_h + (bz1 - bz0) * sc) / 2.0 + bz0 * sc
        self._scala = (sc, ox, oy)
        limiti = (ox + bx0 * sc, ox + bx1 * sc, oy - bz1 * sc, oy - bz0 * sc)

        def rett(r, riempi, bordo=SCURO, spessore=0.8):
            x0, y0, x1, y1 = r[:4]
            self._rett(cnv, ox + x0 * sc, oy - y1 * sc, (x1 - x0) * sc, (y1 - y0) * sc, riempi, bordo, spessore)

        for tipo in ORDINE_CONTORNO:           # intorno al foro, sotto il telaio
            for r in contorno:
                if r[4] == tipo and tipo != u"muro":
                    rett(r, COLORI[tipo])
        pezzi = AN.pezzi_prospetto(self.ris, self.dettaglio)
        for tipo in ORDINE_DISEGNO:
            for pz in pezzi:
                if pz[u"tipo"] == tipo:
                    rett(G.rettangolo(self.ris, pz[u"esterni"]), COLORI[tipo])
        for r in contorno:                     # la mazzetta copre il bordo del telaio
            if r[4] == u"muro":
                rett(r, COLORI[u"muro"], GRIGIO)
        for s in self.ris[u"simboli"]:
            for seg in s[u"segmenti"]:
                self._linea(cnv, ox + seg[u"p0"][0] * sc, oy - seg[u"p0"][1] * sc,
                            ox + seg[u"p1"][0] * sc, oy - seg[u"p1"][1] * sc, tratteggio=True)
        if self.sel is not None and self.passo == 2:      # la zona scelta conta solo al passo Ante
            for c in self.ris[u"celle"]:
                if c[u"percorso"] == self.sel:
                    rett(G.rettangolo(self.ris, c[u"luce"]), u"#33E5862A", ARANCIO, 2.5)
        if self.evid is not None:
            try:
                ev = G.evidenzia(self.ris, self.schema, self.evid)
            except (IndexError, KeyError, TypeError):
                ev = {u"rettangoli": []}     # zona appena tolta: niente da illuminare
            for r in ev[u"rettangoli"]:
                rett(r, u"#661F6FB2", BLU, 2)
        for q in quote:
            self._quota(cnv, q, sc, ox, oy, L, H, limiti)

    def _quota(self, cnv, q, sc, ox, oy, L, H, limiti=None):
        """Una quota fuori dal disegno, sulla sua corsia; blu se e' quella del campo in uso.
        limiti: (sinistra, destra, alto, basso) in pixel di tutto il disegno (contorno compreso):
        le corsie partono da li', le linee di richiamo dal telaio."""
        attiva = self.evid is not None and tuple(self.evid) == tuple(q[u"chiave"])
        tinta, spessore = (BLU, 1.6) if attiva else (GRIGIO, 1.0)
        valore = u"%g" % q[u"valore"]
        lato, k = q[u"lato"], q[u"corsia"]
        l_sx, l_dx, l_alto, l_basso = limiti or (ox, ox + L * sc, oy - H * sc, oy)
        if lato in (u"basso", u"alto"):
            px0, px1 = ox + q[u"a"] * sc, ox + q[u"b"] * sc
            if lato == u"basso":
                bordo, py = oy, l_basso + 12 + k * CORSIA
            else:
                bordo, py = oy - H * sc, l_alto - 12 - k * CORSIA
            for px in (px0, px1):
                self._linea(cnv, px, bordo, px, py, CHIARO, 0.8)
                self._linea(cnv, px, py - 4, px, py + 4, tinta, spessore)
            self._linea(cnv, px0, py, px1, py, tinta, spessore)
            self._testo(cnv, valore, (px0 + px1) / 2.0 - 25, py - 17 if lato == u"alto" else py + 1,
                        tinta, attiva, larghezza=50)
        else:
            py0, py1 = oy - q[u"a"] * sc, oy - q[u"b"] * sc
            if lato == u"sinistra":
                bordo, px = ox, l_sx - 12 - k * CORSIA
            else:
                bordo, px = ox + L * sc, l_dx + 12 + k * (CORSIA + 26)
            for py in (py0, py1):
                self._linea(cnv, bordo, py, px, py, CHIARO, 0.8)
                self._linea(cnv, px - 4, py, px + 4, py, tinta, spessore)
            self._linea(cnv, px, py0, px, py1, tinta, spessore)
            if lato == u"sinistra":
                self._testo(cnv, valore, px - 46, (py0 + py1) / 2.0 - 8, tinta, attiva, larghezza=42, destra=True)
            else:
                self._testo(cnv, valore, px + 4, (py0 + py1) / 2.0 - 8, tinta, attiva)

    def _disegna_pianta(self, cnv, w, h, L):
        p = AN.pianta(self.schema, self.ris, self.dettaglio)
        y0, y1 = p[u"y"]
        alt = max(y1 - y0, 1.0)
        pad_sx, pad_dx, pad_alto, pad_basso = MARGINE + 10, MARGINE + 10, MARGINE + 18, MARGINE + CORSIA + 40
        disp_w, disp_h = w - pad_sx - pad_dx, h - pad_alto - pad_basso
        bx0 = min([0.0] + [r[0] for r in p[u"rettangoli"]])   # col muro ai lati
        bx1 = max([L] + [r[2] for r in p[u"rettangoli"]])
        sc = min(disp_w / (bx1 - bx0), disp_h / alt)
        if sc <= 0:
            return
        ox = pad_sx + (disp_w - (bx1 - bx0) * sc) / 2.0 - bx0 * sc
        oy = pad_alto + (disp_h + alt * sc) / 2.0     # pixel della y minima

        def X(x):
            return ox + x * sc

        def Y(y):
            return oy - (y - y0) * sc

        # asse del muro e lati
        self._linea(cnv, X(0) - 30, Y(0), X(L) + 30, Y(0), CHIARO, 1, tratteggio=True)
        self._testo(cnv, u"INTERNO", X(bx0), Y(y1) - 20, GRIGIO)
        self._testo(cnv, u"ESTERNO", X(bx0), Y(y0) + 4, GRIGIO)
        for tipo in ORDINE_CONTORNO + ORDINE_DISEGNO:
            for r in p[u"rettangoli"]:
                if r[4] == tipo:
                    self._rett(cnv, X(r[0]), Y(r[3]), (r[2] - r[0]) * sc, (r[3] - r[1]) * sc, COLORI[tipo])
        for a, b, tratt in p[u"linee"]:
            self._linea(cnv, X(a[0]), Y(a[1]), X(b[0]), Y(b[1]), SCURO, 1.2, tratt)
        for a, b, c, tratt in p[u"archi"]:
            self._arco(cnv, a, b, c, X, Y, tratt)
        # larghezza sotto
        q = {u"chiave": (u"larghezza",), u"lato": u"basso", u"corsia": 0, u"a": 0.0, u"b": L, u"valore": L}
        self._quota(cnv, q, sc, ox, Y(y0) + 14, L, 0.0)

    def _arco(self, cnv, a, b, c, X, Y, tratteggio):
        """Arco di centro c da a a b (il verso piu' corto), come spezzata."""
        r = math.hypot(a[0] - c[0], a[1] - c[1])
        t0 = math.atan2(a[1] - c[1], a[0] - c[0])
        t1 = math.atan2(b[1] - c[1], b[0] - c[0])
        d = t1 - t0
        while d > math.pi:
            d -= 2 * math.pi
        while d < -math.pi:
            d += 2 * math.pi
        punti = PointCollection()
        passi = 24
        for i in range(passi + 1):
            t = t0 + d * i / float(passi)
            punti.Add(Point(X(c[0] + r * math.cos(t)), Y(c[1] + r * math.sin(t))))
        pl = Polyline()
        pl.Points = punti
        pl.Stroke = colore(SCURO)
        pl.StrokeThickness = 1.2
        if tratteggio:
            pl.StrokeDashArray = _tratteggio()
        cnv.Children.Add(pl)

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
