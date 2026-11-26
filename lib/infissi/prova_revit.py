# -*- coding: utf-8 -*-
"""Prova in Revit di tutti i preset del configuratore (per lo sviluppo).

La chiama l'indirizzo di pyRevit Routes registrato in startup.py:
http://localhost:48884/cdv-tools/infissi/prova/
  ?nome=2 ante                 un preset solo
  &varianti=0                  senza la variante maniglie+pianta
  &salta=simboli,allinea       passaggi del costruttore da saltare (per isolare un problema):
                               piani, estrusioni, allinea, simboli, pianta_e_aperte, flex, ...
Crea ogni famiglia in una cartella temporanea senza caricarla nel progetto e ritorna,
preset per preset, i problemi trovati e i messaggi di Revit. Ricarica i moduli degli
infissi a ogni chiamata, cosi' le modifiche al codice valgono senza ricaricare pyRevit.
"""
import os
import tempfile
import traceback

_MODULI = (u"schema", u"geometria", u"parametri", u"anteprima", u"catalogo", u"revit_famiglia", u"ui")


def _ricarica():
    import sys
    try:
        from importlib import reload as ricarica
    except ImportError:                     # IronPython 2.7
        import __builtin__
        ricarica = __builtin__.reload
    for nome in _MODULI:
        m = sys.modules.get(u"infissi." + nome)
        if m is not None:
            ricarica(m)


def _salta(RF, passaggi):
    """Rende vuoti i passaggi indicati del costruttore (solo per questa prova: i moduli
    vengono ricaricati alla prossima chiamata). "quota:testo" salta le quote il cui
    parametro contiene quel testo."""
    quote = []
    for nome in passaggi:
        nome = nome.strip()
        if nome.startswith(u"quota:"):
            quote.append(nome[6:])
        elif nome and hasattr(RF._Costruttore, u"_" + nome):
            setattr(RF._Costruttore, u"_" + nome, lambda self, *a, **k: None)
    if quote:
        originale = RF._Costruttore._quota

        def _quota(self, rif_a, rif_b, linea, param, vista=None):
            if any(t in param for t in quote):
                return True
            return originale(self, rif_a, rif_b, linea, param, vista)
        RF._Costruttore._quota = _quota


def da_route(app, query):
    """Risposta della route: legge i parametri dell'indirizzo e fa la prova."""
    if not hasattr(query, u"get"):
        query = {}

    def uno(chiave):
        v = query.get(chiave)
        return (v[0] if v else None) if isinstance(v, list) else v
    nome = uno(u"nome")
    if uno(u"finestra") == u"1":
        return {u"finestra": prova_finestra(nomi=[nome] if nome else None)}
    if uno(u"modello"):
        return {u"modello": guarda_modello(app, uno(u"modello"))}
    if uno(u"palette") == u"1":
        return {u"palette": prova_palette(app)}
    if uno(u"finestra") == u"foto":
        return {u"foto": foto_finestra(nome or u"2 ante", modifica=uno(u"modifica") == u"1",
                                       contorno=uno(u"contorno") == u"1")}
    return {u"preset": prova(app, nomi=[nome] if nome else None,
                             varianti=uno(u"varianti") != u"0",
                             salta=(uno(u"salta") or u"").split(u","),
                             contorno=uno(u"contorno") == u"1",
                             posizione=uno(u"posizione") or u"filo_esterno")}


def con_tutto_il_contorno(schema, posizione=u"filo_esterno"):
    """Variante con tutto il contorno acceso (per la prova)."""
    from infissi import schema as S
    s = S.copia(schema)
    c = s[u"contorno"]
    c[u"posizione"] = posizione
    c[u"misure"][u"posizione"] = 50.0
    for k, _e in S.ELEMENTI_CONTORNO:
        c[k] = True
    return s


