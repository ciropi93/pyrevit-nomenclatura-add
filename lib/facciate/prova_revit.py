# -*- coding: utf-8 -*-
"""Prova in Revit degli schemi di facciata pronti (per lo sviluppo).

La chiama l'indirizzo di pyRevit Routes registrato in startup.py:
http://localhost:48884/cdv-tools/facciate/prova/
  ?nome=A-B alternato          uno schema solo
  &lunghezza=12000&altezza=7000   misure del muro di prova (mm)
  &tieni=1                     lascia i muri di prova nel progetto (se no si annulla tutto)
  ?selezione=1                 dice cosa vede il tool nelle curtain wall selezionate
  ?finestra=1                  costruisce la finestra per ogni schema (senza mostrarla), ne
                               percorre i passi e simula clic, assegna, unisci e separa
  ?finestra=foto&nome=...      salva le immagini dei passi della finestra (cartella temporanea)
Nel progetto aperto crea un muro di prova per schema (col primo tipo di facciata continua e
un livello in piu' a 3500 mm se serve), applica lo schema e confronta cosa c'e' in Revit con
cio' che dice ritmo.calcola: linee, segmenti tolti, montanti e tipo di ogni pannello.
Ricarica i moduli a ogni chiamata, cosi' le modifiche al codice valgono senza ricaricare pyRevit.
"""
import os
import tempfile
import traceback

_MODULI = (u"ritmo", u"schema", u"catalogo", u"anteprima", u"revit_facciata", u"ui", u"comandi")


def _ricarica():
    import sys
    try:
        from importlib import reload as ricarica
    except ImportError:                     # IronPython 2.7
        import __builtin__
        ricarica = __builtin__.reload
    for nome in _MODULI:
        m = sys.modules.get(u"facciate." + nome)
        if m is not None:
            ricarica(m)


def da_route(uiapp, query):
    if not hasattr(query, u"get"):
        query = {}

    def uno(chiave):
        v = query.get(chiave)
        return (v[0] if v else None) if isinstance(v, list) else v
    _ricarica()
    nome = uno(u"nome")
    if uno(u"finestra") == u"1":
        return {u"finestra": prova_finestra(nomi=[nome] if nome else None)}
    if uno(u"finestra") == u"foto":
        return {u"foto": foto_finestra(nome or u"Parapetto continuo")}
    uidoc = uiapp.ActiveUIDocument
    if uidoc is None or uidoc.Document.IsFamilyDocument:
        return {u"errore": u"apri un progetto"}
    if uno(u"selezione") == u"1":
        return {u"selezione": guarda_selezione(uidoc)}
    return {u"preset": prova(uidoc.Document, nomi=[nome] if nome else None,
                             lunghezza=float(uno(u"lunghezza") or 12000),
                             altezza=float(uno(u"altezza") or 7000),
                             tieni=uno(u"tieni") == u"1")}


def _parametri_tipo(doc, tipo):
    """I parametri del tipo che il tool usa, col valore: per controllare le ipotesi su
    quale parametro e' delle linee verticali."""
    from Autodesk.Revit import DB
    from facciate import revit_facciata as RV
    out = {}
    for n in RV._LAYOUT + RV._MONTANTI_INTERNI + (u"AUTO_PANEL_WALL",):
        p = RV._param(tipo, n)
        if p is None:
            out[n] = None
        elif p.StorageType == DB.StorageType.ElementId:
            el = doc.GetElement(p.AsElementId())
            out[n] = u"%s = %s" % (p.Definition.Name, RV.chiave_tipo(el) if el is not None else u"-")
        else:
            out[n] = u"%s = %s" % (p.Definition.Name, p.AsValueString() or p.AsInteger())
    return out


def guarda_selezione(uidoc):
    from facciate import revit_facciata as RV
    from facciate import schema as S
    doc = uidoc.Document
    out = []
    for muro in RV.facciate_selezionate(uidoc):
        voce = {u"muro": RV.chiave_id(muro.Id), u"tipo": RV.nome_el(muro.WallType),
                u"parametri_tipo": _parametri_tipo(doc, muro.WallType)}
        try:
            fac = RV.leggi(doc, muro)
            voce.update(lunghezza=round(fac.lunghezza, 1), altezza=round(fac.altezza, 1),
                        da_fine=fac.da_fine,
                        livelli=[round(q) for q in fac.quote_livelli if 0 < q < fac.altezza])
            voce[u"linee"] = _linee_trovate(doc, muro.CurtainGrid, fac)
        except Exception as ex:
            voce[u"errore"] = u"%s" % ex
        s = RV.schema_salvato(muro)
        voce[u"schema"] = S.descrizione(s) if s else None
        out.append(voce)
    return out or u"nessuna curtain wall selezionata"


