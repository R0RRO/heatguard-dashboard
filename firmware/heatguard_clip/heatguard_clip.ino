// HeatGuard Clip: firmware del prototipo (XIAO ESP32-C3).
//
// Idea: el clip pide PAUSAS DE HIDRATACIÓN Y DESCANSO cuando el trabajador acumula cierto tiempo expuesto
// al calor y moviéndose. La pausa empieza y termina SOLO cuando el trabajador mantiene el botón 2 s.
//
//  - Mide temperatura del aire y humedad relativa (AHT10/AHT20 en 0x38 o HTU21D en 0x40) cada 2 s y calcula
//    el Heat Index del NWS (heat_index.h), indicador AUXILIAR (no es WBGT/TGBH).
//  - Índice de movimiento (0–100) con el MPU6050: describe cuánto se mueve el clip; no es tasa metabólica.
//  - EXPOSICIÓN acumulada (% del límite): cada minuto suma (100 / límite) × factor de calor × factor de movimiento.
//    Factor de calor por categoría del Heat Index: ×1, ×1,5, ×2, ×3, ×4. Movimiento: ×0,75 (quieto) a ×1,25.
//    Factor personal (altura y peso del trabajador, lo envía el panel): ×1 a ×1,2.
//    Durante la pausa baja hasta 0 % en la duración configurada. Regla del prototipo, sin validar.
//  - LED de estado:
//      óptimo          verde parpadeante
//      cansancio       amarillo                  (exposición ≥ umbral de cansancio)
//      toca descanso   rojo + 5 vibraciones cada 40 s   (exposición ≥ 100 % o pedido del supervisor)
//      en pausa        azul fijo                 (botón mantenido 2 s)
//      pausa cumplida  azul parpadeante + vibración cada 40 s   (hasta cerrar con el botón)
//  - Envía todo por Bluetooth con el contrato de datos v2 (docs/contrato-datos.md) y recibe la configuración
//    del panel. Funciona igual sin el panel.
//
// Límites: no tiene certificación ISO, no entrega diagnóstico médico y no predice golpes de calor.
//
// Pines de este prototipo
//   I2C: SDA = D4, SCL = D8 (D5 quedó en corto con GND: no usarlo)
//   LED de estado RGB (cátodo común): R = D6, G = D3, B = D2
//   LED de batería: rojo = D9, azul = D10
//   Motor de vibración: D7 (1 kΩ → 2N2222)     Botón: D0 a GND     Divisor de batería: D1
//
// Al encender, dejarlo QUIETO 2 segundos (calibra el giroscopio).
#include <Wire.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#if defined(CONFIG_BLUEDROID_ENABLED)
#include <esp_gap_ble_api.h>   // para leer la intensidad de la señal (RSSI) del enlace
#elif defined(CONFIG_NIMBLE_ENABLED)
#include "host/ble_gap.h"      // ídem con la pila NimBLE
#endif
#if ESP_ARDUINO_VERSION < ESP_ARDUINO_VERSION_VAL(3, 3, 0)
#include <BLE2902.h>
#endif
#include <Preferences.h>
#include "heat_index.h"

// ───────── Pines ─────────
const int SDA_PIN = D4, SCL_PIN = D8;
const int LED_R = D6, LED_G = D3, LED_B = D2;
const int BAT_R = D9, BAT_B = D10;
const int MOTOR = D7;
const int BOTON = D0;
const int PIN_BATERIA = D1;

// ───────── Parámetros (reglas del prototipo, sin validar; el panel puede cambiarlos) ─────────
const uint32_t PERIODO_ENV_MS = 2000;      // lectura de temperatura y humedad, y envío de telemetría
const uint32_t PERIODO_IMU_MS = 20;        // acelerómetro a 50 Hz
const uint32_t PERIODO_EXPOSICION_MS = 1000;    // actualización de la exposición y del estado
const uint32_t PERIODO_PRUEBA_MS = 100;    // paquete de movimiento para el panel de pruebas
const float MOV_ESCALA_G = 0.35f;          // aceleración dinámica RMS (g) que equivale a índice 100
const uint32_t MANTENER_MS = 2000;         // botón mantenido para comenzar o terminar la pausa
const uint32_t AVISO_CADA_MS = 40000;      // repetir la vibración de "toca descanso" y "pausa cumplida"
const uint32_t PRUEBA_MS = 20000;          // tras un comando del panel de pruebas, no tocar LED ni motor
const float EXPOSICION_MAX = 150.0f;            // tope mientras se espera que el trabajador comience la pausa
const float HISTERESIS_CANSANCIO = 5.0f;   // puntos bajo el umbral para volver de amarillo a verde
const float FACTOR_CALOR[] = {1.0f, 1.5f, 2.0f, 3.0f, 4.0f};   // por categoría del Heat Index (0–4)

uint8_t limiteExposicion = 120;                 // minutos-equivalentes para llegar al 100 %
uint8_t umbralCansancio = 70;              // % de exposición para pasar a amarillo
uint8_t minutosPausa = 15;                 // duración de la pausa
bool pausaAutomatica = true;               // pedir la pausa sola al llegar al 100 %
float factorPersonal = 1.0f;               // según el IMC del trabajador asignado (lo envía el panel)
Preferences prefs;                         // la configuración recibida se guarda y sobrevive a un reinicio

