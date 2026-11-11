// HeatGuard Clip: firmware de demostración por Bluetooth (BLE) para la mini app del PC.
//  - Temperatura y humedad (AHT10/AHT20 en 0x38 o HTU21D en 0x40) cada 2 s
//  - Batería (divisor en D1) cada 2 s
//  - MPU6050 (0x68) leído a 50 Hz: cuenta pasos, estima el rumbo con el giroscopio e inclinación
// I2C: SDA = D4, SCL = D8. Nombre Bluetooth: "HeatGuard Clip".
// Al encender, dejarlo QUIETO 2 segundos (calibra el giroscopio).
//
// Servicios BLE:
//   0x181A Environmental Sensing: 0x2A6E temperatura (0,01 °C), 0x2A6F humedad (0,01 %)
//   0x180F Battery: 0x2A19 nivel (%)
//   Nordic UART (texto para nRF Connect): "26.1 C | 61.4 % | bat 3.96 V"
//   Movimiento 7a1e0001-...: 0004 paquete binario de 12 bytes cada 100 ms (ver struct Paquete)
//                            0005 color del LED RGB (escritura, 3 bytes R G B)
#include <Wire.h>
// SCL movido de D5 a D8: el pin D5 de esta placa quedó en corto con GND (no usarlo).
const int SCL_PIN = D8;
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#if ESP_ARDUINO_VERSION < ESP_ARDUINO_VERSION_VAL(3, 3, 0)
#include <BLE2902.h>
#endif

const uint8_t AHT = 0x38, HTU = 0x40, MPU = 0x68;
const uint32_t PERIODO_ENV_MS = 2000, PERIODO_IMU_MS = 20, PERIODO_TX_MS = 100;
// Detección de pasos sobre el módulo de la aceleración (en g)
const float UMBRAL_SUBE = 1.12, UMBRAL_BAJA = 1.02;
const uint32_t PASO_MIN_MS = 300;

#define UUID_TEXTO_SERV "6e400001-b5a3-f393-e0a9-e50e24dcca9e"
#define UUID_TEXTO_CHAR "6e400003-b5a3-f393-e0a9-e50e24dcca9e"
#define UUID_MOV_SERV   "7a1e0001-4865-6174-4775-617264436c70"
#define UUID_PAQ_CHAR   "7a1e0004-4865-6174-4775-617264436c70"
#define UUID_LED_CHAR   "7a1e0005-4865-6174-4775-617264436c70"   // escribir 3 bytes: R, G, B (0-255)

// LED de estado RGB de cátodo común. En este prototipo el rojo quedó cableado en D6 y el azul en D2
// (al revés del mapa original), así que se corrige aquí: R = D6, G = D3, B = D2.
const int LED_R = D6, LED_G = D3, LED_B = D2;

struct __attribute__((packed)) Paquete {
  uint32_t pasos;     // pasos desde el encendido
  int16_t rumbo10;    // rumbo relativo en décimas de grado (0..3599), horario positivo
  int16_t pitch10;    // inclinación adelante/atrás, décimas de grado
  int16_t roll10;     // inclinación lateral, décimas de grado
  uint16_t mag1000;   // módulo de la aceleración en milésimas de g
};

BLECharacteristic *cTemp, *cHum, *cBat, *cTexto, *cPaq, *cLed;
bool conectado = false;

// ---------- estado ----------
uint8_t tipoSensor = 0;            // 0 = ninguno, 1 = AHT, 2 = HTU
bool ahtMidiendo = false;
uint32_t tAhtTrig = 0, tEnv = 0, tImu = 0, tTx = 0, tPaso = 0;
bool mpuOk = false, arriba = false;
float bias[3] = {0, 0, 0}, grav[3] = {0, 0, 1}, magF = 1.0;
float rumbo = 0, pitch = 0, roll = 0;
uint32_t pasos = 0;
float ultT = NAN, ultH = NAN;

class Callbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *) override { conectado = true; Serial.println("BLE: conectado"); }
  void onDisconnect(BLEServer *s) override {
    conectado = false;
    Serial.println("BLE: desconectado, vuelvo a anunciarme");
    delay(200);
    s->startAdvertising();
  }
};

void ponerColor(uint8_t r, uint8_t g, uint8_t b) {
  analogWrite(LED_R, r);
  analogWrite(LED_G, g);
  analogWrite(LED_B, b);
}

class LedCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    uint8_t *d = c->getData();
    if (c->getLength() >= 3) {
      ponerColor(d[0], d[1], d[2]);
      Serial.printf("LED: %u %u %u\n", d[0], d[1], d[2]);
    }
  }
};

bool existe(uint8_t a) { Wire.beginTransmission(a); return Wire.endTransmission() == 0; }

