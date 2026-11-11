# -*- coding: utf-8 -*-
"""Regole di nomenclatura BIM dell'Agenzia del Demanio (BIMMS ADD2024 §4.1).

Questo modulo NON usa le API di Revit: contiene solo la logica di controllo,
cosi' si puo' testare fuori da Revit (vedi cartella tests/).
Compatibile con IronPython 2.7 e CPython 3.
"""
import io
import json
import os
import re

ERRORE = "ERRORE"
AVVISO = "AVVISO"

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# Caratteri vietati (BIMMS §4.1.3 e §4.1.4) piu' quelli che Revit non accetta.
VIETATI = set(u". , / \\ & $ € ? ! \" ” “ ' ^ * + ° § @ = ÷ < > [ ] { } ~ "
              u"‰ £ ¥ % ( ) ; : | # `".split())

_ACCENTI = {u"à": u"a", u"á": u"a", u"è": u"e", u"é": u"e", u"ì": u"i",
            u"í": u"i", u"ò": u"o", u"ó": u"o", u"ù": u"u", u"ú": u"u",
            u"À": u"A", u"È": u"E", u"É": u"E", u"Ì": u"I", u"Ò": u"O",
            u"Ù": u"U"}

_RE_TRE = re.compile(r"^[A-Z]{3}$")
_RE_CF = re.compile(r"^CF\d{7}$")
_RE_CA = re.compile(r"^CA\d{4}$")
_RE_BENE = re.compile(r"^[A-Z]{3}\d{4}$")


# --------------------------------------------------------------------------
# Dati
# --------------------------------------------------------------------------
def _leggi_json(nome):
    with io.open(os.path.join(_DATA, nome), "r", encoding="utf-8") as f:
        return json.load(f)


def carica_codici():
    return _leggi_json("codici_add2024.json")


def percorso_config_default():
    return os.path.join(_DATA, "progetto.json")


def percorso_config_utente():
    """Copia personale delle impostazioni: non viene sovrascritta dagli aggiornamenti del plugin."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "NomenclaturaADD", "progetto.json")


def carica_config():
    p = percorso_config_utente()
    if os.path.exists(p):
        with io.open(p, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        base = _leggi_json("progetto.json")
        base.update(cfg)
        return base
    return _leggi_json("progetto.json")


class Contesto(object):
    """Codici ufficiali + impostazioni di progetto."""

    def __init__(self, codici=None, config=None):
        self.codici = codici if codici is not None else carica_codici()
        self.cfg = config if config is not None else carica_config()

    @property
    def tipi(self):
        return self.codici["tipi_elemento"]

    def sottotipi(self, tipo):
        t = self.tipi.get(tipo)
        return t["sottotipi"] if t else {}

    @property
    def cifre(self):
        return int(self.cfg.get("cifre_progressivo", 2))

    @property
    def lmax(self):
        return int(self.cfg.get("lunghezza_max", 50))


# --------------------------------------------------------------------------
# Risultato di un controllo
# --------------------------------------------------------------------------
class Risultato(object):
    def __init__(self, valore):
        self.valore = valore
        self.problemi = []  # lista di (livello, messaggio)
        self.proposta = None

    def errore(self, msg):
        self.problemi.append((ERRORE, msg))

    def avviso(self, msg):
        self.problemi.append((AVVISO, msg))

    @property
    def ok(self):
        return not self.problemi

    @property
    def ha_errori(self):
        return any(l == ERRORE for l, _ in self.problemi)

    @property
    def livello(self):
        if self.ha_errori:
            return ERRORE
        return AVVISO if self.problemi else "OK"

    def messaggio(self):
        return u"; ".join(m for _, m in self.problemi)

    def __repr__(self):
        return u"<Risultato %s %s %s -> %s>" % (self.valore, self.livello, self.messaggio(), self.proposta)


# --------------------------------------------------------------------------
# Utilita' sul testo
# --------------------------------------------------------------------------
def togli_accenti(s):
    return u"".join(_ACCENTI.get(c, c) for c in s)


def caratteri_vietati(s, consenti=u""):
    return sorted(set(c for c in s if c in VIETATI and c not in consenti))


def pascal(s):
    """'lana di roccia 100mm' -> 'LanaDiRoccia100mm' (non tocca il resto della parola)."""
    parole = [p for p in re.split(r"\s+", s.strip()) if p]
    out = []
    for p in parole:
        out.append(p[0].upper() + p[1:] if p[0].isalpha() else p)
    return u"".join(out)


def pulisci_descrizione(s):
    """Correzioni sicure: accenti, spazi -> PascalCase, iniziale maiuscola."""
    s = pascal(togli_accenti(s))
    if s and s[0].isalpha() and s[0].islower():
        s = s[0].upper() + s[1:]
    return s


def _controlla_descrizione(r, descr, consenti=u""):
    if not descr:
        r.errore(u"descrizione mancante")
        return
    if re.search(r"\s", descr):
        r.errore(u"spazi nella descrizione: usare PascalCase o _")
    if togli_accenti(descr) != descr:
        r.errore(u"lettere accentate")
    vietati = caratteri_vietati(descr, consenti)
    if vietati:
        r.errore(u"caratteri vietati: %s" % u" ".join(vietati))
    if descr[0].isalpha() and descr[0].islower():
        r.avviso(u"descrizione non in PascalCase (iniziale minuscola)")


def _proponi(r, proposta, ricontrolla):
    """Imposta la proposta solo se e' diversa e risolve tutti gli errori."""
    if proposta and proposta != r.valore:
        if not ricontrolla(proposta).ha_errori:
            r.proposta = proposta


