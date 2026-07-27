#pragma once

#include <lvgl.h>
#include "wonderbox_state.h"

// Builds the friendly WonderBox face on the active screen. Designed for the
// 360x360 round display. Call once after Lvgl_Init().
void Face_Create(void);

// Switches the face to a new look. Safe to call from the main loop / event
// callbacks. Re-applies immediately.
void Face_SetState(WbState state);

// Returns the state the face is currently showing.
WbState Face_GetState(void);

// Puts the face into WB_SPELLING and shows `word` one big letter at a time.
// The full word is shown softly at the bottom as a caption.
void Face_ShowSpelling(const char *word);

// Advances all procedural animations. Call frequently from the main loop
// (it is cheap and self-throttling via the LVGL tick).
void Face_Tick(void);