// ---------- MPU6050 ----------
bool iniciarMPU() {
  Wire.beginTransmission(MPU); Wire.write(0x6B); Wire.write(0x00);          // despertar
  if (Wire.endTransmission() != 0) return false;
  Wire.beginTransmission(MPU); Wire.write(0x1A); Wire.write(0x03); Wire.endTransmission();  // filtro ~44 Hz
  delay(50);
  return true;
}

bool leerMPU(float a[3], float g[3]) {       // a en g (±2 g), g en °/s (±250)
  Wire.beginTransmission(MPU); Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(MPU, (uint8_t)14) != 14) return false;
  int16_t v[7];
  for (int i = 0; i < 7; i++) { uint8_t hi = Wire.read(), lo = Wire.read(); v[i] = (int16_t)((hi << 8) | lo); }
  for (int i = 0; i < 3; i++) { a[i] = v[i] / 16384.0; g[i] = v[i + 4] / 131.0; }
  return true;
}

void calibrarGiro() {
  Serial.println("Calibrando giroscopio: no lo muevas...");
  float s[3] = {0, 0, 0}, a[3], g[3], sa[3] = {0, 0, 0};
  int n = 0;
  for (int k = 0; k < 100; k++) {
    if (leerMPU(a, g)) { for (int i = 0; i < 3; i++) { s[i] += g[i]; sa[i] += a[i]; } n++; }
    delay(10);
  }
  if (n) for (int i = 0; i < 3; i++) { bias[i] = s[i] / n; grav[i] = sa[i] / n; }
  Serial.printf("Listo (%d muestras)\n", n);
}

void procesarIMU(float dt) {
  float a[3], g[3];
  if (!leerMPU(a, g)) { mpuOk = false; return; }
  for (int i = 0; i < 3; i++) { g[i] -= bias[i]; grav[i] += 0.04f * (a[i] - grav[i]); }

  float gn = sqrtf(grav[0] * grav[0] + grav[1] * grav[1] + grav[2] * grav[2]);
  if (gn < 0.3f) return;
  float u[3] = {grav[0] / gn, grav[1] / gn, grav[2] / gn};       // "arriba", en ejes del sensor

  // Giro alrededor de la vertical, sin importar cómo esté montado el clip
  float giroVertical = g[0] * u[0] + g[1] * u[1] + g[2] * u[2];
  if (fabsf(giroVertical) > 0.8f) rumbo -= giroVertical * dt;      // zona muerta contra la deriva
  while (rumbo < 0) rumbo += 360;
  while (rumbo >= 360) rumbo -= 360;

  pitch = atan2f(-u[0], sqrtf(u[1] * u[1] + u[2] * u[2])) * 57.2958f;
  roll = atan2f(u[1], u[2]) * 57.2958f;

  // Pasos: pico del módulo de la aceleración
  float mag = sqrtf(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]);
  magF += 0.3f * (mag - magF);
  uint32_t ahora = millis();
  if (!arriba && magF > UMBRAL_SUBE && ahora - tPaso > PASO_MIN_MS) { arriba = true; pasos++; tPaso = ahora; }
  else if (arriba && magF < UMBRAL_BAJA) arriba = false;
}

// ---------- temperatura y humedad ----------
void detectarSensor() {
  if (existe(AHT)) {
    tipoSensor = 1;
    Wire.beginTransmission(AHT); Wire.write(0xE1); Wire.write(0x08); Wire.write(0x00); Wire.endTransmission();
    delay(20);
  } else if (existe(HTU)) tipoSensor = 2;
  else tipoSensor = 0;
}

bool leerHTU(uint8_t cmd, uint16_t &raw) {
  Wire.beginTransmission(HTU); Wire.write(cmd);
  if (Wire.endTransmission() != 0) return false;
  delay(60);
  if (Wire.requestFrom(HTU, (uint8_t)3) < 2) return false;
  uint8_t hi = Wire.read(), lo = Wire.read();
  while (Wire.available()) Wire.read();
  raw = ((hi << 8) | lo) & 0xFFFC;
  return true;
}

float leerBateria() {
  uint32_t mv = 0;
  for (int i = 0; i < 16; i++) mv += analogReadMilliVolts(D1);
  return mv / 16.0 * 2.0 / 1000.0;
}

