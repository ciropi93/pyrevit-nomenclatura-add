# CDV Tools (estensione pyRevit)

Un solo tab `CDV Tools.tab` (la radice del repo è l'estensione) con i pannelli Viste, Grafica, Campiture,
Tavole, Modellazione e Infissi. Utente: scrive in italiano; risposte brevi e semplici.
Il pannello **Infissi** ha la logica in `lib/infissi/` (API Revit solo in `revit_famiglia.py` e `ui.py`, test in `tests/test_infissi.py`).

## Regole di lavoro
- Codice compatibile **IronPython 2.7** (motore predefinito di pyRevit): niente f-string, niente `print()` con keyword, stringhe `u"..."`.
- La logica senza API Revit sta in `lib/` e ha un test in `tests/`; le API Revit stanno negli `script.py` dei pulsanti.
- Flusso dei comandi: prima si seleziona, poi si clicca. Le finestre ricordano le ultime scelte con `lib/memoria_finestre.py`; i comandi con impostazioni eseguono subito con quelle salvate e Maiusc+clic (`EXEC_PARAMS.config_mode`) apre la finestra.
- Finestre: nessuno stile proprio nei `ui.xaml`; si caricano con `SF.xaml(...)` di `lib/stile_finestre.py` (stili `Intestazione`, `Scheda`, `Etichetta`, `Primario`; colori della tavolozza delle icone). Opzioni rare in un `Expander` "Opzioni avanzate".
- I comandi "sorgente nota + elenco da spuntare" usano la finestra condivisa `lib/scelta_wpf.py` (`SCW.scegli`); le voci degli elenchi sono `elenco_wpf.Voce`. Una domanda sola per comando; niente popup di conferma.
- Esiti con `avviso_wpf.mostra` (riga in basso a destra), non con popup.
- Icone: `python tools/genera_icone.py`.
- Il repository è pubblico: niente nomi di persone, clienti, progetti o codici commessa in codice, test, documenti e commit.

## Comandi
- Test: `python -m pytest -q tests`
- Lint: `python -m pyflakes lib "CDV Tools.tab/Infissi.panel" tests`
