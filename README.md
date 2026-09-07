# BrandWave

**AI Intelligence Digital Marketing Automation System**

BrandWave gives small and medium brands one workspace for the marketing work that
normally needs a whole agency: scrape and understand your storefront, audit SEO,
read what customers actually feel, generate image and video ads from real product
data, and hand visitors an embeddable support chatbot.

Final Year Project — Next.js frontend, FastAPI backend, Supabase auth and data.

---

## Features

| Module | What it does |
|---|---|
| **Store Scraping** | Pulls products, images, and metadata from a brand's storefront into a structured catalogue. |
| **SEO Intelligence** | Site audit plus product-grounded keyword generation, enriched with real Google search-volume data from DataForSEO. Missing metrics show as `N/A` — nothing is fabricated. |
| **Sentiment Analysis** | Fine-tuned XLM-RoBERTa classifier over customer reviews and comments, built for Roman-Urdu/English code-switching. |
| **Image Ad Generation** | Product-locked ad creatives from real catalogue images. |
| **Video Ad Generation** | Image-to-video product ads via fal.ai — **Kling** on the free tier, **Google Veo 3.1** on premium — with optional end cards and watermark handling. |
| **Brand Improvement** | Actionable recommendations derived from the scraped store, SEO audit, and sentiment signals. |
| **Chatbot Automation** | Trainable support bot with an embeddable `<script>` widget and email escalation when it can't answer. |
| **AI Assistant** | Conversational layer over the brand's own data. |

---

## Tech Stack

**Frontend** — Next.js 16 (App Router), React 19, TypeScript, Tailwind CSS 4,
Framer Motion, Recharts, React Hook Form + Zod

**Backend** — FastAPI, SQLAlchemy, PostgreSQL, PyTorch + Transformers

**Platform** — Supabase (auth + database), AWS EC2, fal.ai, Groq, OpenAI,
Google Gemini, DataForSEO, Pinecone

---

## Prerequisites

- **Node.js** 18+
- **Python** 3.10+
- **PostgreSQL** (or a Supabase project)
- **FFmpeg** — required by moviepy for video end cards

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
cp .env.example .env      # then fill in your values
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
cp .env.example .env             # then fill in your values

uvicorn main:app --reload --port 8000
```

Runs at **http://localhost:8000**. Interactive API docs at **/docs**.

### 4. Sentiment model weights (separate download)

The fine-tuned XLM-RoBERTa weights are **not in this repository** — `model.safetensors`
alone is ~1.06 GB and GitHub hard-rejects files over 100 MB.

Place the model folder at:

```
backend/modules/sentiment/models/xlm-roberta-sentiment-final/
├── config.json
├── model.safetensors
├── tokenizer.json
├── tokenizer_config.json
└── training_config.json
```

Or point `SENTIMENT_MODEL_DIR` at wherever you keep it. Every other module runs
without it; only sentiment analysis needs the weights.

---

## Environment Variables

Two separate env files. Both are gitignored — **never commit a filled-in one.**

- **`.env`** (repo root) — frontend. See [`.env.example`](.env.example).
- **`backend/.env`** — backend. See [`backend/.env.example`](backend/.env.example).

The keys that matter most:

| Variable | Where | Purpose |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` | root | Supabase client auth |
| `SUPABASE_SERVICE_ROLE_KEY` | both | Server-side Supabase. Bypasses row-level security — **never expose to the browser** |
| `NEXT_PUBLIC_API_URL` | root | Points the frontend at the FastAPI backend |
| `DATABASE_URL` | backend | PostgreSQL connection string |
| `FAL_API_KEY` | backend | Video ads — powers **both** Kling and Veo |
| `GROQ_API_KEY` | backend | Primary LLM for SEO, chatbot, assistant |
| `DATAFORSEO_LOGIN` / `DATAFORSEO_PASSWORD` | backend | Live Google keyword metrics |
| `SMTP_PASSWORD` | backend | Chatbot escalation email. Gmail: use an **App Password** |
| `CORS_ALLOWED_ORIGINS` | backend | Must include your frontend origin |

---

## Deployment (AWS EC2)

The backend runs on an EC2 instance behind an Elastic IP.

1. **Security group** — open `8000` (backend) and `3000` (frontend), or put both
   behind a reverse proxy on `80`/`443`.
2. **Create `backend/.env` on the server.** It is gitignored by design, so it
   never arrives via `git pull` — copy it across separately.
3. **Point the URLs at the instance**, not localhost:

   ```env
   # .env  (frontend)
   NEXT_PUBLIC_API_URL=http://<elastic-ip>:8000

   # backend/.env
   BACKEND_PUBLIC_URL=http://<elastic-ip>:8000
   FRONTEND_URL=http://<elastic-ip>:3000
   CORS_ALLOWED_ORIGINS=http://<elastic-ip>:3000
   ```

   `CORS_ALLOWED_ORIGINS` must match the frontend origin exactly or every API
   call fails in the browser. `BACKEND_PUBLIC_URL` is what gets baked into the
   embeddable chatbot `<script>` tag customers paste on their own sites — if it
   still says `localhost`, the widget silently breaks for every visitor.

4. **Copy the sentiment model** to the instance (see step 4 above). Budget ~1 GB
   of RAM for it: the predictor is a process-wide singleton, loaded once at first
   use, taking ~14s on CPU.

5. **Build and serve the frontend:**

   ```bash
   npm run build && npm run start
   ```

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
- If a key is ever exposed, rotate it. `SUPABASE_SERVICE_ROLE_KEY` and
  `SMTP_PASSWORD` are the two worth guarding hardest.
