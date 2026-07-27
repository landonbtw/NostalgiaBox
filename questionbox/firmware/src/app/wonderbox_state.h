#pragma once

// The WonderBox face has five clear states, matching the product spec.
// The face UI renders one look per state; the app logic drives the transitions.
enum WbState {
  WB_IDLE = 0,   // gentle blinking, ready and calm
  WB_LISTENING,  // mic tapped, actively recording the child's question
  WB_THINKING,   // waiting on the server; charming, not a spinner
  WB_SPEAKING,   // talking animation while the answer audio plays
  WB_SPELLING,   // shows a word big, letter by letter
};

// Human-readable name, handy for serial logging.
inline const char *wb_state_name(WbState s)
{
  switch (s) {
    case WB_IDLE:      return "IDLE";
    case WB_LISTENING: return "LISTENING";
    case WB_THINKING:  return "THINKING";
    case WB_SPEAKING:  return "SPEAKING";
    case WB_SPELLING:  return "SPELLING";
    default:           return "UNKNOWN";
  }
}
