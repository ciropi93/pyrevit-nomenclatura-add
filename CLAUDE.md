# CDV Tools (estensione pyRevit)

Un solo tab `CDV Tools.tab` (la radice del repo è l'estensione) con i pannelli Grafica e Filtri, Campiture,
Modellazione, Infissi, Tavole e Nomenclatura. Le note qui sotto riguardano il pannello **Nomenclatura ADD**;
il pannello **Infissi** ha la logica in `lib/infissi/` (API Revit solo in `revit_famiglia.py` e `ui.py`, test in `tests/test_infissi.py`).

Controlla e corregge i nomi di un modello Revit secondo il BIMMS ADD2024 dell'Agenzia del Demanio
(progetto Sulmona, codice bene AQD0031). Utente: Ciro, scrive in italiano; risposte brevi e semplici.

## Regole di lavoro
- Codice compatibile **IronPython 2.7** (motore predefinito di pyRevit): niente f-string, niente `print()` con keyword, stringhe `u"..."`.
- La logica sta in `lib/nomenclatura/regole.py` e `suggerimenti.py` **senza API Revit**: ogni regola nuova va lì con un test in `tests/`.
- Le API Revit stanno solo in `revit_dati.py` (lettura/scrittura) e negli `script.py` dei pulsanti.
- Ogni scrittura nel modello passa da `revit_dati.applica_lista` (una transazione, annullabile) dopo conferma dell'utente.
- Esiti: ERRORE = non conforme al BIMMS; AVVISO = ammesso ma da dichiarare nel pGI.
- Dati ufficiali in `lib/nomenclatura/data/codici_add2024.json` e `proprieta_add2024.json`; fonti, incoerenze e lacune in `docs/knowledge-base.md`. Non inventare codici: se non sono nei documenti dell'Agenzia, sono AVVISO "da pGI".

## Comandi
- Test: `python -m pytest -q tests`
- Lint: `python -m pyflakes lib "CDV Tools.tab/Nomenclatura.panel" "CDV Tools.tab/Infissi.panel" tests`