def _linee_trovate(doc, griglia, fac):
    from facciate import revit_facciata as RV
    v, o = [], []
    for ln in RV.linee_esistenti(doc, griglia):
        x, y = fac.coordinate(ln.FullCurve.Evaluate(0.5, True))
        tutti = len(list(ln.AllSegmentCurves))
        tolti = tutti - len(list(ln.ExistingSegmentCurves))
        if RV._verticale(ln.FullCurve):
            v.append((round(x, 1), tolti))
        else:
            o.append((round(y, 1), tolti))
    return {u"verticali": sorted(v), u"orizzontali": sorted(o)}


def _classi_di_prova(doc, schema, muro_tipo):
    """Classi diverse da quella predefinita con tipi diversi, per vedere che cambino davvero."""
    from facciate import revit_facciata as RV
    tipi_p = RV.tipi_pannello(doc)
    tipi_m = RV.tipi_montante(doc)
    pan_predef = RV.pannello_predefinito(doc, muro_tipo)
    altro_p = [k for k, t in sorted(tipi_p.items())
               if t.GetType().Name == u"PanelType" and (pan_predef is None or t.Id != pan_predef.Id)]
    altro_m = sorted(tipi_m)
    for k in schema[u"classi"][u"pannelli"]:
        if k != schema[u"pannello"] and altro_p:
            schema[u"classi"][u"pannelli"][k] = altro_p[0]
    for k in schema[u"classi"][u"montanti"]:
        if k not in (u"montante", u"traverso") and len(altro_m) > 1:
            schema[u"classi"][u"montanti"][k] = altro_m[-1]
    return schema


def _confronta(doc, muro, schema):
    """Differenze fra Revit e ritmo.calcola sul muro."""
    from facciate import revit_facciata as RV
    from facciate import ritmo as R
    fac = RV.leggi(doc, muro)
    ris = R.calcola(schema, fac.lunghezza, fac.altezza, fac.quote_livelli)
    trovate = _linee_trovate(doc, muro.CurtainGrid, fac)
    diff = []
    for chiave, linee, senza in ((u"verticali", ris[u"linee_v"], ris[u"senza_linea"][u"verticali"]),
                                 (u"orizzontali", ris[u"linee_o"], ris[u"senza_linea"][u"orizzontali"])):
        attese = sorted((round(l[u"pos"], 1), len(ris[u"tolti"][chiave].get(l[u"indice"], [])))
                        for l in linee if l[u"indice"] not in senza)
        vere = trovate[chiave]
        if len(attese) != len(vere) or any(abs(a[0] - b[0]) > 1 or a[1] != b[1] for a, b in zip(attese, vere)):
            diff.append({u"linee": chiave, u"attese (pos, segmenti tolti)": attese, u"in Revit": vere})
    tipi_p = RV.tipi_pannello(doc)
    pan_predef = RV.pannello_predefinito(doc, muro.WallType)
    sbagliati = []
    griglia = muro.CurtainGrid
    for pid in griglia.GetPanelIds():
        el = doc.GetElement(pid)
        bb = el.get_BoundingBox(None)
        x, y = fac.coordinate((bb.Min + bb.Max) * 0.5)
        c = R.trova_cella(ris[u"celle"], ris[u"colonne"], ris[u"righe"], x, y)
        if c is None:
            sbagliati.append(u"pannello fuori a %d, %d" % (x, y))
            continue
        t = RV._tipo_di(schema[u"classi"][u"pannelli"], c[u"classe"], tipi_p, pan_predef)
        if t is not None and el.GetTypeId() != t.Id:
            vero = doc.GetElement(el.GetTypeId())
            sbagliati.append(u"%s a %d, %d: %s invece di %s" % (
                c[u"classe"], x, y, RV.chiave_tipo(vero) if vero else u"?", RV.chiave_tipo(t)))
    if sbagliati:
        diff.append({u"pannelli": sbagliati})
    attese = len(ris[u"celle"])
    if len(list(griglia.GetPanelIds())) != attese:
        diff.append({u"pannelli_contati": len(list(griglia.GetPanelIds())), u"celle_attese": attese})
    return diff


