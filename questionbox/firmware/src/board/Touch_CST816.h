#pragma once
#include <Arduino.h>
#include <Wire.h>
#include "TCA9554PWR.h"

#define CST816_ADDR           0x15
#define CST816_INT_PIN        4
#define CST816_RST_PIN        -1                      // EXIO1
#define I2C_MASTER_FREQ_HZ    400000                     /*!< I2C master clock frequency */


#define CST816_LCD_TOUCH_MAX_POINTS             (1)    
/* CST816 GESTURE */
enum GESTURE {
  NONE = 0x00,
  SWIPE_UP = 0x01,
  SWIPE_DOWN = 0x02,
  SWIPE_LEFT = 0x03,
  SWIPE_RIGHT = 0x04,
  SINGLE_CLICK = 0x05,
  DOUBLE_CLICK = 0x0B,
  LONG_PRESS = 0x0C

};
//debug info
/****************HYN_REG_MUT_DEBUG_INFO_MODE address start***********/
#define CST816_REG_GestureID      0x01
#define CST816_REG_Version        0x15
#define CST816_REG_ChipID         0xA7
#define CST816_REG_ProjID         0xA8
#define CST816_REG_FwVersion      0xA9
#define CST816_REG_AutoSleepTime  0xF9
#define CST816_REG_DisAutoSleep   0xFE


extern struct CST816_Touch touch_data;

struct CST816_Touch{
  uint8_t points;     // Number of touch points
  GESTURE gesture;    /*!< uint8_t */
  uint16_t x;         /*!< X coordinate */
  uint16_t y;         /*!< Y coordinate */
};

uint8_t Touch_Init();
void Touch_Loop(void);
uint8_t CST816_Touch_Reset(void);
void CST816_AutoSleep(bool Sleep_State);
uint16_t CST816_Read_cfg(void);
String Touch_GestureName(void);
uint8_t Touch_Read_Data(void);
void example_touchpad_read(void);
void IRAM_ATTR Touch_CST816_ISR(void);
