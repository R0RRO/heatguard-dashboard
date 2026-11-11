// HeatGuard Clip: temperatura, humedad y batería por Bluetooth (BLE) cada 2 segundos.
// Sensor I2C en D4 (SDA) / D8 (SCL): AHT10/AHT20 (0x38) o HTU21D (0x40), se detecta solo.
// Batería: divisor en D1. Nombre Bluetooth: "HeatGuard Clip".
//
// Servicios:
//   Environmental Sensing (0x181A): Temperatura 0x2A6E (0,01 °C) y Humedad 0x2A6F (0,01 %)
//   Battery (0x180F): Nivel 0x2A19 (%)
//   Texto legible (UUID propio): "24.3 C | 41.2 % | bat 3.99 V"
//   Movimiento (UUID propio, cada 0,5 s): acelerómetro "a 0.01 -0.02 0.98" (g) y giroscopio "g 1 -3 0" (°/s)
//   MPU6050 (GY-521) en 0x68, mismo bus I2C.
#include <Wire.h>
// SCL movido de D5 a D8: el pin D5 de esta placa quedó en corto con GND (no usarlo).
const int SCL_PIN = D8;
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#if ESP_ARDUINO_VERSION < ESP_ARDUINO_VERSION_VAL(3, 3, 0)
#include <BLE2902.h>
#endif

const uint32_t PERIODO_MS = 2000;
const uint32_t PERIODO_MOV_MS = 500;
const uint8_t AHT = 0x38, HTU = 0x40, MPU = 0x68;
#define UUID_TEXTO_SERV "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
#define UUID_TEXTO_CHAR "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
#define UUID_MOV_SERV "7a1e0001-4865-6174-4775-617264436c70"
#define UUID_ACC_CHAR "7a1e0002-4865-6174-4775-617264436c70"
#define UUID_GIR_CHAR "7a1e0003-4865-6174-4775-617264436c70"

BLECharacteristic *cTemp, *cHum, *cBat, *cTexto, *cAcc, *cGir;
BLEServer *servidor;
bool conectado = false, ahtListo = false, mpuListo = false;

class Callbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *) override { conectado = true; Serial.println("BLE: conectado"); }
  void onDisconnect(BLEServer *s) override {
    conectado = false;
    Serial.println("BLE: desconectado, vuelvo a anunciarme");
    delay(200);
    s->startAdvertising();
  }
};

bool existe(uint8_t a) { Wire.beginTransmission(a); return Wire.endTransmission() == 0; }

bool leerAHT(float &t, float &h) {
  if (!ahtListo) {
    Wire.beginTransmission(AHT); Wire.write(0xE1); Wire.write(0x08); Wire.write(0x00); Wire.endTransmission();
    delay(20); ahtListo = true;
  }
  Wire.beginTransmission(AHT); Wire.write(0xAC); Wire.write(0x33); Wire.write(0x00);
  if (Wire.endTransmission() != 0) return false;
  delay(90);
  if (Wire.requestFrom(AHT, (uint8_t)6) != 6) return false;
  uint8_t b[6]; for (int i = 0; i < 6; i++) b[i] = Wire.read();
  if (b[0] & 0x80) return false;
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

bool leerSensor(float &t, float &h) {
  if (existe(AHT)) return leerAHT(t, h);
  if (existe(HTU)) {
    uint16_t r;
    if (!leerHTU(0xF3, r)) return false; t = -46.85 + 175.72 * r / 65536.0;
    if (!leerHTU(0xF5, r)) return false; h = -6.0 + 125.0 * r / 65536.0;
    return true;
  }
  return false;
}

// MPU6050: acelerómetro ±2 g (16384 por g) y giroscopio ±250 °/s (131 por °/s), valores por defecto
bool leerMPU(float a[3], float g[3]) {
  if (!mpuListo) {
    Wire.beginTransmission(MPU); Wire.write(0x6B); Wire.write(0x00);   // despertar
    if (Wire.endTransmission() != 0) return false;
    delay(50); mpuListo = true;
  }
  Wire.beginTransmission(MPU); Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) { mpuListo = false; return false; }
  if (Wire.requestFrom(MPU, (uint8_t)14) != 14) { mpuListo = false; return false; }
  int16_t v[7];
  for (int i = 0; i < 7; i++) { uint8_t hi = Wire.read(), lo = Wire.read(); v[i] = (int16_t)((hi << 8) | lo); }
  for (int i = 0; i < 3; i++) { a[i] = v[i] / 16384.0; g[i] = v[i + 4] / 131.0; }
  return true;
}

