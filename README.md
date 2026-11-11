# Nomenclatura ADD per pyRevit

Estensione pyRevit che **controlla** e, se serve, **corregge** i nomi di un modello Revit
secondo le codifiche BIM dell'Agenzia del Demanio:

- BIM Method Statement `ADD2024-ADD-METHODSTP-XX-MS-Z-G00001` (§4.1 Sistemi di codifica)
- Allegato D (Codifica elementi), Allegato E (Codifica spazi), Allegato H (Codice documento), Allegato I (Codifica file)

## Pulsanti (scheda *NomenclaturaADD*)

| Pulsante | Cosa fa |
|---|---|
| **Controlla** | Scegli cosa controllare, ottieni un report con link agli elementi e, se vuoi, un CSV. |
| **Correggi** | Applica solo le correzioni sicure (spazi, accenti, maiuscole, progressivo a 2 cifre, contrassegno tipo, nome locale da Allegato E). Prima mostra l'elenco da confermare. Una sola transazione: si annulla con Ctrl+Z. |
| **Suggerisci** | Propone il nome codificato dai dati: categoria Revit → codice (MUR, SOL, POR...), funzione del muro → EST/INT, strati → categorie dei materiali + spessore totale, porte/finestre → larghezza x altezza, progressivo libero. Per i materiali usa la classe Revit (Calcestruzzo → CLC...). Lavora sulla selezione o su tutti i tipi usati. |
| **Importa CSV** | Rinomina in blocco: esporti il CSV con *Controlla*, compili la colonna `NuovoValore` in Excel, lo reimporti. |
| **Impostazioni** | Apre `%APPDATA%\NomenclaturaADD\progetto.json` (codice bene, codici fabbricato, fase, esclusioni). |

## Regole controllate

| Oggetto | Regola | Esempio | Fonte |
|---|---|---|---|
| File modello | `BENE-ADD-CF/CA/MGENERALE/MFEDERATO-Livello-TipoFile-Disciplina-ServizioStatoNNNN` | `AQD0031-ADD-CF1234567-ZZ-M3-U-PN0001` | BIMMS §4.1.1 |
| Livelli | `CodiceLivello-Disciplina` (+ suffisso di progetto `_BOX01`, `_GEN`) | `GF-A`, `01-S`, `GF-U_BOX01` | BIMMS §4.1.5.2 |
| Tipi | `TIPO-[SOTTOTIPO-]Descrizione-NN`, max 50 caratteri, niente caratteri speciali, PascalCase | `MUR-EST-VER_INC_CLC_INC_VER_290mm-01` | BIMMS §4.1.3, All. D |
| Famiglie caricabili | `TIPO-[SOTTOTIPO-]Descrizione` senza progressivo | `POR-AVV-Serranda` | convenzione di progetto (pGI) |
| Contrassegno tipo | `TIPO-[SOTTOTIPO-]NN` ricavato dal nome tipo | `MUR-EST-01` | convenzione di progetto (pGI) |
| Materiali | `Dettaglio-CATEGORIA-[SOTTOCATEGORIA-]Descrizione` | `1-CLC-STR-CA_C32/40_XC4_XF1_250mm` | BIMMS §4.1.4 |
| Locali | Numero `USO-NNN`, Nome = Nome uso dell'Allegato E | `BOX-001` / `Box auto` | BIMMS §4.1.5.1, All. E |
| Tavole | Numero = codice elaborato a 7 campi | `AQD0031-ADD-PLANGENER-ZZ-DR-Z-P00001` | BIMMS §4.1.2, All. H |

## Controlli incrociati (ambito "Coerenza")

| Controllo | Esempio di errore |
|---|---|
| Spessore nel nome = spessore reale della stratigrafia | `MUR-EST-..._300mm-01` ma il muro è 290 mm |
| Strati nel nome = categorie dei materiali degli strati (esterno → interno) | `INC_MRT_INC` ma gli strati sono `VER_INC_CLC_INC_VER` |
| Spessore nel nome del materiale = spessore dello strato | `1-CLC-STR-CA_C32/40_250mm` in uno strato da 300 mm |
| Sottotipo EST/INT = parametro Funzione del muro | `MUR-INT-...` con Funzione = Esterno |
| Dimensioni porte/finestre nel nome = larghezza x altezza del tipo | `POR-ADB-REI120_800x2100mm-01` ma larghezza 900 |

Esiti: **ERRORE** = non conforme al BIMMS; **AVVISO** = ammesso ma da dichiarare nel pGI
(es. sottotipo non presente nell'Allegato D come `POR-SEZ`, suffisso livello, `/` nelle classi del cls,
dettaglio materiale non previsto per la fase).

Viste e schede di vista non sono normate dal BIMMS e per ora non vengono controllate.

## Installazione

1. Installa [pyRevit](https://github.com/pyrevitlabs/pyRevit) (4.8 o successivo).
2. Da riga di comando:
   ```
   pyrevit extend ui NomenclaturaADD https://github.com/<utente>/pyrevit-nomenclatura-add.git
   ```
   oppure copia la cartella `NomenclaturaADD.extension` in una cartella di estensioni
   (pyRevit > Settings > Custom Extension Directories) e fai *Reload*.
3. Apri **Impostazioni** e controlla codice bene, codici fabbricato/area e fase (`servizio`: `P` = PFTE).

## Struttura

```
NomenclaturaADD.extension/
  NomenclaturaADD.tab/Nomenclatura.panel/   pulsanti (script.py + bundle.yaml + icon.png)
  lib/nomenclatura/
    regole.py        regole di codifica (senza API Revit, testabile)
    revit_dati.py    lettura e scrittura dei nomi in Revit
    tabella.py       CSV per Excel (separatore ;)
    ui.py            finestre e report pyRevit
    data/codici_add2024.json   codici estratti dagli allegati (tipi, sottotipi, usi, documenti...)
    data/progetto.json         impostazioni predefinite del progetto
tests/               test delle regole (pytest, senza Revit)
```

## Test

```
pip install pytest
python -m pytest -q tests
```
