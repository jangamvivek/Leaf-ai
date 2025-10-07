import base64
import os
from typing import Optional

import httpx
import logging
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import re


load_dotenv(dotenv_path=Path(__file__).parent / ".env")

PERPLEXITY_API_KEY: Optional[str] = os.getenv("PERPLEXITY_API_KEY")
PERPLEXITY_API_URL = "https://api.perplexity.ai/chat/completions"
MODEL_NAME = os.getenv("PERPLEXITY_MODEL", "sonar-reasoning")

MAX_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_MIME = {"image/png", "image/jpeg"}


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("leaf-ai")

app = FastAPI(title="Leaf AI Backend", version="0.1.0")

# Log whether the API key is present (without exposing it)
logger.info("PERPLEXITY_API_KEY present: %s", "yes" if bool(PERPLEXITY_API_KEY) else "no")

# CORS
frontend_origin_env = os.getenv("FRONTEND_ORIGIN", "http://localhost:4200")
allowed_origins = {
    frontend_origin_env,
    "http://127.0.0.1:4200",
    "http://192.168.1.4:4200",
}
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(allowed_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/analyze")
async def analyze(file: UploadFile = File(...), prompt: str = Form("")):
    if not PERPLEXITY_API_KEY:
        raise HTTPException(status_code=500, detail="PERPLEXITY_API_KEY is not configured")

    if file.content_type not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Only PNG and JPG/JPEG files are allowed.")

    # Read file content once
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=400, detail="File too large. Max 10 MB.")

    # Persist original image to uploads directory
    uploads_dir = Path(__file__).parent / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)
    # Create a safe unique filename
    original_name = Path(file.filename).name
    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%S%fZ")
    safe_name = f"{timestamp}_{original_name}"
    saved_path = uploads_dir / safe_name
    try:
        with open(saved_path, "wb") as f:
            f.write(content)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {ex}")

    # Base64-encode from saved file to ensure full content
    try:
        saved_bytes = saved_path.read_bytes()
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"Failed to read saved file: {ex}")
    b64 = base64.b64encode(saved_bytes).decode("utf-8")
    data_uri = f"data:{file.content_type};base64,{b64}"

    user_text = prompt.strip() if prompt else "Analyze this leaf image for potential diseases and provide suggestions."

    payload = {
        "model": MODEL_NAME,
        "messages": [
            {
                "role": "system",
                "content": "You are an expert agronomist. Identify likely leaf diseases and provide concise, practical guidance."
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_uri}}
                ],
            },
        ],
        "temperature": 0.2,
    }

    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        logger.info("/analyze called: filename=%s, size=%s bytes, mime=%s, prompt_len=%s", file.filename, len(content), file.content_type, len(user_text))
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(PERPLEXITY_API_URL, headers=headers, json=payload)
        logger.info("Perplexity response: status=%s", resp.status_code)
        if resp.status_code >= 400:
            # Surface Perplexity error details if present
            try:
                detail = resp.json()
            except Exception:
                detail = {"message": resp.text}
            # Log the error body for debugging
            try:
                logger.error("Perplexity error body: %s", resp.text)
            except Exception:
                pass
            raise HTTPException(status_code=resp.status_code, detail=detail)

        data = resp.json()

        # Extract assistant text safely from Perplexity response
        assistant_text = ""
        try:
            choice = (data.get("choices") or [{}])[0]
            message = (choice or {}).get("message") or {}
            content = message.get("content")
            if isinstance(content, list):
                # find text-like part
                for part in content:
                    ptype = part.get("type") if isinstance(part, dict) else None
                    if ptype in ("output_text", "text"):
                        assistant_text = part.get("text") or ""
                        break
            elif isinstance(content, str):
                assistant_text = content
            elif isinstance(message, dict) and isinstance(message.get("content"), dict):
                assistant_text = message["content"].get("text", "")
        except Exception:
            assistant_text = ""

        # Final cleanup: remove hidden reasoning tags or meta preambles
        def clean_model_text(text: str) -> str:
            if not isinstance(text, str):
                return ""
            # Remove <think>...</think> blocks, case-insensitive, dotall
            text = re.sub(r"(?is)<think>.*?</think>", "", text)
            # Remove common meta-analysis preambles sometimes included
            meta_patterns = [
                r"(?is)^\s*the\s+user\s+is\s+asking\s+me.*?(?:\n\n|$)",
                r"(?is)^\s*i\s+can\s+see\s+the\s+image.*?(?:\n\n|$)",
                r"(?is)^\s*i\s+should\b.*?(?:\n\n|$)",
                r"(?is)^\s*based\s+on\s+the\s+.*?(?:\n\n|$)",
            ]
            for pat in meta_patterns:
                text = re.sub(pat, "", text)
            # Trim excessive blank lines
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
            return text

        assistant_text = clean_model_text(assistant_text)

        return JSONResponse(content={
            "success": True,
            "data": {
                "filename": file.filename,
                "content_type": file.content_type,
                "prompt": user_text,
                "model": data.get("model"),
                "message": assistant_text,
                "usage": data.get("usage"),
                "source": "perplexity",
                "raw": data,
            }
        })
    except HTTPException:
        raise
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

