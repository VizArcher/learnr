import os
import base64
import time
from typing import Optional, Dict, List
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Security Assertion
assert os.getenv("GEMINI_API_KEY"), "GEMINI_API_KEY must be set in the environment and not hardcoded"

app = FastAPI(title="Learnr API")

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    # Define Content-Security-Policy
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
    origins = ["*"]  # Fallback for local development if not set

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

class ChatResponse(BaseModel):
    reply: str

SYSTEM_PROMPT = """You are Learnr, a friendly and adaptive learning assistant. Your goal is to help users understand new concepts clearly. Ask clarifying questions to gauge their existing knowledge. Use analogies, examples, and step-by-step breakdowns. Keep responses concise and encouraging."""

# In-memory Rate Limiting
rate_limits: Dict[str, List[float]] = {}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    # Rate Limiting Logic (Max 20 requests per minute per session)
    now = time.time()
    user_times = rate_limits.get(request.session_id, [])
    # Filter timestamps within the last 60 seconds
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
        if request.file_content and request.file_type:
            if request.file_type.startswith("image/"):
                # Handle multimodal image directly using native blob
                try:
                    base64_data = request.file_content
                    if "," in base64_data:
                        base64_data = base64_data.split(",")[1]
                    
                    image_bytes = base64.b64decode(base64_data)
                    parts.append({"mime_type": request.file_type, "data": image_bytes})
                    parts.append(request.message)
                except Exception as b64_err:
                    print("Error decoding base64 image:", b64_err)
                    parts.append(request.message)
            else:
                # Sanitize text/PDF extracted content (strip null bytes, limit to 50k chars)
                sanitized_content = request.file_content.replace('\x00', '')[:50000]
                parts.append(f"Here is the content of the file the user uploaded:\n\n{sanitized_content}\n\nNow answer: {request.message}")
        else:
            parts.append(request.message)

        response = model.generate_content(parts)
        reply_text = response.text
        return ChatResponse(reply=reply_text)
    except Exception as e:
        return ChatResponse(reply=f"Error processing your request: {str(e)}")

# Mount the frontend directory to serve the static HTML file
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
