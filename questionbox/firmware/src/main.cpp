/*****************************************************************************
 * WonderBox firmware - Stage 4: real pipeline (animated THINKING).
 *
 * Same loop as Stage 3, but the server now runs the real speech-to-text ->
 * safety -> LLM -> text-to-speech pipeline, which takes a few seconds. So the
 * HTTPS request runs on a background task (core 0) while the main loop (core 1)
 * keeps LVGL + the face animation alive - the THINKING dots bounce during the
 * wait, and the SPEAKING mouth moves during playback.
 *
 * PUSH-TO-TALK ONLY. Audio is recorded, sent, and discarded - never stored.
 *****************************************************************************/
#include <Arduino.h>

#include "I2C_Driver.h"
#include "TCA9554PWR.h"
#include "Display_ST77916.h"
#include "LVGL_Driver.h"

#include "wonderbox_state.h"
#include "face.h"
#include "mic_button.h"

#include "wifi_conn.h"
#include "wonder_client.h"
#include "mic.h"
#include "speaker.h"

// ---- Background request handoff ----
enum ReqStatus { REQ_IDLE, REQ_RUNNING, REQ_DONE, REQ_FAILED };
static volatile ReqStatus g_req = REQ_IDLE;
static AnswerInfo   g_ans;
static const uint8_t *g_wav = nullptr;
static size_t        g_wav_len = 0;

// Keep the UI (display + face animation) alive during blocking playback.
static void pump_ui()
{
  Lvgl_Loop();
  Face_Tick();
}

static void go_idle()
{
  MicButton_SetActive(false);
  Face_SetState(WB_IDLE);
}

// Runs on core 0: does the (blocking) HTTPS request, then signals the result.
static void ask_task(void *)
{
  AnswerInfo ans;
  int code = WonderClient_Ask(g_wav, g_wav_len, ans);
  g_ans = ans;
  g_req = (code == 200) ? REQ_DONE : REQ_FAILED;
  vTaskDelete(nullptr);
}

// Recording finished: fire off the request (non-blocking) and show THINKING.
static void stop_and_send()
{
  MicButton_SetActive(false);
  Mic_Stop();

  if (!Mic_GetWav(&g_wav, &g_wav_len)) {
    Serial.println("[app] nothing recorded");
    go_idle();
    return;
  }

  Face_SetState(WB_THINKING);
  g_req = REQ_RUNNING;
  xTaskCreatePinnedToCore(ask_task, "ask", 16384, nullptr, 4, nullptr, 0);
}

// Called on the main loop once the background request finishes successfully.
static void play_answer()
{
  if (g_ans.isSpelling && g_ans.spellWord.length() > 0) {
    Face_ShowSpelling(g_ans.spellWord.c_str());
  } else {
    Face_SetState(WB_SPEAKING);
  }
  Stream *body = WonderClient_GetStream();
  if (body) Speaker_PlayWavStream(*body, WonderClient_GetLength(), pump_ui);
  WonderClient_End();
  go_idle();
}

// Called on each tap of the on-screen mic button.
static void on_mic_tap()
{
  switch (Face_GetState()) {
    case WB_IDLE:
      if (!WiFiConn_IsConnected()) {
        Serial.println("[app] no Wi-Fi - trying to reconnect");
        WiFiConn_Connect(8000);
      }
      Mic_Start();
      MicButton_SetActive(true);
      Face_SetState(WB_LISTENING);
      break;
    case WB_LISTENING:
      stop_and_send();
      break;
    default:
      // THINKING (request in flight) or during playback: ignore taps.
      break;
  }
}

static void Board_Init()
{
  I2C_Init();
  TCA9554PWR_Init(0x00);
  Backlight_Init();
  LCD_Init();
  Set_Backlight(80);
}

void setup()
{
  Serial.begin(115200);
  delay(200);
  Serial.println("\n=== WonderBox firmware (Stage 4: real pipeline) ===");

  Board_Init();
  Lvgl_Init();

  Face_Create();
  MicButton_Create(lv_scr_act(), on_mic_tap);
  Face_SetState(WB_IDLE);

  Mic_Begin();
  Speaker_Begin();

  WiFiConn_Connect();

  Serial.println("=== setup complete ===");
}

void loop()
{
  Lvgl_Loop();
  Face_Tick();

  // While listening, keep capturing and auto-stop on silence.
  if (Face_GetState() == WB_LISTENING) {
    if (!Mic_Poll()) stop_and_send();
  }

  // Handle the background request result (THINKING kept animating meanwhile).
  if (g_req == REQ_DONE) {
    g_req = REQ_IDLE;
    play_answer();
  } else if (g_req == REQ_FAILED) {
    g_req = REQ_IDLE;
    Serial.println("[app] request failed");
    WonderClient_End();
    go_idle();
  }

  delay(5);
}
