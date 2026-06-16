# ReadFlow AI

ReadFlow AI is a Flask reading platform for uploaded documents, OCR, RSVP speed reading, saved reading history, analytics, notes, highlights, bookmarks, settings, global search, and AI-ready study tools.

## Final Product Features

- User registration, login, logout, password hashing, and session management
- Private document library per user
- PDF, DOCX, TXT, JPG, JPEG, PNG, WEBP upload support
- Scanned PDF OCR fallback with `pdf2image` and EasyOCR
- Continue reading from last saved position
- Rename, reopen, and delete documents
- Reading sessions with duration, WPM, mode, completion, and words read
- Analytics dashboard with totals, averages, highest WPM, streak, completed sessions, and visual bars
- Bookmarks, notes, and highlights per document
- Global search across documents, notes, and history
- Persisted settings for WPM, reading mode, smart pauses, theme, and font size
- Pluggable AI architecture for summaries, takeaways, flashcards, quizzes, study notes, and vocabulary

## Architecture Decisions

- `app.py` owns route registration and keeps the app factory pattern available through `create_app`.
- `db.py` centralizes SQLite connection handling, schema creation, lightweight migrations, and shared queries.
- `auth.py` isolates password hashing, login loading, and the `login_required` decorator.
- `document_utils.py` keeps upload validation, extraction dispatch, text cleanup, and word counting outside routes.
- `services/` remains focused on file extraction and OCR.
- `ai_providers.py` defines a provider contract. The current provider is a local placeholder so OpenAI, Gemini, Anthropic, or local model adapters can be added without changing routes.

## Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`.

## Migration Steps

The app creates and migrates SQLite tables automatically at startup.

For an existing Phase 1 or Phase 2 database:

1. Back up `readflow.db`.
2. Install the new requirements.
3. Start the app once with `python app.py`.
4. New tables are created automatically.
5. Missing `documents` columns are added automatically.

Older anonymous documents will remain in SQLite but will not be assigned to a user. Re-upload or paste them into a signed-in account if they should appear in a private library.

## Environment Variables

```bash
SECRET_KEY=replace-with-a-long-random-secret
DATABASE_PATH=readflow.db
UPLOAD_DIR=uploads
AI_PROVIDER=disabled
```

## OCR Notes

Image OCR uses EasyOCR. Scanned PDF OCR requires Poppler because `pdf2image` uses Poppler tools to render pages.

On Windows, install Poppler and add its `bin` folder to `PATH`.

## Render Deployment

1. Create a new Render Web Service.
2. Set build command:

```bash
pip install -r requirements.txt
```

3. Set start command:

```bash
gunicorn app:app
```

4. Add environment variables:

```bash
SECRET_KEY=<secure random value>
DATABASE_PATH=/var/data/readflow.db
UPLOAD_DIR=/var/data/uploads
AI_PROVIDER=disabled
```

5. Add a persistent disk mounted at `/var/data`.
6. Ensure Poppler is available. For OCR-heavy production, Docker deployment is recommended.

## Railway Deployment

1. Create a Railway project from the repository.
2. Add environment variables:

```bash
SECRET_KEY=<secure random value>
DATABASE_PATH=/data/readflow.db
UPLOAD_DIR=/data/uploads
AI_PROVIDER=disabled
```

3. Use the included `Procfile`:

```bash
web: gunicorn app:app
```

4. Add persistent storage for `/data` if available.
5. Prefer Docker mode when using scanned PDF OCR so Poppler is installed consistently.

## Docker Deployment

```bash
docker build -t readflow-ai .
docker run -p 8000:8000 ^
  -e SECRET_KEY=replace-with-a-long-random-secret ^
  -v readflow_data:/data ^
  readflow-ai
```

Open `http://127.0.0.1:8000`.

## Production Checklist

- Set a strong `SECRET_KEY`.
- Use persistent storage for `DATABASE_PATH` and `UPLOAD_DIR`.
- Keep uploads private and backed up.
- Install Poppler for scanned PDF OCR.
- Put the app behind HTTPS.
- Consider moving from SQLite to Postgres before multi-instance deployment.
- Add a real AI provider by implementing `BaseAIProvider` in `ai_providers.py`.