// ───────── Bluetooth ─────────
// Contrato de datos v2
#define UUID_CLIP_SERV  "7a1e0100-4865-6174-4775-617264436c70"
#define UUID_TELE_CHAR  "7a1e0101-4865-6174-4775-617264436c70"   // notifica y lee: paquete de 20 bytes
#define UUID_CMD_CHAR   "7a1e0102-4865-6174-4775-617264436c70"   // escritura: [comando, argumento]
// Panel de pruebas (panel_pruebas/demo_ble)
#define UUID_MOV_SERV   "7a1e0001-4865-6174-4775-617264436c70"
#define UUID_PAQ_CHAR   "7a1e0004-4865-6174-4775-617264436c70"   // pasos, rumbo e inclinación
#define UUID_LED_CHAR   "7a1e0005-4865-6174-4775-617264436c70"   // escribir R, G, B
#define UUID_MOT_CHAR   "7a1e0006-4865-6174-4775-617264436c70"   // escribir intensidad, décimas de s
#define UUID_BTN_CHAR   "7a1e0007-4865-6174-4775-617264436c70"   // presionado, último evento, contador

const uint8_t CONTRATO_VERSION = 2;
enum Comando : uint8_t { CMD_SOLICITAR_PAUSA = 2, CMD_MINUTOS_PAUSA = 4, CMD_UBICAR = 5, CMD_RETIRAR_PAUSA = 6,
                         CMD_LIMITE_EXPOSICION = 7, CMD_UMBRAL_CANSANCIO = 8, CMD_PAUSA_AUTOMATICA = 9, CMD_FACTOR_PERSONAL = 10 };
enum Bandera : uint8_t { F_AMBIENTE_OK = 1, F_MOVIMIENTO_OK = 2, F_BOTON = 4, F_PEDIDA_SUPERVISOR = 8 };
enum Estado : uint8_t { OPTIMO = 0, CANSANCIO = 1, DESCANSO = 2, EN_PAUSA = 3, PAUSA_CUMPLIDA = 4 };
const char *NOMBRE_ESTADO[] = {"optimo", "cansancio", "TOCA DESCANSO", "en pausa", "PAUSA CUMPLIDA"};

// Paquete de telemetría (20 bytes, little-endian). Debe coincidir con src/lib/telemetry.js
struct __attribute__((packed)) Telemetria {
  uint8_t version;        // 0
  uint8_t banderas;       // 1
  uint16_t secuencia;     // 2
  int16_t temp100;        // 4   centésimas de °C
  uint16_t hum100;        // 6   centésimas de %
  int16_t hi100;          // 8   Heat Index en centésimas de °C (-32768 = sin lectura)
  uint8_t movimiento;     // 10  índice 0–100
  uint8_t bateriaPct;     // 11
  uint16_t bateriaMv;     // 12
  uint8_t exposicion;          // 14  % del límite (tope 150)
  uint8_t estado;         // 15  ver Estado
  uint8_t pausas;         // 16  pausas completadas desde el encendido
  int8_t rssi;            // 17  intensidad de la señal Bluetooth del enlace en dBm (0 = sin dato)
  uint16_t segEstado;     // 18  en pausa: segundos desde que empezó; si no: desde la última pausa
};
static_assert(sizeof(Telemetria) == 20, "El paquete de telemetria debe medir 20 bytes");

struct __attribute__((packed)) PaquetePrueba {
  uint32_t pasos;
  int16_t rumbo10, pitch10, roll10;
  uint16_t mag1000;
};

BLECharacteristic *cTele, *cCmd, *cTemp, *cHum, *cBat, *cPaq, *cLed, *cMot, *cBtn;
volatile bool conectado = false;
volatile uint8_t cmdPendiente = 0, cmdArg = 0;
volatile uint32_t pruebaHasta = 0;         // mientras no pase, mandan el LED y el motor del panel de pruebas

// ───────── Estado ─────────
const uint8_t AHT = 0x38, HTU = 0x40, MPU = 0x68;
uint8_t tipoSensor = 0;                    // 0 ninguno, 1 AHT, 2 HTU
bool ahtMidiendo = false, ambienteOk = false;
float tempC = NAN, humedad = NAN, heatIndex = NAN;
uint32_t tAhtTrig = 0, tEnv = 0, tImu = 0, tPrueba = 0, tPaso = 0, tExposicion = 0;

bool mpuOk = false, arriba = false;
float bias[3] = {0, 0, 0}, grav[3] = {0, 0, 1}, magF = 1.0f;
float magBase = 1.0f;                      // módulo de la aceleración en reposo (cada sensor tiene su desfase)
float rumbo = 0, pitch = 0, roll = 0, movVar = 0;
uint32_t pasos = 0;
uint8_t movimiento = 0;

uint16_t secuencia = 0;
float bateriaV = 0;
uint8_t bateriaPorc = 0;

