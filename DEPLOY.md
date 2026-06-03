# minggultip deploy guide

## Recommended: Render

This project includes `render.yaml`, so Render can create both the web app and PostgreSQL database from the repository.

1. Push this project to GitHub.
2. Go to Render and choose **New > Blueprint**.
3. Select the GitHub repository.
4. Render will read `render.yaml` and create:
   - `minggultip` web service
   - `minggultip-db` PostgreSQL database
5. Deploy.

Render sets these environment variables from `render.yaml`:

- `SECRET_KEY`
- `DATABASE_URL`

The app creates database tables automatically on startup.

## Local run

```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Notes

- Do not commit `.env` or `app.db`.
- SQLite is fine for local development.
- PostgreSQL is recommended for a deployed community site.
