# BrandWave

**AI Intelligence Digital Marketing Automation System**

BrandWave gives small and medium brands one workspace for the marketing work that
normally needs a whole agency: scrape and understand your storefront, audit SEO,
read what customers actually feel, generate image and video ads from real product
data, and hand visitors an embeddable support chatbot.

Next.js frontend, FastAPI backend, Supabase auth and data.

---

## Live Demo

**https://54.144.145.194.sslip.io**

| | |
|---|---|
| **Application** | https://54.144.145.194.sslip.io |
| **API docs (Swagger)** | https://54.144.145.194.sslip.io/docs |
| **API health** | https://54.144.145.194.sslip.io/health |

Running on **AWS EC2** behind an Elastic IP, served over **HTTPS by Caddy**,
which terminates TLS and routes both services under one origin.

---

## Features

| Module | What it does |
|---|---|
| **Store Scraping** | Pulls products, images, and metadata from a brand's storefront into a structured catalogue. Falls back to a headless-Chromium render for JS-heavy stores. |
| **SEO Intelligence** | Site audit plus product-grounded keyword generation, enriched with real Google search-volume data from DataForSEO. Missing metrics show as `N/A` — nothing is fabricated. |
| **Sentiment Analysis** | Fine-tuned XLM-RoBERTa classifier over customer reviews and comments, built for Roman-Urdu/English code-switching. **88.0% test accuracy, 87.8 macro-F1.** |
| **Image Ad Generation** | Product-locked ad creatives from real catalogue images. |
| **Video Ad Generation** | Image-to-video product ads via fal.ai — **Kling** on the free tier, **Google Veo 3.1** on premium — with optional end cards and watermark handling. |
| **Brand Improvement** | Actionable recommendations derived from the scraped store, SEO audit, and sentiment signals. |
| **Chatbot Automation** | Trainable support bot with an embeddable `<script>` widget and email escalation when it can't answer. |
| **AI Assistant** | Conversational layer over the brand's own data. |

---

## Architecture

```
Browser
   |
   |  HTTPS
   v
Caddy  :443                       TLS termination, one public origin
   |                              54.144.145.194.sslip.io
   |
   |-- /            -------->  Next.js 16 (App Router)  ----->  Supabase
   |                           127.0.0.1:3000                   auth + Postgres + RLS
   |
   `-- /api/*  /docs  /health  ->  FastAPI
                                   127.0.0.1:8000
                                      |
                                      |-- scraping/            httpx + BeautifulSoup,
                                      |                        Playwright Chromium fallback
                                      |-- seo/                 DataForSEO + LLM keywords
                                      |-- sentiment/           XLM-RoBERTa, CPU inference
                                      |-- ads_generation/      Gemini / HF / Bria / Claid
                                      |-- video_ads/           fal.ai + moviepy end cards
                                      |-- chatbot_automation/  Pinecone + SMTP escalation
                                      `-- ai_assistant/        Groq conversational layer
```

The frontend never holds a provider key. Every third-party call is made
server-side by FastAPI.

---

## Tech Stack

**Frontend** — Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4,
Framer Motion, Recharts, React Hook Form + Zod

**Backend** — FastAPI, SQLAlchemy, PostgreSQL, PyTorch + Transformers

**Platform** — Supabase (auth + database), AWS EC2, fal.ai, Groq, OpenAI,
Google Gemini, DataForSEO, Pinecone

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| **Node.js** | **20.9+** | Next.js 16 declares `engines: >=20.9.0`. Node 18 fails at install. |
| **Python** | **3.12** | Pinned versions in `requirements.txt` are verified on 3.12. See the note below. |
| **PostgreSQL** | 14+ | Or a Supabase project, which is what this uses. |
| **FFmpeg** | any recent | Required by moviepy for video ad end cards. |
| **Disk** | ~20 GB free | torch + Chromium + model weights add up fast. |
| **RAM** | 4 GB min | The sentiment model alone holds ~1 GB resident. |

> **Python 3.12, not 3.14.** `backend/.python-version` says `3.14`, but that file
> is stale. On 3.14 there are no prebuilt wheels for `torch==2.13.0` /
> `numpy==2.5.2`, so pip tries to build from source and either takes hours or
> fails outright. Use 3.12.

**Installing FFmpeg:**

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt update && sudo apt install -y ffmpeg

# Windows
winget install Gyan.FFmpeg
```

---

## Getting Started

### 1. Clone

```bash
git clone https://github.com/laiba-alyy/BrandWave.git
cd BrandWave
```

### 2. Frontend

```bash
npm install
cp .env.example .env      # then fill in your values — see Environment Variables
npm run dev
```

Runs at **http://localhost:3000**.

### 3. Backend

```bash
cd backend

python -m venv .venv
source .venv/Scripts/activate    # Windows (Git Bash)
# source .venv/bin/activate      # macOS / Linux

pip install -r requirements.txt

# REQUIRED — the scraper's JS fallback runs on headless Chromium.
# Skip this and JS-heavy storefronts silently return empty catalogues.
playwright install chromium

cp .env.example .env             # then fill in your values

uvicorn main:app --reload --port 8000
```

Runs at **http://localhost:8000**. Interactive API docs at **/docs**.

