// Prueba de lectura de batería: divisor 2 x 220 kΩ entre OUT+ y GND, punto medio a D1.
void setup() {
  Serial.begin(115200);
}

void loop() {
  uint32_t mv = 0;
  for (int i = 0; i < 16; i++) mv += analogReadMilliVolts(D1);
  float pin = mv / 16.0 / 1000.0;            // voltaje en el pin D1
  float vbat = pin * 2.0;                    // el divisor entrega la mitad
  int pct = constrain((int)((vbat - 3.3) / (4.2 - 3.3) * 100), 0, 100);
  Serial.printf("D1: %.2f V | bateria: %.2f V (%d %%)\n", pin, vbat, pct);
  delay(1000);
}
