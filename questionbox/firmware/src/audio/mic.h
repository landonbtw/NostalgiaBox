#pragma once
#include <stddef.h>
#include <stdint.h>

// Records mono 16 kHz / 16-bit audio from the board's I2S MEMS microphone into
// a PSRAM buffer, and hands back a ready-to-POST WAV. PUSH-TO-TALK only.

bool Mic_Begin();

// Begin a fresh recording (flushes stale mic data).
void Mic_Start();

// Pump the recording; call frequently while LISTENING. Non-blocking.
// Returns true while still recording, false once it has auto-stopped
// (silence after speech, or the max duration was reached).
bool Mic_Poll();

// Force-stop recording (e.g. the child tapped the mic again).
void Mic_Stop();

// Returns the recorded audio as a self-describing WAV (header + PCM).
// Valid until the next Mic_Start(). Returns false if nothing was recorded.
bool Mic_GetWav(const uint8_t **data, size_t *len);