> `pip install -r requirements.txt` pulls PyTorch and can take 5–10 minutes.
> On Linux you can cut ~2 GB by installing the CPU-only build first:
> `pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu`

### 4. Sentiment model weights — **required for the sentiment module**

The fine-tuned XLM-RoBERTa weights are **not in this repository**.
`model.safetensors` alone is ~1.06 GB and GitHub hard-rejects files over 100 MB.

**Download them from the Hugging Face Hub:**

```bash
pip install -U "huggingface_hub[cli]"

hf download laibialy/brandwave-sentiment-xlm-roberta \
  --local-dir backend/modules/sentiment/models/xlm-roberta-sentiment-final
```

<sub>On <code>huggingface_hub</code> older than 0.34 the command is <code>huggingface-cli download</code> with the same arguments.</sub>

**Expected result** — the folder must contain all of these:

```
backend/modules/sentiment/models/xlm-roberta-sentiment-final/
├── config.json               920 B
├── model.safetensors        ~1.06 GB   <- the big one
├── tokenizer.json           ~16 MB
├── tokenizer_config.json     314 B
└── training_config.json      348 B
```

**Verify it loads:**

```bash
cd backend
python -c "from modules.sentiment.services.model_loader import warmup; print('OK' if warmup() else 'FAILED')"
```

Prints `OK` once the weights are in place. First load takes ~14s on CPU; after
that the predictor is a process-wide singleton and stays warm.

**Keeping the weights elsewhere?** Point `SENTIMENT_MODEL_DIR` at the folder:

```env
# backend/.env
SENTIMENT_MODEL_DIR=/absolute/path/to/xlm-roberta-sentiment-final
```

**Every other module runs without these weights.** Only sentiment analysis needs
them — if they are missing, `/api/sentiment/analyze-from-dropdown` returns
**503 "Sentiment model is not loaded on the server"** and the rest of the app is
unaffected. The backend logs the exact path it searched at startup.

#### Model card

| | |
|---|---|
| Base model | `FacebookAI/xlm-roberta-base` |
| Task | 3-class sentiment — `negative` / `neutral` / `positive` |
| Max sequence length | 128 tokens |
| Test accuracy | **88.04%** |
| Macro F1 | **87.84** |
| Weighted F1 | **88.07** |
| Trained for | Roman-Urdu / English code-switched review text |

<details>
<summary><b>Maintainer: publishing an updated model</b></summary>

```bash
pip install -U "huggingface_hub[cli]"
hf auth login          # paste a token with the WRITE role, not read

hf upload laibialy/brandwave-sentiment-xlm-roberta \
  ./backend/modules/sentiment/models/xlm-roberta-sentiment-final . \
  --exclude "training_args.bin" \
  --repo-type model
```

`hf upload` creates the repo on first push, so there is nothing to set up on the
website beforehand. The trailing `.` places the files at the repo root, which is
where `from_pretrained()` looks for them.

`training_args.bin` is excluded deliberately: it is a pickled `TrainingArguments`
object holding absolute paths from the training machine, and inference never
reads it.

Keep the repo **public** so it downloads without a token.

</details>

---

## Environment Variables

Two separate env files. Both are gitignored — **never commit a filled-in one.**

- **`.env`** (repo root) — frontend. See [`.env.example`](.env.example).
- **`backend/.env`** — backend. See [`backend/.env.example`](backend/.env.example).

### Minimum to boot

The app starts with just these; individual modules degrade gracefully without
their provider keys.

| Variable | File | Purpose |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | root | Supabase client auth |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | root | Supabase client auth |
| `NEXT_PUBLIC_API_URL` | root | Points the frontend at FastAPI |
| `DATABASE_URL` | backend | PostgreSQL connection string — **the backend refuses to start without it** |
| `SECRET_KEY` | backend | Session/token signing |
| `SUPABASE_URL` | backend | Server-side Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | backend | Bypasses row-level security — **never expose to the browser** |
| `CORS_ALLOWED_ORIGINS` | backend | Must match your frontend origin exactly |

### Per-module keys

| Variable | Unlocks |
|---|---|
| `GROQ_API_KEY` | Primary LLM — SEO keywords, chatbot, AI assistant |
| `FAL_API_KEY` | Video ads — powers **both** Kling and Veo 3.1 |
| `GEMINI_API_KEY` | Image ad generation |
| `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` | Live Google keyword volume |
| `YOUTUBE_API_KEY` | YouTube comment ingestion for sentiment |
| `PINECONE_API_KEY` | Chatbot knowledge retrieval |
| `SMTP_USER` / `SMTP_PASSWORD` | Chatbot escalation email. Gmail: use an **App Password**, not your account password |
| `HF_API_KEY`, `BRIA_API_KEY`, `CLAID_API_KEY`, `POLLINATIONS_KEY`, `CLOUDFLARE_API_TOKEN` | Alternative image-generation backends |
| `OPENAI_API_KEY` / `OPENAI_TTS_KEY` | Optional LLM + voiceover |