# --------------------------------------------------------------------------
# Elementi (nome TIPO in Revit) - BIMMS §4.1.3 + Allegato D
#   TIPO-[SOTTOTIPO-]Descrizione-NN
# --------------------------------------------------------------------------
def controlla_elemento(nome, ctx, categoria=None):
    r = Risultato(nome)
    parti = nome.split(u"-")
    if len(parti) < 3:
        r.errore(u"servono 3 o 4 campi separati da '-': TIPO-[SOTTOTIPO-]Descrizione-NN")
        return r
    if len(parti) > 4:
        r.errore(u"troppi campi (%d): massimo 4, usare '_' dentro la descrizione" % len(parti))
        return r

    tipo, prog = parti[0], parti[-1]
    if not _RE_TRE.match(tipo):
        r.errore(u"codice funzione tipo '%s' non valido (3 lettere maiuscole)" % tipo)
    elif tipo not in ctx.tipi:
        r.errore(u"codice funzione tipo '%s' non presente nell'Allegato D" % tipo)

    if not re.match(r"^\d{%d}$" % ctx.cifre, prog):
        if re.match(r"^\d+$", prog):
            r.errore(u"progressivo '%s' deve avere %d cifre" % (prog, ctx.cifre))
        else:
            r.errore(u"manca il progressivo finale (es. -01)")

    sott = None
    if len(parti) == 4:
        sott, descr = parti[1], parti[2]
        if not _RE_TRE.match(sott):
            r.errore(u"sottotipo '%s' non valido (3 lettere maiuscole)" % sott)
        elif tipo in ctx.tipi and sott not in ctx.sottotipi(tipo):
            r.avviso(u"sottotipo '%s' non previsto per %s nell'Allegato D (dichiararlo nel pGI)" % (sott, tipo))
    else:
        descr = parti[1]
        if tipo in ctx.tipi and descr in ctx.sottotipi(tipo):
            r.errore(u"manca la descrizione dopo il sottotipo")

    _controlla_descrizione(r, descr)

    if len(nome) > ctx.lmax:
        r.errore(u"lunghezza %d > %d caratteri" % (len(nome), ctx.lmax))

    if categoria and tipo in ctx.tipi:
        ammessi = ctx.cfg.get("categorie_codici", {}).get(categoria)
        if ammessi and tipo not in ammessi:
            r.avviso(u"codice %s insolito per la categoria Revit %s (attesi: %s)"
                     % (tipo, categoria, u", ".join(ammessi)))

    if not r.ok:
        nuove = [parti[0].upper()]
        if sott is not None:
            nuove.append(sott.upper())
        nuove.append(pulisci_descrizione(descr))
        nuove.append(prog.zfill(ctx.cifre) if prog.isdigit() else prog)
        _proponi(r, u"-".join(nuove), lambda p: controlla_elemento(p, ctx))
    return r


