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
3. Open `http://localhost:8000` in your browser.

## Future: Firebase Authentication
To protect the `/chat` endpoint from unauthorized access in a future phase:
1. Initialize Firebase Auth in `frontend/index.html` using the CDN.
2. Force users to sign in before seeing the chat UI.
3. Call `firebase.auth().currentUser.getIdToken()` to get a fresh token.
4. Add the token to the `/chat` request: `headers: { 'Authorization': 'Bearer ' + token }`.
5. In `backend/main.py`, use the `firebase-admin` Python SDK. Create a FastAPI dependency (`Depends()`) that calls `auth.verify_id_token(token)` to validate the user before processing the message.