def prova(doc, nomi=None, lunghezza=12000.0, altezza=7000.0, tieni=False):
    from Autodesk.Revit import DB
    from facciate import catalogo as C
    from facciate import revit_facciata as RV
    from facciate import schema as S
    MM = RV.MM
    tipo = [t for t in DB.FilteredElementCollector(doc).OfClass(DB.WallType) if t.Kind == DB.WallKind.Curtain]
    if not tipo:
        return u"nel progetto non c'è un tipo di facciata continua"
    tipo = sorted(tipo, key=lambda t: RV.nome_el(t))[0]
    out = []
    messaggi = []
    gruppo = DB.TransactionGroup(doc, u"CDV prova facciate")
    gruppo.Start()
    try:
        t = RV.transazione(doc, u"CDV prova: livelli", messaggi)
        t.Start()
        livelli = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level), key=lambda l: l.ProjectElevation)
        base = livelli[0]
        if not [l for l in livelli if 1000 * MM < l.ProjectElevation - base.ProjectElevation < altezza * MM]:
            DB.Level.Create(doc, base.Elevation + 3500 * MM)
        t.Commit()
        for n, schema in enumerate(C.preimpostati()):
            if nomi and schema[u"nome"] not in nomi:
                continue
            voce = {u"nome": schema[u"nome"], u"descrizione": S.descrizione(schema)}
            try:
                t = RV.transazione(doc, u"CDV prova: muro", messaggi)
                t.Start()
                y = -20000 * MM - n * 3000 * MM
                linea = DB.Line.CreateBound(DB.XYZ(0, y, 0), DB.XYZ(lunghezza * MM, y, 0))
                muro = DB.Wall.Create(doc, linea, tipo.Id, base.Id, altezza * MM, 0.0, False, False)
                t.Commit()
                schema = _classi_di_prova(doc, schema, tipo)
                esito = RV.applica(doc, [muro], schema)
                voce[u"applica"] = esito
                voce[u"parametri_tipo"] = _parametri_tipo(doc, muro.WallType)
                diff = _confronta(doc, muro, schema)
                voce[u"differenze"] = diff
                salvato = RV.schema_salvato(muro)
                voce[u"schema_salvato"] = salvato == S.normalizza(schema)
                errore = esito[u"muri"][0].get(u"errore")
                voce[u"esito"] = u"errore" if errore else (u"da controllare" if diff or not voce[u"schema_salvato"] else u"ok")
            except Exception as ex:
                voce.update(esito=u"errore", errore=u"%s" % ex, traccia=traceback.format_exc())
            out.append(voce)
    finally:
        if tieni:
            gruppo.Assimilate()
        else:
            gruppo.RollBack()
    if messaggi:
        out.append({u"avvisi_revit": messaggi})
    return out


def _clic(win, x, y, maiuscolo=False):
    """Clic simulato sul disegno nel punto (x, y) in mm (Maiusc: aggiunge alla scelta)."""
    from facciate import anteprima as AN
    el = AN.elemento_in_punto(win.ris, x, y, 1.0)
    if el is None:
        win.sel = None
    elif el[0] == u"cella":
        if maiuscolo and win.sel and win.sel[u"tipo"] == u"celle":
            win.sel[u"punti"].append((x, y))
        else:
            win.sel = {u"tipo": u"celle", u"punti": [(x, y)]}
    else:
        win.sel = {u"tipo": el[0], u"pos": el[1][u"pos"]}
    win.vai_al_passo(4)


