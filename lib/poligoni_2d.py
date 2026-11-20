# -*- coding: utf-8 -*-
"""Differenza tra regioni 2D (senza API Revit), per le campiture di sezione.

Una regione e' una lista di facce; una faccia e' una lista di anelli [(u, v), ...]
(contorno e fori, regola pari/dispari). Le facce di una regione si sommano (unione).

Metodo a fasce verticali: il piano si divide in fasce a ogni vertice e incrocio di lati;
in ogni fascia le regioni sono intervalli tra lati rettilinei, e la differenza diventa
una differenza tra intervalli. Regge i lati coincidenti (es. bordo superiore comune tra
pavimento esistente e di progetto), dove le operazioni booleane di Revit falliscono.
"""
import bisect
import math

EPS = 1e-6           # piedi: tolleranza numerica
SPESSORE_MIN = 3e-3  # piedi (~1 mm): pezzi o vertici piu' vicini si scartano (schegge)


def _lati(faccia):
    """Lati non verticali della faccia, orientati da sinistra a destra."""
    out = []
    for anello in faccia:
        for i in range(len(anello)):
            a, b = anello[i], anello[(i + 1) % len(anello)]
            if abs(a[0] - b[0]) > EPS:
                out.append((a, b) if a[0] < b[0] else (b, a))
    return out


def _v(lato, x):
    (u0, v0), (u1, v1) = lato
    return v0 + (v1 - v0) * (x - u0) / (u1 - u0)


def _incrocio(l1, l2):
    """Ascissa in cui i due lati si incrociano (strettamente), oppure None."""
    lo, hi = max(l1[0][0], l2[0][0]), min(l1[1][0], l2[1][0])
    if hi - lo <= EPS:
        return None
    d_lo, d_hi = _v(l1, lo) - _v(l2, lo), _v(l1, hi) - _v(l2, hi)
    if d_lo * d_hi >= 0:
        return None
    return lo + (hi - lo) * d_lo / (d_lo - d_hi)


def _m(bordo):
    """Quota media (x2) di un bordo (v a sinistra, v a destra) nella fascia."""
    return bordo[0] + bordo[1]


def _intervalli(lati, x0, x1):
    """Parti piene di una faccia nella fascia [x0, x1]: lista di (basso, alto)."""
    bordi = sorted(((_v(l, x0), _v(l, x1)) for l in lati
                    if l[0][0] <= x0 + EPS and l[1][0] >= x1 - EPS), key=_m)
    return [(bordi[i], bordi[i + 1]) for i in range(0, len(bordi) - 1, 2)]


def _unisci(intervalli):
    out = []
    for lo, hi in sorted(intervalli, key=lambda p: _m(p[0])):
        if out and _m(lo) <= _m(out[-1][1]) + 2 * SPESSORE_MIN:
            if _m(hi) > _m(out[-1][1]):
                out[-1] = (out[-1][0], hi)
        else:
            out.append((lo, hi))
    return out


def _sottrai(a, b):
    out = []
    for pezzo in a:
        pezzi = [pezzo]
        for blo, bhi in b:
            nuovi = []
            for plo, phi in pezzi:
                if _m(bhi) <= _m(plo) or _m(blo) >= _m(phi):
                    nuovi.append((plo, phi))
                    continue
                if _m(blo) > _m(plo):
                    nuovi.append((plo, blo))
                if _m(bhi) < _m(phi):
                    nuovi.append((bhi, phi))
            pezzi = nuovi
        out.extend(p for p in pezzi if max(p[1][0] - p[0][0], p[1][1] - p[0][1]) > SPESSORE_MIN)
    return out


def _meno_1d(a, b):
    """Parti degli intervalli a (lo, hi) non coperte da b."""
    out = []
    for pezzo in a:
        pezzi = [pezzo]
        for blo, bhi in b:
            nuovi = []
            for lo, hi in pezzi:
                if bhi <= lo or blo >= hi:
                    nuovi.append((lo, hi))
                    continue
                if blo - lo > EPS:
                    nuovi.append((lo, blo))
                if hi - bhi > EPS:
                    nuovi.append((bhi, hi))
            pezzi = nuovi
        out.extend(pezzi)
    return out


class _Vertici(object):
    """Fonde i punti piu' vicini della tolleranza in un solo vertice."""

    def __init__(self, tol=1e-4):
        self.tol, self.celle, self.punti = tol, {}, []

    def id(self, p):
        cx, cy = int(round(p[0] / self.tol)), int(round(p[1] / self.tol))
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for i in self.celle.get((cx + dx, cy + dy), ()):
                    q = self.punti[i]
                    if abs(q[0] - p[0]) <= self.tol and abs(q[1] - p[1]) <= self.tol:
                        return i
        self.punti.append(p)
        self.celle.setdefault((cx, cy), []).append(len(self.punti) - 1)
        return len(self.punti) - 1


def _segmenti(trapezi):
    """Contorno dei trapezi, orientato con l'interno a sinistra; i lati interni si annullano."""
    seg, sx, dx = [], {}, {}
    for x0, x1, lo, hi in trapezi:
        seg.append(((x0, lo[0]), (x1, lo[1])))
        seg.append(((x1, hi[1]), (x0, hi[0])))
        sx.setdefault(x0, []).append((lo[0], hi[0]))
        dx.setdefault(x1, []).append((lo[1], hi[1]))
    for x in set(sx) | set(dx):
        for lo, hi in _meno_1d(sx.get(x, []), dx.get(x, [])):
            seg.append(((x, hi), (x, lo)))
        for lo, hi in _meno_1d(dx.get(x, []), sx.get(x, [])):
            seg.append(((x, lo), (x, hi)))
    return seg


