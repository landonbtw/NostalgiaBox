#pragma once

#include <lvgl.h>
#include "lv_conf.h"
#include <esp_heap_caps.h>
#include "Display_ST77916.h"
#include "Touch_CST816.h"

#define LCD_WIDTH     EXAMPLE_LCD_WIDTH
#define LCD_HEIGHT    EXAMPLE_LCD_HEIGHT

// Partial render buffer: 1/10 of the screen, double-buffered. Small enough for
// internal SRAM, big enough to keep the face animation smooth.
#define LVGL_BUF_LEN  (LCD_WIDTH * LCD_HEIGHT / 10)

#define EXAMPLE_LVGL_TICK_PERIOD_MS  10

// Brings up LVGL, the ST77916 display flush callback and the CST816 touch
// input. Call after LCD_Init().
void Lvgl_Init(void);

// Must be called frequently from the main loop so LVGL can render and process
// input. Returns the number of ms until it wants to be called again.
uint32_t Lvgl_Loop(void);
