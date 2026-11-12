# CDV Tools per pyRevit

Estensione pyRevit con un solo tab, **CDV Tools**:

| Pannello | Pulsanti |
|---|---|
| **Grafica e Filtri** | Copia proprietà grafiche categoria/elemento, Aggiorna modello di vista, Copia ritaglio di vista, Cambia livello della pianta, Crea filtro da selezione |
| **Campiture** | Campitura da polilinea/offset, Campitura da sezione |
| **Modellazione** | Inverti muro sull'asse centrale |
| **Tavole e Legende** | Allinea viste su tavole, Componenti in legenda, Allinea al Nord reale |
| **Nomenclatura** | Controllo e correzione dei nomi secondo il BIMMS ADD2024 (vedi sotto) |

## Nomenclatura ADD

Il pannello **Nomenclatura** **controlla** e, se serve, **corregge** i nomi di un modello Revit
secondo le codifiche BIM dell'Agenzia del Demanio:

- BIM Method Statement `ADD2024-ADD-METHODSTP-XX-MS-Z-G00001` (§4.1 Sistemi di codifica)
- Allegato D (Codifica elementi), Allegato E (Codifica spazi), Allegato H (Codice documento), Allegato I (Codifica file)

### Pulsanti (pannello *Nomenclatura*)

| Pulsante | Cosa fa |
|---|---|
| **Controlla** | Scegli cosa controllare, ottieni un report con link agli elementi e, se vuoi, un CSV. |
| **Correggi** | Applica solo le correzioni sicure (spazi, accenti, maiuscole, unità di misura, progressivo a 2 cifre, contrassegno tipo, nome locale da Allegato E). Prima mostra l'elenco da confermare: sono già spuntate solo le correzioni di errori senza conflitti; quelle che nascono da un AVVISO o che porterebbero a un nome già in uso/doppio vanno spuntate a mano. Una sola transazione: si annulla con Ctrl+Z. |
| **Suggerisci** | Propone il nome codificato dai dati: categoria Revit → codice (MUR, SOL, POR...), funzione del muro → EST/INT, strati → categorie dei materiali + spessore totale, porte/finestre → larghezza x altezza, progressivo libero. Per i materiali usa la classe Revit (Calcestruzzo → CLC...). Lavora sulla selezione o su tutti i tipi usati. |
| **Importa CSV** | Rinomina in blocco: esporti il CSV con *Controlla*, compili la colonna `NuovoValore` in Excel, lo reimporti. Vedi [Importa CSV](#importa-csv). |
| **Impostazioni** | Finestra per inserire **codice fabbricato** (CF + 7 cifre), codice bene e fase, oppure per aprire il file delle impostazioni del progetto (`NomenclaturaADD.json` accanto al modello) o quello personale (`%APPDATA%\NomenclaturaADD\progetto.json`). I valori si salvano nel file del progetto se esiste, altrimenti in quello personale. Il codice fabbricato viene usato nei controlli di file modello e tavole (segnaposto `CFNNNNNNN` o codice diverso = errore, con correzione proposta per le tavole). Vedi [Impostazioni](#impostazioni). |

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

Altri controlli:

- **Progressivo univoco**: due tipi con lo stesso `TIPO-[SOTTOTIPO-]NN` (es. `MUR-EST-MuroA-01` e
  `MUR-EST-MuroB-01`) darebbero lo stesso contrassegno tipo: è un ERRORE.
- **Spazi all'inizio o alla fine** del nome: ERRORE, con proposta del nome ripulito.
- **Lettere accentate e caratteri non ASCII** (`Ü`, `×`, `²`…): ERRORE; la proposta li sostituisce
  quando c'è un equivalente sicuro (`U`, `x`, `2`).
- **Nome locale vuoto**: ERRORE (proposta dall'Allegato E se l'uso ha un solo nome).

Viste e schede di vista non sono normate dal BIMMS e per ora non vengono controllate.

## Impostazioni

Le impostazioni si sommano in quest'ordine (l'ultima prevale, i blocchi `{...}` si fondono voce per voce):

1. predefinite del plugin (`lib/nomenclatura/data/progetto.json`);
2. personali: `%APPDATA%\NomenclaturaADD\progetto.json`;
3. **di progetto**: `NomenclaturaADD.json` nella cartella del modello (per i modelli condivisi,
   quella del file centrale). Qui vanno codice bene, codici fabbricato/area e fase della commessa.

Il file di progetto si crea dal pulsante *Impostazioni* e basta scriverci le voci che cambiano.
Per i modelli su cloud (ACC/BIM 360) o non ancora salvati valgono solo le impostazioni personali.
Se un file non è un JSON valido, il plugin lo segnala con il percorso e la riga dell'errore.
Il report di *Controlla* elenca i file di impostazioni usati.

## Importa CSV

- Il CSV contiene la colonna `Modello`: se viene da un altro modello il plugin chiede conferma.
- Prima di rinominare confronta il valore nel modello con `ValoreAttuale` del CSV: se sono diversi
  (CSV di un altro modello o modello cambiato dopo l'esportazione) la riga viene scartata.
- In Excel si può salvare sia come "CSV UTF-8" sia come "CSV (delimitato dal separatore di elenco)".
- Le righe il cui nuovo valore resta in ERRORE, o è già usato da un altro elemento, non sono spuntate.

## Installazione

1. Installa [pyRevit](https://github.com/pyrevitlabs/pyRevit) (4.8 o successivo).
2. Clona il repository e aggiungi la sua cartella ai percorsi delle estensioni, poi fai *Reload*:
   ```
   git clone https://github.com/ciropi93/pyrevit-nomenclatura-add.git
   pyrevit extensions paths add <cartella>\pyrevit-nomenclatura-add
   ```
   (oppure pyRevit > Settings > Custom Extension Directories). Per aggiornare basta `git pull` e *Reload*.
3. Apri **Impostazioni** e inserisci il codice fabbricato; controlla codice bene e fase (`P` = PFTE).

## Struttura

```
CDVTools.extension/
  CDV Tools.tab/
    Grafica e Filtri.panel/ Campiture.panel/ Modellazione.panel/ Tavole.panel/
    Nomenclatura.panel/   pulsanti (script.py + bundle.yaml + icon.png)
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

La CI esegue i test anche con Python 2.7 (il più vicino a IronPython 2.7 di pyRevit):

```
docker run --rm -v "$PWD":/src -w /src python:2.7-slim sh -c 'pip install -q "pytest<5" && python -m pytest -q -p no:cacheprovider tests'
```
