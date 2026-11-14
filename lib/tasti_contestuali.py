# -*- coding: utf-8 -*-
"""Quali tasti mostrare nel pannello in sovraimpressione (senza API Revit).

In tavola, cliccando il titolo di una vista si seleziona il suo riquadro (Viewport),
quindi "viste" e "titoli" selezionati sono la stessa cosa: si contano le viste.
Il riquadro di sfondo di una sezione conta come la sua sezione madre.
"""

SEZIONE_APRI = u"sezione_apri"
SEZIONE_SINCRONIZZA = u"sezione_sincronizza"
MURO_INVERTI = u"muro_inverti_centro"

# (comando, etichetta, suggerimento)
_SEZIONE = [
    (SEZIONE_APRI, u"Profondità sezione", u"Apri Profondità Sezione su questa sezione"),
    (SEZIONE_SINCRONIZZA, u"Sincronizza sfondo",
     u"Riallinea sfondo e tavole alla sezione madre (annullabile)"),
]

# Sezione o prospetto senza sfondo: solo il tasto per attivarlo
_SEZIONE_DA_ATTIVARE = [
    (SEZIONE_APRI, u"Attiva profondità sezione",
     u"Apri Profondità Sezione su questa vista per creare lo sfondo"),
]

# Uno o piu' muri selezionati
_MURI = [
    (MURO_INVERTI, u"Inverti muro sul centro",
     u"Scambia esterno e interno tenendo fermo l'asse del muro (annullabile).\n"
     u"Maiusc+clic: linea di ubicazione su Asse del muro"),
]

_TITOLO_SINGOLO = [
    (u"titolo_bordo_sinistro", u"A filo del ritaglio",
     u"Porta il titolo sul bordo sinistro del ritaglio della vista"),
    (u"titolo_larghezza_vista", u"Linea = larghezza ritaglio",
     u"Linea del titolo lunga quanto il ritaglio della vista"),
]

_TITOLI_MULTI = [
    (u"titolo_colonna", u"Incolonna (X)",
     u"Titoli sulla stessa verticale (riferimento: la vista più a sinistra)"),
    (u"titolo_riga", u"In riga (Y)",
     u"Titoli sulla stessa orizzontale (riferimento: la vista più in basso)"),
    (u"titolo_distanza_y", u"Stessa distanza",
     u"Stessa distanza verticale tra titolo e fondo del ritaglio (riferimento: la vista più in basso)"),
    (u"titolo_lunghezza_rif", u"Stessa linea",
     u"Stessa lunghezza della linea del titolo (riferimento scelto in automatico)"),
]

_VISTE = [
    (u"box_sinistra", u"Sinistra", u"Allinea il bordo sinistro dei ritagli (riferimento: la vista più a sinistra)"),
    (u"box_centro_x", u"Centro X", u"Allinea il centro orizzontale dei ritagli"),
    (u"box_destra", u"Destra", u"Allinea il bordo destro dei ritagli (riferimento: la vista più a destra)"),
    (u"box_modello_x", u"Modello X", u"Allinea le viste sulle stesse coordinate del modello (X)"),
    (u"box_alto", u"Alto", u"Allinea il bordo superiore dei ritagli (riferimento: la vista più in alto)"),
    (u"box_centro_y", u"Centro Y", u"Allinea il centro verticale dei ritagli"),
    (u"box_basso", u"Basso", u"Allinea il bordo inferiore dei ritagli (riferimento: la vista più in basso)"),
    (u"box_modello_y", u"Modello Y", u"Allinea le viste sulle stesse coordinate del modello (Y / quote)"),
]

_DISTRIBUISCI = [
    (u"distribuisci_x", u"Orizzontale", u"Stessa distanza tra le viste in orizzontale (le estreme restano ferme)"),
    (u"distribuisci_y", u"Verticale", u"Stessa distanza tra le viste in verticale (le estreme restano ferme)"),
]


def viste_distinte(id_viste, sfondo_a_madre):
    """Id delle viste selezionate, con lo sfondo sostituito dalla sua madre, senza doppioni."""
    out = []
    for v in id_viste:
        m = sfondo_a_madre.get(v, v)
        if m not in out:
            out.append(m)
    return out


def comandi_per_selezione(n_viste, in_tavola=True, sezione_con_sfondo=False,
                          sezione_senza_sfondo=False, n_muri=0):
    """Gruppi di tasti da mostrare: lista di (titolo_gruppo, [(comando, etichetta, suggerimento)]).

    sezione_senza_sfondo: la vista selezionata e' una sezione/prospetto su cui
    Profondita' Sezione non e' ancora attivo (si propone di attivarlo).
    n_muri: muri selezionati (la selezione e' fatta solo di muri).
    """
    gruppi = []
    if n_muri >= 1:
        gruppi.append((u"Muri", list(_MURI)))
    if sezione_con_sfondo and n_viste == 1:
        gruppi.append((u"Sezione", list(_SEZIONE)))
    elif sezione_senza_sfondo and n_viste == 1:
        gruppi.append((u"Sezione", list(_SEZIONE_DA_ATTIVARE)))
    if in_tavola and n_viste == 1:
        gruppi.append((u"Titolo", list(_TITOLO_SINGOLO)))
    if in_tavola and n_viste >= 2:
        gruppi.append((u"Titoli", list(_TITOLI_MULTI) + list(_TITOLO_SINGOLO)))
        gruppi.append((u"Allinea viste", list(_VISTE)))
    if in_tavola and n_viste >= 3:
        gruppi.append((u"Distribuisci", list(_DISTRIBUISCI)))
    return gruppi


