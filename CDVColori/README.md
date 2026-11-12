# CDV Colori

Piccolo programma per Windows che si aggancia alla finestra **Colore** di Revit e le aggiunge:

- un pulsante **contagocce** a sinistra di "Aggiungi": prende un colore da qualsiasi punto dello
  schermo (anche fuori da Revit) con una lente d'ingrandimento; clic destro o `Esc` per annullare;
- un **pannello palette** accanto alla finestra: palette illimitate, colori recenti, campo per
  scrivere `#RRGGBB` o `R,G,B`.
  - clic su un colore: lo imposta nella finestra Colore;
  - doppio clic: lo imposta e preme OK;
  - "+ Aggiungi colore attuale": salva nella palette il colore impostato nella finestra;
  - tasto destro su un colore: rinomina, sposta, elimina, copia HEX;
  - **varianti**: riga con il colore attuale al centro, 4 varianti più scure a sinistra e 4 più chiare
    a destra (stessa tinta e saturazione, luminosità a passi uguali verso nero e bianco). Si aggiorna da sola
    quando il colore cambia; scegliendo una variante la riga resta ferma. Tasto destro: "Usa come colore base",
    "Aggiungi alla palette", copia HEX.

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
    {"nome": "Demolizioni", "hex": "#FFFF00"},
    {"nome": "Costruzioni", "hex": "#FF0000"}
  ]
}
```

Per condividerle con i colleghi metti in `config.json` (menu → Apri impostazioni) una cartella di rete:

```json
"cartellaPalette": "\\\\server\\progetti\\CDV\\palette"
```

Al primo avvio viene creata la palette **Base** (39 colori del diagramma a corona Materialen / Energie /
Klimaatadaptatie / Stikstof). Se la modifichi o la elimini, dal menu "…" del pannello c'è
"Ripristina palette di base".

I **Recenti** sono personali (`%APPDATA%\CDVColori\recenti.json`).

Altre impostazioni in `config.json`: `programmi` (default `["Revit"]`, `"*"` = tutti i programmi
che usano la finestra colori di Windows), `mostraPannello`, `mostraContagocce`.

## Se qualcosa non va

Con la finestra Colore aperta: menu dell'icona → **Diagnosi finestra Colore**. Crea
`CDVColori_diagnosi.txt` sul Desktop con l'elenco dei campi della finestra. Il registro degli errori è in
`%APPDATA%\CDVColori\log.txt`.

Nota sul contagocce: in una vista di Revit il colore a schermo può differire da quello impostato
(ombreggiatura, luci, trasparenza, antialiasing delle linee). Per risultati esatti campiona aree piene.

## Compilazione

Serve il .NET SDK (anche su Linux): `./build.sh` → `build/CDVColori.exe`.
