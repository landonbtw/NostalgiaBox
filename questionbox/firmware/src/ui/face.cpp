/*****************************************************************************
 * The WonderBox face.
 *
 * A friendly, warm, slightly playful face designed for the 360x360 round LCD.
 * Everything is drawn with plain LVGL objects (no image assets) and animated
 * procedurally from Face_Tick(), driven by lv_tick_get(). One look per state:
 *
 *   IDLE      gentle blinking, soft smile  -> ready and calm
 *   LISTENING wide eyes + a pulsing ring   -> "I'm listening"
 *   THINKING  eyes look up, bouncing dots  -> charming wait, not a spinner
 *   SPEAKING  mouth opens and closes       -> talking
 *   SPELLING  one big letter at a time      -> spelling a word out loud
 *****************************************************************************/
#include "face.h"
#include <Arduino.h>
#include <math.h>
#include <string.h>
#include <ctype.h>

// ---- Warm, friendly palette ------------------------------------------------
#define COL_BG      0xFFF3E0  // warm cream background
#define COL_INK     0x3A3F58  // soft dark navy for eyes / mouth
#define COL_CHEEK   0xFFB4A2  // soft coral cheeks
#define COL_ACCENT  0xFF7A59  // coral: listening ring / active bits
#define COL_DOT     0x6FA8FF  // friendly blue thinking dots
#define COL_LETTER  0x2E7DE1  // clear blue spelling letters

// ---- Base geometry (screen is 360x360, center 180,180) ---------------------
static const int EYE_D     = 66;   // eye diameter when fully open
static const int EYE_DX    = 62;   // horizontal distance of each eye from center
static const int EYE_DY    = -30;  // eyes sit above center
static const int MOUTH_DY  = 60;   // mouth sits below center

// ---- Objects ---------------------------------------------------------------
static lv_obj_t *eye_l, *eye_r;
static lv_obj_t *cheek_l, *cheek_r;
static lv_obj_t *mouth;
static lv_obj_t *ring;
static lv_obj_t *dots[3];
static lv_obj_t *letter_lbl;
static lv_obj_t *word_lbl;

// ---- Animation state -------------------------------------------------------
static WbState current = WB_IDLE;
static uint32_t blink_next_ms = 0;   // when the next blink starts
static uint32_t blink_start_ms = 0;  // when the current blink started (0 = not blinking)
static const uint32_t BLINK_MS = 150;

static char spell_word[32] = {0};
static int  spell_len = 0;
static int  spell_index = 0;
static uint32_t spell_last_ms = 0;
static const uint32_t SPELL_STEP_MS = 800;

