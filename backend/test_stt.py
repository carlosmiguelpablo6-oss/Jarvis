import sounddevice as sd
from faster_whisper import WhisperModel

RATE = 16000
SECONDS = 5

print("Loading model...")
model = WhisperModel("small", device="cpu", compute_type="int8")

print("Speak now for 5 seconds...")
audio = sd.rec(int(SECONDS * RATE), samplerate=RATE,
               channels=1, dtype="float32")
sd.wait()

segments, _ = model.transcribe(audio.flatten(),
                               language="en", beam_size=5)
print("Heard:", " ".join(s.text.strip() for s in segments))