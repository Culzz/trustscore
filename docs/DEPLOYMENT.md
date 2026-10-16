# Deployment

Two shapes are supported. Start with the first unless you hit a limit.

* **A. Single Vercel project** — Next.js frontend + FastAPI as a serverless
  Python function, one URL.
* **B. Split** — Next.js on Vercel, API as a Docker service on Render/Railway.
  No serverless bundle limit; recommended if the Python bundle is too big or
  cold starts annoy you.

The database is optional and provider-agnostic. The API is fully functional with
logging disabled.

---

## Free database options (no lock-in)

The storage layer speaks **plain Postgres**. Any of these works by pasting a
connection string into `DATABASE_URL`. Nothing in the code changes.

| Provider | Free tier | Card required? | Notes |
| --- | --- | --- | --- |
| **Supabase** | 500 MB Postgres | No | Best default. Use the *Connection string (URI)* with `?sslmode=require`. |
| **Aiven** | 1 GB Postgres | No | Good alternative; copy the service URI. |
| **Neon** | small free tier | Sometimes | `postgresql://…?sslmode=require`. |
| **Render Postgres** | free | No | Expires after 90 days — fine for a demo. |
| **SQLite** | unlimited | No | Local files only. Great for development and for `docker compose`. |

If you prefer **no database at all**, set `STORAGE_BACKEND=none`. The app runs,
the dashboard counters show as disabled, and nothing else changes.

---

## Local

### Docker (one command)

```bash
docker compose up --build
# web  -> http://localhost:3000
# api  -> http://localhost:8000/docs
```

Predictions are logged to a local SQLite file, so the lender counters work with
zero cloud setup.

### Manual

```bash
# --- API ---
cd api
python -m venv .venv && .venv\Scripts\activate      # or: source .venv/bin/activate
pip install -r requirements.txt
copy ..\.env.example .env                            # set STORAGE_BACKEND=sqlite
uvicorn app.main:app --reload --port 8000

# --- web (new terminal) ---
cd web
npm install
copy .env.example .env.local                         # NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

Training (only needed if you change the model; the artifact is committed):

```bash
pip install -r training/requirements.txt
python -m training.src.train
```

---

## A. Single Vercel project

1. Push the repo to GitHub.
2. In Vercel: **Add New → Project → Import** the repo. **Leave the Root
   Directory empty** — `vercel.json` drives the monorepo build.
3. Add environment variables (Project → Settings → Environment Variables):

   | Name | Value |
   | --- | --- |
   | `NEXT_PUBLIC_API_BASE_URL` | `/api` |
   | `STORAGE_BACKEND` | `postgres` |
   | `DATABASE_URL` | your Postgres URI (e.g. Supabase) |
   | `ENABLE_DOCS` | `true` |

4. Deploy. Vercel builds `web/` (Next.js) and `api/index.py` (Python), and
   routes `/api/*` to the function. `/api/health` should return `status: ok`.

> If the Python bundle trips Vercel's size limit or cold starts are slow, switch
> to **shape B**. The model is already dependency-light (no scikit-learn, no
> SciPy, no shap), so this is unlikely.

---

## B. Split (API on Render, web on Vercel)

1. **Database (optional):** create a Supabase project and copy the URI.
2. **API on Render:** New → Blueprint → point at this repo. Render reads
   `render.yaml` and builds `api/Dockerfile`. Set `DATABASE_URL` in the
   dashboard (it is marked `sync: false`).
3. **Web on Vercel:** import the repo, set **Root Directory = `web`**, framework
   preset **Next.js**, and set:

   | Name | Value |
   | --- | --- |
   | `NEXT_PUBLIC_API_BASE_URL` | `https://your-api.onrender.com` |

4. Redeploy the web app after changing `NEXT_PUBLIC_API_BASE_URL` (it is baked
   in at build time).

---

## Environment variables

See `.env.example` (API) and `web/.env.example` (web). Never commit `.env`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `STORAGE_BACKEND` | `auto` | `auto`, `postgres`, `sqlite`, `none` |
| `DATABASE_URL` | – | Postgres URI (any provider) |
| `SQLITE_PATH` | `predictions.db` | SQLite file when backend is sqlite |
| `LOG_PREDICTIONS` | `true` | Master switch for logging |
| `CORS_ORIGINS` | localhost | Comma-separated allowed origins |
| `RATE_LIMIT` | `120/minute` | slowapi limit |
| `ENABLE_DOCS` | `true` | Serve `/docs` and `/openapi.json` |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | API base for the browser |

---

## CI

`.github/workflows/ci.yml` runs on every push:

* **api-tests** — `pytest` against the committed artifact.
* **web-build** — `npm ci`, `npm run lint`, `npm run build`.

## Troubleshooting

* **`/model` returns 503** — training has not been run; `api/artifacts/model.joblib`
  and `api/artifacts/metadata.json` must exist (they are committed).
* **Counters always zero** — `STORAGE_BACKEND=none`, or `DATABASE_URL` unset, or
  the DB is unreachable. `/health` reports `database_configured`.
* **CORS errors in the browser** — add your frontend origin to `CORS_ORIGINS`.
