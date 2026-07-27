/*****************************************************************************
 * WonderBox firmware - Stage 2: the face + the mic button.
 *
 * Brings up the Waveshare ESP32-S3-Touch-LCD-1.85C(-BOX) display and touch
 * (using the board drivers ported from the official demo), then renders the
 * WonderBox face and a tap-to-talk microphone button.
 *
 * There is no server, Wi-Fi, or audio yet (those arrive in Stage 3+). To let
 * you verify every face look on the real device, tapping the mic walks through
 * the states. This DEMO FLOW is replaced by the real record -> send -> play
 * loop in Stage 3.
 *
 *   Tap in IDLE       -> LISTENING (mic button turns coral)
 *   Tap in LISTENING  -> THINKING -> (auto) SPEAKING -> (auto) SPELLING "WONDER" -> IDLE
 *   Tap any other time-> back to IDLE (lets a child restart)
 *****************************************************************************/
#include <Arduino.h>

#include "I2C_Driver.h"
#include "TCA9554PWR.h"
#include "Display_ST77916.h"
#include "LVGL_Driver.h"

#include "wonderbox_state.h"
#include "face.h"
#include "mic_button.h"

// ---- Stage 2 demo scheduler ------------------------------------------------
static uint32_t transition_at = 0;      // millis() deadline for the next auto step (0 = none)
static WbState  transition_to = WB_IDLE;
static bool     transition_is_spell = false;

static void schedule(WbState to, uint32_t delay_ms)
{
  transition_to = to;
  transition_is_spell = false;
  transition_at = millis() + delay_ms;
}

static void schedule_spell(uint32_t delay_ms)
{
  transition_is_spell = true;
  transition_at = millis() + delay_ms;
}

static void go_idle()
{
  transition_at = 0;
  MicButton_SetActive(false);
  Face_SetState(WB_IDLE);
}

// Called by the mic button on each tap.
static void on_mic_tap()
{
  switch (Face_GetState()) {
    case WB_IDLE:
      MicButton_SetActive(true);
      Face_SetState(WB_LISTENING);
      break;
    case WB_LISTENING:
      // Simulate "send audio to server".
      MicButton_SetActive(false);
      Face_SetState(WB_THINKING);
      schedule(WB_SPEAKING, 1600);
      break;
    default:
      // Mid-sequence tap: calmly return to the ready face.
      go_idle();
      break;
  }
}

// Drives the queued auto-transitions of the Stage 2 demo flow.
static void demo_flow_loop()
{
  if (transition_at == 0 || (int32_t)(millis() - transition_at) < 0) return;
  transition_at = 0;

  if (transition_is_spell) {
    Face_ShowSpelling("WONDER");
    schedule(WB_IDLE, 6000);
    return;
  }

  switch (transition_to) {
    case WB_SPEAKING:
      Face_SetState(WB_SPEAKING);
      schedule_spell(2600);     // "speak" for a bit, then show a spelling demo
      break;
    case WB_IDLE:
    default:
      go_idle();
      break;
  }
}

static void Board_Init()
{
  I2C_Init();
  TCA9554PWR_Init(0x00);
  Backlight_Init();
  LCD_Init();          // ST77916 display + CST816 touch
  Set_Backlight(80);
}

void setup()
{
  Serial.begin(115200);
  delay(200);
  Serial.println("\n=== WonderBox firmware (Stage 2: face + mic button) ===");

  Board_Init();
  Lvgl_Init();

  Face_Create();
  MicButton_Create(lv_scr_act(), on_mic_tap);
  Face_SetState(WB_IDLE);

  Serial.println("=== setup complete ===");
}

void loop()
{
  Lvgl_Loop();
  Face_Tick();
  demo_flow_loop();
  delay(5);
}
