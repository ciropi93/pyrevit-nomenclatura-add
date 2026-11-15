# -*- coding: utf-8 -*-
"""Avviso piccolo in basso a destra nella vista (senza API Revit ne' WPF).

Al posto delle notifiche di Windows e delle finestre con OK: una riga di testo con un
simbolo colorato, senza riquadro, nell'angolo in basso a destra della vista attiva.
Sparisce da sola; un messaggio nuovo sostituisce il vecchio e lo stesso messaggio
ripetuto mostra un contatore ("x3"). La finestra sta in avviso_wpf.py.
"""

INFO = u"info"
ATTENZIONE = u"attenzione"
ERRORE = u"errore"

# livello -> (simbolo, colore)
STILI = {
    INFO: (u"✓", u"#2563EB"),        # spunta blu
    ATTENZIONE: (u"!", u"#D97706"),       # punto esclamativo arancio
    ERRORE: (u"✕", u"#DC2626"),      # croce rossa
}
COLORE_TESTO = u"#334155"

DURATE_MS = {INFO: 2500, ATTENZIONE: 3500, ERRORE: 4000}
DISSOLVENZA_MS = 300
LARGHEZZA_MAX = 360       # unita' WPF: oltre, il testo finisce con "..."
MARGINE = 10              # dai bordi della vista


def livello_valido(livello):
    return livello if livello in STILI else INFO


def durata_avviso(livello):
    """Millisecondi in cui l'avviso resta pieno prima di sfumare."""
    return DURATE_MS[livello_valido(livello)]


def una_riga(testo):
    """Il testo su una riga: gli a capo diventano " · ", spazi doppi tolti."""
    if testo is None:
        return u""
    if not isinstance(testo, type(u"")):
        try:
            testo = testo.decode("utf-8")
        except Exception:
            testo = u"%s" % (testo,)
    righe = [u" ".join(r.split()) for r in testo.splitlines()]
    return u" · ".join(r for r in righe if r)


def testo_con_contatore(testo, ripetizioni):
    """"Mezzitoni attivati" ripetuto 3 volte -> "Mezzitoni attivati  ×3"."""
    if ripetizioni and ripetizioni > 1:
        return u"%s  ×%d" % (testo, ripetizioni)
    return testo


def con_errori(msg, errori, max_errori=2):
    """Esito con errori parziali su una riga: "msg · 3 con errori: a; b; ..."."""
    errori = [una_riga(e) for e in (errori or []) if e]
    if not errori:
        return una_riga(msg)
    elenco = u"; ".join(errori[:max_errori])
    if len(errori) > max_errori:
        elenco += u"; …"
    testo = u"%d con errori: %s" % (len(errori), elenco)
    msg = una_riga(msg)
    return u"%s · %s" % (msg, testo) if msg else testo


def posizione_avviso(rett_vista, larghezza, altezza, margine=MARGINE):
    """Angolo in alto a sinistra dell'avviso: in basso a destra della vista.

    rett_vista: (sinistra, alto, destra, basso) della vista, stesse unita' di larghezza e
    altezza. Se la vista e' piu' piccola dell'avviso, l'avviso parte dal suo bordo
    sinistro/alto (resta comunque attaccato alla vista).
    """
    sx, alto, dx, basso = rett_vista
    x = dx - margine - larghezza
    y = basso - margine - altezza
    return max(x, sx), max(y, alto)