def prefisso_codice(nome_tipo, ctx):
    """'MUR-EST-Descr-01' -> 'MUR-EST' ; 'CLN-CLC_500mm-03' -> 'CLN'. None se non leggibile."""
    parti = nome_tipo.split(u"-")
    if len(parti) == 4:
        return u"-".join(parti[:2])
    if len(parti) == 3:
        return parti[0]
    return None


# --------------------------------------------------------------------------
# Famiglie caricabili - convenzione di progetto (pGI):
#   TIPO-[SOTTOTIPO-]Descrizione   (senza progressivo)
# --------------------------------------------------------------------------
def controlla_famiglia(nome, ctx, prefissi_tipi=None):
    r = Risultato(nome)
    parti = nome.split(u"-")
    if len(parti) not in (2, 3):
        r.errore(u"usare TIPO-[SOTTOTIPO-]Descrizione (2 o 3 campi)")
        return r
    tipo = parti[0]
    if not _RE_TRE.match(tipo) or tipo not in ctx.tipi:
        r.errore(u"codice funzione tipo '%s' non presente nell'Allegato D" % tipo)
    if len(parti) == 3:
        sott = parti[1]
        if not _RE_TRE.match(sott):
            r.errore(u"sottotipo '%s' non valido" % sott)
        elif tipo in ctx.tipi and sott not in ctx.sottotipi(tipo):
            r.avviso(u"sottotipo '%s' non previsto per %s nell'Allegato D (pGI)" % (sott, tipo))
    descr = parti[-1]
    if re.match(r"^\d+$", descr):
        r.errore(u"il nome famiglia non deve finire col progressivo")
    else:
        _controlla_descrizione(r, descr)
    if len(nome) > ctx.lmax:
        r.errore(u"lunghezza %d > %d" % (len(nome), ctx.lmax))
    if prefissi_tipi:
        pref_fam = u"-".join(parti[:-1])
        diversi = sorted(set(p for p in prefissi_tipi if p and p != pref_fam))
        if diversi:
            r.avviso(u"i tipi della famiglia hanno codice diverso: %s" % u", ".join(diversi))
    if not r.ok:
        nuove = [p.upper() for p in parti[:-1]] + [pulisci_descrizione(descr)]
        _proponi(r, u"-".join(nuove), lambda p: controlla_famiglia(p, ctx))
    return r


# --------------------------------------------------------------------------
# Contrassegno tipo (Type Mark) - convenzione di progetto: TIPO-[SOTTOTIPO-]NN
# --------------------------------------------------------------------------
def contrassegno_atteso(nome_tipo, ctx):
    if controlla_elemento(nome_tipo, ctx).ha_errori:
        return None
    parti = nome_tipo.split(u"-")
    return u"-".join(parti[:-2] + [parti[-1]])


def controlla_contrassegno(valore, nome_tipo, ctx):
    r = Risultato(valore or u"")
    atteso = contrassegno_atteso(nome_tipo, ctx)
    if atteso is None:
        r.avviso(u"correggere prima il nome del tipo")
        return r
    if (valore or u"") != atteso:
        r.errore(u"atteso '%s'" % atteso)
        r.proposta = atteso
    return r


# --------------------------------------------------------------------------
# Materiali - BIMMS §4.1.4:  Dettaglio-CAT-[SUB-]Descrizione
# --------------------------------------------------------------------------
def materiale_escluso(nome, ctx):
    for rx in ctx.cfg.get("materiali", {}).get("escludi_regex", []):
        if re.search(rx, nome):
            return True
    return False


