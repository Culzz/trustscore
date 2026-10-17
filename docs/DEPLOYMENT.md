# Deployment

Three shapes are supported. Start with the first unless you hit a limit.

* **A. Single Vercel project** — Next.js frontend + FastAPI as a serverless
  Python function, one URL. Jobs run in-process; progress degrades to polling.
* **B. Split** — Next.js on Vercel, API as a Docker service on Render/Railway.
  No serverless bundle limit; WebSocket progress works. Recommended if the Python
  bundle is too big or cold starts annoy you.
* **C. Docker Compose with real workers** — the API plus Redis and a Celery
  worker, for the full asynchronous path.

The database is optional and provider-agnostic. The API is fully functional with
logging disabled. So is Redis: without a broker, jobs run in-process.

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

To run the real asynchronous path (Redis + Celery worker) as well:

```bash
REDIS_URL=redis://redis:6379/0 docker compose --profile async up --build
# the API resolves JOB_BACKEND to celery and WS /ws/jobs/{id} streams live
```

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

## C. Docker Compose with real workers

The full asynchronous path: a long-lived API, Redis, and a Celery worker.

```bash
REDIS_URL=redis://redis:6379/0 docker compose --profile async up --build
```

* `api` — FastAPI; `JOB_BACKEND` resolves to `celery` because a broker URL is set,
  and `WS /ws/jobs/{id}` relays Redis pub/sub to the browser.
* `redis` — broker plus result backend.
* `worker` — `celery -A app.worker.celery_app worker`, running the identical
  `run_application` flow as the in-process path.

Any Docker host works (Render paid, Railway, Fly, a VPS). The only requirements
are the `api/` image, a Redis URL, and `pip install -r api/requirements-async.txt`
in that image. **Render's free plan has no background workers** — for a free
single-service deployment use shape B and leave the broker unset, which keeps
jobs in-process while WebSocket progress still works.

---

## Environment variables

See `.env.example` (API) and `web/.env.example` (web). Never commit `.env`.

| Variable | Default | Meaning |
| --- | --- | --- |
| `STORAGE_BACKEND` | `auto` | `auto`, `postgres`, `sqlite`, `none` |
| `DATABASE_URL` | – | Postgres URI (any provider) |
| `SQLITE_PATH` | `predictions.db` | SQLite file when backend is sqlite |
| `LOG_PREDICTIONS` | `true` | Master switch for logging |
| `JOB_BACKEND` | `auto` | `auto`, `memory`, `celery` |
| `JOB_TTL_SECONDS` | `900` | In-memory job retention |
| `REDIS_URL` | – | Enables the Celery path when set |
| `CELERY_BROKER_URL` | – | Same, if you prefer an explicit broker |
| `CELERY_RESULT_BACKEND` | – | Celery result store |
| `ALERT_WEBHOOK_URL` | – | Slack-style webhook for drift alerts |
| `PII_SALT` | `trustscore-demo-salt` | Salt for the privacy gateway; **change in production** |
| `MODEL_VERSION` | `trustscore-1.0.0` | Default (Alpha) version |
| `FAIR_MODEL_VERSION` | `trustscore-1.1.0` | Fairness-tuned (Beta) version |
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
* **`/portfolio` or `/policy/simulate` returns 503** — the audit portfolio is
  missing; rerun `python -m training.src.train` to regenerate
  `api/artifacts/portfolio.json` and `registry.json`.
* **Counters always zero** — `STORAGE_BACKEND=none`, or `DATABASE_URL` unset, or
  the DB is unreachable. `/health` reports `database_configured`.
* **`/drift/live` reports `simulated: true`** — expected without storage: with no
  live stream there is no real traffic to compare, so the panel runs a labelled
  synthetic window.
* **Jobs stay `queued`** — `JOB_BACKEND=celery` is set but no worker is running.
  Either start the worker (`docker compose --profile async up`) or unset the
  broker so jobs run in-process.
* **Applicant progress never updates on Vercel** — serverless functions cannot
  hold a WebSocket. The client switches to polling automatically; if it does not,
  check that `NEXT_PUBLIC_API_BASE_URL=/api` was set **before** the build.
* **CORS errors in the browser** — add your frontend origin to `CORS_ORIGINS`.
* **A `x-pii-redactions` header appears on a response** — that is the privacy
  gateway removing a direct identifier from the request body, working as
  intended.
