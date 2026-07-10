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