def controlla_materiale(nome, ctx):
    r = Risultato(nome)
    parti = nome.split(u"-")
    if len(parti) not in (3, 4):
        r.errore(u"usare Dettaglio-CATEGORIA-[SOTTOCATEGORIA-]Descrizione")
        return r
    det, cat = parti[0], parti[1]
    if det not in (u"0", u"1", u"2"):
        r.errore(u"codice dettaglio '%s' deve essere 0, 1 o 2" % det)
    else:
        serv = ctx.cfg.get("servizio", u"P")
        ammessi = {u"S": u"012", u"P": u"01", u"E": u"12", u"A": u"2"}.get(serv)
        if ammessi and det not in ammessi:
            r.avviso(u"dettaglio %s non previsto per la fase %s (Tab. 26: %s)"
                     % (det, serv, u", ".join(ammessi)))
    cats = ctx.codici["categorie_materiali"]
    if cat not in cats:
        if _RE_TRE.match(cat):
            r.avviso(u"categoria '%s' non in Tab. 27 (aggiuntiva: dichiararla nel pGI)" % cat)
        else:
            r.errore(u"categoria '%s' non valida (3 lettere maiuscole, Tab. 27)" % cat)
    sub = None
    if len(parti) == 4:
        sub = parti[2]
        subs = ctx.codici["sottocategorie_materiali"]
        if sub not in subs:
            if _RE_TRE.match(sub):
                r.avviso(u"sottocategoria '%s' non in Tab. 28 (dichiararla nel pGI)" % sub)
            else:
                r.errore(u"sottocategoria '%s' non valida (Tab. 28)" % sub)
    descr = parti[-1]
    consenti = u"/" if ctx.cfg.get("materiali", {}).get("consenti_slash_classe", True) else u""
    _controlla_descrizione(r, descr, consenti)
    if consenti and u"/" in descr:
        r.avviso(u"'/' tollerato solo per classi tipo C32/40 (vietato dal BIMMS)")
    if not r.ok:
        nuove = [det, cat.upper()] + ([sub.upper()] if sub is not None else []) + [pulisci_descrizione(descr)]
        _proponi(r, u"-".join(nuove), lambda p: controlla_materiale(p, ctx))
    return r


# --------------------------------------------------------------------------
# Livelli - BIMMS §4.1.5.2:  CodiceLivello-Disciplina[_Suffisso]
# --------------------------------------------------------------------------
def _livello_valido(cod, ctx):
    return cod in ctx.codici["codici_livello"] or bool(re.match(r"^(\d{2}|[MG]\d)$", cod))


def controlla_livello(nome, ctx):
    r = Risultato(nome)
    m = re.match(r"^([A-Z0-9]{2})-([A-Z])(.*)$", nome)
    if not m:
        r.errore(u"usare CodiceLivello-Disciplina (es. GF-A, 01-S, G1-A)")
        m2 = re.match(r"^\s*([A-Za-z0-9]{2})\s*[-_ ]\s*([A-Za-z])\s*$", nome)
        if m2:
            _proponi(r, u"%s-%s" % (m2.group(1).upper(), m2.group(2).upper()),
                     lambda p: controlla_livello(p, ctx))
        return r
    cod, disc, suff = m.groups()
    if not _livello_valido(cod, ctx):
        r.errore(u"codice livello '%s' non valido (GF, 01, 02, M1, G1...)" % cod)
    if disc not in ctx.codici["discipline"]:
        r.errore(u"disciplina '%s' non in Tab. 15" % disc)
    elif disc not in (u"A", u"S"):
        r.avviso(u"il BIMMS (§4.1.5.2) prevede solo A o S per i livelli: '%s' va dichiarato nel pGI" % disc)
    if suff:
        rx = ctx.cfg.get("livelli", {}).get("suffisso_regex")
        if rx and re.match(rx, suff):
            r.avviso(u"suffisso '%s' = convenzione di progetto, da dichiarare nel pGI" % suff)
        else:
            r.errore(u"suffisso '%s' non previsto" % suff)
    return r


