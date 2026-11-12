# -*- coding: utf-8 -*-
"""Suggerimento del nome e controlli incrociati nome <-> dati del tipo.

Lavora su un dizionario di dati semplici (preparato da revit_dati.dati_tipo),
cosi' si testa senza Revit. Chiavi usate:
    bic          categoria Revit, es. 'OST_Walls'
    nome         nome attuale del tipo
    funzione     'EST' / 'INT' / None (funzione del muro)
    strati       lista di {'materiale': nome materiale, 'spessore': mm}
                 in ordine esterno -> interno (muri) o alto -> basso (solai)
    spessore     spessore totale in mm
    larghezza, altezza   mm (porte, finestre)
"""
import re

from nomenclatura import regole as R

# Codice funzione tipo (e sottotipo) suggerito per categoria Revit
CODICE_CATEGORIA = {
    "OST_Walls": ("MUR", None),
    "OST_Floors": ("SOL", None),
    "OST_Roofs": ("SOL", "TET"),
    "OST_Ceilings": ("FNT", "SOF"),
    "OST_Doors": ("POR", None),
    "OST_Windows": ("FIN", None),
    "OST_Columns": ("CLN", None),
    "OST_StructuralColumns": ("CLN", None),
    "OST_StructuralFraming": ("TRV", None),
    "OST_StructuralFoundation": ("FON", None),
    "OST_Railings": ("CRR", None),
    "OST_StairsRailing": ("CRR", None),
    "OST_Stairs": ("SCA", None),
    "OST_Ramps": ("RMP", None),
    "OST_Planting": ("VEG", None),
    "OST_Furniture": ("ARR", None),
    "OST_Casework": ("ARR", None),
    "OST_GenericModel": ("GEN", None),
}

STRATIFICATI = ("OST_Walls", "OST_Floors", "OST_Roofs", "OST_Ceilings")
APERTURE = ("OST_Doors", "OST_Windows")

# Classe materiale Revit -> categoria Tab. 27
CLASSE_MATERIALE = {
    "concrete": "CLC", "calcestruzzo": "CLC", "cls": "CLC",
    "masonry": "MRT", "muratura": "MRT",
    "metal": "MTL", "metallo": "MTL",
    "wood": "LGN", "legno": "LGN",
    "glass": "VTR", "vetro": "VTR",
    "plastic": "PLS", "plastica": "PLS",
    "stone": "PIE", "pietra": "PIE",
    "ceramic": "CER", "ceramica": "CER",
    "paint/coating": "VER", "paint": "VER", "vernice": "VER", "vernice/rivestimento": "VER",
    "plaster": "INC", "intonaco": "INC",
    "insulation": "ISO", "isolante": "ISO", "isolamento": "ISO",
    "gas": "GAS",
    "earth": "TER", "terra": "TER",
    "textile": "TES", "tessuto": "TES",
    "membrane": "MBR", "membrana": "MBR",
    "gypsum": "CRT", "cartongesso": "CRT",
    "generic": "GEN", "generico": "GEN",
}

_RE_MM = re.compile(r"(\d+)mm")
_RE_DIM = re.compile(r"(\d+)x(\d+)mm")


def _mm(v):
    return int(round(v)) if v is not None else None


def categoria_materiale(nome_materiale, ctx):
    """'1-CLC-STR-CA_C32/40' -> 'CLC' (None se il materiale non e' codificato)."""
    parti = (nome_materiale or u"").split(u"-")
    if len(parti) >= 3 and parti[0] in (u"0", u"1", u"2") and re.match(r"^[A-Z]{3}$", parti[1]):
        return parti[1]
    return None


def sequenza_strati(strati, ctx):
    """Categorie degli strati senza ripetizioni consecutive. None se qualche strato non e' codificato."""
    seq = []
    for s in strati:
        c = categoria_materiale(s.get("materiale"), ctx)
        if c is None:
            return None
        if not seq or seq[-1] != c:
            seq.append(c)
    return seq


