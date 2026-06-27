# Offline LLM handwriting OCR (Elwe / Slurm)

The BPR tool can read handwriting with an **offline open-source vision model**
served by [Ollama] on a GPU node, instead of Tesseract alone. Tesseract still
provides the page layout (word boxes, sections); the vision model re-reads only
the low-confidence runs — the handwritten, filled-in values — so the viewer
overlays and all extractors keep working, just with accurate handwriting.

No extra Python packages are needed (the client uses the standard library).
Ollama is provided as a cluster **module** (`module avail ollama`).

## How the switch works

The backend is chosen by config / env (default stays `tesseract`):

| Variable             | Default                  | Meaning                                   |
|----------------------|--------------------------|-------------------------------------------|
| `OCR_BACKEND`        | `tesseract`              | set to `llm` to use the vision model      |
| `OLLAMA_HOST`        | `http://127.0.0.1:11434` | where the Ollama server is reachable      |
| `OLLAMA_VL_MODEL`    | `qwen2.5vl:7b`           | vision model tag                          |
| `OLLAMA_TIMEOUT`     | `180`                    | per-request timeout (s)                   |
| `LLM_CORRECT_BELOW`  | `60`                     | Tesseract conf at/below which to re-read  |
| `LLM_MAX_CROPS_PER_PAGE` | `60`                 | safety cap on model calls per page        |

Good handwriting models on Ollama: `qwen2.5vl:7b` (recommended), `qwen2.5vl:3b`
(lighter), `llama3.2-vision:11b`, `minicpm-v`, `granite3.2-vision`.

## Option A — one self-contained batch job (simplest)

Starts Ollama on the GPU node, pulls the model, runs the tool, cleans up:

```bash
sbatch slurm/bpr_ocr_llm.sbatch /path/to/batch.pdf
# pick a model / GPU type (script already targets -p downtime-gpu):
OLLAMA_VL_MODEL=qwen2.5vl:3b sbatch --gres=gpu:a30:1 \
    slurm/bpr_ocr_llm.sbatch /path/to/batch.pdf
```

Edit the `#SBATCH` lines (account, `--gres` GPU type, `--constraint`, time) for
your project. Logs land in `bpr-ocr-<jobid>.out/.err`.

## Option B — interactive: server on GPU, tool wherever you like

Use this to keep the GUI/tool on a login node while the model runs on the GPU.

```bash
# 1) interactive GPU allocation (use your site's rz-launch if preferred).
#    During the maintenance downtime use partition "downtime-gpu";
#    outside downtime drop "-p downtime-gpu" (default partition is "gpu").
salloc -N 1 -p downtime-gpu --gres=gpu:1 -t 4:00:00

# 2) inside that shell — start the server (prints the address to use)
./slurm/ollama_serve.sh

# 3) from where you run the tool (this node, or a login node that can reach it)
export OCR_BACKEND=llm
export OLLAMA_HOST=http://<gpu-node>:11434     # printed by step 2
python main.py /path/to/batch.pdf              # or just `python main.py` for the GUI
```

## Quick check

Verify the tool can reach a running server and the model answers:

```bash
OCR_BACKEND=llm OLLAMA_HOST=http://<node>:11434 python slurm/check_ollama.py
```

## First run downloads the model

`ollama pull` fetches a few GB the first time; it is cached under
`$OLLAMA_MODELS` (default `~/.ollama/models`) and reused by later jobs. If
compute nodes have no internet, run the `ollama pull` once on a node that does
(same `OLLAMA_MODELS`).

[Ollama]: https://ollama.com
