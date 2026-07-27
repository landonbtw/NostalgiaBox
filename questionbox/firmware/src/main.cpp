/*****************************************************************************
 * WonderBox firmware - Stage 3: the real device <-> server loop.
 *
 * Tap the mic to record a question; tap again (or stop on silence) to send it.
 * The device POSTs the audio to the WonderBox server (/api/ask), gets back
 * spoken audio + answer text, and plays it while showing the SPEAKING (or
 * SPELLING) face. In Stage 3 the server returns a hardcoded test answer; the
 * real STT -> safety -> LLM -> TTS pipeline arrives in Stage 4.
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

// Recording finished: send it to the server and play the answer.
static void stop_and_send()
{
  MicButton_SetActive(false);
  Mic_Stop();
  Face_SetState(WB_THINKING);
  pump_ui();  // paint the thinking face before the (brief) blocking request

  const uint8_t *wav = nullptr;
  size_t len = 0;
  if (!Mic_GetWav(&wav, &len)) {
    Serial.println("[app] nothing recorded");
    go_idle();
    return;
  }

  AnswerInfo ans;
  int code = WonderClient_Ask(wav, len, ans);
  if (code == 200) {
    if (ans.isSpelling && ans.spellWord.length() > 0) {
      Face_ShowSpelling(ans.spellWord.c_str());
    } else {
      Face_SetState(WB_SPEAKING);
    }
    Stream *body = WonderClient_GetStream();
    if (body) Speaker_PlayWavStream(*body, WonderClient_GetLength(), pump_ui);
  } else {
    Serial.printf("[app] request failed (%d)\n", code);
  }
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
      // Mid-answer tap: calmly return to the ready face.
      go_idle();
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
  Serial.println("\n=== WonderBox firmware (Stage 3: device<->server loop) ===");

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

  delay(5);
}