def prova_finestra(nomi=None):
    """Costruisce il configuratore (senza mostrarlo) per ogni preset, nuovo e in modifica, e
    ne percorre passi, viste e livelli di dettaglio: [{nome, modifica, esito, errore}]."""
    _ricarica()
    from infissi import catalogo as C
    from infissi import schema as S
    from infissi import ui as UI
    out = []
    for base in C.preimpostati():
        if nomi and base[u"nome"] not in nomi:
            continue
        for modifica in (False, True):
            voce = {u"nome": base[u"nome"], u"modifica": modifica}
            win = None
            try:
                win = UI.Configuratore(schema=S.copia(base), nome_famiglia=base[u"nome"] if modifica else None,
                                       modifica=modifica)
                for n in (1, 2, 3, 4, 5, 3, 2):
                    win.vai_al_passo(n)
                # contorno tutto acceso, poi di nuovo spento
                win.schema = con_tutto_il_contorno(win.schema)
                win._aggiorna_contorno()
                win.vai_al_passo(5)
                win.rbPianta.IsChecked = True
                win.rbProspetto.IsChecked = True
                voce[u"contorno_campi"] = win.pnlContorno.Children.Count
                voce[u"contorno_errori"] = win.txtErrori.Text
                win.schema[u"contorno"] = S.contorno_vuoto()
                win._aggiorna_contorno()
                for vista in (win.rbPianta, win.rbProspetto):
                    vista.IsChecked = True
                    for i in range(win.cmbDettaglio.Items.Count):
                        win.cmbDettaglio.SelectedIndex = i
                for _volta in (1, 2):
                    win.chkManiglie.IsChecked = not win.chkManiglie.IsChecked
                    win.su_maniglie(None, None)
                    win.chkSoglia.IsChecked = not win.chkSoglia.IsChecked
                    win.su_soglia(None, None)
                win.vai_al_passo(4)
                voce.update(esito=u"ok", passo=win.passo, profili=win.pnlProfili.Children.Count,
                            disegno=win.cnvAnteprima.Children.Count, errori=win.txtErrori.Text)
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


def guarda_modello(app, categoria):
    """Cosa c'e' gia' nel modello famiglia (finestre/porte): solidi, parametri, tipi."""
    from Autodesk.Revit import DB
    from infissi import catalogo as C
    from infissi import revit_famiglia as RF
    modello = C.trova_modello(categoria, [app.FamilyTemplatePath], C.carica_impostazioni())
    famdoc = app.NewFamilyDocument(modello)
    try:
        solidi = []
        for cls in (DB.Extrusion, DB.Sweep, DB.Blend, DB.Revolution, DB.SweptBlend, DB.FreeFormElement):
            for e in DB.FilteredElementCollector(famdoc).OfClass(cls):
                sc = e.Subcategory.Name if getattr(e, u"Subcategory", None) is not None else u""
                legati = []
                for p in e.Parameters:
                    try:
                        fp = famdoc.FamilyManager.GetAssociatedFamilyParameter(p)
                    except Exception:
                        fp = None
                    if fp is not None:
                        legati.append(u"%s -> %s" % (p.Definition.Name, fp.Definition.Name))
                solidi.append({u"classe": cls.__name__, u"id": RF._chiave_id(e.Id), u"sottocategoria": sc,
                               u"parametri": legati})
        fm = famdoc.FamilyManager
        parametri = [u"%s (%s)" % (p.Definition.Name, u"istanza" if p.IsInstance else u"tipo")
                     for p in fm.Parameters]
        istanze = [u"%s: %s" % (e.Category.Name if e.Category else u"?", e.Name)
                   for e in DB.FilteredElementCollector(famdoc).OfClass(DB.FamilyInstance)]
        mm = 304.8
        piani = []
        for rp in DB.FilteredElementCollector(famdoc).OfClass(DB.ReferencePlane):
            n = rp.Normal
            piani.append(u"%s  normale(%.0f,%.0f,%.0f)  a %.0f/%.0f/%.0f mm" % (
                rp.Name, n.X, n.Y, n.Z, rp.BubbleEnd.X * mm, rp.BubbleEnd.Y * mm, rp.BubbleEnd.Z * mm))
        muri = []
        for w in DB.FilteredElementCollector(famdoc).OfClass(DB.Wall):
            facce = []
            for lato in (DB.ShellLayerType.Exterior, DB.ShellLayerType.Interior):
                try:
                    for rif in DB.HostObjectUtils.GetSideFaces(w, lato):
                        f = w.GetGeometryObjectFromReference(rif)
                        facce.append(u"%s: origine y %.0f mm, normale y %.0f" % (
                            lato, f.Origin.Y * mm, f.FaceNormal.Y))
                except Exception as ex:
                    facce.append(u"%s: %s" % (lato, ex))
            muri.append({u"spessore_mm": w.Width * mm, u"facce": facce})
        aperture = [u"%s (%s)" % (o.GetType().Name, o.Name)
                    for o in DB.FilteredElementCollector(famdoc).OfClass(DB.Opening)]
        quote = []
        for d in DB.FilteredElementCollector(famdoc).OfClass(DB.Dimension):
            try:
                et = d.FamilyLabel.Definition.Name if d.FamilyLabel is not None else u""
            except Exception:
                et = u""
            nomi = []
            for r in d.References:
                el = famdoc.GetElement(r.ElementId)
                try:
                    nome = el.Name
                except Exception:
                    nome = u""
                nomi.append(u"%s %s" % (el.GetType().Name, nome))
            quote.append(u"%s %s" % (et, u", ".join(nomi)))
        viste = [u"%s %s" % (v.ViewType, v.Name) for v in DB.FilteredElementCollector(famdoc).OfClass(DB.View)
                 if not v.IsTemplate]
        return {u"file": modello, u"solidi": solidi, u"parametri": sorted(parametri),
                u"famiglie_annidate": istanze, u"piani": piani, u"muri": muri,
                u"aperture": aperture, u"quote": quote, u"viste": viste}
    finally:
        famdoc.Close(False)


