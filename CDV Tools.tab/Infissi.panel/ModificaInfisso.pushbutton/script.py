# -*- coding: utf-8 -*-
"""Modifica infisso: riapre lo schema di un infisso CDV e rigenera la sua famiglia."""
from pyrevit import DB, revit, script

from infissi import parametri as PA
from infissi import revit_famiglia as RF
from infissi import schema as S
import avviso_wpf as AVW
from infissi import ui as UI


def _nome(elemento):
    """Nome del tipo. Su FamilySymbol .Name puo' non andare in IronPython; le proprieta' .NET
    lette dalla classe vogliono __get__ (GetValue e' di pythonnet e qui non esiste)."""
    try:
        p = elemento.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        if p is not None and p.AsString():
            return p.AsString()
    except Exception:
        pass
    try:
        return elemento.Name
    except Exception:
        return DB.Element.Name.__get__(elemento)


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
        AVW.errore(u"Apri un progetto (non una famiglia)")
        return
    doc = uidoc.Document
    istanza = _istanza(uidoc)
    if istanza is None:
        script.exit()
    tipo = doc.GetElement(istanza.GetTypeId())
    try:
        schema = RF.schema_del_tipo(tipo)
    except S.SchemaErrore as ex:
        AVW.errore(u"Lo schema salvato nella famiglia è rovinato: %s" % ex)
        return
    if schema is None:
        AVW.errore(u"Questo elemento non è stato creato con il Configuratore infissi")
        return
    famiglia = tipo.Family
    risultato = UI.apri(schema=schema, nome_famiglia=famiglia.Name, modifica=True)
    if not risultato:
        script.exit()
    tipi, saltati = _tipi(doc, famiglia, tipo, risultato[u"schema"])
    famiglia_nuova = UI.crea_e_carica(uidoc, risultato, tipi, posiziona=False)
    if famiglia_nuova is not None and saltati:
        # i tipi con misure che non stanno nel nuovo schema restano com'erano: lo si dice dopo
        AVW.attenzione(u"Tipi rimasti com'erano (misure fuori dal nuovo schema): " + u", ".join(saltati))


if __name__ == "__main__":
    main()
