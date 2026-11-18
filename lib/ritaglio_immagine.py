# -*- coding: utf-8 -*-
"""Calcoli del Ritaglia Immagine, senza API Revit (testabili con pytest)."""


def rettangolo_pixel(x0, y0, x1, y1, scala, larghezza_px, altezza_px):
    """Converte il rettangolo trascinato in anteprima (unita' schermo) in pixel
    dell'immagine: ritorna (x, y, w, h) interi, dentro i bordi.
    scala = pixel immagine per unita' di anteprima."""
    sx0, sx1 = sorted((x0, x1))
    sy0, sy1 = sorted((y0, y1))
    x = max(0, min(larghezza_px, int(round(sx0 * scala))))
    y = max(0, min(altezza_px, int(round(sy0 * scala))))
    x2 = max(0, min(larghezza_px, int(round(sx1 * scala))))
    y2 = max(0, min(altezza_px, int(round(sy1 * scala))))
    if x2 - x < 2 or y2 - y < 2:
        raise ValueError(u"Area di ritaglio troppo piccola.")
    return x, y, x2 - x, y2 - y


def nuova_geometria(larghezza, altezza, larghezza_px, altezza_px, rett):
    """Dimensioni e spostamento del centro perche' la parte ritagliata resti
    dove si trova (come in Word). Ritorna (larghezza, altezza, dx, dy) nelle
    unita' di larghezza/altezza; dy positivo verso l'alto."""
    x, y, w, h = rett
    sx = float(larghezza) / larghezza_px
    sy = float(altezza) / altezza_px
    dx = (x + w / 2.0 - larghezza_px / 2.0) * sx
    dy = -(y + h / 2.0 - altezza_px / 2.0) * sy  # pixel: y verso il basso
    return w * sx, h * sy, dx, dy


def geometria_completa(larghezza, altezza, larghezza_px, altezza_px, rett):
    """Inverso di nuova_geometria: da un'immagine gia' ritagliata (dimensioni
    larghezza x altezza, ritaglio rett dell'originale) ricava le dimensioni
    dell'originale intero e lo spostamento (dx, dy) del centro del ritaglio
    rispetto al centro dell'originale."""
    x, y, w, h = rett
    piena_l = float(larghezza) * larghezza_px / w
    piena_a = float(altezza) * altezza_px / h
    _, _, dx, dy = nuova_geometria(piena_l, piena_a, larghezza_px, altezza_px, rett)
    return piena_l, piena_a, dx, dy


def nome_univoco(base, esistenti):
    """Primo nome '<base>_ritaglio_N' non presente in esistenti."""
    esistenti = set(n.lower() for n in esistenti)
    n = 1
    while True:
        nome = u"%s_ritaglio_%d" % (base, n)
        if nome.lower() not in esistenti:
            return nome
        n += 1
