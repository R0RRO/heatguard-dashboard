// Diagnóstico del bus I2C sin multímetro: revisa el estado eléctrico de SDA (D4) y SCL (D8)
// y luego busca dispositivos. Se repite cada 2 segundos.
#include <Wire.h>
// SCL movido de D5 a D8: el pin D5 de esta placa quedó en corto con GND (no usarlo).
const int SCL_PIN = D8;

const char *estado(int pin) {
  pinMode(pin, INPUT);              // sin pull-up interno: solo cuentan las resistencias de los módulos
  delay(5);
  int sinPull = digitalRead(pin);
  pinMode(pin, INPUT_PULLUP);       // con pull-up interno: si igual lee 0, la línea está a GND
  delay(5);
  int conPull = digitalRead(pin);
  pinMode(pin, INPUT);
  if (sinPull) return "OK (en alto, los modulos tienen alimentacion)";
  if (conPull) return "SIN PULL-UP (ningun modulo alimentado en esta linea, o cable cortado)";
  return "EN CORTO A GND (algo une esta linea con GND)";
}

// ¿El pin es capaz de bajar la línea a 0 V? (es lo que hace la XIAO para hablar por I2C)
const char *salida(int pin) {
  pinMode(pin, OUTPUT_OPEN_DRAIN);
  digitalWrite(pin, LOW);
  delay(5);
  int bajo = digitalRead(pin);
  digitalWrite(pin, HIGH);
  delay(5);
  int suelto = digitalRead(pin);
  pinMode(pin, INPUT);
  if (!bajo && suelto) return "OK (baja y sube la linea)";
  if (bajo) return "FALLA: no logra bajar la linea (pin danado o algo la fuerza a 3,3 V)";
  return "FALLA: la linea no vuelve a subir";
}

// ¿Están unidas dos líneas que deberían ir separadas? Baja una y mira si la otra la sigue.
bool unidos(int a, int b) {
  pinMode(b, INPUT);
  pinMode(a, OUTPUT_OPEN_DRAIN);
  digitalWrite(a, LOW);
  delay(5);
  int lb = digitalRead(b);
  digitalWrite(a, HIGH);
  pinMode(a, INPUT);
  delay(5);
  return lb == 0 && digitalRead(b) == 1;
}

int escanear(int sda, int scl, const char *titulo) {
  Wire.begin(sda, scl);
  Wire.setClock(100000);
  Wire.setTimeOut(20);
  Serial.print(titulo);
  int n = 0;
  for (uint8_t a = 1; a < 127; a++) {
    Wire.beginTransmission(a);
    if (Wire.endTransmission() == 0) {
      n++;
      Serial.printf(" 0x%02X", a);
      if (a == 0x38) Serial.print("(AHT10)");
      if (a == 0x40) Serial.print("(HTU21D)");
      if (a == 0x68 || a == 0x69) Serial.print("(MPU6050)");
    }
  }
  Serial.println(n ? "" : " nada");
  Wire.end();
  delay(20);
  return n;
}

void setup() { Serial.begin(115200); }

void loop() {
  Serial.println("------------------------------");
  Serial.printf("SDA (D4): %s\n", estado(D4));
  Serial.printf("SCL (D8): %s\n", estado(SCL_PIN));
  Serial.printf("Salida D4: %s\n", salida(D4));
  Serial.printf("Salida D8: %s\n", salida(SCL_PIN));
  Serial.printf("D4 y D8 unidos entre si: %s\n", unidos(D4, SCL_PIN) ? "SI (error: SDA y SCL estan juntos)" : "no (bien)");
  pinMode(D5, INPUT_PULLUP); delay(5);
  Serial.printf("D5 (no usado): %s\n", digitalRead(D5) ? "libre, ya no esta en corto" : "sigue en corto a GND");
  pinMode(D5, INPUT);

  int n1 = escanear(D4, SCL_PIN, "I2C normal  (SDA=D4, SCL=D8):");
  int n2 = escanear(SCL_PIN, D4, "I2C cruzado (SDA=D8, SCL=D4):");
  if (!n1 && n2) Serial.println(">> Los cables SDA y SCL estan cruzados: intercambialos (o avisame y cambio el programa).");
  if (!n1 && !n2) Serial.println(">> Ningun dispositivo responde en ninguna orientacion.");
  delay(3000);
}