def prova_palette(app):
    """Per ogni finestra/porta dei progetti aperti: e' un infisso CDV e quali strumenti CDV
    proporrebbe la palette selezionandola da sola."""
    from Autodesk.Revit import DB
    import tasti_overlay as TO
    out = []
    for doc in app.Documents:
        if doc.IsFamilyDocument:
            continue
        for e in DB.FilteredElementCollector(doc).OfClass(DB.FamilyInstance):
            cat = e.Category.Name if e.Category is not None else u""
            cdv = TO._infisso_cdv(doc, e)
            if not cdv and cat not in (u"Finestre", u"Porte", u"Windows", u"Doors"):
                continue
            gruppi, _m = TO._gruppi_cdv(doc, [e])
            out.append({u"documento": doc.Title, u"categoria": cat, u"cdv": cdv,
                        u"strumenti": [c for _g, tasti in gruppi for c, _e, _s in tasti]})
    return out


def foto_finestra(nome, modifica=False, contorno=False):
    """Immagini PNG del configuratore (passi 1-4, pianta) per guardarlo senza cliccare.
    La finestra si apre fuori dallo schermo e si chiude subito. Ritorna i percorsi."""
    _ricarica()
    import clr
    clr.AddReference("PresentationCore")
    from System.IO import File
    from System.Windows.Media import PixelFormats
    from System.Windows.Media.Imaging import PngBitmapEncoder, BitmapFrame, RenderTargetBitmap
    from infissi import catalogo as C
    from infissi import schema as S
    from infissi import ui as UI

    base = [s for s in C.preimpostati() if s[u"nome"] == nome][0]
    if contorno:
        base = con_tutto_il_contorno(base)
    cartella = os.path.join(tempfile.gettempdir(), u"CDV infissi prova", u"foto")
    if not os.path.isdir(cartella):
        os.makedirs(cartella)
    win = UI.Configuratore(schema=S.copia(base), nome_famiglia=nome if modifica else None, modifica=modifica)
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
        for n in range(2 if modifica else 1, 6):
            win.vai_al_passo(n)
            scatta(u"passo %d" % n)
        win.rbPianta.IsChecked = True
        scatta(u"pianta")
        win.cmbDettaglio.SelectedIndex = 0
        scatta(u"pianta basso")
        win.rbProspetto.IsChecked = True
        win.vai_al_passo(3)
        win.evid = (u"larghezza",)
        scatta(u"misura evidenziata")
    finally:
        win.Close()
    return out


def prova(app, nomi=None, varianti=True, salta=(), contorno=False, posizione=u"filo_esterno"):
    """[{nome, variante, esito, problemi, report|errore}] per ogni preset (e variante)."""
    _ricarica()
    from infissi import catalogo as C
    from infissi import revit_famiglia as RF
    from infissi import schema as S
    _salta(RF, salta)

    cartella = os.path.join(tempfile.gettempdir(), u"CDV infissi prova")
    if not os.path.isdir(cartella):
        os.makedirs(cartella)
    imp = C.carica_impostazioni()
    out = []
    for base in C.preimpostati():
        if nomi and base[u"nome"] not in nomi:
            continue
        prove = [(u"base", S.copia(base))]
        if contorno:
            prove = [(u"contorno " + posizione, con_tutto_il_contorno(base, posizione))]
        elif varianti:
            s = S.copia(base)
            s[u"maniglie"] = True
            s[u"simbolo_pianta"] = u"continuo"
            prove.append((u"maniglie+pianta", s))
        for variante, schema in prove:
            voce = {u"nome": base[u"nome"], u"variante": variante}
            modello = C.trova_modello(schema[u"categoria"], [app.FamilyTemplatePath], imp)
            if not modello:
                voce.update(esito=u"errore", errore=u"modello famiglia non trovato")
                out.append(voce)
                continue
            voce[u"modello"] = modello
            percorso = os.path.join(cartella, u"%s %s.rfa" % (base[u"nome"], variante))
            try:
                famdoc, report = RF.crea_famiglia(app, modello, schema, percorso)
                famdoc.Close(False)
                problemi = RF.problemi(report)
                voce.update(esito=u"da controllare" if problemi else u"ok", problemi=problemi,
                            report=dict((k, v) for k, v in report.items() if v))
            except Exception as ex:
                voce.update(esito=u"errore", errore=u"%s" % ex, traccia=traceback.format_exc())
                if getattr(ex, u"elementi", None):
                    voce[u"elementi"] = ex.elementi
            out.append(voce)
    return out
