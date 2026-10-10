import os
import tempfile
from fastapi import APIRouter, UploadFile, File
from faster_whisper import WhisperModel

router = APIRouter()
_model = None


def get_model():
    global _model
    if _model is None:
        _model = WhisperModel("small", device="cpu", compute_type="int8")
    return _model


@router.post("/voice/transcribe")
def transcribe(audio: UploadFile = File(...)):
    suffix = os.path.splitext(audio.filename or "")[1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(audio.file.read())
        path = tmp.name
    try:
        segments, _ = get_model().transcribe(
            path, language="en", beam_size=5, vad_filter=True
        )
        text = " ".join(s.text.strip() for s in segments).strip()
    finally:
        os.remove(path)
    return {"text": text}