def prova_finestra(nomi=None):
    """Per ogni schema: costruisce la finestra, percorre i passi, cambia modo, aggiunge un
    modulo, assegna classi, unisce e separa celle. [{nome, esito, errore, ...}]"""
    from facciate import catalogo as C
    from facciate import ritmo as R
    from facciate import schema as S
    from facciate import ui as UI
    tipi = {u"pannelli": [u"Pannello di sistema: Vetrato", u"Pannello di sistema: Pieno"],
            u"montanti": [u"Montante rettangolare: 50 x 150 mm"]}
    out = []
    for base in C.preimpostati():
        if nomi and base[u"nome"] not in nomi:
            continue
        voce = {u"nome": base[u"nome"]}
        win = None
        try:
            win = UI.FinestraFacciata(schema=S.copia(base), tipi=tipi)
            for n in (1, 2, 3, 4, 5, 2):
                win.vai_al_passo(n)
            for k in (u"colonne", u"righe"):
                for modo, _e in R.MODI:
                    win.schema[k][u"modo"] = modo
                    win.editor_regola(k)
                    win.ridisegna()
            win.schema = S.copia(base)
            win.carica_schema()
            S.aggiungi_modulo(win.schema[u"colonne"])
            win.editor_regola(u"colonne")
            win.ridisegna()
            win.schema = S.copia(base)
            win.carica_schema()
            col, rig = win.ris[u"colonne"], win.ris[u"righe"]
            x0 = (col[0][u"da"] + col[0][u"a"]) / 2.0
            y0 = (rig[-1][u"da"] + rig[-1][u"a"]) / 2.0
            _clic(win, x0, y0)
            win.assegna(u"prova")
            voce[u"classe_assegnata"] = u"prova" in win.schema[u"classi"][u"pannelli"]
            if len(col) > 1:
                _clic(win, (col[1][u"da"] + col[1][u"a"]) / 2.0, y0, maiuscolo=True)
                win.su_unisci(None, None)
                voce[u"unioni"] = len(win.schema[u"unioni"])
                _clic(win, x0, y0)
                win.su_separa(None, None)
            if win.ris[u"linee_v"]:
                _clic(win, win.ris[u"linee_v"][0][u"pos"], y0)
                win.assegna(u"lesena_prova")
                voce[u"linea_assegnata"] = u"lesena_prova" in win.schema[u"classi"][u"montanti"]
            win.vai_al_passo(5)
            voce[u"righe_tipi"] = win.pnlTipiPannelli.Children.Count + win.pnlTipiMontanti.Children.Count
            win.su_applica(None, None)
            voce[u"risultato"] = win.risultato is not None
            voce[u"errori"] = win.txtErrori.Text
            voce[u"esito"] = u"ok" if win.risultato is not None else u"da controllare"
        except Exception as ex:
            voce.update(esito=u"errore", errore=u"%s" % ex, traccia=traceback.format_exc())
        finally:
            if win is not None:
                try:
                    win.Close()
                except Exception:
                    pass
        out.append(voce)
    return out


def foto_finestra(nome):
    """Immagini PNG dei passi della finestra per guardarla senza cliccare. Ritorna i percorsi."""
    import clr
    clr.AddReference("PresentationCore")
    from System.IO import File
    from System.Windows.Media import PixelFormats
    from System.Windows.Media.Imaging import PngBitmapEncoder, BitmapFrame, RenderTargetBitmap
    from facciate import catalogo as C
    from facciate import schema as S
    from facciate import ui as UI

    base = [s for s in C.preimpostati() if s[u"nome"] == nome][0]
    cartella = os.path.join(tempfile.gettempdir(), u"CDV facciate prova", u"foto")
    if not os.path.isdir(cartella):
        os.makedirs(cartella)
    win = UI.FinestraFacciata(schema=S.copia(base))
    out = []

    def scatta(etichetta):
        win.UpdateLayout()
        win.ridisegna()
        win.UpdateLayout()
        el = win.Content
        bmp = RenderTargetBitmap(int(el.ActualWidth), int(el.ActualHeight), 96, 96, PixelFormats.Pbgra32)
        bmp.Render(el)
        enc = PngBitmapEncoder()
        enc.Frames.Add(BitmapFrame.Create(bmp))
        percorso = os.path.join(cartella, u"%s %s.png" % (nome, etichetta))
        flusso = File.Create(percorso)
        try:
            enc.Save(flusso)
        finally:
            flusso.Close()
        out.append(percorso)

    try:
        win.ShowActivated = False
        win.WindowStartupLocation = 0       # Manual
        win.Left, win.Top = -20000, -20000
        win.Show()
        for n in range(1, 6):
            win.vai_al_passo(n)
            scatta(u"passo %d" % n)
        col, rig = win.ris[u"colonne"], win.ris[u"righe"]
        _clic(win, (col[0][u"da"] + col[0][u"a"]) / 2.0, (rig[0][u"da"] + rig[0][u"a"]) / 2.0)
        scatta(u"cella scelta")
    finally:
        win.Close()
    return out
