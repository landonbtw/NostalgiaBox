#include "speaker.h"
#include <ESP_I2S.h>

// ---- Speaker (PCM5101 DAC) I2S pins (Waveshare wiki) ----
#define SPK_BCK   48
#define SPK_WS    38
#define SPK_DOUT  47

#define PLAY_RATE 24000    // answer audio is 24 kHz mono (see server lib/wav.ts)

static I2SClass s_i2s;

bool Speaker_Begin()
{
  s_i2s.setPins(SPK_BCK, SPK_WS, SPK_DOUT, -1 /*din*/, -1 /*mclk*/);
  if (!s_i2s.begin(I2S_MODE_STD, PLAY_RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_STEREO)) {
    Serial.println("[spk] i2s begin FAILED");
    return false;
  }
  Serial.println("[spk] ready");
  return true;
}

// Read exactly `want` bytes from the stream (blocking with a bounded wait),
// pumping the UI while we wait. Returns bytes actually read.
static int read_exact(Stream &s, uint8_t *buf, int want, void (*pump)())
{
  int got = 0;
  uint32_t deadline = millis() + 4000;
  while (got < want && millis() < deadline) {
    int n = s.readBytes((char *)(buf + got), want - got);
    if (n > 0) {
      got += n;
      deadline = millis() + 4000;
    } else {
      if (pump) pump();
      delay(2);
    }
  }
  return got;
}

void Speaker_PlayWavStream(Stream &s, int contentLen, void (*pump)())
{
  uint8_t header[44];
  if (read_exact(s, header, 44, pump) < 44) {
    Serial.println("[spk] short WAV header");
    return;
  }
  if (memcmp(header, "RIFF", 4) != 0 || memcmp(header + 8, "WAVE", 4) != 0) {
    Serial.println("[spk] not a WAV stream");
    return;
  }

  int dataRemaining = (contentLen > 44) ? (contentLen - 44) : INT32_MAX;

  int16_t mono[512];
  int16_t stereo[512 * 2];

  while (dataRemaining > 0) {
    int want = (int)sizeof(mono);
    if (want > dataRemaining) want = dataRemaining;
    want &= ~0x1;                       // whole 16-bit samples
    if (want <= 0) break;

    int got = read_exact(s, (uint8_t *)mono, want, pump);
    if (got <= 0) break;
    dataRemaining -= got;

    int samples = got / 2;
    for (int i = 0; i < samples; i++) {
      stereo[i * 2] = mono[i];
      stereo[i * 2 + 1] = mono[i];
    }
    s_i2s.write((uint8_t *)stereo, samples * 2 * sizeof(int16_t));

    if (pump) pump();
  }
  Serial.println("[spk] playback done");
}