`backend/.env.example` documents all of them with inline notes.

### Two variables that break things quietly

- **`NEXT_PUBLIC_API_URL`** is read at **build time** by Next.js and baked into
  the browser bundle. Changing it means rebuilding the frontend — restarting is
  not enough.
- **`BACKEND_PUBLIC_URL`** is baked into the embeddable chatbot `<script>` tag
  that customers paste on their own sites. If it still says `localhost`, the
  widget works for you and silently fails for every real visitor.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| **503** `Sentiment model is not loaded on the server` | Weights missing, or `SENTIMENT_MODEL_DIR` points somewhere wrong | See [step 4](#4-sentiment-model-weights--required-for-the-sentiment-module). The startup log prints the exact path it searched. |
| `RuntimeError: DATABASE_URL is not configured` | No `backend/.env`, or the backend was started from the wrong directory | `cp .env.example .env` inside `backend/`, and run `uvicorn` from `backend/` |
| `npm install` fails on an engine check | Node 18 or older | Next.js 16 needs **Node 20.9+** |
| CORS error in the browser, server logs look fine | `CORS_ALLOWED_ORIGINS` does not match the frontend origin exactly | Match scheme, host, and port |
| Frontend still calls `localhost:8000` in production | `NEXT_PUBLIC_API_URL` is baked in at build time | Change it, then **rebuild** — restarting will not do it |
| Scraper returns empty results on a JS-heavy store | Chromium was never installed | `playwright install chromium` |
| Embedded chatbot widget works for you, fails for visitors | `BACKEND_PUBLIC_URL` still points at localhost | Set it to the public backend URL, then regenerate the embed snippet |
| Video ads fail at the end-card step | FFmpeg not on PATH | Install FFmpeg (see [Prerequisites](#prerequisites)) |
| `No space left on device` during install | torch, Chromium, `node_modules` and the 1.06 GB model together need ~20 GB | Free up space (see [Prerequisites](#prerequisites)) |
| `Blocked loading mixed active content` | Page is served over HTTPS but `NEXT_PUBLIC_API_URL` is `http://` | Set it to the `https://` origin and **rebuild** the frontend |

---

## Project Structure

```
├── app/                    # Next.js App Router — pages and server actions
│   ├── business/           # Main product surface (one folder per module)
│   ├── auth/ login/ signup/
│   └── admin/
├── components/             # Shared React components
├── lib/                    # API clients and helpers
├── types/                  # Shared TypeScript types
├── public/                 # Static assets, feature videos
├── db/
│   └── policies.sql        # Supabase RLS policies + column grants (see Security Notes)
├── FAQs.txt                # Sample chatbot training data — for testing
├── KnowledegeDocument.txt  # Sample chatbot knowledge base — for testing
├── TestWidget.html         # Standalone page for testing the embeddable chat widget
└── backend/
    ├── main.py             # FastAPI app + route registration
    ├── api/routes/         # HTTP endpoints, one file per module
    ├── modules/            # Business logic
    │   ├── scraping/  seo/  sentiment/
    │   ├── ads_generation/  video_ads/
    │   ├── chatbot_automation/  brand_improvement/  ai_assistant/
    │   └── llm_config.py   # Shared LLM client + rate-limit handling
    ├── models/             # SQLAlchemy models
    ├── database/           # Session and connection setup
    └── scripts/            # Maintenance and migration scripts
```

---

## Security Notes

- All `.env*` files are gitignored, at every directory level.
- Generated ads, uploads, scraped PDFs, and database backup dumps are excluded —
  they contain real user content.
- Model weights (`*.safetensors`, `*.pkl`, `*.pt`) are excluded.
- Provider keys live only in `backend/.env`. The browser bundle carries the
  Supabase **anon** key and the API URL, nothing else.
- **Role escalation is blocked at the database layer.** Row-level security alone
  was not enough: RLS decides which *row* you may write, and a user updating
  their own `role` to `admin` is writing their own row. `db/policies.sql` revokes
  column-level `UPDATE` on `role` and `email_verified` from `anon` and
  `authenticated`, so Postgres refuses before RLS is consulted. Promotion now
  requires the service-role key. Run that file in the Supabase SQL editor when
  setting up a new project — it is idempotent and ends with verification queries.
- If a key is ever exposed, rotate it. `SUPABASE_SERVICE_ROLE_KEY` and
  `SMTP_PASSWORD` are the two worth guarding hardest.
