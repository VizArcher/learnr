import os
import base64
import time
from datetime import datetime
from typing import Optional, Dict, List
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import google.generativeai as genai
from google.cloud import storage
import google.cloud.logging
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Setup Google Cloud Logging
try:
    client = google.cloud.logging.Client()
    client.setup_logging()
except Exception as e:
    # Fallback to standard logging if not running in GCP / lacking credentials
    logging.basicConfig(level=logging.INFO)
    logging.warning(f"Could not initialize Google Cloud Logging: {e}")

logger = logging.getLogger("learnr")

# Setup Google Cloud Storage
storage_client = None
try:
    storage_client = storage.Client()
except Exception as e:
    logger.warning(f"Could not initialize Google Cloud Storage client: {e}")

# Security Assertion
assert os.getenv("GEMINI_API_KEY"), "GEMINI_API_KEY must be set in the environment and not hardcoded"

app = FastAPI(title="Learnr API")

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    csp = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self';"
    )
    response.headers["Content-Security-Policy"] = csp
    return response

# Setup CORS
allowed_origins_env = os.getenv("ALLOWED_ORIGINS", "")
origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]
if not origins:
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Google client
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Validation Schemas
class ChatRequest(BaseModel):
    message: str = Field(..., max_length=4000)
    session_id: str = Field(..., pattern=r'^[a-zA-Z0-9\-]+$')
    file_content: Optional[str] = Field(None, max_length=500_000)
    file_type: Optional[str] = None
    filename: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str
    gcs_uri: Optional[str] = None

SYSTEM_PROMPT = """You are Learnr, a friendly and adaptive learning assistant. Your goal is to help users understand new concepts clearly. Ask clarifying questions to gauge their existing knowledge. Use analogies, examples, and step-by-step breakdowns. Keep responses concise and encouraging."""

# In-memory Rate Limiting
rate_limits: Dict[str, List[float]] = {}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    start_time = time.time()
    
    # Rate Limiting Logic (Max 20 requests per minute per session)
    now = time.time()
    user_times = rate_limits.get(request.session_id, [])
    user_times = [t for t in user_times if now - t < 60]
    
    if len(user_times) >= 20:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Maximum 20 requests per minute.")
    
    user_times.append(now)
    rate_limits[request.session_id] = user_times

    try:
        model = genai.GenerativeModel(
            model_name="gemini-3-flash-preview",
            system_instruction=SYSTEM_PROMPT
        )
        
        parts = []
        gcs_uri = None
        raw_bytes_to_upload = None
        content_type_to_upload = request.file_type or "text/plain"

        if request.file_content and request.file_type:
            if request.file_type.startswith("image/"):
                try:
                    base64_data = request.file_content
                    if "," in base64_data:
                        base64_data = base64_data.split(",")[1]
                    
                    image_bytes = base64.b64decode(base64_data)
                    raw_bytes_to_upload = image_bytes
                    parts.append({"mime_type": request.file_type, "data": image_bytes})
                    parts.append(request.message)
                except Exception as b64_err:
                    logger.error(f"Error decoding base64 image: {b64_err}")
                    parts.append(request.message)
            else:
                sanitized_content = request.file_content.replace('\x00', '')[:50000]
                raw_bytes_to_upload = sanitized_content.encode("utf-8")
                parts.append(f"Here is the content of the file the user uploaded:\n\n{sanitized_content}\n\nNow answer: {request.message}")
        else:
            parts.append(request.message)

        # Handle GCS Upload
        if raw_bytes_to_upload and request.filename and storage_client:
            project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
            if project_id:
                bucket_name = f"learnr-uploads-{project_id}"
                try:
                    bucket = storage_client.bucket(bucket_name)
                    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
                    blob_name = f"uploads/{request.session_id}/{timestamp}_{request.filename}"
                    blob = bucket.blob(blob_name)
                    blob.upload_from_string(raw_bytes_to_upload, content_type=content_type_to_upload)
                    gcs_uri = f"gs://{bucket_name}/{blob_name}"
                except Exception as e:
                    logger.error(f"GCS upload failed: {e}")

        response = model.generate_content(parts)
        reply_text = response.text
        
        # Logging
        response_time_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "Chat request processed",
            extra={
                "json_fields": {
                    "session_id": request.session_id,
                    "message_length": len(request.message),
                    "file_type": request.file_type,
                    "response_time_ms": response_time_ms,
                    "gcs_uri": gcs_uri
                }
            }
        )
        
        return ChatResponse(reply=reply_text, gcs_uri=gcs_uri)
    except Exception as e:
        logger.error(f"Chat request failed: {str(e)}")
        return ChatResponse(reply=f"Error processing your request: {str(e)}")

# Mount the frontend directory to serve the static HTML file
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