// Exposición y pausa
float exposicion = 0;                           // % del límite
Estado estado = OPTIMO;
bool pausaSolicitada = false, pausaAuto = false, enPausa = false;
uint8_t pausasHechas = 0;
uint32_t tPausaInicio = 0, tUltimaPausa = 0, tAviso = 0;

// Vibración por pulsos (sin bloquear)
uint8_t vibPulsos = 0, vibIntensidad = 255;
uint16_t vibOn = 0, vibOff = 0;
bool vibEncendido = false;
uint32_t tVib = 0, motorHasta = 0;

// Destello del LED por un evento (ubicar)
uint8_t fxR = 0, fxG = 0, fxB = 0;
uint16_t fxPeriodo = 0;
uint32_t fxHasta = 0;

// Intensidad de la señal Bluetooth del enlace con el panel
volatile int8_t rssiEnlace = 0;
uint32_t tRssi = 0;
int rssiError = 0;                         // último código de error al leer la señal (para diagnóstico)
BLEServer *servidor = nullptr;
#if defined(CONFIG_BLUEDROID_ENABLED)
esp_bd_addr_t direccionPanel;
volatile bool hayDireccion = false;
#endif

// Botón
uint16_t eventosBoton = 0;
uint8_t ultimoEvento = 0;                  // 1 corta (sin efecto), 3 comenzó la pausa, 4 terminó la pausa
bool presionado = false, largoAvisado = false;
uint32_t tCambio = 0, tPresion = 0;

// ───────── Salidas ─────────
void ponerColor(uint8_t r, uint8_t g, uint8_t b) {
  analogWrite(LED_R, r);
  analogWrite(LED_G, g);
  analogWrite(LED_B, b);
}

void vibrarPulsos(uint8_t pulsos, uint16_t msOn, uint16_t msOff, uint8_t intensidad) {
  vibPulsos = pulsos; vibOn = msOn; vibOff = msOff; vibIntensidad = intensidad;
  vibEncendido = true; tVib = millis();
  analogWrite(MOTOR, intensidad);
}

void destello(uint8_t r, uint8_t g, uint8_t b, uint16_t periodoMs, uint32_t duracionMs) {
  fxR = r; fxG = g; fxB = b; fxPeriodo = periodoMs; fxHasta = millis() + duracionMs;
}

void tareaVibracion(uint32_t ahora) {
  if (motorHasta && (int32_t)(ahora - motorHasta) >= 0) { analogWrite(MOTOR, 0); motorHasta = 0; }  // panel de pruebas
  if (!vibPulsos) return;
  if (vibEncendido && ahora - tVib >= vibOn) {
    analogWrite(MOTOR, 0); vibEncendido = false; tVib = ahora; vibPulsos--;
  } else if (!vibEncendido && ahora - tVib >= vibOff) {
    analogWrite(MOTOR, vibIntensidad); vibEncendido = true; tVib = ahora;
  }
}

// Vibraciones de cada aviso
void vibrarDescanso() { vibrarPulsos(5, 200, 200, 255); }        // 5 pulsos en ~2 s
void vibrarPausaCumplida() { vibrarPulsos(3, 450, 300, 255); }   // 3 pulsos largos

// LED de estado según el estado del clip
void tareaLed(uint32_t ahora) {
  if ((int32_t)(pruebaHasta - ahora) > 0) return;                    // manda el panel de pruebas
  if ((int32_t)(fxHasta - ahora) > 0) {                              // destello de un evento
    bool on = fxPeriodo == 0 || (ahora % fxPeriodo) < fxPeriodo / 2;
    if (on) ponerColor(fxR, fxG, fxB); else ponerColor(0, 0, 0);
    return;
  }
  switch (estado) {
    case OPTIMO:         if (ahora % 3000 < 150) ponerColor(0, 120, 0); else ponerColor(0, 0, 0); break;   // verde parpadeante
    case CANSANCIO:      ponerColor(200, 90, 0); break;                                                    // amarillo
    case DESCANSO:       ponerColor(220, 0, 0); break;                                                     // rojo
    case EN_PAUSA:       ponerColor(0, 0, 160); break;                                                     // azul fijo
    case PAUSA_CUMPLIDA: if (ahora % 1000 < 500) ponerColor(0, 0, 200); else ponerColor(0, 0, 0); break;   // azul parpadeante
  }
}

// ───────── Batería ─────────
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
  for (int i = 0; i < 16; i++) mv += analogReadMilliVolts(PIN_BATERIA);
  return mv / 16.0 * 2.0 / 1000.0;     // el divisor entrega la mitad
}

// Al encender, 3 segundos con el nivel de batería en el LED de batería:
//   0-20 %: rojo parpadeante · 20-50 %: rojo · 50-80 %: azul parpadeante · 80 % o más: azul
void indicarBateria() {
  pinMode(BAT_R, OUTPUT); pinMode(BAT_B, OUTPUT);
  digitalWrite(BAT_R, LOW); digitalWrite(BAT_B, LOW);
  delay(50);
  bateriaV = leerBateria();
  bateriaPorc = bateriaPct(bateriaV);
  Serial.printf("Bateria al encender: %.2f V (%u %%)\n", bateriaV, bateriaPorc);
  int pin = (bateriaPorc < 50) ? BAT_R : BAT_B;
  bool parpadea = (bateriaPorc < 20) || (bateriaPorc >= 50 && bateriaPorc < 80);
  if (parpadea) {
    for (int i = 0; i < 6; i++) { digitalWrite(pin, HIGH); delay(250); digitalWrite(pin, LOW); delay(250); }
  } else {
    digitalWrite(pin, HIGH); delay(3000); digitalWrite(pin, LOW);
  }
}

