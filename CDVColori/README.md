# CDV Colori

Piccolo programma per Windows che si aggancia alla finestra **Colore** di Revit e le aggiunge:

- un pulsante **contagocce** a sinistra di "Aggiungi": prende un colore da qualsiasi punto dello
  schermo (anche fuori da Revit) con una lente d'ingrandimento:
  - clic: prende il colore e termina; **Maiusc+clic**: prende il colore (va nei Recenti) e continua;
  - **1 / 3 / 5**: area di campionamento 1×1, 3×3, 5×5 pixel (media: più preciso su linee e bordi sfumati);
  - **rotellina**: zoom della lente; **frecce**: spostano il cursore di 1 pixel; **Invio**: prende il punto attuale;
  - clic destro o `Esc`: annulla;
- un **pannello palette** accanto alla finestra:
  - palette illimitate, colori recenti, campo per scrivere `#RRGGBB` o `R,G,B`;
  - clic su un colore: lo imposta nella finestra Colore; doppio clic: lo imposta e preme OK;
  - **ricerca** in tutte le palette per nome, gruppo o HEX;
  - **gruppi** dentro la palette (es. Anello interno / medio / esterno nella Base);
  - **trascina** i colori per riordinarli o spostarli in un altro gruppo (anche sull'intestazione del gruppo);
  - "+ Aggiungi colore attuale": salva nella palette il colore impostato nella finestra;
  - tasto destro su un colore: rinomina, sposta nel gruppo, elimina, copia HEX, usa come base per le varianti;
  - menu "…": nuova/rinomina/elimina palette, **cambia cartella palette** (anche di rete), ripristina Base;
- **varianti** del colore attuale, con 4 modalità: **Luminosità** (più scuro ← → più chiaro),
  **Saturazione** (grigio ← → pieno), **Tinta** (±10° per passo), **Armonie** (complementare, analoghi,
  triade, complementari divisi); da 2 a 6 varianti per lato. La riga segue il colore della finestra e resta
  ferma quando scegli una sua variante. Tasto destro: "Usa come colore base", "Aggiungi alla palette", copia HEX.

- **estrai palette da immagine** (menu "…" del pannello o menu dell'icona): apri un file, incolla
  (Ctrl+V), trascina un file nella finestra oppure **cattura una zona dello schermo**. Il programma trova i
  colori "piatti" (esclude testo e bordi sfumati), li numera sull'immagine e li elenca: spunta quelli da tenere,
  rinominali (F2) e crea una nuova palette o aggiungili a una esistente. Regolazioni: numero massimo di
  colori, soglia di **fusione** dei colori simili (più bassa = più colori distinti), ignora bianco/nero,
  ordine per area o per tinta. Con le foto (niente zone piatte) usa colori medi per gruppi simili.

La finestra di Revit resta quella originale: PANTONE, "Nessuna sostituzione" ecc. funzionano come prima.

## Come funziona (e perché è sicuro)

Il programma non entra in Revit e non ne modifica i file. Osserva Windows dall'esterno e,
quando compare la finestra Colore, le mette accanto le sue finestre. Il colore viene passato con i messaggi
standard di Windows e scritto nei campi Rosso/Verde/Blu, come faresti tu digitandoli.
Il mouse viene "agganciato" solo mentre usi il contagocce.

Non servono installazione né diritti di amministratore: basta .NET Framework 4.8, già presente
in Windows 10/11.

## Uso

1. Copia `CDVColori.exe` dove vuoi (es. `Documenti\CDVColori`) e avvialo. Compare l'icona nell'area di notifica.
   Al primo avvio Windows può mostrare "PC protetto": *Ulteriori informazioni → Esegui comunque*.
2. In Revit apri una finestra Colore: compaiono contagocce e pannello.
3. Menu dell'icona (tasto destro): attiva/pausa, mostra o nascondi pannello e contagocce, contagocce
   "libero" (copia l'HEX negli appunti), cartella palette, impostazioni, **Diagnosi**, avvio con Windows.

## Palette

Ogni palette è un file JSON nella cartella palette (predefinita `%APPDATA%\CDVColori\palette`):

```json
{
  "nome": "Studio CDV",
  "colori": [
    {"nome": "Demolizioni", "hex": "#FFFF00", "gruppo": "Stato di progetto"},
    {"nome": "Costruzioni", "hex": "#FF0000", "gruppo": "Stato di progetto"}
  ]
}
```

`gruppo` è facoltativo.

Per condividerle con i colleghi metti in `config.json` (menu → Apri impostazioni) una cartella di rete:

```json
"cartellaPalette": "\\\\server\\progetti\\CDV\\palette"
```

Al primo avvio viene creata la palette **Base** (39 colori del diagramma a corona Materialen / Energie /
Klimaatadaptatie / Stikstof). Se la modifichi o la elimini, dal menu "…" del pannello c'è
"Ripristina palette di base" (serve anche per avere i gruppi se la Base è stata creata con la versione 0.1).

I **Recenti** sono personali (`%APPDATA%\CDVColori\recenti.json`).

La cartella si cambia anche dal pannello (menu "…" → Cambia cartella palette).

Altre impostazioni in `config.json`: `programmi` (default `["Revit"]`, `"*"` = tutti i programmi
che usano la finestra colori di Windows), `mostraPannello`, `mostraContagocce`.

## Se qualcosa non va

Con la finestra Colore aperta: menu dell'icona → **Diagnosi finestra Colore**. Crea
`CDVColori_diagnosi.txt` sul Desktop con l'elenco dei campi della finestra. Il registro degli errori è in
`%APPDATA%\CDVColori\log.txt`.

Nota sul contagocce: in una vista di Revit il colore a schermo può differire da quello impostato
(ombreggiatura, luci, trasparenza, antialiasing delle linee). Per risultati esatti campiona aree piene.

## Compilazione

Serve il .NET SDK (anche su Linux): `./build.sh` lancia i test della logica (`tests/`, xUnit) e
compila `build/CDVColori.exe`.
