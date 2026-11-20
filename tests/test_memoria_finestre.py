# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lib"))

import memoria_finestre as M  # noqa: E402


class Casella(object):
    def __init__(self, v=False):
        self.IsChecked = v


class Scelta(Casella):
    GroupName = u"g"


class Campo(object):
    def __init__(self, t=u""):
        self.Text = t


class Voce(object):
    def __init__(self, nome):
        self.Name = nome


class Elenco(object):
    def __init__(self, voci, i=0):
        self.Items = [Voce(v) for v in voci]
        self.SelectedIndex = i

    @property
    def SelectedItem(self):
        return self.Items[self.SelectedIndex] if 0 <= self.SelectedIndex < len(self.Items) else None


class Finestra(object):
    def __init__(self):
        self.chkA = Casella(True)
        self.rbSx = Scelta(False)
        self.rbDx = Scelta(True)
        self.txtOffset = Campo(u"150 cm")
        self.cmbTipo = Elenco([u"Terreno", u"Calcestruzzo", u"Vuoto"], 0)


NOMI = [u"chkA", u"rbSx", u"rbDx", u"txtOffset", u"cmbTipo"]


def test_salva_e_ripristina(tmp_path):
    p = str(tmp_path / u"sub" / u"finestre.json")
    w = Finestra()
    w.chkA.IsChecked = False
    w.txtOffset.Text = u"75 cm"
    w.cmbTipo.SelectedIndex = 1
    assert not M.ha_impostazioni(u"cmd", p)
    M.salva(w, u"cmd", NOMI, p)
    assert M.ha_impostazioni(u"cmd", p)

    nuova = Finestra()
    assert M.ripristina(nuova, u"cmd", NOMI, p)
    assert nuova.chkA.IsChecked is False
    assert nuova.rbDx.IsChecked is True
    assert nuova.txtOffset.Text == u"75 cm"
    assert nuova.cmbTipo.SelectedItem.Name == u"Calcestruzzo"


def test_scelta_spenta_non_viene_toccata():
    s = Scelta(True)
    assert not M.scrivi_controllo(s, False)
    assert s.IsChecked is True


def test_voce_sparita_lascia_la_predefinita():
    e = Elenco([u"A", u"B"], 1)
    assert not M.scrivi_controllo(e, u"Non esiste")
    assert e.SelectedIndex == 1


def test_comandi_separati_e_file_rovinato(tmp_path):
    p = str(tmp_path / u"finestre.json")
    with open(p, "w") as f:
        f.write("{non json")
    assert M.leggi_tutto(p) == {}
    w = Finestra()
    M.salva(w, u"uno", [u"chkA"], p)
    M.salva(w, u"due", [u"txtOffset"], p)
    assert M.impostazioni(u"uno", p) == {u"chkA": True}
    assert M.impostazioni(u"due", p) == {u"txtOffset": u"150 cm"}


def test_controlli_mancanti_ignorati(tmp_path):
    p = str(tmp_path / u"finestre.json")
    w = Finestra()
    M.salva(w, u"cmd", [u"chkA", u"nonEsiste"], p)
    assert M.impostazioni(u"cmd", p) == {u"chkA": True}
    assert M.ripristina(Finestra(), u"cmd", [u"chkA", u"nonEsiste"], p)


def test_testo_voce():
    class ConContent(object):
        Content = u"In colonna"
    assert M.testo_voce(ConContent()) == u"In colonna"
    assert M.testo_voce(u"x") == u"x"