void publicarAmbiente(bool ok, float t, float h) {
  if (ok) { ultT = t; ultH = h; }
  float vbat = leerBateria();
  uint8_t pct = constrain((int)((vbat - 3.3) / (4.2 - 3.3) * 100), 0, 100);
  char texto[64];
  if (ok) snprintf(texto, sizeof texto, "%.1f C | %.1f %% | bat %.2f V", t, h, vbat);
  else snprintf(texto, sizeof texto, "sensor sin respuesta | bat %.2f V", vbat);
  Serial.printf("%s | pasos %lu | rumbo %.0f%s%s\n", texto, (unsigned long)pasos, rumbo,
                mpuOk ? "" : " | MPU sin respuesta", conectado ? "  [BLE]" : "");
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

void tareaAmbiente(uint32_t ahora) {
  if (ahtMidiendo) {                                   // AHT: leer 100 ms después del disparo
    if (ahora - tAhtTrig < 100) return;
    ahtMidiendo = false;
    float t = NAN, h = NAN; bool ok = false;
    if (Wire.requestFrom(AHT, (uint8_t)6) == 6) {
      uint8_t b[6]; for (int i = 0; i < 6; i++) b[i] = Wire.read();
      if (!(b[0] & 0x80)) {
        uint32_t rh = ((uint32_t)b[1] << 12) | ((uint32_t)b[2] << 4) | (b[3] >> 4);
        uint32_t rt = ((uint32_t)(b[3] & 0x0F) << 16) | ((uint32_t)b[4] << 8) | b[5];
        h = rh * 100.0 / 1048576.0; t = rt * 200.0 / 1048576.0 - 50.0; ok = true;
      }
    }
    publicarAmbiente(ok, t, h);
    return;
  }
  if (ahora - tEnv < PERIODO_ENV_MS) return;
  tEnv = ahora;
  if (tipoSensor == 0) detectarSensor();
  if (tipoSensor == 1) {
    Wire.beginTransmission(AHT); Wire.write(0xAC); Wire.write(0x33); Wire.write(0x00);
    if (Wire.endTransmission() == 0) { ahtMidiendo = true; tAhtTrig = ahora; }
    else { tipoSensor = 0; publicarAmbiente(false, 0, 0); }
  } else if (tipoSensor == 2) {
    uint16_t r; float t = 0, h = 0;
    bool ok = leerHTU(0xF3, r); t = -46.85 + 175.72 * r / 65536.0;
    ok = ok && leerHTU(0xF5, r); h = -6.0 + 125.0 * r / 65536.0;
    if (!ok) tipoSensor = 0;
    publicarAmbiente(ok, t, h);
  } else publicarAmbiente(false, 0, 0);
}

// ---------- BLE ----------
BLECharacteristic *crear(BLEService *s, BLEUUID uuid) {
  BLECharacteristic *c = s->createCharacteristic(uuid, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
#if ESP_ARDUINO_VERSION < ESP_ARDUINO_VERSION_VAL(3, 3, 0)
  c->addDescriptor(new BLE2902());
#endif
  return c;
}

void setup() {
  Serial.begin(115200);
  // Prueba del LED al encender: rojo, verde, azul y apagado
  ponerColor(255, 0, 0); delay(300);
  ponerColor(0, 255, 0); delay(300);
  ponerColor(0, 0, 255); delay(300);
  ponerColor(0, 0, 0);
  Wire.begin(D4, SCL_PIN);
  Wire.setClock(100000);   // 100 kHz: más tolerante a cables largos y pull-ups débiles

  mpuOk = iniciarMPU();
  if (mpuOk) calibrarGiro(); else Serial.println("MPU6050 no encontrado");
  detectarSensor();

  BLEDevice::init("HeatGuard Clip");
  BLEServer *servidor = BLEDevice::createServer();
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
  cPaq = crear(mov, BLEUUID(UUID_PAQ_CHAR));
  cLed = mov->createCharacteristic(BLEUUID(UUID_LED_CHAR),
           BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  cLed->setCallbacks(new LedCallbacks());
  uint8_t apagado[3] = {0, 0, 0};
  cLed->setValue(apagado, 3);
  mov->start();

  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(BLEUUID((uint16_t)0x181A));
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.println("BLE: anunciándome como \"HeatGuard Clip\"");
  tImu = millis();
}

void loop() {
  uint32_t ahora = millis();

  if (ahora - tImu >= PERIODO_IMU_MS) {
    float dt = (ahora - tImu) / 1000.0f;
    tImu = ahora;
    if (mpuOk) procesarIMU(dt);
    else if (iniciarMPU()) { mpuOk = true; calibrarGiro(); }
  }

  if (ahora - tTx >= PERIODO_TX_MS) {
    tTx = ahora;
    Paquete p;
    p.pasos = pasos;
    p.rumbo10 = (int16_t)lroundf(rumbo * 10) % 3600;
    p.pitch10 = (int16_t)lroundf(pitch * 10);
    p.roll10 = (int16_t)lroundf(roll * 10);
    p.mag1000 = (uint16_t)constrain(lroundf(magF * 1000), 0, 65535);
    cPaq->setValue((uint8_t *)&p, sizeof p);
    if (conectado) cPaq->notify();
  }

  tareaAmbiente(ahora);
  delay(2);
}
