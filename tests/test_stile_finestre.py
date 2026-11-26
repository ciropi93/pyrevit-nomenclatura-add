# -*- coding: utf-8 -*-
import glob
import io
import os
import re
import sys
import xml.dom.minidom

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(QUI, "..", "lib"))

import stile_finestre as SF  # noqa: E402

TAB = os.path.join(QUI, "..", "CDV Tools.tab")
FINESTRE = sorted(glob.glob(os.path.join(TAB, "*", "*", "ui.xaml"))
                  + glob.glob(os.path.join(TAB, "*", "*", "*", "ui.xaml")))

BASE = (u'<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation" '
        u'xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml" Title="T">%s<Grid/></Window>')


def _leggi(p):
    with io.open(p, encoding="utf-8-sig") as f:
        return f.read()


def test_risorse_inserite_e_xml_valido():
    for interno in (u"", u'<Window.Resources><Style TargetType="Button"/></Window.Resources>'):
        out = SF.prepara_xaml(BASE % interno)
        xml.dom.minidom.parseString(out.encode("utf-8"))
        assert out.count(u"<Window.Resources>") == 1
        assert u'x:Key="Primario"' in out


def test_converti_colori():
    assert SF.converti_colori(u'Background="#0284c7" Foreground="#DC2626"') == \
        u'Background="%s" Foreground="#DC2626"' % SF.BLU


def test_ci_sono_finestre():
    assert len(FINESTRE) >= 5  # le finestre "scegli da un elenco" sono una sola, in lib


def test_finestre_usano_lo_stile_condiviso():
    """Nessuna finestra ridefinisce gli stili; ogni chiave usata esiste nello stile comune."""
    chiavi = set(re.findall(u'x:Key="([^"]+)"', SF.RISORSE))
    for p in FINESTRE:
        t = _leggi(p)
        assert u"<Window.Resources>" not in t, p
        for k in re.findall(u"StaticResource (\\w+)", t):
            assert k in chiavi, (p, k)
        out = SF.prepara_xaml(t)
        xml.dom.minidom.parseString(out.encode("utf-8"))


def test_finestre_senza_vecchi_colori_ne_emoji():
    vecchi = set(SF.CONVERSIONE_COLORI)
    for p in FINESTRE:
        t = _leggi(p)
        for c in re.findall(u"#[0-9A-Fa-f]{6}\\b", t):
            assert c.upper() not in vecchi, (p, c)
        assert not re.search(u"[\U0001F300-\U0001FAFF←-⇿⬅-⬇️]", t), p
        assert u"CDV Tools" not in t, p


def test_script_caricano_lo_stile():
    for p in FINESTRE:
        s = _leggi(os.path.join(os.path.dirname(p), "script.py"))
        assert u"SF.xaml(" in s and u"literal_string=True" in s, p


def test_finestre_in_lib_usano_lo_stile_condiviso():
    """Anche le finestre in lib/ (scelta, configuratore infissi) senza stili propri ne' vecchi colori."""
    lib = os.path.join(QUI, "..", "lib")
    finestre = sorted(glob.glob(os.path.join(lib, "*.xaml")) + glob.glob(os.path.join(lib, "*", "*.xaml")))
    assert len(finestre) >= 2
    chiavi = set(re.findall(u'x:Key="([^"]+)"', SF.RISORSE))
    vecchi = set(SF.CONVERSIONE_COLORI)
    for p in finestre:
        t = _leggi(p)
        assert u"<Window.Resources>" not in t, p
        assert u"CDV Tools" not in t, p
        for k in re.findall(u"StaticResource (\\w+)", t):
            assert k in chiavi, (p, k)
        for c in re.findall(u"#[0-9A-Fa-f]{6}\\b", t):
            assert c.upper() not in vecchi, (p, c)
        xml.dom.minidom.parseString(SF.prepara_xaml(t).encode("utf-8"))
