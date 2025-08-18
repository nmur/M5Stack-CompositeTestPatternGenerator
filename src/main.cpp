#include <Arduino.h>
#include "M5GFX.h"
#include "M5Unified.h"

// put function declarations here:
int myFunction(int, int);

void setup() {
  M5.begin();
  M5.Lcd.fillScreen(BLACK);
  M5.Lcd.setTextColor(WHITE);
  M5.Lcd.setTextSize(2);
  M5.Lcd.setCursor(20, 100);
  M5.Lcd.print("Hello, PlatformIO!");
}

void loop() {

}
