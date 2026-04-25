import os
import base64
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(title="Learnr API")

# Setup CORS to allow frontend testing
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Google client
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

class ChatRequest(BaseModel):
    message: str
    session_id: str
    file_content: Optional[str] = None
    file_type: Optional[str] = None

class ChatResponse(BaseModel):
    reply: str

SYSTEM_PROMPT = """You are Learnr, a friendly and adaptive learning assistant. Your goal is to help users understand new concepts clearly. Ask clarifying questions to gauge their existing knowledge. Use analogies, examples, and step-by-step breakdowns. Keep responses concise and encouraging."""

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
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
                    # Strip base64 prefix if present (e.g. data:image/jpeg;base64,...)
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
                # Handle text/PDF extracted content
                parts.append(f"Here is the content of the file the user uploaded:\n\n{request.file_content}\n\nNow answer: {request.message}")
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
