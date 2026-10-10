// Audio helpers for the microphone button.
// Turns a recording (from MediaRecorder) into the 16 kHz mono WAV that Whisper expects.
(function (root) {
  const TARGET_RATE = 16000;

  // Average all channels into one.
  function mixToMono(audioBuffer) {
    const channels = audioBuffer.numberOfChannels;
    const length = audioBuffer.length;
    if (channels === 1) return audioBuffer.getChannelData(0);
    const mono = new Float32Array(length);
    for (let c = 0; c < channels; c++) {
      const data = audioBuffer.getChannelData(c);
      for (let i = 0; i < length; i++) mono[i] += data[i] / channels;
    }
    return mono;
  }

  // Lower the sample rate by averaging each window (a simple low-pass filter).
  function downsample(samples, srcRate, targetRate = TARGET_RATE) {
    if (srcRate === targetRate) return samples;
    const ratio = srcRate / targetRate;
    const outLength = Math.floor(samples.length / ratio);
    const out = new Float32Array(outLength);
    for (let i = 0; i < outLength; i++) {
      const start = i * ratio;
      const end = (i + 1) * ratio;
      let sum = 0;
      let weight = 0;
      for (let j = Math.floor(start); j < Math.ceil(end) && j < samples.length; j++) {
        const w = Math.min(j + 1, end) - Math.max(j, start);
        sum += samples[j] * w;
        weight += w;
      }
      out[i] = weight ? sum / weight : 0;
    }
    return out;
  }

  // Float samples (-1 to 1) to a 16-bit mono WAV file.
  function encodeWav(samples, sampleRate = TARGET_RATE) {
    const buffer = new ArrayBuffer(44 + samples.length * 2);
    const view = new DataView(buffer);
    const writeText = (offset, text) => {
      for (let i = 0; i < text.length; i++) view.setUint8(offset + i, text.charCodeAt(i));
    };
    writeText(0, "RIFF");
    view.setUint32(4, 36 + samples.length * 2, true);
    writeText(8, "WAVE");
    writeText(12, "fmt ");
    view.setUint32(16, 16, true); // size of the fmt block
    view.setUint16(20, 1, true); // PCM
    view.setUint16(22, 1, true); // mono
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * 2, true); // bytes per second
    view.setUint16(32, 2, true); // bytes per sample frame
    view.setUint16(34, 16, true); // bits per sample
    writeText(36, "data");
    view.setUint32(40, samples.length * 2, true);
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return buffer;
  }

  function blobToArrayBuffer(blob) {
    if (blob.arrayBuffer) return blob.arrayBuffer();
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result);
      reader.onerror = () => reject(reader.error);
      reader.readAsArrayBuffer(blob);
    });
  }

  async function blobToWav(blob) {
    const Context = root.AudioContext || root.webkitAudioContext;
    const context = new Context();
    try {
      const decoded = await context.decodeAudioData(await blobToArrayBuffer(blob));
      const mono = mixToMono(decoded);
      return encodeWav(downsample(mono, decoded.sampleRate), TARGET_RATE);
    } finally {
      if (context.close) context.close();
    }
  }

  const api = { mixToMono, downsample, encodeWav, blobToWav, TARGET_RATE };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.JarvisAudio = api;
})(typeof window !== "undefined" ? window : globalThis);