# ==============================================================================
# ICONE (tracciati WPF in un quadrato 16x16) E POSIZIONE DEI TASTINI
# ==============================================================================

# Geometrie in sintassi "Path Markup" di WPF. F1 = riempimento pieno anche dove le
# forme si sovrappongono; senza F1 (pari/dispari) un rettangolo dentro l'altro fa un buco.
ICONE = {
    SEZIONE_APRI: u"F1 M1,2 H3 V14 H1 Z M4,7 H10 V4 L15,8 L10,12 V9 H4 Z",
    SEZIONE_SINCRONIZZA: (u"F1 M8,2 A6,6 0 1 0 14,8 H12 A4,4 0 1 1 8,4 V6.5 "
                          u"L11.5,3 L8,-0.5 Z"),
    u"titolo_bordo_sinistro": (u"M1,1 H15 V9 H1 Z M2.5,2.5 V7.5 H13.5 V2.5 Z "
                               u"M1,11 H9 V12.5 H1 Z M1,14 H11 V15 H1 Z"),
    u"titolo_larghezza_vista": (u"M1,1 H15 V9 H1 Z M2.5,2.5 V7.5 H13.5 V2.5 Z "
                                u"M1,11 H8 V12.5 H1 Z M1,14 H15 V15.5 H1 Z"),
    u"titolo_colonna": (u"M1,1 H2.5 V15 H1 Z M4,3 H10 V4.5 H4 Z M4,5.5 H14 V6.5 H4 Z "
                        u"M4,10 H10 V11.5 H4 Z M4,12.5 H12 V13.5 H4 Z"),
    u"titolo_riga": (u"M1,13.5 H15 V15 H1 Z M1,8 H5.5 V9.5 H1 Z M1,10.5 H7 V11.5 H1 Z "
                     u"M9,8 H13.5 V9.5 H9 Z M9,10.5 H15 V11.5 H9 Z"),
    u"titolo_distanza_y": (u"M1,1 H7 V8 H1 Z M2.2,2.2 V6.8 H5.8 V2.2 Z "
                           u"M9,1 H15 V8 H9 Z M10.2,2.2 V6.8 H13.8 V2.2 Z "
                           u"M1,12.5 H7 V14 H1 Z M9,12.5 H15 V14 H9 Z"),
    u"titolo_lunghezza_rif": u"F1 M1,4 H12 V5.5 H1 Z M1,10.5 H12 V12 H1 Z M12.5,2 H14 V14 H12.5 Z",
    u"box_sinistra": u"F1 M1,1 H2.5 V15 H1 Z M4,3 H14 V7 H4 Z M4,9 H10 V13 H4 Z",
    u"box_centro_x": u"F1 M7.25,1 H8.75 V15 H7.25 Z M2,3 H14 V7 H2 Z M4,9 H12 V13 H4 Z",
    u"box_destra": u"F1 M13.5,1 H15 V15 H13.5 Z M2,3 H12 V7 H2 Z M6,9 H12 V13 H6 Z",
    u"box_modello_x": (u"F1 M7.25,1 H8.75 V15 H7.25 Z M5.6,4 A2.4,2.4 0 1 1 10.4,4 "
                       u"A2.4,2.4 0 1 1 5.6,4 Z M5.6,12 A2.4,2.4 0 1 1 10.4,12 "
                       u"A2.4,2.4 0 1 1 5.6,12 Z"),
    u"box_alto": u"F1 M1,1 V2.5 H15 V1 Z M3,4 V14 H7 V4 Z M9,4 V10 H13 V4 Z",
    u"box_centro_y": u"F1 M1,7.25 V8.75 H15 V7.25 Z M3,2 V14 H7 V2 Z M9,4 V12 H13 V4 Z",
    u"box_basso": u"F1 M1,13.5 V15 H15 V13.5 Z M3,2 V12 H7 V2 Z M9,6 V12 H13 V6 Z",
    u"box_modello_y": (u"F1 M1,7.25 V8.75 H15 V7.25 Z M4,5.6 A2.4,2.4 0 1 1 4,10.4 "
                       u"A2.4,2.4 0 1 1 4,5.6 Z M12,5.6 A2.4,2.4 0 1 1 12,10.4 "
                       u"A2.4,2.4 0 1 1 12,5.6 Z"),
    u"distribuisci_x": u"F1 M1,3 H4 V13 H1 Z M6.5,3 H9.5 V13 H6.5 Z M12,3 H15 V13 H12 Z",
    u"distribuisci_y": u"F1 M3,1 V4 H13 V1 Z M3,6.5 V9.5 H13 V6.5 Z M3,12 V15 H13 V12 Z",
    # asse fisso al centro, frecce opposte ai due lati
    MURO_INVERTI: (u"F1 M7.25,1 H8.75 V15 H7.25 Z M1,4.5 L4,1.5 V3.5 H6 V5.5 H4 V7.5 Z "
                   u"M15,11.5 L12,8.5 V10.5 H10 V12.5 H12 V14.5 Z"),
}


