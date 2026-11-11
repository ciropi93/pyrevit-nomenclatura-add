# Knowledge base del plugin: fonti, copertura, problemi noti

Verifica del 2026-11-11 su tutti i documenti delle cartelle `CODIFICHE BIM/` e `BIM Share/` del progetto Sulmona (AQD0031).

## Fonti e cosa ne usa il plugin

| Documento | Contenuto | Nel plugin |
|---|---|---|
| BIMMS `ADD2024-ADD-METHODSTP-XX-MS-Z-G00001` §4.1.1 | Codifica modelli (7 campi), Tab. 11-16 | `regole.controlla_file_modello` + `codici_add2024.json` |
| BIMMS §4.1.2 + Allegato H | Codifica elaborati, 147 codici documento | `regole.controlla_tavola`, `codici_documento` |
| BIMMS §4.1.3 Tab. 23-24 + Allegato D | Codifica elementi, tipi e sottotipi | `regole.controlla_elemento`, `tipi_elemento` (unione D + Tab. 23-24) |
| BIMMS §4.1.4 Tab. 25-28 | Codifica materiali | `regole.controlla_materiale` |
| BIMMS §4.1.5.1 + Allegato E | Codifica spazi, 60 codici uso | `regole.controlla_numero_locale` / `controlla_nome_locale` |
| BIMMS §4.1.5.2 Tab. 30 | Codifica livelli | `regole.controlla_livello` |
| Allegato I | Tipo file e terzo campo ammessi per categoria/disciplina | regole di coerenza in `controlla_file_modello` |
| Allegato A, B | PSet e proprietà (277 + 20) | estratti in `data/proprieta_add2024.json`, **non ancora controllati** |
| Allegato C | Proprietà elementi/oggetti/vegetazione (tabella ruotata) | non estratto |
| Allegato F | Destinazioni d'uso del Bene (proprietà `DestinazioneUso`) | non usato (riguarda il Bene, non i locali) |
| Allegato G | Autorizzazioni upDATe | non pertinente |
| Errata corrige ADD2023 | Cartelle upDATe (cap. 5) | non pertinente alla nomenclatura |
| Specifica `23_AQD0031_ADM-SPECPFTE_2.1` | Codice bene AQD0031; chiede di codificare "modelli, elaborati, elementi, viste, materiali" secondo il BIMMS | codice bene in `progetto.json`. **Codice fabbricato non indicato** (Tab. 4 riporta solo "Denominazione AQD0031"): va chiesto all'Agenzia |
| Specifica `AQD0031-ADM-SPECIFRIL` | Rilievo (stessa struttura) | nessun codice aggiuntivo |

## Correzioni fatte in questa verifica

- **Codici elemento mancanti** (l'Allegato D è meno completo della Tab. 24 del BIMMS): aggiunti `ANT-SPK` (sprinkler, perso in estrazione), `FCO-RIM`, `ELR-REM`, `MAC-GRU/MSR/MSC`, 45 sottotipi `ARR-*` (TAV, SGA, DIV, POL, ARM...), tipo `PNT` (Tab. 23). Nel JSON sono marcati `[solo BIMMS Tab.24]`.
- **Codici documento mancanti**: `PROFILIID`, `PROFILIST`, `TRACCIAM`, `RELBARARC`, `PIAGEOSTR`.
- **Livelli**: il BIMMS §4.1.5.2 cita solo A e S come disciplina del livello. Ora `GF-U` ecc. è un AVVISO (da dichiarare nel pGI), non più OK.
- **File modello** (BIMMS §4.1.1.4 N.B. + Allegato I): federati C/K/Y solo M2 o MR; MFEDERATO solo M2/MR/PC; MGENERALE solo M3/MR/PC; disciplina Y solo con MFEDERATO.

## Incoerenze nei documenti dell'Agenzia (il plugin accetta entrambe le forme)

| Punto | Documento A | Documento B |
|---|---|---|
| Rete metallica | Allegato D: `ELR-RES` | BIMMS Tab. 24: `ELR-REM` |
| Gru e mezzi | Allegato D: sotto `TRA` | BIMMS Tab. 24: sotto `MAC` |
| Rapporti di prova | BIMMS Tab. 20: `RAPPROVA` | Allegato H: `RAPDPROVA` |
| `/` nei materiali | BIMMS §4.1.4 lo vieta | esempio BIMMS `1-CLC-STR-CA_C35/45` lo usa → AVVISO |
| Esempio elemento | regola: 4 campi | esempio BIMMS `SOL-STR-CLC_MRT-350mm-02` ha 5 campi → ERRORE |
| PSet | Tab. 32: `ElementoDatiIndagini`, `OggettoDatiQualitativo` | Allegato A: `ElementoDatiIdagini`, `OggettoDatiQualitativi`; in A anche `ElementoDatiQuantitativi`, `SpazioCodifica`, `VegetazioneDatiManutenzione` che Tab. 32 non elenca |
| Proprietà | regola: niente spazi | Allegato A: `Classe Energetica Complessiva` |

## Convenzioni di progetto (non nel BIMMS, da dichiarare nel pGI)

Nome famiglia `TIPO-[SOTT-]Descrizione`; Type Mark `TIPO-[SOTT-]NN`; suffisso livelli `_BOX01`/`_GEN`; Revit Numero locale = codice spazio, Nome = nome uso; sottotipi aggiuntivi tipo `POR-SEZ`, `POR-BAS`.

## Non coperto (possibili prossimi passi)

1. **Proprietà/parametri** (Allegati A, B, C): verificare che i parametri condivisi abbiano i nomi e i PSet giusti e che quelli obbligatori siano compilati (es. `ElementoCodifica.CodiceElemento` = nome tipo, `SpazioCodifica.CodiceSpazio` = numero locale). I dati di A e B sono già in `proprieta_add2024.json`.
2. **Classificazione UNI 8290** (BIMMS §4.2, Tab. 33) per `ElementoCodifica.ClasseElementoTecnico`.
3. **Viste**: la specifica AQD0031 chiede di codificarle, ma il BIMMS non dà una regola. Rimandato per scelta di Ciro (2026-11-11): non implementare per ora.
4. **Disciplina per tipo elemento** (colonna disciplina dell'Allegato D, es. FNT→A, ELM→S): utile per segnalare elementi nel modello sbagliato, ma la colonna estratta è poco affidabile e va verificata a mano.
5. **Codice fabbricato**: si inserisce dal pulsante Impostazioni (`codice_fabbricato`); il valore reale va chiesto all'Agenzia.
