# -*- coding: utf-8 -*-
import io
import os
import sys
import xml.dom.minidom

QUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(QUI, "..", "lib"))

import scelta as S  # noqa: E402
import stile_finestre as SF  # noqa: E402


def test_testo_pulsante():
    assert S.testo_pulsante(1, u"Copia su 1 vista", u"Copia su %d viste") == u"Copia su 1 vista"
    assert S.testo_pulsante(3, u"Copia su 1 vista", u"Copia su %d viste") == u"Copia su 3 viste"
    assert S.testo_pulsante(0, u"a", u"Copia su %d viste", u"Scegli le viste") == u"Scegli le viste"


def test_corrisponde():
    assert S.corrisponde(u"", u"qualsiasi")
    assert S.corrisponde(u"piano pri", u"Pianta Piano Primo", u"Piano Primo")
    assert S.corrisponde(u"PRIMO", u"Pianta Piano Primo")
    assert not S.corrisponde(u"terra", u"Pianta Piano Primo", u"Piano Primo")
    assert S.corrisponde(u"pianta terra", u"Pianta", u"Piano Terra")


def test_testo_tutte():
    assert S.testo_tutte(0, 3) == u"Seleziona tutte"
    assert S.testo_tutte(3, 3) == u"Deseleziona tutte"
    assert S.testo_tutte(0, 0) == u"Seleziona tutte"


def test_xaml_della_finestra_valido():
    with io.open(os.path.join(QUI, "..", "lib", "scelta.xaml"), encoding="utf-8") as f:
        t = f.read()
    assert u"<Window.Resources>" not in t
    xml.dom.minidom.parseString(SF.prepara_xaml(t).encode("utf-8"))
