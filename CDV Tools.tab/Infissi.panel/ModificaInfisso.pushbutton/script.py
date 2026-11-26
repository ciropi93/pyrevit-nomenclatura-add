# -*- coding: utf-8 -*-
"""Modifica infisso: riapre lo schema di un infisso CDV e rigenera la sua famiglia."""
from pyrevit import DB, revit, script

from infissi import parametri as PA
from infissi import revit_famiglia as RF
from infissi import schema as S
from infissi import ui as UI

forms = UI.forms


def _nome(elemento):
    try:
        return elemento.Name
    except Exception:
        return DB.Element.Name.GetValue(elemento)


def _istanza(uidoc):
    doc = uidoc.Document
    for eid in uidoc.Selection.GetElementIds():
        el = doc.GetElement(eid)
        if isinstance(el, DB.FamilyInstance):
            return el
    try:
        from Autodesk.Revit.UI.Selection import ObjectType
        rif = uidoc.Selection.PickObject(ObjectType.Element, u"Seleziona un infisso CDV")
        el = doc.GetElement(rif)
        return el if isinstance(el, DB.FamilyInstance) else None
    except Exception:
        return None


def _tipi(doc, famiglia, tipo_scelto, schema_nuovo):
    """Tutti i tipi della famiglia con lo schema nuovo e le loro misure; quello scelto per primo."""
    tipi = [(_nome(tipo_scelto), schema_nuovo)]
    saltati = []
    for sid in famiglia.GetFamilySymbolIds():
        if sid == tipo_scelto.Id:
            continue
        t = doc.GetElement(sid)
        try:
            vecchio = RF.schema_del_tipo(t)
            valori = PA.valori_input(PA.elenco(vecchio)) if vecchio else {}
            s = PA.schema_da_valori(schema_nuovo, valori)
            PA.elenco(s)        # controlla che le misure stiano nel nuovo schema
            tipi.append((_nome(t), s))
        except Exception:
            saltati.append(_nome(t))
    return tipi, saltati


def main():
    uidoc = revit.uidoc
    if uidoc is None or uidoc.Document.IsFamilyDocument:
        forms.alert(u"Apri un progetto (non una famiglia).", title=UI.TITOLO)
        return
    doc = uidoc.Document
    istanza = _istanza(uidoc)
    if istanza is None:
        script.exit()
    tipo = doc.GetElement(istanza.GetTypeId())
    try:
        schema = RF.schema_del_tipo(tipo)
    except S.SchemaErrore as ex:
        forms.alert(u"Lo schema salvato nella famiglia e' rovinato:\n%s" % ex, title=UI.TITOLO)
        return
    if schema is None:
        forms.alert(u"Questo elemento non e' stato creato con il Configuratore infissi "
                    u"(manca il parametro \"%s\")." % PA.SCHEMA, title=UI.TITOLO)
        return
    famiglia = tipo.Family
    risultato = UI.apri(schema=schema, nome_famiglia=famiglia.Name, modifica=True)
    if not risultato:
        script.exit()
    tipi, saltati = _tipi(doc, famiglia, tipo, risultato[u"schema"])
    if saltati:
        if not forms.alert(u"Con il nuovo schema questi tipi non stanno e restano come sono:\n- " +
                           u"\n- ".join(saltati) + u"\n\nContinuo?", title=UI.TITOLO, yes=True, no=True):
            return
    UI.crea_e_carica(uidoc, risultato, tipi, posiziona=False)


if __name__ == "__main__":
    main()
