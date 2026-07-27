#pragma once
#include <Arduino.h>

struct AnswerInfo {
  String text;
  String mode;          // "answered" | "deferred" | "refused"
  bool   isSpelling = false;
  String spellWord;
};

// POSTs the recorded WAV to <SERVER_BASE_URL>/api/ask with the device token.
// On HTTP 200, fills `out` from the response headers and LEAVES THE CONNECTION
// OPEN so the audio body can be streamed via WonderClient_GetStream().
// Returns the HTTP status code (or a negative value on transport error).
int WonderClient_Ask(const uint8_t *wav, size_t len, AnswerInfo &out);

// The response body stream (audio), valid until WonderClient_End().
Stream *WonderClient_GetStream();

// Content-Length of the audio body, or -1 if unknown.
int WonderClient_GetLength();

// Closes the connection and frees resources. Always call after a request.
void WonderClient_End();
