/**
 * Minimal WAV (PCM 16-bit) helpers.
 *
 * The device plays raw PCM straight to the PCM5101 speaker, so we hand it a
 * self-describing WAV (the 44-byte header carries sample rate / channels /
 * bit depth). This same helper wraps real TTS PCM output in Stage 4.
 */

export interface WavParams {
  sampleRate: number;
  numChannels: number;
}

/** Wrap 16-bit little-endian PCM bytes in a WAV container. */
export function encodeWav(pcm: Buffer, { sampleRate, numChannels }: WavParams): Buffer {
  const bitsPerSample = 16;
  const byteRate = (sampleRate * numChannels * bitsPerSample) / 8;
  const blockAlign = (numChannels * bitsPerSample) / 8;
  const header = Buffer.alloc(44);

  header.write("RIFF", 0);
  header.writeUInt32LE(36 + pcm.length, 4);
  header.write("WAVE", 8);
  header.write("fmt ", 12);
  header.writeUInt32LE(16, 16); // PCM fmt chunk size
  header.writeUInt16LE(1, 20); // audio format = PCM
  header.writeUInt16LE(numChannels, 22);
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(byteRate, 28);
  header.writeUInt16LE(blockAlign, 32);
  header.writeUInt16LE(bitsPerSample, 34);
  header.write("data", 36);
  header.writeUInt32LE(pcm.length, 40);

  return Buffer.concat([header, pcm]);
}

/**
 * A warm, short "hello" chime (rising major arpeggio) used as the Stage 3
 * placeholder answer audio, purely to prove the speaker path end-to-end.
 * Replaced by real text-to-speech in Stage 4.
 */
export function generateChimeWav(sampleRate = 24000): Buffer {
  const notes = [523.25, 659.25, 783.99, 1046.5]; // C5 E5 G5 C6
  const noteDur = 0.16; // seconds per note
  const total = notes.length * noteDur;
  const n = Math.floor(total * sampleRate);
  const pcm = Buffer.alloc(n * 2);

  for (let i = 0; i < n; i++) {
    const t = i / sampleRate;
    const noteIndex = Math.min(notes.length - 1, Math.floor(t / noteDur));
    const tIn = t - noteIndex * noteDur;
    // Gentle attack/decay envelope so it sounds soft, not harsh.
    const env = Math.sin((Math.PI * tIn) / noteDur);
    const sample = Math.sin(2 * Math.PI * notes[noteIndex] * t) * env * 0.5;
    const s = Math.max(-1, Math.min(1, sample));
    pcm.writeInt16LE((s * 32767) | 0, i * 2);
  }

  return encodeWav(pcm, { sampleRate, numChannels: 1 });
}
