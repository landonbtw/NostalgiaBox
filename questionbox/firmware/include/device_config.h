#pragma once
//
// Pulls in your private secrets.h if it exists, otherwise falls back to empty
// placeholders so the project still COMPILES without secrets committed.
//
// To configure a real device: copy include/secrets.h.example to
// include/secrets.h and fill in your values. secrets.h is gitignored.
//
#if defined(__has_include)
#  if __has_include("secrets.h")
#    include "secrets.h"
#  endif
#endif

#ifndef WIFI_SSID
#define WIFI_SSID ""
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif
#ifndef SERVER_BASE_URL
#define SERVER_BASE_URL ""
#endif
#ifndef DEVICE_TOKEN
#define DEVICE_TOKEN ""
#endif

// True only when the essential fields have been filled in.
static inline bool DeviceConfigValid()
{
  return sizeof(WIFI_SSID) > 1 && sizeof(SERVER_BASE_URL) > 1 && sizeof(DEVICE_TOKEN) > 1;
}
