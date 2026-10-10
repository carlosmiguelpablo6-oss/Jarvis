import io
import re
import wave
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from piper import PiperVoice

router = APIRouter()

# Download once with: python -m piper.download_voices en_US-lessac-medium
VOICE_PATH = Path(__file__).parent.parent / "voices" / "en_US-lessac-medium.onnx"
MAX_SPOKEN_CHARS = 700

_voice = None


def get_voice():
    global _voice
    if _voice is None:
        _voice = PiperVoice.load(str(VOICE_PATH))
    return _voice


def clean_for_speech(text):
    """Make a chat reply sound natural when read aloud."""
    text = re.sub(r"https?://\S+", "", text)
    text = re.sub(r"[*_`#>]", "", text)
    text = text.replace("\u00b0C", " degrees Celsius").replace("%", " percent")
    text = re.sub(r"\s+-\s+", ", ", text)
    text = re.sub(r"\s*\n+\s*", ". ", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_SPOKEN_CHARS]


class SpeakRequest(BaseModel):
    text: str


@router.post("/voice/speak")
def speak(req: SpeakRequest):
    text = clean_for_speech(req.text)
    if not text:
        raise HTTPException(status_code=400, detail="Nothing to say.")
    if _voice is None and not VOICE_PATH.exists():
        raise HTTPException(
            status_code=503,
            detail=f"Voice file not found: {VOICE_PATH}. See the Piper setup steps.",
        )
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        get_voice().synthesize_wav(text, wav_file)
    return Response(content=buffer.getvalue(), media_type="audio/wav")