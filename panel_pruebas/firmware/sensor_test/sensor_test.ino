// Prueba del sensor de temperatura y humedad por I2C (SDA = D4, SCL = D8).
// Detecta solo cuál está conectado: AHT10/AHT20 (0x38) o HTU21D/GY-21 (0x40).
// Cada ciclo también lista los dispositivos I2C encontrados (el MPU6050 aparece en 0x68).
#include <Wire.h>
// SCL movido de D5 a D8: el pin D5 de esta placa quedó en corto con GND (no usarlo).
const int SCL_PIN = D8;

const uint8_t AHT = 0x38, HTU = 0x40;
bool ahtListo = false;

bool existe(uint8_t a) {
  Wire.beginTransmission(a);
  return Wire.endTransmission() == 0;
}

void escanear() {
  Serial.print("I2C:");
  int n = 0;
  for (uint8_t a = 1; a < 127; a++) if (existe(a)) { Serial.printf(" 0x%02X", a); n++; }
  if (!n) Serial.print(" nada (revisa SDA/SCL, 3V3 y GND)");
  Serial.println();
}

bool leerAHT(float &t, float &h) {
  if (!ahtListo) {                       // inicialización (AHT10: 0xE1; AHT20 ignora y sigue)
    Wire.beginTransmission(AHT); Wire.write(0xE1); Wire.write(0x08); Wire.write(0x00); Wire.endTransmission();
    delay(20); ahtListo = true;
  }
  Wire.beginTransmission(AHT); Wire.write(0xAC); Wire.write(0x33); Wire.write(0x00);
  if (Wire.endTransmission() != 0) return false;
  delay(90);
  if (Wire.requestFrom(AHT, (uint8_t)6) != 6) return false;
  uint8_t b[6]; for (int i = 0; i < 6; i++) b[i] = Wire.read();
  if (b[0] & 0x80) return false;         // sigue ocupado
  uint32_t rh = ((uint32_t)b[1] << 12) | ((uint32_t)b[2] << 4) | (b[3] >> 4);
  uint32_t rt = ((uint32_t)(b[3] & 0x0F) << 16) | ((uint32_t)b[4] << 8) | b[5];
  h = rh * 100.0 / 1048576.0;
  t = rt * 200.0 / 1048576.0 - 50.0;
  return true;
}

bool leerHTU(uint8_t cmd, uint16_t &raw) {
  Wire.beginTransmission(HTU); Wire.write(cmd);
  if (Wire.endTransmission() != 0) return false;
  delay(60);
  if (Wire.requestFrom(HTU, (uint8_t)3) < 2) return false;
  uint8_t hi = Wire.read(), lo = Wire.read();   // en este orden: primero el byte alto
  raw = ((hi << 8) | lo) & 0xFFFC;
  while (Wire.available()) Wire.read();
  return true;
}

void setup() {
  Serial.begin(115200);
  Wire.begin(D4, SCL_PIN);
}

void loop() {
  escanear();
  float t, h; uint16_t r;
  if (existe(AHT)) {
    if (leerAHT(t, h)) Serial.printf("AHT10: %.1f C | humedad %.1f %%\n", t, h);
    else Serial.println("AHT10: responde pero la lectura falló");
  } else if (existe(HTU)) {
    bool ok = leerHTU(0xF3, r); t = -46.85 + 175.72 * r / 65536.0;
    ok = ok && leerHTU(0xF5, r); h = -6.0 + 125.0 * r / 65536.0;
    if (ok) Serial.printf("HTU21D: %.1f C | humedad %.1f %%\n", t, h);
    else Serial.println("HTU21D: responde pero la lectura falló");
  } else {
    Serial.println("Sensor de temperatura: no encontrado");
  }
  delay(1500);
}
