# BPR Validation Tool

Reads scanned pharmaceutical **Batch Production Records** (PDF), extracts the
filled-in fields (printed **and** handwriting), flags uncertain reads, runs
validation rules, and shows a **side-by-side viewer** — the scanned page with
coloured bounding boxes next to the extracted values. Exports a multi-sheet
Excel report. Runs locally; the optional vision-LLM backend can be offline (GPU)
or via a hosted API.

---

## Quick start (macOS / Linux)

```bash
# 1. Clone and switch to this branch
git clone https://github.com/bbakdoga/rentschler-biopharma.git
cd rentschler-biopharma
git checkout fix/llm-structured-extraction

# 2. One-time setup — creates .venv, installs Python deps + Tesseract OCR
./install.sh

# 3a. Add your OpenRouter API key (for the cloud vision-LLM backend)
cp .env.example .env          # then edit .env and paste your key
#     get a key at https://openrouter.ai/keys  (or ask Barış for his)

# 3b. Run the GUI
./run.sh                      # cloud vision-LLM (Qwen2.5-VL-72B) — best handwriting
# …or fully offline, no API key, Tesseract only:
source .venv/bin/activate && python main.py
```

Then click **Upload PDF** and pick a scanned BPR. (Ask Barış for the demo PDF if
you don't have one.)

---

## Using the app

- **Upload PDF** — processes the document page by page (progress bar shows each
  step). Big scans take a while; the cloud backend re-reads handwriting per page.
- **Tabs:** Validation Results · Signatures · Extracted Fields · Personnel ·
  **Page Viewer**.
- **Page Viewer** — the scanned page with a coloured box around every extracted
  value; the field list on the right is colour-matched. A **dashed box / ⚠** =
  low OCR confidence (usually handwriting). Click a field row or a box to
  cross-highlight. Use Prev/Next to page through.
- **Export Excel** — saves Summary, Validation, Signatures, Extracted Fields
  (with an OCR-confidence column), and Personnel sheets.

---

## OCR backends (set with `OCR_BACKEND`)

| Value | What it does | Needs |
|-------|--------------|-------|
| `tesseract` (default) | CPU-only, fully offline | nothing |
| `api` | Hybrid: Tesseract geometry + **Qwen2.5-VL-72B** re-reads handwriting via an OpenAI-compatible cloud endpoint (OpenRouter) | network + API key |
| `llm`  | Same hybrid but against an **offline** Ollama vision server (e.g. a GPU node) | `OLLAMA_HOST` + a pulled vision model |

`./run.sh` uses the `api` backend. Qwen2.5-VL-72B is **open-weights**, so the
hosted API demo matches an offline GPU deployment of the identical model.

Key env vars (see `config.py` for all of them):

```bash
OCR_BACKEND=api
OPENAI_API_BASE=https://openrouter.ai/api/v1
OPENAI_VL_MODEL=qwen/qwen2.5-vl-72b-instruct
OPENAI_API_KEY=sk-or-...        # in .env (gitignored), loaded by run.sh
```

---

## ⚠️ Notes

- The `api` backend sends page/crop **images to OpenRouter (a public cloud
  service)**. That's fine for the synthetic demo PDF, but **not** for real GMP
  batch records — for those use `tesseract` or the offline `llm` backend.
- The OpenRouter key is **not** committed — it lives in a gitignored `.env`
  (GitHub blocks pushing secrets, and keys shouldn't be in git history). Each
  person creates their own `.env` from `.env.example`. Get a key at
  https://openrouter.ai/keys.
