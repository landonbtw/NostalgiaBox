/*****************************************************************************
 * LVGL glue for the WonderBox.
 *
 * Ported from the Waveshare ESP32-S3-Touch-LCD-1.85C "LVGL_Arduino" demo
 * (display flush + touch read), with two changes:
 *   - partial rendering (full_refresh = 0) so the small double buffer is valid
 *   - no demo "Hello" label; the UI is built by the WonderBox face code
 *****************************************************************************/
#include "LVGL_Driver.h"

static lv_disp_draw_buf_t draw_buf;
static lv_color_t buf1[LVGL_BUF_LEN];
static lv_color_t buf2[LVGL_BUF_LEN];

// Push a rendered LVGL area to the ST77916 panel.
static void Lvgl_Display_LCD(lv_disp_drv_t *disp_drv, const lv_area_t *area, lv_color_t *color_p)
{
  LCD_addWindow(area->x1, area->y1, area->x2, area->y2, (uint16_t *)&color_p->full);
  lv_disp_flush_ready(disp_drv);
}

// Feed CST816 touch coordinates into LVGL's pointer input device.
static void Lvgl_Touchpad_Read(lv_indev_drv_t *indev_drv, lv_indev_data_t *data)
{
  Touch_Read_Data();
  if (touch_data.points != 0x00) {
    data->point.x = touch_data.x;
    data->point.y = touch_data.y;
    data->state = LV_INDEV_STATE_PR;
  } else {
    data->state = LV_INDEV_STATE_REL;
  }
  touch_data.x = 0;
  touch_data.y = 0;
  touch_data.points = 0;
  touch_data.gesture = NONE;
}

static void example_increase_lvgl_tick(void *arg)
{
  lv_tick_inc(EXAMPLE_LVGL_TICK_PERIOD_MS);
}

void Lvgl_Init(void)
{
  lv_init();
  lv_disp_draw_buf_init(&draw_buf, buf1, buf2, LVGL_BUF_LEN);

  static lv_disp_drv_t disp_drv;
  lv_disp_drv_init(&disp_drv);
  disp_drv.hor_res = LCD_WIDTH;
  disp_drv.ver_res = LCD_HEIGHT;
  disp_drv.flush_cb = Lvgl_Display_LCD;
  disp_drv.full_refresh = 0;
  disp_drv.draw_buf = &draw_buf;
  lv_disp_drv_register(&disp_drv);

  static lv_indev_drv_t indev_drv;
  lv_indev_drv_init(&indev_drv);
  indev_drv.type = LV_INDEV_TYPE_POINTER;
  indev_drv.read_cb = Lvgl_Touchpad_Read;
  lv_indev_drv_register(&indev_drv);

  // Drive lv_tick_inc() from a hardware timer so timing is accurate even if the
  // main loop is briefly busy.
  const esp_timer_create_args_t lvgl_tick_timer_args = {
    .callback = &example_increase_lvgl_tick,
    .name = "lvgl_tick"
  };
  esp_timer_handle_t lvgl_tick_timer = NULL;
  esp_timer_create(&lvgl_tick_timer_args, &lvgl_tick_timer);
  esp_timer_start_periodic(lvgl_tick_timer, EXAMPLE_LVGL_TICK_PERIOD_MS * 1000);
}

uint32_t Lvgl_Loop(void)
{
  return lv_timer_handler();
}