float leerBateria() {
  uint32_t mv = 0;
  for (int i = 0; i < 16; i++) mv += analogReadMilliVolts(D1);
  return mv / 16.0 * 2.0 / 1000.0;
}

BLECharacteristic *crear(BLEService *s, BLEUUID uuid) {
  BLECharacteristic *c = s->createCharacteristic(uuid, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
#if ESP_ARDUINO_VERSION < ESP_ARDUINO_VERSION_VAL(3, 3, 0)
  c->addDescriptor(new BLE2902());
#endif
  return c;
}

void nombrar(BLECharacteristic *c, const char *nombre) {   // nombre visible en nRF Connect
  BLEDescriptor *d = new BLEDescriptor(BLEUUID((uint16_t)0x2901));
  d->setValue(nombre);
  c->addDescriptor(d);
}

void setup() {
  Serial.begin(115200);
  Wire.begin(D4, SCL_PIN);

  BLEDevice::init("HeatGuard Clip");
  servidor = BLEDevice::createServer();
  servidor->setCallbacks(new Callbacks());

  BLEService *amb = servidor->createService(BLEUUID((uint16_t)0x181A));
  cTemp = crear(amb, BLEUUID((uint16_t)0x2A6E));
  cHum = crear(amb, BLEUUID((uint16_t)0x2A6F));
  amb->start();

  BLEService *bat = servidor->createService(BLEUUID((uint16_t)0x180F));
  cBat = crear(bat, BLEUUID((uint16_t)0x2A19));
  bat->start();

  BLEService *txt = servidor->createService(UUID_TEXTO_SERV);
  cTexto = crear(txt, BLEUUID(UUID_TEXTO_CHAR));
  txt->start();

  BLEService *mov = servidor->createService(UUID_MOV_SERV);
  cAcc = crear(mov, BLEUUID(UUID_ACC_CHAR)); nombrar(cAcc, "Acelerometro (g) X Y Z");
  cGir = crear(mov, BLEUUID(UUID_GIR_CHAR)); nombrar(cGir, "Giroscopio (grados/s) X Y Z");
  mov->start();

  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(BLEUUID((uint16_t)0x181A));
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.println("BLE: anunciándome como \"HeatGuard Clip\"");
}

void loop() {
  static uint32_t ultimoMov = 0, cuentaMov = 0;
  if (millis() - ultimoMov >= PERIODO_MOV_MS) {
    ultimoMov = millis();
    float a[3], g[3];
    char sa[24], sg[24];
    if (leerMPU(a, g)) {
      snprintf(sa, sizeof sa, "a %.2f %.2f %.2f", a[0], a[1], a[2]);
      snprintf(sg, sizeof sg, "g %d %d %d", (int)lroundf(g[0]), (int)lroundf(g[1]), (int)lroundf(g[2]));
    } else {
      snprintf(sa, sizeof sa, "MPU sin respuesta");
      snprintf(sg, sizeof sg, "MPU sin respuesta");
    }
    cAcc->setValue((uint8_t *)sa, strlen(sa));
    cGir->setValue((uint8_t *)sg, strlen(sg));
    if (conectado) { cAcc->notify(); cGir->notify(); }
    if (++cuentaMov % 4 == 0) Serial.printf("%s | %s\n", sa, sg);   // al monitor, cada 2 s
  }

  static uint32_t ultimo = 0;
  if (millis() - ultimo < PERIODO_MS) { delay(10); return; }
  ultimo = millis();

  float t = NAN, h = NAN;
  bool ok = leerSensor(t, h);
  float vbat = leerBateria();
  uint8_t pct = constrain((int)((vbat - 3.3) / (4.2 - 3.3) * 100), 0, 100);

  char texto[64];
  if (ok) snprintf(texto, sizeof texto, "%.1f C | %.1f %% | bat %.2f V", t, h, vbat);
  else snprintf(texto, sizeof texto, "sensor sin respuesta | bat %.2f V", vbat);
  Serial.printf("%s%s\n", texto, conectado ? "  [BLE]" : "");

  if (ok) {
    int16_t t100 = (int16_t)lroundf(t * 100);
    uint16_t h100 = (uint16_t)constrain(lroundf(h * 100), 0, 10000);
    cTemp->setValue((uint8_t *)&t100, 2);
    cHum->setValue((uint8_t *)&h100, 2);
  }
  cBat->setValue(&pct, 1);
  cTexto->setValue((uint8_t *)texto, strlen(texto));

  if (conectado) {
    if (ok) { cTemp->notify(); cHum->notify(); }
    cBat->notify();
    cTexto->notify();
  }
}
