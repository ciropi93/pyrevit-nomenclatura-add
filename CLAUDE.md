# CDV Tools (estensione pyRevit)

Un solo tab `CDV Tools.tab` (la radice del repo è l'estensione) con i pannelli Grafica e Filtri, Campiture,
Modellazione e Tavole. Utente: scrive in italiano; risposte brevi e semplici.

## Regole di lavoro
- Codice compatibile **IronPython 2.7** (motore predefinito di pyRevit): niente f-string, niente `print()` con keyword, stringhe `u"..."`.
- La logica senza API Revit sta in `lib/` e ha un test in `tests/`; le API Revit stanno negli `script.py` dei pulsanti.
- Il repository è pubblico: niente nomi di persone, clienti, progetti o codici commessa in codice, test, documenti e commit.

## Comandi
- Test: `python -m pytest -q tests`
- Lint: `python -m pyflakes lib tests`