// ───────── Sensores ─────────
bool existe(uint8_t a) { Wire.beginTransmission(a); return Wire.endTransmission() == 0; }

bool iniciarMPU() {
  Wire.beginTransmission(MPU); Wire.write(0x6B); Wire.write(0x00);          // despertar
  if (Wire.endTransmission() != 0) return false;
  Wire.beginTransmission(MPU); Wire.write(0x1A); Wire.write(0x03); Wire.endTransmission();  // filtro ~44 Hz
  Wire.beginTransmission(MPU); Wire.write(0x1C); Wire.write(0x08); Wire.endTransmission();  // acelerómetro ±4 g (al correr se pasa de 2 g)
  Wire.beginTransmission(MPU); Wire.write(0x1B); Wire.write(0x08); Wire.endTransmission();  // giroscopio ±500 °/s
  delay(50);
  return true;
}

bool leerMPU(float a[3], float g[3]) {       // a en g (±4 g), g en °/s (±500)
  Wire.beginTransmission(MPU); Wire.write(0x3B);
  if (Wire.endTransmission(false) != 0) return false;
  if (Wire.requestFrom(MPU, (uint8_t)14) != 14) return false;
  int16_t v[7];
  for (int i = 0; i < 7; i++) { uint8_t hi = Wire.read(), lo = Wire.read(); v[i] = (int16_t)((hi << 8) | lo); }
  for (int i = 0; i < 3; i++) { a[i] = v[i] / 8192.0; g[i] = v[i + 4] / 65.5; }
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
  if (n) {
    for (int i = 0; i < 3; i++) { bias[i] = s[i] / n; grav[i] = sa[i] / n; }
    magBase = sqrtf(grav[0] * grav[0] + grav[1] * grav[1] + grav[2] * grav[2]);
  }
  movVar = 0;
  Serial.printf("Listo (%d muestras)\n", n);
}

void procesarIMU(float dt, uint32_t ahora) {
  float a[3], g[3];
  if (!leerMPU(a, g)) { mpuOk = false; movimiento = 0; return; }
  for (int i = 0; i < 3; i++) { g[i] -= bias[i]; grav[i] += 0.04f * (a[i] - grav[i]); }

  // Índice de movimiento: aceleración dinámica RMS en una ventana de ~2 s. Se resta el módulo en reposo
  // (promedio lento, ~10 s) y no 1 g exacto, porque el sensor tiene un desfase propio: con 1 g fijo el
  // clip quieto marcaba ~27 en vez de ~0.
  float mag = sqrtf(a[0] * a[0] + a[1] * a[1] + a[2] * a[2]);
  float beta = dt / 10.0f; if (beta > 1) beta = 1;
  magBase += beta * (mag - magBase);
  float din = mag - magBase;
  float alfa = dt / 2.0f; if (alfa > 1) alfa = 1;
  movVar += alfa * (din * din - movVar);
  float idx = sqrtf(movVar) / MOV_ESCALA_G * 100.0f;
  movimiento = (uint8_t)constrain(lroundf(idx), 0, 100);

  // Lo que sigue solo lo usa el panel de pruebas: rumbo relativo, inclinación y pasos
  float gn = sqrtf(grav[0] * grav[0] + grav[1] * grav[1] + grav[2] * grav[2]);
  if (gn < 0.3f) return;
  float u[3] = {grav[0] / gn, grav[1] / gn, grav[2] / gn};
  float giroVertical = g[0] * u[0] + g[1] * u[1] + g[2] * u[2];
  if (fabsf(giroVertical) > 0.8f) rumbo -= giroVertical * dt;
  while (rumbo < 0) rumbo += 360;
  while (rumbo >= 360) rumbo -= 360;
  pitch = atan2f(-u[0], sqrtf(u[1] * u[1] + u[2] * u[2])) * 57.2958f;
  roll = atan2f(u[1], u[2]) * 57.2958f;
  magF += 0.3f * (mag - magF);
  if (!arriba && magF > 1.12f && ahora - tPaso > 300) { arriba = true; pasos++; tPaso = ahora; }
  else if (arriba && magF < 1.02f) arriba = false;
}

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

// ───────── Exposición y estado ─────────
float factorCalor() {
  if (!ambienteOk) return FACTOR_CALOR[0];
  return FACTOR_CALOR[hgCategoria(heatIndex)];
}
float factorMovimiento() { return mpuOk ? 0.75f + 0.5f * movimiento / 100.0f : 1.0f; }

Estado calcularEstado(uint32_t ahora) {
  if (enPausa) return (ahora - tPausaInicio >= (uint32_t)minutosPausa * 60000UL) ? PAUSA_CUMPLIDA : EN_PAUSA;
  if (pausaSolicitada) return DESCANSO;
  if (exposicion >= umbralCansancio) return CANSANCIO;
  if (estado == CANSANCIO && exposicion > umbralCansancio - HISTERESIS_CANSANCIO) return CANSANCIO;
  return OPTIMO;
}

