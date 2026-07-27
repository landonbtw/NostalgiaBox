#include "wifi_conn.h"
#include "device_config.h"
#include <Arduino.h>
#include <WiFi.h>

bool WiFiConn_IsConnected()
{
  return WiFi.status() == WL_CONNECTED;
}

bool WiFiConn_Connect(uint32_t timeout_ms)
{
  if (sizeof(WIFI_SSID) <= 1) {
    Serial.println("[wifi] WIFI_SSID is empty - create include/secrets.h from the example");
    return false;
  }
  if (WiFiConn_IsConnected()) return true;

  Serial.printf("[wifi] connecting to \"%s\" ...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && (millis() - start) < timeout_ms) {
    delay(250);
  }

  if (WiFiConn_IsConnected()) {
    Serial.printf("[wifi] connected, IP = %s\n", WiFi.localIP().toString().c_str());
    return true;
  }
  Serial.println("[wifi] connection FAILED");
  return false;
}
