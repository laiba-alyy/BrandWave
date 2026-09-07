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
which terminates TLS and routes both services under one origin. See
[Deployment](#deployment-aws-ec2) to reproduce the setup from scratch.

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

hf download laiba-alyy/brandwave-sentiment-xlm-roberta \
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
hf auth login          # paste a token with write scope

hf upload laiba-alyy/brandwave-sentiment-xlm-roberta \
  ./backend/modules/sentiment/models/xlm-roberta-sentiment-final . \
  --repo-type model
```

Create the repo first at https://huggingface.co/new if it does not exist, and
keep it **public** so judges and collaborators can download without a token.

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

## Deployment (AWS EC2)

BrandWave runs on an EC2 instance with an Elastic IP, managed over SSH, with
**Caddy** in front terminating TLS and reverse-proxying both services under a
single HTTPS origin.

The public hostname is `54.144.145.194.sslip.io`. [sslip.io](https://sslip.io)
is a free wildcard DNS service that resolves any hostname containing an IP back
to that IP — so `54.144.145.194.sslip.io` resolves to `54.144.145.194` with no
domain registration and no DNS setup. That matters because Caddy needs a real
hostname to obtain a Let's Encrypt certificate; it cannot issue one for a bare
IP address. This gives the demo working HTTPS for free.

These are the steps to reproduce it.

### 1. Provision the instance

- **AMI** — Ubuntu 22.04 LTS
- **Type** — `t3.medium` minimum (4 GB RAM), `t3.large` recommended. The
  sentiment predictor holds ~1 GB resident on its own.
- **Storage** — **expand the root volume to 30 GB.** The 8 GB default is not
  enough: PyTorch, Chromium, `node_modules`, and the 1.06 GB model together run
  well past it, and you hit `No space left on device` mid-install.
- **Elastic IP** — allocate one and associate it, so the address survives a
  stop/start.

### 2. Security group

Only Caddy is public. The app ports stay closed to the internet — traffic
reaches them through the proxy on the instance itself.

| Port | Source | Purpose |
|---|---|---|
| 22 | your IP only | SSH |
| 80 | 0.0.0.0/0 | HTTP — Caddy redirects to HTTPS, and Let's Encrypt validates here |
| 443 | 0.0.0.0/0 | HTTPS — all application traffic |
| ~~3000~~ | — | Frontend. **Not exposed.** Caddy proxies it locally. |
| ~~8000~~ | — | Backend. **Not exposed.** Caddy proxies it locally. |

Port 80 must stay open even though everything redirects to HTTPS — Let's
Encrypt's HTTP-01 challenge uses it, and certificate renewal fails silently
without it. The certificate then expires ~90 days later, mid-demo.

### 3. Connect and install system dependencies

```bash
ssh -i your-key.pem ubuntu@54.144.145.194

sudo apt update && sudo apt upgrade -y

# Node 20 (Ubuntu's default apt Node is too old for Next.js 16)
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# Python 3.12 + FFmpeg + git
sudo apt install -y python3.12 python3.12-venv python3-pip ffmpeg git

# Libraries rembg/Pillow need at runtime
sudo apt install -y libgl1 libglib2.0-0
```

### 4. Clone and configure

```bash
git clone https://github.com/laiba-alyy/BrandWave.git
cd BrandWave
```

Create both env files **on the server**. They are gitignored by design, so they
never arrive via `git pull` — copy them across separately:

```bash
scp -i your-key.pem .env         ubuntu@54.144.145.194:~/BrandWave/.env
scp -i your-key.pem backend/.env ubuntu@54.144.145.194:~/BrandWave/backend/.env
```

Point every URL at the **public HTTPS origin** — not localhost, and not an
`http://ip:port` pair. Because Caddy serves both services under one hostname,
every value is the same origin with **no port number**:

```env
# .env  (frontend)
NEXT_PUBLIC_API_URL=https://54.144.145.194.sslip.io

# backend/.env
BACKEND_PUBLIC_URL=https://54.144.145.194.sslip.io
FRONTEND_URL=https://54.144.145.194.sslip.io
CORS_ALLOWED_ORIGINS=https://54.144.145.194.sslip.io
```

The frontend builds request paths as `${NEXT_PUBLIC_API_URL}/api/...`, and Caddy
routes anything starting with `/api` to FastAPI — so the origin alone is correct
here. Appending `:8000` would point the browser at a port the security group
does not expose.

`CORS_ALLOWED_ORIGINS` must match the browser's origin **exactly** — scheme,
host, and port. `http://` instead of `https://` is a mismatch, and so is a
trailing slash. Get it wrong and every API call fails in the browser with a CORS
error while the server logs look perfectly healthy.

### 5. Install and build

```bash
# ── Backend ──────────────────────────────────────────────
cd ~/BrandWave/backend
python3.12 -m venv .venv
source .venv/bin/activate

# CPU-only torch — the default PyPI wheel ships ~2.5 GB of CUDA this box cannot use
pip install torch==2.13.0 --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
playwright install --with-deps chromium

# Sentiment weights
pip install -U "huggingface_hub[cli]"
hf download laiba-alyy/brandwave-sentiment-xlm-roberta \
  --local-dir modules/sentiment/models/xlm-roberta-sentiment-final

# ── Frontend ─────────────────────────────────────────────
cd ~/BrandWave
npm ci
npm run build
```

### 6. Run both services

Start them so they survive the SSH session ending and come back after a reboot —
`pm2`, a `systemd` unit, or `tmux` for a short-lived demo all work.

```bash
# Backend — 1 worker is deliberate: each extra worker loads its own
#           ~1 GB copy of the sentiment model.
cd ~/BrandWave/backend
source .venv/bin/activate
uvicorn main:app --host 127.0.0.1 --port 8000 --workers 1

# Frontend
cd ~/BrandWave
npm run start
```

Both bind to **localhost only**. Caddy is on the same host and reaches them
there; binding to `0.0.0.0` would put them on the public interface, bypassing
TLS. The security group blocks those ports anyway — this is the second layer,
not the only one.

> Backgrounding with plain `nohup ... &` works but does **not** survive an
> instance reboot. If the demo has to stay up, use `pm2 save && pm2 startup` or a
> `systemd` unit with `Restart=always`.

### 7. Caddy — TLS and routing

```bash
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
  | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
  | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install -y caddy
```

Write `/etc/caddy/Caddyfile`. This is the routing the live deployment serves —
one origin, frontend at the root, FastAPI on the API paths:

```caddyfile
54.144.145.194.sslip.io {
    # FastAPI — everything the backend owns.
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle /docs* {
        reverse_proxy 127.0.0.1:8000
    }
    handle /openapi.json {
        reverse_proxy 127.0.0.1:8000
    }
    handle /health {
        reverse_proxy 127.0.0.1:8000
    }

    # Everything else — Next.js.
    handle {
        reverse_proxy 127.0.0.1:3000
    }
}
```

```bash
sudo systemctl reload caddy
```

Caddy obtains and renews the Let's Encrypt certificate automatically on first
request — no certbot, no cron job. It also enables HTTP/3 and redirects
`http://` to `https://` by default.

**WebSockets need no extra configuration.** Two endpoints run on them —
`/api/chatbot/ws/{user_id}` and `/api/scraping/scrape-progress/{uid}` — and
Caddy's `reverse_proxy` upgrades connections automatically. They fall under the
`/api/*` rule already.

### 8. Verify

```bash
curl https://54.144.145.194.sslip.io/health                    # module status
curl https://54.144.145.194.sslip.io/api/scraping/health
curl -I https://54.144.145.194.sslip.io/                       # expect: Via: 1.1 Caddy
```

Then open the site in a browser and check the console — a working frontend makes
**no** requests to `localhost:8000` and **no** mixed-content warnings. If you see
`Blocked loading mixed active content`, `NEXT_PUBLIC_API_URL` still says `http://`
and the frontend needs a rebuild, not a restart.

### Redeploying after a push

```bash
cd ~/BrandWave
git pull

# Backend — only if requirements.txt changed
cd backend && source .venv/bin/activate && pip install -r requirements.txt

# Frontend — ALWAYS rebuild. NEXT_PUBLIC_* values are compiled into the bundle.
cd ~/BrandWave && npm ci && npm run build
```

Then restart both services.

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
| `No space left on device` during install | 8 GB default EC2 volume | Expand the root volume to 30 GB |
| `Blocked loading mixed active content` | Page is HTTPS but `NEXT_PUBLIC_API_URL` is `http://` | Set it to the `https://` origin and **rebuild** the frontend |
| `502 Bad Gateway` from Caddy | The upstream service is not running, or bound to the wrong interface | Check both processes are up and listening on `127.0.0.1`; `sudo journalctl -u caddy -f` |
| Certificate expired / renewal failed | Port 80 closed in the security group | Let's Encrypt validates over HTTP-01 on port 80 — reopen it, then `sudo systemctl reload caddy` |
| WebSocket features (chat alerts, scrape progress) never connect | Request not matching the `/api/*` proxy rule | Confirm the path starts with `/api`; Caddy upgrades connections automatically |

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
- If a key is ever exposed, rotate it. `SUPABASE_SERVICE_ROLE_KEY` and
  `SMTP_PASSWORD` are the two worth guarding hardest.