void solicitarPausa(bool automatica) {
  if (enPausa) return;
  pausaSolicitada = true; pausaAuto = automatica;
  Serial.printf("Pausa: toca descanso (%s, exposicion %.0f %%)\n", automatica ? "exposicion al 100" : "supervisor", exposicion);
}

void tareaExposicion(uint32_t ahora) {
  if (ahora - tExposicion < PERIODO_EXPOSICION_MS) return;
  float dtMin = (ahora - tExposicion) / 60000.0f;
  tExposicion = ahora;
  if (enPausa) exposicion -= 100.0f / minutosPausa * dtMin;
  else exposicion += 100.0f * factorCalor() * factorMovimiento() * factorPersonal / limiteExposicion * dtMin;
  if (exposicion < 0) exposicion = 0;
  if (exposicion > EXPOSICION_MAX) exposicion = EXPOSICION_MAX;

  if (pausaAutomatica && !enPausa && !pausaSolicitada && exposicion >= 100.0f) solicitarPausa(true);

  Estado nuevo = calcularEstado(ahora);
  if (nuevo != estado) {
    if (nuevo == DESCANSO) { vibrarDescanso(); tAviso = ahora; }
    if (nuevo == PAUSA_CUMPLIDA) { vibrarPausaCumplida(); tAviso = ahora; Serial.println("Pausa: tiempo cumplido"); }
    estado = nuevo;
  } else if ((estado == DESCANSO || estado == PAUSA_CUMPLIDA) && ahora - tAviso >= AVISO_CADA_MS) {
    tAviso = ahora;
    if (estado == DESCANSO) vibrarDescanso(); else vibrarPausaCumplida();
  }
}

// ───────── Pausa (solo con el botón) ─────────
void comenzarPausa(uint32_t ahora) {
  bool pedida = pausaSolicitada;
  pausaSolicitada = false; enPausa = true; tPausaInicio = ahora;
  vibrarPulsos(1, 600, 0, 255);
  estado = calcularEstado(ahora);
  Serial.printf("Pausa: comenzada con el boton (%s, exposicion %.0f %%)\n", pedida ? "solicitada" : "voluntaria", exposicion);
}

void terminarPausa(uint32_t ahora) {
  enPausa = false; tUltimaPausa = ahora;
  if (pausasHechas < 255) pausasHechas++;
  vibrarPulsos(2, 150, 150, 255);
  estado = calcularEstado(ahora);
  Serial.printf("Pausa: terminada con el boton (%lu min, exposicion %.0f %%)\n", (unsigned long)((ahora - tPausaInicio) / 60000), exposicion);
}

// ───────── Telemetría ─────────
void enviarTelemetria(uint32_t ahora) {
  Telemetria t;
  t.version = CONTRATO_VERSION;
  t.banderas = (ambienteOk ? F_AMBIENTE_OK : 0) | (mpuOk ? F_MOVIMIENTO_OK : 0) | (presionado ? F_BOTON : 0)
             | (pausaSolicitada && !pausaAuto ? F_PEDIDA_SUPERVISOR : 0);
  t.secuencia = secuencia++;
  t.temp100 = ambienteOk ? (int16_t)lroundf(tempC * 100) : 0;
  t.hum100 = ambienteOk ? (uint16_t)constrain(lroundf(humedad * 100), 0, 10000) : 0;
  t.hi100 = ambienteOk ? (int16_t)constrain(lroundf(heatIndex * 100), -32767, 32767) : INT16_MIN;
  t.movimiento = mpuOk ? movimiento : 0;
  t.bateriaPct = bateriaPorc;
  t.bateriaMv = (uint16_t)constrain(lroundf(bateriaV * 1000), 0, 65535);
  t.exposicion = (uint8_t)constrain(lroundf(exposicion), 0, 255);
  t.estado = estado;
  t.pausas = pausasHechas;
  t.rssi = conectado ? rssiEnlace : 0;
  uint32_t seg = (ahora - (enPausa ? tPausaInicio : tUltimaPausa)) / 1000;
  t.segEstado = seg > 65535 ? 65535 : (uint16_t)seg;
  cTele->setValue((uint8_t *)&t, sizeof t);
  if (conectado) cTele->notify();
}

