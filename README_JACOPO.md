# 👉 TPIMS Poller — cosa devi fare TU (10 minuti, una volta sola)

Questo mini-progetto scarica **ogni 15 minuti** i posti-camion liberi **REALI** di
**Illinois, Indiana, Kentucky, Minnesota, Ohio** (feed pubblici TPIMS, nessuna
registrazione). Gira **gratis** su GitHub Actions, i cui server sono **in USA** —
per questo funziona anche se dall'Italia i feed rispondono "403 Forbidden".

**A cosa serve:** è il nostro "controllo di realtà". Confrontiamo le stime del
motore con l'occupazione vera, e usiamo questi dati come **etichette per
addestrare il modello predittivo** (le ore di sera/notte che il satellite non vede).
È il mattone n.1 per rendere il sistema davvero predittivo.

---

## ⚠️ Prima cosa: fai il repo PUBBLICO (non privato)

Girando ogni 15 minuti servono ~2.900 esecuzioni al mese. Un repo **privato** ha solo
2.000 minuti gratis/mese → li sforeremmo. Un repo **pubblico** ha **minuti illimitati e gratis**,
e i dati sono comunque dati pubblici DOT (nessun segreto). → **Scegli Public.**

---

## Strada A — senza terminale (consigliata, tutto dal browser)

1. **Crea il repo:** vai su https://github.com/new
   - Repository name: `parkalive-tpims-poller`
   - Seleziona **Public** ✔
   - Spunta **"Add a README file"** → **Create repository**

2. **Carica i file:** nel repo appena creato clicca **Add file → Upload files**.
   - Trascina dentro **tutto il contenuto** della cartella `tpims-poller/`:
     `poll_tpims.py`, `README_JACOPO.md`, e — **importante** — la cartella nascosta **`.github`**
     (contiene il "programma" che fa partire tutto ogni 15 min).
   - ⚠️ Se dal Finder non vedi `.github` (le cartelle che iniziano con punto sono nascoste):
     premi **Cmd + Shift + .** nel Finder per mostrarle, poi trascinala.
   - In fondo alla pagina → **Commit changes**.

3. **Dai il permesso di scrittura:** **Settings → Actions → General** →
   sezione "Workflow permissions" → scegli **Read and write permissions** → **Save**.

4. **Accendi e prova:** tab **Actions** in alto → se compare un avviso, clicca
   **"I understand my workflows, go ahead and enable them"** →
   apri **"TPIMS poller"** a sinistra → bottone **Run workflow** → **Run workflow** (verde).

5. **Controlla il risultato** (dopo ~1 minuto): torna nella home del repo →
   deve esserci una cartella `data/2026-…/` con dentro **`tpims_dynamic.csv`**.
   Aprilo: se ha **delle righe** (una per area, con posti liberi e capienza) → **funziona!** 🎉
   Da qui in poi va da solo ogni 15 minuti, senza che tu faccia nulla.

6. **Mandami il link del repo** (es. `https://github.com/TUO_NOME/parkalive-tpims-poller`):
   mi collego io, analizzo i dati e li aggancio al modello.

---

## Strada B — da terminale (se preferisci)

Dentro la cartella `tpims-poller/`:
```bash
git init -b main
git add -A
git commit -m "TPIMS poller v1"
git remote add origin https://github.com/TUO_USERNAME/parkalive-tpims-poller.git
git push -u origin main
```
Poi fai i passi **3–6** qui sopra.

---

## Cosa aspettarsi al primo run (leggi prima di allarmarti)

- **Caso buono:** il CSV ha righe per (quasi) tutti e 5 gli stati → siamo in pista.
- **Caso "alcuni stati sì, altri no":** normale. Alcuni feed (MN/OH) sono su host
  particolari; se 3 su 5 rispondono, ci bastano per partire. Me lo dici e vediamo.
- **Caso "ancora 0 righe, tutti 403":** vorrebbe dire che il blocco non è solo
  geografico. Poco probabile dagli USA, ma se capita **non insistere**: mandami il
  log (lo trovi in `data/…/poll_log.txt`) e cambiamo strategia.

## Note
- **Costo:** zero (repo pubblico = minuti Actions illimitati).
- I dati crescono di pochi MB al giorno: ogni giorno una cartella con CSV + snapshot.
- Se ogni tanto un run salta, non è un problema: il successivo recupera.
- GitHub a volte ritarda i lavori schedulati di qualche minuto: è normale, non perdiamo dati utili.