# --------------------------------------------------------------------------
# Locali / spazi - BIMMS §4.1.5.1 + Allegato E
#   Numero = USO-NNN ; Nome = Nome Uso dell'Allegato E
# --------------------------------------------------------------------------
def controlla_numero_locale(numero, ctx):
    r = Risultato(numero)
    usi = ctx.codici["codici_uso"]
    m = re.match(r"^([A-Z]{3})-(\d{3})$", numero)
    if m:
        if m.group(1) not in usi:
            r.errore(u"codice uso '%s' non presente nell'Allegato E" % m.group(1))
        return r
    r.errore(u"usare CODICEUSO-NNN (es. BOX-001)")
    m2 = re.match(r"^\s*([A-Za-z]{3})[\s_\-.]*(\d{1,3})\s*$", numero)
    if m2:
        _proponi(r, u"%s-%s" % (m2.group(1).upper(), m2.group(2).zfill(3)),
                 lambda p: controlla_numero_locale(p, ctx))
    return r


def controlla_nome_locale(nome, numero, ctx):
    r = Risultato(nome)
    m = re.match(r"^([A-Z]{3})-\d{3}$", numero or u"")
    if not m:
        m2 = re.match(r"^\s*([A-Za-z]{3})", numero or u"")
        uso = m2.group(1).upper() if m2 else None
    else:
        uso = m.group(1)
    nomi = ctx.codici["codici_uso"].get(uso) if uso else None
    if not nomi:
        if not nome:
            r.errore(u"nome mancante")
        return r
    if nome in nomi:
        return r
    uguali = [n for n in nomi if n.lower() == (nome or u"").strip().lower()]
    if uguali:
        r.errore(u"scrivere esattamente '%s'" % uguali[0])
        r.proposta = uguali[0]
    else:
        r.avviso(u"nome diverso dall'Allegato E per %s (%s)" % (uso, u" / ".join(nomi)))
        if len(nomi) == 1:
            r.proposta = nomi[0]
    return r


# --------------------------------------------------------------------------
# Codici a 7 campi: modelli (§4.1.1) ed elaborati/tavole (§4.1.2)
# --------------------------------------------------------------------------
def _controlla_bene(r, bene, ctx):
    atteso = ctx.cfg.get("codice_bene")
    if not _RE_BENE.match(bene):
        r.errore(u"codice bene '%s' non valido (3 lettere + 4 cifre)" % bene)
    elif atteso and bene != atteso:
        r.errore(u"codice bene '%s' diverso da quello di progetto %s" % (bene, atteso))


def _controlla_cf(r, cod, ctx):
    if cod in (u"CFNNNNNNN", u"CANNNN"):
        r.avviso(u"'%s' e' ancora un segnaposto: inserire il codice fabbricato/area" % cod)
        return
    noti = ctx.cfg.get("codici_fabbricato_area") or []
    if noti and cod not in noti:
        r.avviso(u"codice fabbricato/area '%s' non tra quelli di progetto" % cod)


