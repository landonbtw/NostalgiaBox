#include "wonder_client.h"
#include "device_config.h"
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

// -----------------------------------------------------------------------------
// TLS trust
//
// SECURITY: by default we skip certificate validation (setInsecure) so the loop
// works out of the box. This means the connection is encrypted but NOT
// authenticated (a determined attacker on your network could impersonate the
// server). To harden, set WB_TLS_INSECURE to 0 and paste your server's root CA
// certificate into WB_ROOT_CA below, then re-flash. Tracked for a later
// security pass.
// -----------------------------------------------------------------------------
#ifndef WB_TLS_INSECURE
#define WB_TLS_INSECURE 1
#endif

#if !WB_TLS_INSECURE
static const char *WB_ROOT_CA = R"CERT(
-----BEGIN CERTIFICATE-----
... paste your server's root CA certificate here ...
-----END CERTIFICATE-----
)CERT";
#endif

static WiFiClientSecure s_tls;
static HTTPClient s_http;
static bool s_open = false;

// Decode %XX percent-encoding (from encodeURIComponent on the server).
static String urlDecode(const String &in)
{
  String out;
  out.reserve(in.length());
  for (size_t i = 0; i < in.length(); i++) {
    char c = in[i];
    if (c == '%' && i + 2 < in.length()) {
      auto hex = [](char h) -> int {
        if (h >= '0' && h <= '9') return h - '0';
        if (h >= 'a' && h <= 'f') return h - 'a' + 10;
        if (h >= 'A' && h <= 'F') return h - 'A' + 10;
        return 0;
      };
      out += (char)((hex(in[i + 1]) << 4) | hex(in[i + 2]));
      i += 2;
    } else {
      out += c;
    }
  }
  return out;
}

int WonderClient_Ask(const uint8_t *wav, size_t len, AnswerInfo &out)
{
  if (sizeof(SERVER_BASE_URL) <= 1 || sizeof(DEVICE_TOKEN) <= 1) {
    Serial.println("[net] SERVER_BASE_URL / DEVICE_TOKEN not set (see secrets.h)");
    return -1;
  }

#if WB_TLS_INSECURE
  s_tls.setInsecure();
#else
  s_tls.setCACert(WB_ROOT_CA);
#endif

  String url = String(SERVER_BASE_URL) + "/api/ask";
  if (!s_http.begin(s_tls, url)) {
    Serial.println("[net] http.begin failed");
    return -1;
  }
  s_open = true;

  s_http.setTimeout(15000);
  s_http.addHeader("Content-Type", "audio/wav");
  s_http.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);

  static const char *collect[] = {"X-Answer-Text", "X-Answer-Mode", "X-Is-Spelling", "X-Spell-Word"};
  s_http.collectHeaders(collect, 4);

  Serial.printf("[net] POST %s (%u bytes)\n", url.c_str(), (unsigned)len);
  int code = s_http.POST((uint8_t *)wav, len);
  Serial.printf("[net] status %d\n", code);

  if (code == 200) {
    out.text = urlDecode(s_http.header("X-Answer-Text"));
    out.mode = s_http.header("X-Answer-Mode");
    out.isSpelling = s_http.header("X-Is-Spelling") == "1";
    out.spellWord = urlDecode(s_http.header("X-Spell-Word"));
    Serial.printf("[net] answer (%s): %s\n", out.mode.c_str(), out.text.c_str());
  }
  return code;
}

Stream *WonderClient_GetStream()
{
  return s_open ? s_http.getStreamPtr() : nullptr;
}

int WonderClient_GetLength()
{
  return s_open ? s_http.getSize() : -1;
}

void WonderClient_End()
{
  if (s_open) {
    s_http.end();
    s_tls.stop();
    s_open = false;
  }
}
