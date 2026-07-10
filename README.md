# Expert Call Rating Interface

Mobile-first call review workspace for expert raters. The app is split into two deployable modules:

- `frontend/`: Vite + React static app, ready for Vercel.
- `backend/`: Python HTTP API with SQLite by default and a repository interface that can be swapped to Postgres.

## Quick Start

```bash
cd backend
python3 scripts/import_calls.py "/Users/rohithputha/Downloads/Rubric Sample Calls.xlsx"
python3 app.py
```

```bash
cd frontend
npm install
npm run dev
```

Set `VITE_API_URL=http://localhost:8787` for local API-backed mode. Without it, the frontend falls back to bundled sample data.

## Backend

The backend defaults to `backend/data/calls.sqlite3`.

Environment variables:

- `PORT`: API port, default `8787`.
- `DATABASE_URL`: SQLite file path or URL. Use `sqlite:///path/to/file.sqlite3` for SQLite. A Postgres URL selects the Postgres adapter placeholder in `backend/db.py`.
- `CORS_ORIGIN`: allowed origin, default `*`.

API endpoints:

- `GET /health`
- `GET /api/rubric`
- `GET /api/calls`
- `GET /api/calls/{call_id}`
- `POST /api/ratings`

## Frontend

The frontend is designed for expert phone use first:

- sticky audio player and call position
- segmented conversation/tool-call review
- vertical rating choices with descriptions visible
- required evidence notes
- call queue and completion progress

For Vercel, set the project root to `frontend/` and add `VITE_API_URL` pointing at the deployed backend.

## Railway Backend Deployment

This repo includes a root `Dockerfile` for Railway. It builds only the Python backend and ignores local/generated artifacts through `.dockerignore`.

1. In Railway, create a new project from the GitHub repo `rohithputha/expert-interface`.
2. Add a PostgreSQL service in the same Railway project.
3. On the backend service, set variables:
   - `DATABASE_URL=${{Postgres.DATABASE_URL}}`
   - `CORS_ORIGIN=https://your-vercel-domain.vercel.app,http://localhost:5173`
4. Deploy the backend service.
5. In backend service settings, generate a Railway public domain.
6. Test `https://your-railway-domain/health`.
7. In Vercel, set `VITE_API_URL=https://your-railway-domain` and redeploy the frontend.

To import real calls into Railway Postgres, do not commit the workbook or generated call JSON. Use the Railway Postgres external connection string, then run locally:

```bash
cd backend
DATABASE_URL="postgresql://..." python3 scripts/import_calls.py "/path/to/Rubric Sample Calls.xlsx"
```

The importer writes directly into the configured database and keeps transcript/audio data out of GitHub.
