// Busca en qué pines están conectados los sensores I2C probando todas las combinaciones
// SDA/SCL entre D0 y D10, y luego lee sus datos con los pines encontrados.
// Sensor de temperatura: AHT10 (0x38) o HTU21D (0x40). MPU6050: 0x68 o 0x69.
#include <Wire.h>

const int PINES[] = {D0, D1, D2, D3, D4, D5, D6, D7, D8, D9, D10};
const char *NOMBRES[] = {"D0", "D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8", "D9", "D10"};
const int N = 11;
const uint8_t DIRS[] = {0x38, 0x40, 0x68, 0x69};

int sdaOk = -1, sclOk = -1;
uint8_t dirTemp = 0, dirMpu = 0;

bool existe(uint8_t a) { Wire.beginTransmission(a); return Wire.endTransmission() == 0; }

void buscar() {
  sdaOk = sclOk = -1; dirTemp = dirMpu = 0;
  for (int i = 0; i < N; i++) for (int j = 0; j < N; j++) {
    if (i == j) continue;
    Wire.begin(PINES[i], PINES[j]);
    Wire.setClock(100000);
    Wire.setTimeOut(10);
    uint8_t t = 0, m = 0;
    for (uint8_t a : DIRS) if (existe(a)) { if (a < 0x60) t = a; else m = a; }
    Wire.end();
    pinMode(PINES[i], INPUT); pinMode(PINES[j], INPUT);
    if (t || m) {
      Serial.printf("ENCONTRADO: SDA=%s SCL=%s ->%s%s\n", NOMBRES[i], NOMBRES[j],
                    t ? (t == 0x38 ? " sensor AHT10 (0x38)" : " sensor HTU21D (0x40)") : "",
                    m ? " MPU6050" : "");
      if ((t ? 1 : 0) + (m ? 1 : 0) > (dirTemp ? 1 : 0) + (dirMpu ? 1 : 0)) { sdaOk = i; sclOk = j; dirTemp = t; dirMpu = m; }
    }
  }
}

void leer() {
  Wire.begin(PINES[sdaOk], PINES[sclOk]);
  Wire.setClock(100000);
  if (dirTemp == 0x38) {
    Wire.beginTransmission(0x38); Wire.write(0xE1); Wire.write(0x08); Wire.write(0x00); Wire.endTransmission();
    delay(20);
    Wire.beginTransmission(0x38); Wire.write(0xAC); Wire.write(0x33); Wire.write(0x00); Wire.endTransmission();
    delay(90);
    if (Wire.requestFrom((uint8_t)0x38, (uint8_t)6) == 6) {
      uint8_t b[6]; for (int i = 0; i < 6; i++) b[i] = Wire.read();
      uint32_t rh = ((uint32_t)b[1] << 12) | ((uint32_t)b[2] << 4) | (b[3] >> 4);
      uint32_t rt = ((uint32_t)(b[3] & 0x0F) << 16) | ((uint32_t)b[4] << 8) | b[5];
      Serial.printf("Temperatura: %.1f C | Humedad: %.1f %%\n", rt * 200.0 / 1048576.0 - 50.0, rh * 100.0 / 1048576.0);
    } else Serial.println("Temperatura: no respondio a la lectura");
  } else if (dirTemp == 0x40) {
    uint16_t r[2]; const uint8_t cmd[2] = {0xF3, 0xF5}; bool ok = true;
    for (int k = 0; k < 2; k++) {
      Wire.beginTransmission(0x40); Wire.write(cmd[k]); Wire.endTransmission(); delay(60);
      if (Wire.requestFrom((uint8_t)0x40, (uint8_t)3) < 2) { ok = false; break; }
      uint8_t hi = Wire.read(), lo = Wire.read(); while (Wire.available()) Wire.read();
      r[k] = ((hi << 8) | lo) & 0xFFFC;
    }
    if (ok) Serial.printf("Temperatura: %.1f C | Humedad: %.1f %%\n", -46.85 + 175.72 * r[0] / 65536.0, -6.0 + 125.0 * r[1] / 65536.0);
    else Serial.println("Temperatura: no respondio a la lectura");
  }
  if (dirMpu) {
    Wire.beginTransmission(dirMpu); Wire.write(0x6B); Wire.write(0x00); Wire.endTransmission();
    delay(10);
    Wire.beginTransmission(dirMpu); Wire.write(0x3B); Wire.endTransmission(false);
    if (Wire.requestFrom(dirMpu, (uint8_t)14) == 14) {
      int16_t v[7];
      for (int i = 0; i < 7; i++) { uint8_t hi = Wire.read(), lo = Wire.read(); v[i] = (int16_t)((hi << 8) | lo); }
      Serial.printf("Acelerometro (g): %.2f %.2f %.2f | Giroscopio (grados/s): %.0f %.0f %.0f\n",
                    v[0] / 16384.0, v[1] / 16384.0, v[2] / 16384.0, v[4] / 131.0, v[5] / 131.0, v[6] / 131.0);
    } else Serial.println("MPU6050: no respondio a la lectura");
  }
  Wire.end();
}

void setup() { Serial.begin(115200); }

void loop() {
  Serial.println("------------------------------");
  buscar();
  if (sdaOk < 0) Serial.println("Ningun sensor responde en ninguna combinacion de pines D0 a D10.");
  else {
    Serial.printf("Usando SDA=%s SCL=%s\n", NOMBRES[sdaOk], NOMBRES[sclOk]);
    leer();
    if (!dirTemp) Serial.println("Sensor de temperatura: no aparece");
    if (!dirMpu) Serial.println("MPU6050: no aparece");
  }
  delay(1500);
}