# --------------------------------------------------------------------------
# Controlli incrociati
# --------------------------------------------------------------------------
def controlla_coerenza(dati, ctx):
    """Confronta il nome del tipo con spessori, strati, funzione e dimensioni."""
    nome = dati.get("nome") or u""
    r = R.Risultato(nome)
    bic = dati.get("bic")
    parti = nome.split(u"-")
    if len(parti) not in (3, 4):
        r.avviso(u"nome non codificato: controllo incrociato non possibile")
        return r
    descr = parti[-2]
    sott = parti[1] if len(parti) == 4 else None

    if bic == "OST_Walls" and dati.get("funzione") and sott in ("EST", "INT") and sott != dati["funzione"]:
        r.errore(u"sottotipo %s ma il muro in Revit e' %s (parametro Funzione)"
                 % (sott, u"esterno" if dati["funzione"] == "EST" else u"interno"))

    if bic in STRATIFICATI and dati.get("strati"):
        tot = _mm(dati.get("spessore"))
        nums = _RE_MM.findall(descr)
        if not nums:
            r.avviso(u"manca lo spessore totale nel nome (%dmm)" % tot)
        elif int(nums[-1]) != tot:
            r.errore(u"spessore nel nome %smm, spessore reale %dmm" % (nums[-1], tot))

        seq = sequenza_strati(dati["strati"], ctx)
        if seq is None:
            non_cod = [s.get("materiale") or u"(nessuno)" for s in dati["strati"]
                       if categoria_materiale(s.get("materiale"), ctx) is None]
            r.avviso(u"strati con materiale non codificato: %s" % u", ".join(non_cod))
        else:
            cats = set(ctx.codici["categorie_materiali"])
            nel_nome = [t for t in descr.split(u"_") if t in cats]
            if nel_nome and nel_nome != seq:
                r.errore(u"strati nel nome %s, stratigrafia reale %s"
                         % (u"_".join(nel_nome), u"_".join(seq)))
            elif not nel_nome:
                r.avviso(u"il nome non elenca gli strati (%s)" % u"_".join(seq))

        for s in dati["strati"]:
            m = _RE_MM.findall(s.get("materiale") or u"")
            sp = _mm(s.get("spessore"))
            if m and sp and int(m[-1]) != sp:
                r.errore(u"materiale %s ma lo strato e' %dmm" % (s.get("materiale"), sp))

    if bic in APERTURE and dati.get("larghezza") and dati.get("altezza"):
        w, h = _mm(dati["larghezza"]), _mm(dati["altezza"])
        m = _RE_DIM.findall(descr)
        if not m:
            r.avviso(u"mancano le dimensioni nel nome (%dx%dmm)" % (w, h))
        elif (int(m[-1][0]), int(m[-1][1])) != (w, h):
            r.errore(u"dimensioni nel nome %sx%smm, reali %dx%dmm" % (m[-1][0], m[-1][1], w, h))

    if r.problemi:
        r.proposta = suggerisci_tipo(dati, ctx)
        if r.proposta == nome:
            r.proposta = None
    return r


# --------------------------------------------------------------------------
# Suggerimento del nome
# --------------------------------------------------------------------------
def _descr_libera(descr):
    """Parte descrittiva senza strati e senza dimensioni: 'REI120_900x2100mm' -> 'REI120'."""
    t = [x for x in descr.split(u"_") if x and not _RE_MM.search(x) and not re.match(r"^[A-Z]{3}$", x)]
    return u"_".join(t)


def suggerisci_tipo(dati, ctx, occupati=None):
    """Nome proposto TIPO-[SOTTOTIPO-]Descrizione-NN, o None se mancano dati.

    occupati: insieme dei nomi gia' presenti (per scegliere il progressivo libero).
    """
    bic = dati.get("bic")
    nome = dati.get("nome") or u""
    parti = nome.split(u"-")
    attuale_ok = len(parti) in (3, 4) and parti[0] in ctx.tipi

    tipo, sott = CODICE_CATEGORIA.get(bic, (None, None))
    if attuale_ok:
        tipo = parti[0]
        if len(parti) == 4 and re.match(r"^[A-Z]{3}$", parti[1]):
            sott = parti[1]
    if tipo is None:
        return None
    if bic == "OST_Walls" and dati.get("funzione"):
        sott = dati["funzione"]

    vecchia = parti[-2] if attuale_ok else R.pulisci_descrizione(nome)
    if bic in STRATIFICATI and dati.get("strati"):
        seq = sequenza_strati(dati["strati"], ctx)
        if seq is None:
            return None
        descr = u"_".join(seq + [u"%dmm" % _mm(dati.get("spessore"))])
    elif bic in APERTURE and dati.get("larghezza") and dati.get("altezza"):
        libera = _descr_libera(vecchia) if attuale_ok else u""
        dim = u"%dx%dmm" % (_mm(dati["larghezza"]), _mm(dati["altezza"]))
        descr = u"_".join([x for x in (libera, dim) if x])
    else:
        descr = vecchia
    descr = R.pulisci_descrizione(descr)
    if not descr or R.caratteri_vietati(descr):
        return None

    base = u"-".join([x for x in (tipo, sott, descr) if x])
    prog = parti[-1] if attuale_ok and re.match(r"^\d{%d}$" % ctx.cifre, parti[-1]) else None
    occupati = set(occupati or [])
    occupati.discard(nome)
    if prog is None or (base + u"-" + prog) in occupati:
        n = 1
        while (base + u"-" + str(n).zfill(ctx.cifre)) in occupati:
            n += 1
        prog = str(n).zfill(ctx.cifre)
    proposta = base + u"-" + prog
    if len(proposta) > ctx.lmax:
        return None
    return proposta


def suggerisci_materiale(nome, classe, ctx):
    """Nome materiale proposto dalla classe Revit: 'Calcestruzzo C25/30' + Concrete -> '1-CLC-Calcestruzzo...'."""
    if not R.controlla_materiale(nome, ctx).ha_errori:
        return None
    cat = CLASSE_MATERIALE.get((classe or u"").strip().lower())
    if cat is None:
        return None
    det = u"1" if ctx.cfg.get("servizio", u"P") in (u"P", u"E") else u"0"
    descr = R.pulisci_descrizione(nome).replace(u"-", u"_")
    descr = u"".join(c for c in descr if c not in R.VIETATI or c == u"/")
    if not descr:
        return None
    proposta = u"%s-%s-%s" % (det, cat, descr)
    return None if R.controlla_materiale(proposta, ctx).ha_errori else proposta
