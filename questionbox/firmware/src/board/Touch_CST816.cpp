#include "Touch_CST816.h"

struct CST816_Touch touch_data = {0};
uint8_t Touch_interrupts=0;

////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
// I2C
////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////////
bool I2C_Read_Touch(uint16_t Driver_addr, uint8_t Reg_addr, uint8_t *Reg_data, uint32_t Length)
{
  Wire.beginTransmission(Driver_addr);
  Wire.write(Reg_addr); 
  if ( Wire.endTransmission(true)){
    printf("The I2C transmission fails. - I2C Read\r\n");
    return true;
  }
  Wire.requestFrom(Driver_addr, Length);
  for (int i = 0; i < Length; i++) {
    *Reg_data++ = Wire.read();
  }
  return true;
}
bool I2C_Write_Touch(uint8_t Driver_addr, uint8_t Reg_addr, const uint8_t *Reg_data, uint32_t Length)
{
  Wire.beginTransmission(Driver_addr);
  Wire.write(Reg_addr);       
  for (int i = 0; i < Length; i++) {
    Wire.write(*Reg_data++);
  }
  if ( Wire.endTransmission(true))
  {
    printf("The I2C transmission fails. - I2C Write\r\n");
    return false;
  }
  return true;
}
/*!
    @brief  handle interrupts
*/
void ARDUINO_ISR_ATTR Touch_CST816_ISR(void) {
  Touch_interrupts = true;
}

uint8_t Touch_Init(void) {
  CST816_Touch_Reset();
  uint16_t Verification = CST816_Read_cfg();
  CST816_AutoSleep(true);
   
  pinMode(CST816_INT_PIN, INPUT_PULLUP);
  attachInterrupt(CST816_INT_PIN, Touch_CST816_ISR, FALLING); 

  return true;
}
/* Reset controller */
uint8_t CST816_Touch_Reset(void)
{
  Set_EXIO(EXIO_PIN1,Low);
  vTaskDelay(pdMS_TO_TICKS(10));
  Set_EXIO(EXIO_PIN1,High);
  vTaskDelay(pdMS_TO_TICKS(50));
  return true;
}
uint16_t CST816_Read_cfg(void) {

  uint8_t buf[3];
  I2C_Read_Touch(CST816_ADDR, CST816_REG_Version,buf, 1);
  printf("TouchPad_Version:0x%02x\r\n", buf[0]);
  I2C_Read_Touch(CST816_ADDR, CST816_REG_ChipID, buf, 3);
  printf("ChipID:0x%02x   ProjID:0x%02x   FwVersion:0x%02x \r\n",buf[0], buf[1], buf[2]);

  return true;
}
/*!
    @brief  Fall asleep automatically
*/
void CST816_AutoSleep(bool Sleep_State) {
  CST816_Touch_Reset();
  uint8_t Sleep_State_Set = (uint8_t)(!Sleep_State);
  Sleep_State_Set = 10;
  I2C_Write_Touch(CST816_ADDR, CST816_REG_DisAutoSleep, &Sleep_State_Set, 1);
}

// reads sensor and touches
// updates Touch Points
uint8_t Touch_Read_Data(void) {
  uint8_t buf[6];
  uint8_t touchpad_cnt = 0;
  I2C_Read_Touch(CST816_ADDR, CST816_REG_GestureID, buf, 6);
  /* touched gesture */
  if (buf[0] != 0x00) 
    touch_data.gesture = (GESTURE)buf[0];
  if (buf[1] != 0x00) {        
    noInterrupts(); 
    /* Number of touched points */
    touch_data.points = (uint8_t)buf[1];
    if(touch_data.points > CST816_LCD_TOUCH_MAX_POINTS)
        touch_data.points = CST816_LCD_TOUCH_MAX_POINTS;
    /* Fill coordinates */
    touch_data.x = ((buf[2] & 0x0F) << 8) + buf[3];               
    touch_data.y = ((buf[4] & 0x0F) << 8) + buf[5];
      
    interrupts(); 
    // printf(" points=%d \r\n",touch_data.points);
  }
  return true;
}
void example_touchpad_read(void){
  Touch_Read_Data();
  if (touch_data.gesture != NONE ||  touch_data.points != 0x00) {
      printf("Touch : X=%u Y=%u points=%d\r\n",  touch_data.x , touch_data.y,touch_data.points);
  } else {
      // data->state = LV_INDEV_STATE_REL;
  }
}
void Touch_Loop(void){
  if(Touch_interrupts){
    Touch_interrupts = false;
    example_touchpad_read();
  }
}


/*!
    @brief  get the gesture event name
*/
String Touch_GestureName(void) {
  switch (touch_data.gesture) {
    case NONE:
      return "NONE";
      break;
    case SWIPE_DOWN:
      return "SWIPE DOWN";
      break;
    case SWIPE_UP:
      return "SWIPE UP";
      break;
    case SWIPE_LEFT:
      return "SWIPE LEFT";
      break;
    case SWIPE_RIGHT:
      return "SWIPE RIGHT";
      break;
    case SINGLE_CLICK:
      return "SINGLE CLICK";
      break;
    case DOUBLE_CLICK:
      return "DOUBLE CLICK";
      break;
    case LONG_PRESS:
      return "LONG PRESS";
      break;
    default:
      return "UNKNOWN";
      break;
  }
}