// ---------------------------------------------------------------------------
static lv_obj_t *make_blob(lv_obj_t *parent, uint32_t color, lv_opa_t opa)
{
  lv_obj_t *o = lv_obj_create(parent);
  lv_obj_remove_style_all(o);
  lv_obj_clear_flag(o, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_style_radius(o, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_bg_color(o, lv_color_hex(color), 0);
  lv_obj_set_style_bg_opa(o, opa, 0);
  return o;
}

static inline void show(lv_obj_t *o, bool visible)
{
  if (visible) lv_obj_clear_flag(o, LV_OBJ_FLAG_HIDDEN);
  else         lv_obj_add_flag(o, LV_OBJ_FLAG_HIDDEN);
}

static void schedule_blink(uint32_t now)
{
  blink_next_ms = now + 2400 + (esp_random() % 2600);  // 2.4s - 5.0s
}

// ---------------------------------------------------------------------------
void Face_Create(void)
{
  lv_obj_t *scr = lv_scr_act();
  lv_obj_clear_flag(scr, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_style_bg_color(scr, lv_color_hex(COL_BG), 0);
  lv_obj_set_style_bg_opa(scr, LV_OPA_COVER, 0);

  // Listening ring (drawn first so it sits behind the face).
  ring = lv_obj_create(scr);
  lv_obj_remove_style_all(ring);
  lv_obj_clear_flag(ring, LV_OBJ_FLAG_SCROLLABLE);
  lv_obj_set_size(ring, 320, 320);
  lv_obj_center(ring);
  lv_obj_set_style_radius(ring, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_bg_opa(ring, LV_OPA_TRANSP, 0);
  lv_obj_set_style_border_color(ring, lv_color_hex(COL_ACCENT), 0);
  lv_obj_set_style_border_width(ring, 10, 0);
  lv_obj_set_style_border_opa(ring, LV_OPA_60, 0);

  cheek_l = make_blob(scr, COL_CHEEK, LV_OPA_50);
  cheek_r = make_blob(scr, COL_CHEEK, LV_OPA_50);
  lv_obj_set_size(cheek_l, 34, 34);
  lv_obj_set_size(cheek_r, 34, 34);
  lv_obj_align(cheek_l, LV_ALIGN_CENTER, -96, 18);
  lv_obj_align(cheek_r, LV_ALIGN_CENTER,  96, 18);

  eye_l = make_blob(scr, COL_INK, LV_OPA_COVER);
  eye_r = make_blob(scr, COL_INK, LV_OPA_COVER);
  lv_obj_set_size(eye_l, EYE_D, EYE_D);
  lv_obj_set_size(eye_r, EYE_D, EYE_D);
  lv_obj_align(eye_l, LV_ALIGN_CENTER, -EYE_DX, EYE_DY);
  lv_obj_align(eye_r, LV_ALIGN_CENTER,  EYE_DX, EYE_DY);

  mouth = make_blob(scr, COL_INK, LV_OPA_COVER);
  lv_obj_set_size(mouth, 96, 30);
  lv_obj_align(mouth, LV_ALIGN_CENTER, 0, MOUTH_DY);

  for (int i = 0; i < 3; i++) {
    dots[i] = make_blob(scr, COL_DOT, LV_OPA_COVER);
    lv_obj_set_size(dots[i], 22, 22);
    lv_obj_align(dots[i], LV_ALIGN_CENTER, (i - 1) * 34, 40);
  }

  // Big spelling letter + soft full-word caption.
  letter_lbl = lv_label_create(scr);
  lv_obj_set_style_text_color(letter_lbl, lv_color_hex(COL_LETTER), 0);
  lv_obj_set_style_text_font(letter_lbl, &lv_font_montserrat_48, 0);
  lv_label_set_text(letter_lbl, "");
  lv_obj_align(letter_lbl, LV_ALIGN_CENTER, 0, -18);

  word_lbl = lv_label_create(scr);
  lv_obj_set_style_text_color(word_lbl, lv_color_hex(COL_INK), 0);
  lv_obj_set_style_text_font(word_lbl, &lv_font_montserrat_28, 0);
  lv_label_set_text(word_lbl, "");
  lv_obj_align(word_lbl, LV_ALIGN_CENTER, 0, 70);

  schedule_blink(lv_tick_get());
  Face_SetState(WB_IDLE);
}

// ---------------------------------------------------------------------------
WbState Face_GetState(void) { return current; }

void Face_SetState(WbState state)
{
  current = state;
  Serial.printf("[face] state -> %s\n", wb_state_name(state));

  const bool is_face  = (state != WB_SPELLING);
  const bool is_think = (state == WB_THINKING);
  const bool is_spell = (state == WB_SPELLING);

  show(eye_l,  is_face);
  show(eye_r,  is_face);
  show(cheek_l, is_face);
  show(cheek_r, is_face);
  show(mouth,  is_face && !is_think);        // dots replace the mouth while thinking
  show(ring,   state == WB_LISTENING);
  for (int i = 0; i < 3; i++) show(dots[i], is_think);
  show(letter_lbl, is_spell);
  show(word_lbl,   is_spell);

  // Reset per-state timing so animations start cleanly.
  uint32_t now = lv_tick_get();
  blink_start_ms = 0;
  schedule_blink(now);
  spell_last_ms = now;
}

void Face_ShowSpelling(const char *word)
{
  strncpy(spell_word, word ? word : "", sizeof(spell_word) - 1);
  spell_word[sizeof(spell_word) - 1] = '\0';
  spell_len = strlen(spell_word);
  spell_index = 0;
  lv_label_set_text(word_lbl, spell_word);
  Face_SetState(WB_SPELLING);
  if (spell_len > 0) {
    char c[2] = { (char)toupper((unsigned char)spell_word[0]), '\0' };
    lv_label_set_text(letter_lbl, c);
  } else {
    lv_label_set_text(letter_lbl, "");
  }
  spell_last_ms = lv_tick_get();
}

// ---- helpers used by Face_Tick --------------------------------------------
static void set_eye_open(float open)  // open: 0 (closed) .. 1 (wide)
{
  int h = (int)(6 + (EYE_D - 6) * open);
  if (h < 6) h = 6;
  lv_obj_set_height(eye_l, h);
  lv_obj_set_height(eye_r, h);
}

static void set_eye_look(int dy)  // vertical gaze offset
{
  lv_obj_align(eye_l, LV_ALIGN_CENTER, -EYE_DX, EYE_DY + dy);
  lv_obj_align(eye_r, LV_ALIGN_CENTER,  EYE_DX, EYE_DY + dy);
}

// Returns eye "open" factor accounting for the occasional blink.
static float blink_factor(uint32_t now)
{
  if (blink_start_ms == 0 && now >= blink_next_ms) blink_start_ms = now;
  if (blink_start_ms != 0) {
    uint32_t t = now - blink_start_ms;
    if (t >= BLINK_MS) {           // blink finished
      blink_start_ms = 0;
      schedule_blink(now);
      return 1.0f;
    }
    float p = (float)t / BLINK_MS; // 0..1 across the blink
    float closed = 1.0f - fabsf(1.0f - 2.0f * p);  // 0->1->0 triangle
    return 1.0f - closed;          // open->closed->open
  }
  return 1.0f;
}

// ---------------------------------------------------------------------------
void Face_Tick(void)
{
  uint32_t now = lv_tick_get();
  float t = now / 1000.0f;

  switch (current) {
    case WB_IDLE: {
      set_eye_look(0);
      set_eye_open(blink_factor(now));
      lv_obj_set_size(mouth, 96, 30);      // wide gentle smile
      break;
    }
    case WB_LISTENING: {
      set_eye_look(0);
      set_eye_open(fminf(1.0f, blink_factor(now) * 1.12f));  // eyes a touch wider
      lv_obj_set_size(mouth, 40, 30);       // small attentive mouth
      // Pulse the ring: breathe its size and opacity.
      float pulse = 0.5f + 0.5f * sinf(t * 3.2f);
      int d = 300 + (int)(28 * pulse);
      lv_obj_set_size(ring, d, d);
      lv_obj_center(ring);
      lv_obj_set_style_border_opa(ring, (lv_opa_t)(120 + 100 * pulse), 0);
      break;
    }
    case WB_THINKING: {
      set_eye_look(-10);                     // glance upward, pondering
      set_eye_open(blink_factor(now));
      // Three dots bounce in a wave.
      for (int i = 0; i < 3; i++) {
        float ph = t * 4.0f - i * 0.6f;
        float bob = sinf(ph);
        int dy = 40 - (int)(10 * fmaxf(0.0f, bob));
        lv_obj_align(dots[i], LV_ALIGN_CENTER, (i - 1) * 34, dy);
        lv_obj_set_style_bg_opa(dots[i], (lv_opa_t)(120 + 120 * (0.5f + 0.5f * bob)), 0);
      }
      break;
    }
    case WB_SPEAKING: {
      set_eye_look(0);
      set_eye_open(blink_factor(now));
      // Mouth opens and closes as if talking.
      float m = 0.5f + 0.5f * sinf(t * 11.0f);
      int h = 16 + (int)(40 * m);
      lv_obj_set_size(mouth, 72, h);
      lv_obj_align(mouth, LV_ALIGN_CENTER, 0, MOUTH_DY);
      break;
    }
    case WB_SPELLING: {
      if (spell_len > 0 && now - spell_last_ms >= SPELL_STEP_MS) {
        spell_last_ms = now;
        spell_index = (spell_index + 1) % spell_len;
        char c[2] = { (char)toupper((unsigned char)spell_word[spell_index]), '\0' };
        lv_label_set_text(letter_lbl, c);
      }
      break;
    }
  }
}
