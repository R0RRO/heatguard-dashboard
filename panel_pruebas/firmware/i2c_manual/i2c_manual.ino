// I2C "a mano" (sin la librería Wire), muy lento (~5 kHz), para descartar un problema de software
// o de cables largos. Busca dispositivos con SDA=D4/SCL=D8 y con los pines cruzados.
const int T = 100;   // medio periodo en microsegundos

int SDA_P, SCL_P;

void suelta(int p) { digitalWrite(p, HIGH); }   // open-drain: HIGH = soltar la línea
void baja(int p) { digitalWrite(p, LOW); }

bool esperaSCL() {                               // por si el dispositivo estira el reloj
  uint32_t t0 = micros();
  while (!digitalRead(SCL_P)) if (micros() - t0 > 2000) return false;
  return true;
}

void inicio() {
  suelta(SDA_P); suelta(SCL_P); delayMicroseconds(T);
  baja(SDA_P); delayMicroseconds(T);
  baja(SCL_P); delayMicroseconds(T);
}

void fin() {
  baja(SDA_P); delayMicroseconds(T);
  suelta(SCL_P); esperaSCL(); delayMicroseconds(T);
  suelta(SDA_P); delayMicroseconds(T);
}

bool escribir(uint8_t b) {                       // devuelve true si el dispositivo responde (ACK)
  for (int i = 7; i >= 0; i--) {
    if (b & (1 << i)) suelta(SDA_P); else baja(SDA_P);
    delayMicroseconds(T);
    suelta(SCL_P); esperaSCL(); delayMicroseconds(T);
    baja(SCL_P);
  }
  suelta(SDA_P); delayMicroseconds(T);
  suelta(SCL_P); esperaSCL(); delayMicroseconds(T / 2);
  bool ack = digitalRead(SDA_P) == 0;
  delayMicroseconds(T / 2);
  baja(SCL_P); delayMicroseconds(T);
  return ack;
}

void liberarBus() {                              // 9 pulsos de reloj por si algo quedó trabado
  suelta(SDA_P);
  for (int i = 0; i < 9; i++) { baja(SCL_P); delayMicroseconds(T); suelta(SCL_P); delayMicroseconds(T); }
  fin();
}

void probar(int sda, int scl, const char *titulo) {
  SDA_P = sda; SCL_P = scl;
  pinMode(SDA_P, OUTPUT_OPEN_DRAIN); pinMode(SCL_P, OUTPUT_OPEN_DRAIN);
  liberarBus();
  Serial.printf("%s (lineas en reposo: SDA %s, SCL %s):", titulo,
                digitalRead(SDA_P) ? "alto" : "BAJO", digitalRead(SCL_P) ? "alto" : "BAJO");
  int n = 0;
  for (uint8_t a = 1; a < 127; a++) {
    inicio();
    bool ack = escribir(a << 1);
    fin();
    if (ack) {
      n++;
      Serial.printf(" 0x%02X", a);
      if (a == 0x38) Serial.print("(AHT10)");
      if (a == 0x40) Serial.print("(HTU21D)");
      if (a == 0x68 || a == 0x69) Serial.print("(MPU6050)");
    }
  }
  if (!n) Serial.print(" nada");
  if (n > 100) Serial.print("  <- responde a todo: SDA esta pegado a GND");
  Serial.println();
  pinMode(SDA_P, INPUT); pinMode(SCL_P, INPUT);
}

void setup() { Serial.begin(115200); }

void loop() {
  Serial.println("------------------------------");
  probar(D4, D8, "Normal ");
  probar(D8, D4, "Cruzado");
  delay(1500);
}
