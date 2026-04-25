# learnr
An intelligent learning assistant web app.

## Setup

1. Add your Google Gemini API Key to `backend/.env`.
2. Start the backend:
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   uvicorn main:app --reload
   ```
3. Open `frontend/index.html` in your browser.