def proietta(punto_uv, zoom_uv, finestra):
    """Punto in coordinate della vista (u, v) -> pixel sullo schermo (x, y).

    zoom_uv: ((u0, v0), (u1, v1)) angoli in basso a sinistra e in alto a destra
    dell'area visibile; finestra: (sinistra, alto, destra, basso) in pixel.
    """
    (u0, v0), (u1, v1) = zoom_uv
    sx, alto, dx, basso = finestra
    du = (u1 - u0) or 1e-9
    dv = (v1 - v0) or 1e-9
    x = sx + (punto_uv[0] - u0) / du * (dx - sx)
    y = basso - (punto_uv[1] - v0) / dv * (basso - alto)
    return x, y


def riquadro_schermo(punti_uv, zoom_uv, finestra):
    """Rettangolo (sinistra, alto, destra, basso) in pixel che contiene tutti i punti."""
    if not punti_uv:
        return None
    pts = [proietta(p, zoom_uv, finestra) for p in punti_uv]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def posizione_striscia(riquadro, finestra, larghezza, altezza, distacco=3):
    """Angolo in alto a sinistra (x, y) della fila di tastini, in pixel.

    La fila sta appena sopra il bordo superiore della selezione, allineata al suo
    bordo sinistro; se sopra non c'e' posto va sotto, altrimenti dentro in alto.
    Ritorna None se la selezione e' fuori dall'area visibile della vista.
    """
    if riquadro is None:
        return None
    r_sx, r_alto, r_dx, r_basso = riquadro
    f_sx, f_alto, f_dx, f_basso = finestra
    if r_dx < f_sx or r_sx > f_dx or r_basso < f_alto or r_alto > f_basso:
        return None
    x = max(r_sx, f_sx)
    x = max(min(x, f_dx - larghezza), f_sx)
    y = r_alto - altezza - distacco
    if y < f_alto:
        y = r_basso + distacco
        if y + altezza > f_basso:
            y = max(r_alto, f_alto) + distacco
    return x, y


# ==============================================================================
# LETTERE E / I AI LATI DEI MURI SELEZIONATI
# ==============================================================================

# Valori di "Linea di ubicazione" (WALL_KEY_REF_PARAM / WallLocationLine)
ASSE_MURO, ASSE_NUCLEO, FINITURA_EST, FINITURA_INT, NUCLEO_EST, NUCLEO_INT = range(6)


def offset_linea_ubicazione(codice, spessore, strati=None, primo_nucleo=-1, ultimo_nucleo=-1):
    """Distanza della linea di ubicazione dall'asse del muro, positiva verso l'esterno.

    La curva di un muro in Revit sta sulla linea di ubicazione, non sempre sull'asse:
    serve per ritrovare il centro. strati: spessori dall'esterno verso l'interno;
    primo/ultimo_nucleo: indici del nucleo (-1 se non c'e').
    """
    tot = float(sum(strati)) if strati and sum(strati) > 0 else float(spessore or 0.0)
    meta = tot / 2.0
    if codice == FINITURA_EST:
        return meta
    if codice == FINITURA_INT:
        return -meta
    if codice in (ASSE_NUCLEO, NUCLEO_EST, NUCLEO_INT):
        if (not strati or primo_nucleo is None or primo_nucleo < 0
                or ultimo_nucleo < primo_nucleo or ultimo_nucleo >= len(strati)):
            est, int_ = meta, -meta
        else:
            est = meta - sum(strati[:primo_nucleo])
            int_ = meta - sum(strati[:ultimo_nucleo + 1])
        if codice == NUCLEO_EST:
            return est
        if codice == NUCLEO_INT:
            return int_
        return (est + int_) / 2.0
    return 0.0


def posizioni_lati(centro, verso_esterno, mezzo_spessore, distacco=9.0):
    """Punti sullo schermo (pixel) dove scrivere E e I: ((xE, yE), (xI, yI)) oppure None.

    centro: asse del muro proiettato; verso_esterno: proiezione del punto a 1 unita'
    dal centro verso il lato esterno; mezzo_spessore nella stessa unita'.
    Le lettere stanno appena fuori dalle due facce, a 'distacco' pixel.
    None se il muro e' visto di fronte (esterno e interno cadono nello stesso punto).
    """
    dx = verso_esterno[0] - centro[0]
    dy = verso_esterno[1] - centro[1]
    lung = (dx * dx + dy * dy) ** 0.5
    if lung < 1e-6:
        return None
    ux, uy = dx / lung, dy / lung
    d = mezzo_spessore * lung + distacco
    return ((centro[0] + ux * d, centro[1] + uy * d),
            (centro[0] - ux * d, centro[1] - uy * d))
