import os
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
        response = model.generate_content(request.message)
        reply_text = response.text
        return ChatResponse(reply=reply_text)
    except Exception as e:
        return ChatResponse(reply=f"Error processing your request: {str(e)}")

# Mount the frontend directory to serve the static HTML file
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