void publicarAmbiente(bool ok, float t, float h, uint32_t ahora) {
  ambienteOk = ok;
  if (ok) { tempC = t; humedad = h; heatIndex = hgHeatIndexC(t, h); }
  bateriaV = leerBateria();
  bateriaPorc = bateriaPct(bateriaV);

  if (ok) {
    int16_t t100 = (int16_t)lroundf(t * 100);
    uint16_t h100 = (uint16_t)constrain(lroundf(h * 100), 0, 10000);
    cTemp->setValue((uint8_t *)&t100, 2);
    cHum->setValue((uint8_t *)&h100, 2);
    if (conectado) { cTemp->notify(); cHum->notify(); }
  }
  cBat->setValue(&bateriaPorc, 1);
  if (conectado) cBat->notify();
  enviarTelemetria(ahora);

  if (ok) Serial.printf("T %.1f C | HR %.0f %% | HI %.1f C (%s x%.1f)", tempC, humedad, heatIndex, hgCategoriaNombre(hgCategoria(heatIndex)), factorCalor());
  else Serial.print("sensor ambiental sin respuesta");
  if (mpuOk) Serial.printf(" | mov %u", movimiento); else Serial.print(" | MPU sin respuesta");
  Serial.printf(" | bat %.2f V %u %% | exposicion %.0f %% | %s", bateriaV, bateriaPorc, exposicion, NOMBRE_ESTADO[estado]);
  if (enPausa) Serial.printf(" %lu/%u min", (unsigned long)((ahora - tPausaInicio) / 60000), minutosPausa);
  Serial.printf(" | pausas %u", pausasHechas);
  if (conectado) {
    if (rssiEnlace) Serial.printf("  [BLE %d dBm]", rssiEnlace);
    else Serial.printf("  [BLE sin dato de senal, error %d]", rssiError);
  }
  Serial.println();
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
    publicarAmbiente(ok, t, h, ahora);
    return;
  }
  if (ahora - tEnv < PERIODO_ENV_MS) return;
  tEnv = ahora;
  if (tipoSensor == 0) detectarSensor();
  if (tipoSensor == 1) {
    Wire.beginTransmission(AHT); Wire.write(0xAC); Wire.write(0x33); Wire.write(0x00);
    if (Wire.endTransmission() == 0) { ahtMidiendo = true; tAhtTrig = ahora; }
    else { tipoSensor = 0; publicarAmbiente(false, 0, 0, ahora); }
  } else if (tipoSensor == 2) {
    uint16_t r; float t = 0, h = 0;
    bool ok = leerHTU(0xF3, r); t = -46.85 + 175.72 * r / 65536.0;
    ok = ok && leerHTU(0xF5, r); h = -6.0 + 125.0 * r / 65536.0;
    if (!ok) tipoSensor = 0;
    publicarAmbiente(ok, t, h, ahora);
  } else publicarAmbiente(false, 0, 0, ahora);
}

// ───────── Botón ─────────
void publicarBoton() {
  uint8_t d[4] = {(uint8_t)presionado, ultimoEvento, (uint8_t)(eventosBoton & 0xFF), (uint8_t)(eventosBoton >> 8)};
  cBtn->setValue(d, 4);
  if (conectado) cBtn->notify();
}

// Hay que MANTENERLO 2 s para que no se active por accidente: en pausa la termina; si no, la comienza
// (pedida por el clip o el supervisor, o voluntaria). Una pulsación corta no hace nada.
void tareaBoton(uint32_t ahora) {
  bool p = digitalRead(BOTON) == LOW;
  if (p != presionado && ahora - tCambio > 30) {          // antirrebote de 30 ms
    tCambio = ahora;
    presionado = p;
    if (p) { tPresion = ahora; largoAvisado = false; vibrarPulsos(1, 60, 0, 200); }
    else if (!largoAvisado) { ultimoEvento = 1; eventosBoton++; }
    publicarBoton();
  }
  if (presionado && !largoAvisado && ahora - tPresion >= MANTENER_MS) {
    largoAvisado = true;
    eventosBoton++;
    if (enPausa) { ultimoEvento = 4; terminarPausa(ahora); }
    else { ultimoEvento = 3; comenzarPausa(ahora); }
    publicarBoton();
    enviarTelemetria(ahora);                               // que el panel lo vea de inmediato
  }
}

// ───────── Configuración guardada (memoria no volátil) ─────────
void guardarConfig() {
  prefs.putUChar("limite", limiteExposicion);
  prefs.putUChar("cansancio", umbralCansancio);
  prefs.putUChar("pausa", minutosPausa);
  prefs.putBool("auto", pausaAutomatica);
  prefs.putFloat("personal", factorPersonal);
}

void cargarConfig() {
  prefs.begin("heatguard", false);
  limiteExposicion = prefs.getUChar("limite", limiteExposicion);
  umbralCansancio = prefs.getUChar("cansancio", umbralCansancio);
  minutosPausa = prefs.getUChar("pausa", minutosPausa);
  pausaAutomatica = prefs.getBool("auto", pausaAutomatica);
  factorPersonal = prefs.getFloat("personal", factorPersonal);
  Serial.printf("Config: limite %u min-eq, cansancio %u %%, pausa %u min, automatica %s, factor personal x%.2f\n",
                limiteExposicion, umbralCansancio, minutosPausa, pausaAutomatica ? "si" : "no", factorPersonal);
}

