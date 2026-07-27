#pragma once

#include <lvgl.h>

// Creates the round tap-to-talk microphone button near the bottom of the face.
// `on_tap` is called once per tap (LV_EVENT_CLICKED). PUSH-TO-TALK ONLY: the
// mic never listens unless the child taps this button.
void MicButton_Create(lv_obj_t *parent, void (*on_tap)(void));

// Highlights the button while actively recording (coral) vs. idle (muted).
void MicButton_SetActive(bool active);