def _anelli(seg):
    """Concatena i segmenti orientati in anelli chiusi (svolta piu' a sinistra ai vertici multipli: ogni pezzo resta un anello semplice)."""
    vert = _Vertici()
    archi = [(vert.id(a), vert.id(b)) for a, b in seg]
    archi = [ab for ab in archi if ab[0] != ab[1]]
    uscite = {}
    for k, (a, b) in enumerate(archi):
        uscite.setdefault(a, []).append(k)
    P = vert.punti
    usati, anelli = set(), []
    for k0 in range(len(archi)):
        if k0 in usati:
            continue
        usati.add(k0)
        inizio, cur = archi[k0]
        prev, anello = inizio, [inizio]
        while cur != inizio:
            anello.append(cur)
            cand = [k for k in uscite.get(cur, ()) if k not in usati]
            if not cand:
                break
            d_in = (P[cur][0] - P[prev][0], P[cur][1] - P[prev][1])

            def svolta(k):
                n = P[archi[k][1]]
                d = (n[0] - P[cur][0], n[1] - P[cur][1])
                return math.atan2(d_in[0] * d[1] - d_in[1] * d[0], d_in[0] * d[0] + d_in[1] * d[1])
            k = max(cand, key=svolta)
            usati.add(k)
            prev, cur = cur, archi[k][1]
        if cur == inizio:
            anelli.append(_semplifica([P[i] for i in anello]))
    return [a for a in anelli if len(a) >= 3 and abs(area(a)) > SPESSORE_MIN ** 2]


def _semplifica(anello):
    """Toglie vertici allineati o troppo vicini al precedente."""
    cambiato = True
    while cambiato and len(anello) >= 3:
        cambiato = False
        for i in range(len(anello)):
            a, b, c = anello[i - 1], anello[i], anello[(i + 1) % len(anello)]
            ab = ((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) ** 0.5
            ac = ((c[0] - a[0]) ** 2 + (c[1] - a[1]) ** 2) ** 0.5
            croce = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
            if ab < SPESSORE_MIN or (ac > EPS and abs(croce) / ac < EPS * 10):
                del anello[i]
                cambiato = True
                break
    return anello


def area(anello):
    """Area con segno (positiva se antioraria)."""
    n = len(anello)
    return sum(anello[i - 1][0] * anello[i][1] - anello[i][0] * anello[i - 1][1] for i in range(n)) / 2.0


def _dentro(p, anello):
    c = False
    for i in range(len(anello)):
        (x0, y0), (x1, y1) = anello[i - 1], anello[i]
        if (y0 > p[1]) != (y1 > p[1]) and p[0] < x0 + (p[1] - y0) * (x1 - x0) / (y1 - y0):
            c = not c
    return c


def _facce(anelli):
    """Raggruppa: contorni (antiorari) con i loro fori (orari)."""
    contorni = sorted((a for a in anelli if area(a) > 0), key=area)
    facce = [[c] for c in contorni]
    for foro in (a for a in anelli if area(a) < 0):
        mezzo = ((foro[0][0] + foro[1][0]) / 2.0, (foro[0][1] + foro[1][1]) / 2.0)
        for f in facce:
            if _dentro(mezzo, f[0]):
                f.append(foro)
                break
    return facce


def _aggancia(xs):
    """Ascisse piu' vicine di SPESSORE_MIN -> stesso valore (niente fasce sottilissime)."""
    mappa, rif = {}, None
    for x in sorted(xs):
        if rif is None or x - rif > SPESSORE_MIN:
            rif = x
        mappa[x] = rif
    return mappa


def differenza(a, b):
    """Regione a meno regione b (b vuota = unione delle facce di a). Ritorna facce [contorno, fori...]."""
    mappa = _aggancia(set(p[0] for f in a + b for anello in f for p in anello))
    a, b = [[[[(mappa[p[0]], p[1]) for p in anello] for anello in f] for f in r] for r in (a, b)]
    la, lb = [_lati(f) for f in a], [_lati(f) for f in b]
    tutti = [l for ls in la + lb for l in ls]
    xs = sorted(set(mappa.values()))
    for i in range(len(tutti)):
        for j in range(i + 1, len(tutti)):
            x = _incrocio(tutti[i], tutti[j])
            k = bisect.bisect(xs, x) if x is not None else None
            if k is not None and all(abs(x - xs[m]) > SPESSORE_MIN for m in (k - 1, k) if 0 <= m < len(xs)):
                xs.insert(k, x)
    trapezi = []
    for x0, x1 in zip(xs, xs[1:]):
        if x1 - x0 <= EPS:
            continue
        pieno = _unisci([iv for ls in la for iv in _intervalli(ls, x0, x1)])
        if not pieno:
            continue
        vuoto = _unisci([iv for ls in lb for iv in _intervalli(ls, x0, x1)])
        trapezi.extend((x0, x1, lo, hi) for lo, hi in _sottrai(pieno, vuoto))
    return _facce(_anelli(_segmenti(trapezi)))
