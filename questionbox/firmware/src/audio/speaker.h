#pragma once
#include <Arduino.h>

// Plays answer audio out of the PCM5101 speaker over I2S.
//
// Answer audio is standardized as 16-bit PCM WAV, MONO, 24 kHz (what the server
// produces). The 44-byte WAV header is skipped; mono samples are duplicated to
// both stereo channels for the DAC.

bool Speaker_Begin();

// Streams a WAV response body to the speaker. `pump` is called repeatedly during
// playback so the UI (LVGL + face animation) keeps running. Audio is played
// transiently and never stored.
void Speaker_PlayWavStream(Stream &s, int contentLen, void (*pump)());
