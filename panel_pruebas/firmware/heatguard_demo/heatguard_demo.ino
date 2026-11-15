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
//                            0006 motor de vibración (escritura: intensidad, duración en décimas de s)
//                            0007 botón (notifica: presionado, último evento, contador)
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
#define UUID_MOT_CHAR   "7a1e0006-4865-6174-4775-617264436c70"   // escribir 2 bytes: intensidad (0-255), duración en décimas de s (0 = sin límite)

// Motor de vibración: D7 → 1 kΩ → base del 2N2222 (colector al − del motor, + del motor a 3V3, 1N4148 en paralelo)
const int MOTOR = D7;

// LED de batería bicolor: rojo en D9, azul en D10 (cada uno con su resistencia)
const int BAT_R = D9, BAT_B = D10;

// Botón de hidratación: D0 a GND (pull-up interno). Corto = pulsación; mantener 1 s = hidratación
const int BOTON = D0;
#define UUID_BTN_CHAR   "7a1e0007-4865-6174-4775-617264436c70"   // notifica 4 bytes: presionado, último evento (1 corto, 2 largo), contador (uint16)
uint32_t motorHasta = 0;   // millis() en que se apaga; 0 = sin límite

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

BLECharacteristic *cTemp, *cHum, *cBat, *cTexto, *cPaq, *cLed, *cMot, *cBtn;
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

// Al encender, 3 segundos con el nivel de batería en el LED de batería (D9 rojo, D10 azul):
//   0-20 %: rojo parpadeante · 20-50 %: rojo · 50-80 %: azul parpadeante · 80 % o más: azul
void indicarBateria() {
  pinMode(BAT_R, OUTPUT); pinMode(BAT_B, OUTPUT);
  digitalWrite(BAT_R, LOW); digitalWrite(BAT_B, LOW);
  delay(50);                                   // que se estabilice el voltaje
  float v = leerBateria();
  uint8_t pct = bateriaPct(v);
  Serial.printf("Bateria al encender: %.2f V (%u %%)\n", v, pct);
  int pin = (pct < 50) ? BAT_R : BAT_B;
  bool parpadea = (pct < 20) || (pct >= 50 && pct < 80);
  if (parpadea) {
    for (int i = 0; i < 6; i++) { digitalWrite(pin, HIGH); delay(250); digitalWrite(pin, LOW); delay(250); }
  } else {
    digitalWrite(pin, HIGH); delay(3000); digitalWrite(pin, LOW);
  }
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

void vibrar(uint8_t intensidad, uint32_t ms) {
  analogWrite(MOTOR, intensidad);
  motorHasta = (intensidad && ms) ? millis() + ms : 0;
}

class MotorCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    uint8_t *d = c->getData();
    size_t n = c->getLength();
    if (n >= 1) {
      uint32_t ms = (n >= 2) ? d[1] * 100UL : 0;
      vibrar(d[0], ms);
      Serial.printf("Motor: %u%s\n", d[0], ms ? "" : " (sin limite)");
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

// Porcentaje aproximado según el voltaje de una LiPo en reposo (curva típica, no medida en esta batería)
uint8_t bateriaPct(float v) {
  const float V[] = {3.30, 3.45, 3.68, 3.74, 3.77, 3.79, 3.82, 3.87, 3.92, 4.00, 4.10, 4.20};
  const float P[] = {0,    5,    10,   20,   30,   40,   50,   60,   70,   80,   90,   100};
  if (v <= V[0]) return 0;
  for (int i = 1; i < 12; i++)
    if (v <= V[i]) return (uint8_t)lroundf(P[i - 1] + (P[i] - P[i - 1]) * (v - V[i - 1]) / (V[i] - V[i - 1]));
  return 100;
}

float leerBateria() {
  uint32_t mv = 0;
  for (int i = 0; i < 16; i++) mv += analogReadMilliVolts(D1);
  return mv / 16.0 * 2.0 / 1000.0;
}

void publicarAmbiente(bool ok, float t, float h) {
  if (ok) { ultT = t; ultH = h; }
  float vbat = leerBateria();
  uint8_t pct = bateriaPct(vbat);
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
  // Prueba del LED de estado al encender: rojo, verde, azul y apagado
  ponerColor(255, 0, 0); delay(300);
  ponerColor(0, 255, 0); delay(300);
  ponerColor(0, 0, 255); delay(300);
  ponerColor(0, 0, 0);
  indicarBateria();
  pinMode(BOTON, INPUT_PULLUP);
  // Prueba del motor al encender: una vibración corta
  pinMode(MOTOR, OUTPUT); digitalWrite(MOTOR, LOW);
  analogWrite(MOTOR, 255); delay(250); analogWrite(MOTOR, 0);
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
  cMot = mov->createCharacteristic(BLEUUID(UUID_MOT_CHAR), BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  cMot->setCallbacks(new MotorCallbacks());
  cBtn = crear(mov, BLEUUID(UUID_BTN_CHAR));
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

// ---------- botón ----------
uint16_t eventos = 0;
uint8_t ultimoEvento = 0;
bool presionado = false, largoAvisado = false;
uint32_t tCambio = 0, tPresion = 0;

void publicarBoton() {
  uint8_t d[4] = {(uint8_t)presionado, ultimoEvento, (uint8_t)(eventos & 0xFF), (uint8_t)(eventos >> 8)};
  cBtn->setValue(d, 4);
  if (conectado) cBtn->notify();
}

void tareaBoton(uint32_t ahora) {
  bool p = digitalRead(BOTON) == LOW;
  if (p != presionado && ahora - tCambio > 30) {          // antirrebote de 30 ms
    tCambio = ahora;
    presionado = p;
    if (p) { tPresion = ahora; largoAvisado = false; vibrar(200, 60); }
    else if (!largoAvisado) {
      ultimoEvento = 1; eventos++;
      Serial.println("Boton: pulsacion corta");
    }
    publicarBoton();
  }
  if (presionado && !largoAvisado && ahora - tPresion >= 1000) {   // mantener 1 s = hidratación
    largoAvisado = true;
    ultimoEvento = 2; eventos++;
    vibrar(255, 400);
    Serial.println("Boton: pulsacion larga (hidratacion)");
    publicarBoton();
  }
}

void loop() {
  uint32_t ahora = millis();
  tareaBoton(ahora);
  if (motorHasta && (int32_t)(ahora - motorHasta) >= 0) { analogWrite(MOTOR, 0); motorHasta = 0; }

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
