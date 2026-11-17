# Deployment guide

MediScan AI has two deployable parts:

| Part | Where | Why |
|---|---|---|
| `frontend/` (Next.js) | **Vercel** | Static + client-rendered pages; ideal for Vercel. |
| `backend/` + `ml/` + `models/` (FastAPI) | **Docker host** (Render, Railway, Fly.io, AWS App Runner, Azure Container Apps, a VM…) | Needs the Tesseract binary, OpenCV, XGBoost, SHAP and PyTorch (~1 GB+). Vercel Python functions have a 250 MB unzipped bundle limit, a read-only filesystem and no apt packages, and time-limited executions – unsuitable for OCR + ML inference and for long-running jobs. Check current limits at vercel.com/docs/functions/limitations before changing this. |

Status: the frontend production build and the API (with SQLite **and** PostgreSQL 16) were tested locally. The Docker image could not be built in the authoring environment (Docker Hub blocked) and nothing has been deployed publicly yet. Verify each step below yourself.

## 1. Push to GitHub

```bash
cd MediScan-AI
git init && git add . && git commit -m "MediScan AI initial commit"
git branch -M main
git remote add origin https://github.com/<you>/MediScan-AI.git
git push -u origin main
```

`models/` (≈ 10 MB) is committed so the API can serve without retraining. Datasets and `.env` are git-ignored.

## 2. Deploy the backend (Render example)

1. Render → **New → Blueprint** → select the repo. `render.yaml` creates `mediscan-api` (Docker) and a PostgreSQL database.
2. Choose an instance with **≥ 2 GB RAM** (OCR + XGBoost + PyTorch). The free 512 MB plan will run out of memory.
3. Set the secret env vars when prompted:
   * `MEDISCAN_ENCRYPTION_KEY` – `python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"` (keep it safe: losing it makes stored data unreadable)
   * `CORS_ORIGINS` – your Vercel URL, e.g. `https://mediscan-ai.vercel.app`
   * `MEDISCAN_API_KEY` – optional shared secret
4. Wait for the deploy, then open `https://<api>.onrender.com/health` → `{"status":"ok","models":["ecg","liver"]}`.

Other hosts: `docker build -f backend/Dockerfile -t mediscan-api .` from the repo root, run with `-p 8000:8000 -e DATABASE_URL=… -e MEDISCAN_ENCRYPTION_KEY=… -e CORS_ORIGINS=… -v data:/data`. The container honours `$PORT`.

`postgres://` and `postgresql://` URLs (as issued by Render/Heroku-style providers) are automatically rewritten to `postgresql+psycopg://`.

## 3. Deploy the frontend on Vercel

1. vercel.com → **Add New → Project** → import the GitHub repo.
2. **Root Directory: `frontend`** (Framework preset: Next.js is detected; `frontend/vercel.json` pins the build commands and security headers). The app is built as a static export (`output: "export"`).
3. Environment variables: `NEXT_PUBLIC_API_URL=https://<api-host>` (no trailing slash); `NEXT_PUBLIC_API_KEY` only if you set `MEDISCAN_API_KEY` (note it is visible in the browser – it is a basic gate, not authentication).
4. Deploy, then add the final Vercel URL to the backend's `CORS_ORIGINS` (or keep `CORS_ORIGIN_REGEX=https://.*\.vercel\.app` for previews) and redeploy the backend.
5. Smoke test: Dashboard loads stats → Upload a synthetic report from `tests/fixtures/make_fixtures.py` → Review → Confirm → module page → Summary PDF → delete it in History.

**Without Git (Vercel Drop / drag-and-drop):** Vercel Drop does not run a build, so dropping the source folder gives a `404: NOT_FOUND`. The frontend is a static export, so build it first and drop the *output*:

```bash
cd frontend && npm install && npm run build     # creates frontend/out/
```

Then drag the `out` folder onto vercel.com/new (Vercel Drop). Alternatively use the CLI from `frontend/`: `npx vercel --prod`.

**API URL at runtime:** if the site cannot reach the backend, the Dashboard shows a "Backend API URL" box; the value is saved in that browser and overrides `NEXT_PUBLIC_API_URL`.

## 4. Asynchronous processing

`POST /api/reports/upload` returns `{report_id, job_id}` immediately; the browser polls `GET /api/jobs/{job_id}` (`queued → running → succeeded|failed`, `progress`, `stage`, `attempts`). Failed jobs are retried `JOB_MAX_RETRIES` times; the report row is marked `failed` with a safe message. The in-process executor is fine for one instance; for horizontal scaling move `backend/services/jobs.py` to Redis + RQ/Celery/Arq (same `submit/get_job` interface).

## 5. Production checklist

- [ ] `ENFORCE_HTTPS=true` behind the platform's TLS proxy (HSTS + redirect)
- [ ] Explicit `MEDISCAN_ENCRYPTION_KEY`, backed up securely; database encryption at rest enabled at the provider
- [ ] `CORS_ORIGINS` limited to your frontend
- [ ] Add real authentication (e.g. Auth.js / Clerk on the frontend + JWT verification in FastAPI) before storing real patient data
- [ ] Persistent disk mounted at `/data` only if users may consent to file storage
- [ ] Platform logs do not include request bodies (the app itself logs no document content)