def controlla_file_modello(nome, ctx):
    r = Risultato(nome)
    parti = nome.split(u"-")
    if len(parti) != 7:
        r.errore(u"il nome del modello deve avere 7 campi: BENE-ADD-CF/CA-LL-TT-D-XX0000")
        return r
    bene, add, fab, liv, tf, disc, alfa = parti
    _controlla_bene(r, bene, ctx)
    if add != u"ADD":
        r.errore(u"il secondo campo deve essere ADD")
    if _RE_CF.match(fab) or _RE_CA.match(fab):
        _controlla_cf(r, fab, ctx)
    elif fab in (u"CFNNNNNNN", u"CANNNN"):
        _controlla_cf(r, fab, ctx)
    elif fab not in (u"MGENERALE", u"MFEDERATO"):
        r.errore(u"terzo campo '%s': atteso CFnnnnnnn, CAnnnn, MGENERALE o MFEDERATO" % fab)
    if not _livello_valido(liv, ctx):
        r.errore(u"codice livello '%s' non valido" % liv)
    if tf not in (u"M2", u"M3", u"MR", u"PC"):
        r.errore(u"tipo file '%s' non valido per un modello (M2, M3, MR, PC)" % tf)
    if disc not in ctx.codici["discipline"]:
        r.errore(u"disciplina '%s' non in Tab. 15" % disc)
    # Coerenze da BIMMS §4.1.1.4 (N.B.) e Allegato I
    if disc in (u"C", u"K", u"Y") and tf not in (u"M2", u"MR"):
        r.errore(u"i modelli federati (disciplina %s) devono essere M2 o MR" % disc)
    if fab == u"MFEDERATO" and tf not in (u"M2", u"MR", u"PC"):
        r.errore(u"MFEDERATO ammette solo M2, MR o PC (Allegato I)")
    if fab == u"MGENERALE" and tf not in (u"M3", u"MR", u"PC"):
        r.errore(u"MGENERALE ammette solo M3, MR o PC (Allegato I)")
    if disc == u"Y" and fab != u"MFEDERATO":
        r.errore(u"la disciplina Y (federato di sintesi) richiede MFEDERATO come terzo campo")
    if tf == u"PC" and alfa[:1] not in (u"S", u"G", u""):
        r.avviso(u"le nuvole di punti sono di norma Stato di fatto (S)")
    m = re.match(r"^([A-Z])([A-Z0])(\d{4})$", alfa)
    if not m:
        r.errore(u"codice alfanumerico '%s' non valido (es. PN0001, S00001)" % alfa)
    else:
        if m.group(1) not in ctx.codici["servizi"]:
            r.errore(u"servizio '%s' non in Tab. 16" % m.group(1))
        if m.group(2) != u"0" and m.group(2) not in ctx.codici["stati"]:
            r.errore(u"stato '%s' non in Tab. 16" % m.group(2))
        serv = ctx.cfg.get("servizio")
        if serv and m.group(1) != serv:
            r.avviso(u"servizio %s diverso da quello di progetto (%s)" % (m.group(1), serv))
    return r


def controlla_tavola(numero, ctx):
    r = Risultato(numero)
    if re.search(r"\s", numero):
        r.errore(u"spazi nel codice")
        _proponi(r, re.sub(r"\s+", u"", numero), lambda p: controlla_tavola(p, ctx))
        return r
    parti = numero.split(u"-")
    if len(parti) != 7:
        r.errore(u"il numero tavola deve avere 7 campi: BENE-ADD-CODDOC-LL-DR-D-X00000")
        return r
    bene, add, doc, liv, tf, disc, alfa = parti
    _controlla_bene(r, bene, ctx)
    if add != u"ADD":
        r.errore(u"il secondo campo deve essere ADD")
    if _RE_CF.match(doc) or _RE_CA.match(doc) or doc in (u"CFNNNNNNN", u"CANNNN"):
        _controlla_cf(r, doc, ctx)
    elif doc not in ctx.codici["codici_documento"]:
        if re.match(r"^[A-Z0-9]{8,9}$", doc):
            r.avviso(u"codice documento '%s' non nell'Allegato H (concordarlo e dichiararlo nel pGI)" % doc)
        else:
            r.errore(u"codice documento/fabbricato '%s' non valido" % doc)
    if not _livello_valido(liv, ctx):
        r.errore(u"codice livello '%s' non valido" % liv)
    if tf not in ctx.codici["tipi_file"]:
        r.errore(u"tipo file '%s' non in Tab. 14" % tf)
    else:
        ammessi = ctx.cfg.get("tavole", {}).get("tipi_file_ammessi")
        if ammessi and tf not in ammessi:
            r.avviso(u"tipo file %s insolito per una tavola (atteso %s)" % (tf, u", ".join(ammessi)))
    if disc not in ctx.codici["discipline"]:
        r.errore(u"disciplina '%s' non in Tab. 15" % disc)
    m = re.match(r"^([A-Z])(\d)(\d{4})$", alfa)
    if not m:
        r.errore(u"codice alfanumerico '%s' non valido (es. P00001)" % alfa)
    else:
        if m.group(1) not in ctx.codici["servizi"]:
            r.errore(u"servizio '%s' non in Tab. 16" % m.group(1))
        serv = ctx.cfg.get("servizio")
        if serv and m.group(1) != serv:
            r.avviso(u"servizio %s diverso da quello di progetto (%s)" % (m.group(1), serv))
    return r
