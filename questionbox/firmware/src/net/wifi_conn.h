#pragma once
#include <stdint.h>

// Connects to the Wi-Fi configured in secrets.h. Blocks up to timeout_ms.
// Returns true if connected. The ESP32-S3 is 2.4GHz only.
bool WiFiConn_Connect(uint32_t timeout_ms = 20000);

bool WiFiConn_IsConnected();