// ───────── Comandos del panel ─────────
void atenderComando(uint32_t ahora) {
  uint8_t cmd = cmdPendiente, arg = cmdArg;
  if (!cmd) return;
  cmdPendiente = 0;
  switch (cmd) {
    case CMD_SOLICITAR_PAUSA:
      if (!enPausa && !pausaSolicitada) solicitarPausa(false);
      else if (pausaSolicitada) pausaAuto = false;
      break;
    case CMD_RETIRAR_PAUSA:
      if (pausaSolicitada && !pausaAuto) { pausaSolicitada = false; Serial.println("Panel: solicitud de pausa retirada"); }
      break;
    case CMD_MINUTOS_PAUSA:    minutosPausa = constrain(arg, 5, 60); break;
    case CMD_LIMITE_EXPOSICION:     limiteExposicion = constrain(arg, 30, 250); break;
    case CMD_UMBRAL_CANSANCIO: umbralCansancio = constrain(arg, 30, 95); break;
    case CMD_PAUSA_AUTOMATICA: pausaAutomatica = arg != 0; break;
    case CMD_FACTOR_PERSONAL:  factorPersonal = constrain(arg, 50, 200) / 100.0f; break;
    case CMD_UBICAR:
      vibrarPulsos(3, 150, 150, 255);
      destello(255, 255, 255, 300, 2400);
      break;
    default:
      Serial.printf("Panel: comando desconocido %u\n", cmd);
  }
  if (cmd == CMD_MINUTOS_PAUSA || cmd == CMD_LIMITE_EXPOSICION || cmd == CMD_UMBRAL_CANSANCIO || cmd == CMD_PAUSA_AUTOMATICA || cmd == CMD_FACTOR_PERSONAL) {
    guardarConfig();
    Serial.printf("Panel: limite %u min-eq, cansancio %u %%, pausa %u min, automatica %s, factor personal x%.2f\n",
                  limiteExposicion, umbralCansancio, minutosPausa, pausaAutomatica ? "si" : "no", factorPersonal);
  }
  estado = calcularEstado(ahora);
  enviarTelemetria(ahora);
}

// ───────── Callbacks BLE ─────────
// ───────── Intensidad de la señal (RSSI) ─────────
// La mide el clip sobre el enlace con el panel, porque el navegador no puede leerla de un dispositivo
// ya conectado. Funciona con la pila Bluetooth Bluedroid o NimBLE (según la versión del soporte de ESP32).
#if defined(CONFIG_BLUEDROID_ENABLED)
void manejadorGap(esp_gap_ble_cb_event_t evento, esp_ble_gap_cb_param_t *param) {
  if (evento == ESP_GAP_BLE_READ_RSSI_COMPLETE_EVT && param->read_rssi_cmpl.status == ESP_BT_STATUS_SUCCESS)
    rssiEnlace = param->read_rssi_cmpl.rssi;
}
#endif

void tareaRssi(uint32_t ahora) {
  if (!conectado || ahora - tRssi < 2000) return;
  tRssi = ahora;
#if defined(CONFIG_BLUEDROID_ENABLED)
  if (hayDireccion) rssiError = esp_ble_gap_read_rssi(direccionPanel);   // el valor llega en manejadorGap
  else rssiError = -1;
#elif defined(CONFIG_NIMBLE_ENABLED)
  int8_t r = 0;
  rssiError = ble_gap_conn_rssi(servidor->getConnId(), &r);
  if (rssiError == 0) rssiEnlace = r;
#else
  rssiError = -2;
#endif
}

class Callbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *) override { conectado = true; tRssi = 0; Serial.println("BLE: conectado"); }
#if defined(CONFIG_BLUEDROID_ENABLED)
  void onConnect(BLEServer *, esp_ble_gatts_cb_param_t *param) override {
    memcpy(direccionPanel, param->connect.remote_bda, sizeof(esp_bd_addr_t));
    hayDireccion = true;
    Serial.println("BLE: direccion del panel registrada");
  }
#endif
  void onDisconnect(BLEServer *s) override {
    conectado = false;
    rssiEnlace = 0;
#if defined(CONFIG_BLUEDROID_ENABLED)
    hayDireccion = false;
#endif
    Serial.println("BLE: desconectado, vuelvo a anunciarme");
    delay(200);
    s->startAdvertising();
  }
};

class CmdCallbacks : public BLECharacteristicCallbacks {
  void onWrite(BLECharacteristic *c) override {
    uint8_t *d = c->getData();
    size_t n = c->getLength();
    if (n >= 1) { cmdArg = n >= 2 ? d[1] : 0; cmdPendiente = d[0]; }
  }
};

class LedCallbacks : public BLECharacteristicCallbacks {   // panel de pruebas
  void onWrite(BLECharacteristic *c) override {
    uint8_t *d = c->getData();
    if (c->getLength() >= 3) { pruebaHasta = millis() + PRUEBA_MS; ponerColor(d[0], d[1], d[2]); }
  }
};

class MotorCallbacks : public BLECharacteristicCallbacks { // panel de pruebas
  void onWrite(BLECharacteristic *c) override {
    uint8_t *d = c->getData();
    size_t n = c->getLength();
    if (n >= 1) {
      uint32_t ms = (n >= 2) ? d[1] * 100UL : 0;
      vibPulsos = 0;
      analogWrite(MOTOR, d[0]);
      motorHasta = (d[0] && ms) ? millis() + ms : 0;
    }
  }
};

BLECharacteristic *crear(BLEService *s, BLEUUID uuid) {
  BLECharacteristic *c = s->createCharacteristic(uuid, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY);
#if ESP_ARDUINO_VERSION < ESP_ARDUINO_VERSION_VAL(3, 3, 0)
  c->addDescriptor(new BLE2902());
#endif
  return c;
}

