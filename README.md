# CDV Tools per pyRevit

Estensione pyRevit con un solo tab, **CDV Tools**:

| Pannello | Pulsanti |
|---|---|
| **Viste** | Cambia livello della pianta, Profondità sezione (sfondo vettoriale), Copia ritaglio di vista, Aggiorna modello di vista |
| **Grafica** | Copia proprietà grafiche categoria/elemento tra viste (anche tra legende), Crea filtro da selezione |
| **Campiture** | Campitura da polilinea/offset, Campitura per sezione, Campitura sezionato, Campitura differenza |
| **Tavole** | Allinea viste su tavole, **Allinea in tavola** (un solo menu con allinea/distribuisci ritagli e titoli), Componenti in legenda, Ritaglia immagine, Allinea al Nord reale |
| **Modellazione** | Inverti muro sull'asse centrale; Palette On/Off e Personalizza Palette (piccoli) |

**Come si usano.** Prima selezioni, poi clicchi. I comandi che creano qualcosa con delle
impostazioni (campiture) le **ricordano**: un clic esegue subito con le ultime scelte,
**Maiusc+clic** apre la finestra per cambiarle (la finestra si apre da sola al primo uso o se
qualcosa non va). Anche le altre finestre si riaprono con le ultime opzioni scelte; le scelte
stanno in `%APPDATA%\pyRevit\CDVTools\finestre.json`.

**Avvisi.** L'esito dei comandi CDV (palette e pulsanti) compare come una riga di testo
piccola in basso a destra nella vista attiva: ✓ blu = fatto, ! arancio = fatto con qualche
errore, ✕ rosso = non si può fare. Sparisce da sola dopo pochi secondi, un messaggio nuovo
sostituisce il vecchio e lo stesso messaggio ripetuto mostra "×3". Niente più notifiche di
Windows; la finestra con OK resta solo per errori imprevisti e domande.

**Palette contestuale (stile ArchiCAD).** Quando selezioni qualcosa nella vista, accanto al
cursore compare una palette piccola:
- **sopra, la fila fissa**, uguale per tutte le categorie: **Crea simile** (con un solo
  elemento selezionato), Nascondi elementi, Nascondi categoria, Mezzitoni, **Copia grafica** (come il matchprop di AutoCAD: con un elemento
  selezionato clicchi quelli a cui copiarne la grafica nella vista, Esc per finire; con più
  elementi selezionati clicchi quello da cui copiarla) e Blocca/Sblocca;
- **sotto, i tasti famiglia**: prima, in azzurro con bordo blu, gli strumenti CDV della
  selezione (vedi sotto), poi **Trasforma** (Sposta, Copia, Ruota, Specchia, Serie, Scala),
  **Forma** (Allinea, Offset, Dividi, Taglia/Estendi), **Seleziona** (stesso tipo
  nella vista o nel progetto, stessa categoria), **Isola** (temporaneo). Il tasto mostra
  l'ultimo strumento usato della famiglia e un clic lo rifà; **passando sopra** si apre la
  griglia con tutti gli strumenti, icona e nome.

Come la mini barra di Word, la palette compare **semitrasparente**, diventa piena quando ci
vai sopra e **sparisce se allontani il mouse** (ricompare se torni vicino). I comandi di
modifica sono quelli di Revit e partono con la selezione già fatta; durante un comando la
palette sparisce e torna a comando finito, anche se lo annulli con Esc. Le icone sono disegnate da noi nello
stile di Revit (blu l'oggetto, arancio l'azione). Con una selezione mista compaiono solo gli
strumenti comuni. Se la selezione arriva dal browser di progetto la palette va sul bordo
superiore della selezione. **Palette On/Off** (pannello Modellazione) la spegne o la
riaccende; lo stato resta dopo il riavvio. **Personalizza Palette** apre una finestra dove
spunti, per ogni categoria, gli strumenti di ogni famiglia e scegli la fila fissa (al massimo
7); vale subito, senza riavviare. Le scelte stanno in `%APPDATA%\pyRevit\CDVTools\palette.json`.

**Doppio clic dove non c'è nulla** (in pianta, sezione, prospetto, dettaglio, legenda o
tavola): compare la palette delle annotazioni, con le famiglie **Quote** (allineata, lineare,
angolare, altimetrica), **Campiture** (regione di riempimento, area di mascheratura),
**Testo** ed **Etichette** (per categoria, materiale, locale, tutti gli elementi non
etichettati). Sono i comandi di Revit; un clic altrove la chiude.

Strumenti CDV della categoria (in tavola, cliccare il titolo seleziona la vista):
- linea di sezione o riquadro di una sezione con sfondo attivo: **Profondità sezione**
  (apre la finestra già su quella sezione) e **Sincronizza sfondo**; se lo sfondo non c'è
  ancora, solo **Attiva profondità sezione** (apre la finestra per crearlo);
- una vista in tavola: titolo a filo del ritaglio, linea del titolo = larghezza del ritaglio;
- due o più viste/titoli: incolonna/in riga i titoli, stessa distanza, stessa linea,
  allinea i riquadri (sinistra, centro, destra, alto, basso, coordinate del modello);
- tre o più: distribuisci in orizzontale/verticale.
- due o più oggetti del modello o di dettaglio: **Allinea oggetti** (sinistra, centro, destra,
  alto, basso sull'oggetto più esterno; i centri sul centro del gruppo) e, da tre, **Distribuisci
  oggetti** (gli estremi restano fermi); oggetti bloccati o in gruppi vengono saltati.
  Vale in pianta, sezione, prospetto, dettaglio e legenda, non nelle viste 3D.
- uno o più muri: **Inverti muro sul centro** (Maiusc+clic: linea di ubicazione su Asse del muro);
  accanto a ogni muro selezionato compaiono le lettere **E** (esterno, rossa) e **I** (interno, blu)
  sui due lati, in pianta e in sezione, così si vede subito come è girata la stratigrafia.
- una immagine raster: **Ritaglia immagine**.
- mentre sposti o zoomi la vista (rotellina) palette e lettere spariscono e tornano al loro posto.

La palette resta aperta, quindi puoi fare più allineamenti di fila; ogni tasto si annulla con
Ctrl+Z. Lo sfondo di una sezione si sposta sempre insieme alla sua madre. Si accende da solo
all'avvio (`startup.py`); su Revit 2023+ usa l'evento di selezione, prima controlla la
selezione a riposo.

## Installazione

1. Installa [pyRevit](https://github.com/pyrevitlabs/pyRevit) (4.8 o successivo).
2. In Revit apri **pyRevit > Extensions**, scrivi nel campo *Git URL*
   `<URL-del-repository>.git`, lascia *Path* e *Token* come sono
   e premi **Add and install**. Per aggiornare usa lo stesso Extension Manager (o pyRevit > Update).

   In alternativa, da riga di comando:
   ```
   pyrevit extend ui CDVTools <URL-del-repository>.git
   ```

## Struttura

La radice del repository è l'estensione: pyRevit la clona in una cartella `<nome>.extension`
dentro `%APPDATA%\pyRevit\Extensions`.

```
extension.json       manifest dell'estensione
startup.py           eseguito da pyRevit all'avvio
CDV Tools.tab/
  Viste.panel/ Grafica.panel/ Campiture.panel/ Tavole.panel/ Modellazione.panel/
tools/genera_icone.py  disegna le icone della ribbon (stile della palette)
lib/                 logica condivisa degli script
tests/               test della logica (pytest, senza Revit)
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
