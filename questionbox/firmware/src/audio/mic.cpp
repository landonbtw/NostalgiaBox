#include "mic.h"
#include <Arduino.h>
#include <ESP_I2S.h>
#include <esp_heap_caps.h>

// ---- Microphone I2S pins (Waveshare wiki) ----
#define MIC_BCK   15
#define MIC_WS     2
#define MIC_DIN   39

#define REC_RATE        16000        // 16 kHz is plenty for speech-to-text
#define REC_MAX_SEC     10
#define REC_MAX_SAMPLES (REC_RATE * REC_MAX_SEC)   // mono samples
#define WAV_HEADER_LEN  44

// Auto-stop tuning.
#define SILENCE_RMS      700         // below this counts as "quiet"
#define SILENCE_MS       1200        // stop this long after speech ends
#define MIN_RECORD_MS    400         // don't auto-stop before this

static I2SClass s_i2s;
static uint8_t *s_buf = nullptr;     // [WAV header | mono int16 PCM]
static size_t   s_count = 0;         // mono samples captured
static bool     s_recording = false;

static bool     s_speech = false;
static uint32_t s_start_ms = 0;
static uint32_t s_last_loud_ms = 0;

static inline int16_t clamp16(int32_t v)
{
  if (v > 32767) return 32767;
  if (v < -32768) return -32768;
  return (int16_t)v;
}

static void write_wav_header(uint8_t *h, uint32_t dataLen, uint32_t rate)
{
  const uint16_t channels = 1, bits = 16;
  const uint32_t byteRate = rate * channels * bits / 8;
  const uint16_t blockAlign = channels * bits / 8;
  memcpy(h + 0, "RIFF", 4);
  *(uint32_t *)(h + 4) = 36 + dataLen;
  memcpy(h + 8, "WAVE", 4);
  memcpy(h + 12, "fmt ", 4);
  *(uint32_t *)(h + 16) = 16;
  *(uint16_t *)(h + 20) = 1;          // PCM
  *(uint16_t *)(h + 22) = channels;
  *(uint32_t *)(h + 24) = rate;
  *(uint32_t *)(h + 28) = byteRate;
  *(uint16_t *)(h + 32) = blockAlign;
  *(uint16_t *)(h + 34) = bits;
  memcpy(h + 36, "data", 4);
  *(uint32_t *)(h + 40) = dataLen;
}

bool Mic_Begin()
{
  s_buf = (uint8_t *)heap_caps_malloc(WAV_HEADER_LEN + REC_MAX_SAMPLES * 2, MALLOC_CAP_SPIRAM);
  if (!s_buf) {
    Serial.println("[mic] FAILED to allocate PSRAM record buffer");
    return false;
  }
  // Capture in STEREO and sum the two slots when downmixing: this makes us
  // robust to whether the MEMS mic sits on the left or right I2S slot.
  s_i2s.setPins(MIC_BCK, MIC_WS, -1 /*dout*/, MIC_DIN, -1 /*mclk*/);
  if (!s_i2s.begin(I2S_MODE_STD, REC_RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO)) {
    Serial.println("[mic] i2s begin FAILED");
    return false;
  }
  Serial.println("[mic] ready");
  return true;
}

void Mic_Start()
{
  // Drop any stale samples sitting in the DMA buffer.
  uint8_t scratch[512];
  while (s_i2s.available() > 0) {
    int n = s_i2s.available();
    if (n > (int)sizeof(scratch)) n = sizeof(scratch);
    if (s_i2s.readBytes((char *)scratch, n) <= 0) break;
  }
  s_count = 0;
  s_recording = true;
  s_speech = false;
  s_start_ms = millis();
  s_last_loud_ms = s_start_ms;
  Serial.println("[mic] recording started");
}

void Mic_Stop()
{
  if (!s_recording) return;
  s_recording = false;
  Serial.printf("[mic] recording stopped (%u samples, %.2fs)\n",
                (unsigned)s_count, (float)s_count / REC_RATE);
}

bool Mic_Poll()
{
  if (!s_recording) return false;

  // Read whatever is currently available (non-blocking), a chunk at a time.
  uint8_t tmp[2048];                          // stereo int16 frames = 4 bytes each
  int avail = s_i2s.available();
  if (avail > 0) {
    int n = avail;
    if (n > (int)sizeof(tmp)) n = sizeof(tmp);
    n &= ~0x3;                                 // whole stereo frames only
    if (n > 0) {
      int got = s_i2s.readBytes((char *)tmp, n);
      int frames = got / 4;
      int16_t *in = (int16_t *)tmp;
      int16_t *out = (int16_t *)(s_buf + WAV_HEADER_LEN);
      uint64_t energy = 0;
      for (int i = 0; i < frames && s_count < REC_MAX_SAMPLES; i++) {
        int32_t mono = (int32_t)in[i * 2] + (int32_t)in[i * 2 + 1];  // L + R
        int16_t m = clamp16(mono);
        out[s_count++] = m;
        energy += (uint64_t)((int32_t)m * m);
      }
      if (frames > 0) {
        uint32_t rms = (uint32_t)sqrt((double)energy / frames);
        if (rms > SILENCE_RMS) {
          s_speech = true;
          s_last_loud_ms = millis();
        }
      }
    }
  }

  uint32_t now = millis();
  bool max_reached = s_count >= REC_MAX_SAMPLES;
  bool silence_stop = s_speech && (now - s_start_ms > MIN_RECORD_MS) &&
                      (now - s_last_loud_ms > SILENCE_MS);
  if (max_reached || silence_stop) {
    Mic_Stop();
    return false;
  }
  return true;
}

bool Mic_GetWav(const uint8_t **data, size_t *len)
{
  if (!s_buf || s_count == 0) return false;
  uint32_t dataLen = s_count * 2;
  write_wav_header(s_buf, dataLen, REC_RATE);
  *data = s_buf;
  *len = WAV_HEADER_LEN + dataLen;
  return true;
}