// ───────── Arranque ─────────
void setup() {
  Serial.begin(115200);
  cargarConfig();
  pinMode(MOTOR, OUTPUT); digitalWrite(MOTOR, LOW);
  pinMode(BOTON, INPUT_PULLUP);

  // Autoprueba: LED de estado (rojo, verde, azul), nivel de batería y una vibración corta
  ponerColor(255, 0, 0); delay(300);
  ponerColor(0, 255, 0); delay(300);
  ponerColor(0, 0, 255); delay(300);
  ponerColor(0, 0, 0);
  indicarBateria();
  analogWrite(MOTOR, 255); delay(250); analogWrite(MOTOR, 0);

  Wire.begin(SDA_PIN, SCL_PIN);
  Wire.setClock(100000);
  mpuOk = iniciarMPU();
  if (mpuOk) calibrarGiro(); else Serial.println("MPU6050 no encontrado");
  detectarSensor();
  if (!tipoSensor) Serial.println("Sensor de temperatura y humedad no encontrado");

  BLEDevice::init("HeatGuard Clip");
#if defined(CONFIG_BLUEDROID_ENABLED)
  BLEDevice::setCustomGapHandler(manejadorGap);
#endif
  servidor = BLEDevice::createServer();
  servidor->setCallbacks(new Callbacks());

  BLEService *clip = servidor->createService(BLEUUID(UUID_CLIP_SERV));
  cTele = crear(clip, BLEUUID(UUID_TELE_CHAR));
  cCmd = clip->createCharacteristic(BLEUUID(UUID_CMD_CHAR), BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  cCmd->setCallbacks(new CmdCallbacks());
  clip->start();

  BLEService *amb = servidor->createService(BLEUUID((uint16_t)0x181A));   // Environmental Sensing
  cTemp = crear(amb, BLEUUID((uint16_t)0x2A6E));
  cHum = crear(amb, BLEUUID((uint16_t)0x2A6F));
  amb->start();

  BLEService *bat = servidor->createService(BLEUUID((uint16_t)0x180F));   // Battery
  cBat = crear(bat, BLEUUID((uint16_t)0x2A19));
  bat->start();

  BLEService *mov = servidor->createService(BLEUUID(UUID_MOV_SERV));               // panel de pruebas
  cPaq = crear(mov, BLEUUID(UUID_PAQ_CHAR));
  cLed = mov->createCharacteristic(BLEUUID(UUID_LED_CHAR), BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  cLed->setCallbacks(new LedCallbacks());
  cMot = mov->createCharacteristic(BLEUUID(UUID_MOT_CHAR), BLECharacteristic::PROPERTY_WRITE | BLECharacteristic::PROPERTY_WRITE_NR);
  cMot->setCallbacks(new MotorCallbacks());
  cBtn = crear(mov, BLEUUID(UUID_BTN_CHAR));
  mov->start();

  BLEAdvertising *adv = BLEDevice::getAdvertising();
  adv->addServiceUUID(BLEUUID(UUID_CLIP_SERV));
  adv->setScanResponse(true);
  BLEDevice::startAdvertising();
  Serial.printf("BLE: anunciandome como \"HeatGuard Clip\" (contrato de datos v%u)\n", CONTRATO_VERSION);
#if defined(CONFIG_BLUEDROID_ENABLED)
  Serial.println("BLE: pila Bluedroid");
#elif defined(CONFIG_NIMBLE_ENABLED)
  Serial.println("BLE: pila NimBLE");
#else
  Serial.println("BLE: pila desconocida (sin lectura de senal)");
#endif

  uint32_t ahora = millis();
  tImu = tExposicion = tUltimaPausa = ahora;
}

void loop() {
  uint32_t ahora = millis();
  tareaBoton(ahora);
  atenderComando(ahora);
  tareaVibracion(ahora);

  if (ahora - tImu >= PERIODO_IMU_MS) {
    float dt = (ahora - tImu) / 1000.0f;
    tImu = ahora;
    if (mpuOk) procesarIMU(dt, ahora);
    else if (ahora % 5000 < PERIODO_IMU_MS && iniciarMPU()) { mpuOk = true; calibrarGiro(); }   // reintento cada 5 s
  }

  if (ahora - tPrueba >= PERIODO_PRUEBA_MS) {              // paquete para el panel de pruebas
    tPrueba = ahora;
    PaquetePrueba p;
    p.pasos = pasos;
    p.rumbo10 = (int16_t)lroundf(rumbo * 10) % 3600;
    p.pitch10 = (int16_t)lroundf(pitch * 10);
    p.roll10 = (int16_t)lroundf(roll * 10);
    p.mag1000 = (uint16_t)constrain(lroundf(magF * 1000), 0, 65535);
    cPaq->setValue((uint8_t *)&p, sizeof p);
    if (conectado) cPaq->notify();
  }

  tareaAmbiente(ahora);
  tareaExposicion(ahora);
  tareaRssi(ahora);
  tareaLed(ahora);
  delay(2);
}
