#include "mic_button.h"
#include <Arduino.h>

#define COL_BTN_IDLE    0xCED6E0  // muted grey-blue when resting
#define COL_BTN_ACTIVE  0xFF7A59  // coral while recording
#define COL_BTN_ICON    0x3A3F58

static lv_obj_t *btn = nullptr;
static lv_obj_t *icon = nullptr;
static void (*tap_cb)(void) = nullptr;

static void mic_event_cb(lv_event_t *e)
{
  if (lv_event_get_code(e) == LV_EVENT_CLICKED && tap_cb) {
    Serial.println("[mic] tapped");
    tap_cb();
  }
}

void MicButton_Create(lv_obj_t *parent, void (*on_tap)(void))
{
  tap_cb = on_tap;

  btn = lv_btn_create(parent);
  lv_obj_set_size(btn, 88, 88);
  lv_obj_align(btn, LV_ALIGN_BOTTOM_MID, 0, -26);
  lv_obj_set_style_radius(btn, LV_RADIUS_CIRCLE, 0);
  lv_obj_set_style_bg_color(btn, lv_color_hex(COL_BTN_IDLE), 0);
  lv_obj_set_style_shadow_width(btn, 12, 0);
  lv_obj_set_style_shadow_opa(btn, LV_OPA_20, 0);
  lv_obj_add_event_cb(btn, mic_event_cb, LV_EVENT_CLICKED, nullptr);

  icon = lv_label_create(btn);
  lv_label_set_text(icon, LV_SYMBOL_AUDIO);
  lv_obj_set_style_text_color(icon, lv_color_hex(COL_BTN_ICON), 0);
  lv_obj_set_style_text_font(icon, &lv_font_montserrat_28, 0);
  lv_obj_center(icon);
}

void MicButton_SetActive(bool active)
{
  if (!btn) return;
  lv_obj_set_style_bg_color(btn, lv_color_hex(active ? COL_BTN_ACTIVE : COL_BTN_IDLE), 0);
  lv_obj_set_style_text_color(icon, lv_color_hex(active ? 0xFFFFFF : COL_BTN_ICON), 0);
}
