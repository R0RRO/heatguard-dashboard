#!/usr/bin/env bash
# Compila y sube un programa a la XIAO ESP32-C3 sin Arduino IDE (usa arduino-cli).
# Uso: ./subir_xiao.sh [carpeta_del_programa]   (por defecto: firmware/bateria_test)
set -e
cd "$(dirname "$0")"
SKETCH="${1:-firmware/bateria_test}"
FQBN="esp32:esp32:XIAO_ESP32C3"
URL="https://espressif.github.io/arduino-esp32/package_esp32_index.json"
export PATH="$HOME/.local/bin:$PATH"

if ! command -v arduino-cli >/dev/null; then
  echo ">> Instalando arduino-cli en ~/.local/bin ..."
  mkdir -p "$HOME/.local/bin"
  curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR="$HOME/.local/bin" sh
fi

if ! arduino-cli core list | grep -q "^esp32:esp32"; then
  echo ">> Instalando el soporte para ESP32 (descarga grande, solo la primera vez) ..."
  arduino-cli core update-index --additional-urls "$URL"
  arduino-cli core install esp32:esp32 --additional-urls "$URL"
fi

PORT=$(ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -n 1)
if [ -z "$PORT" ]; then echo "ERROR: no encuentro la XIAO por USB."; exit 1; fi

echo ">> Compilando $SKETCH ..."
arduino-cli compile --fqbn "$FQBN" "$SKETCH"
echo ">> Subiendo a $PORT ..."
arduino-cli upload --fqbn "$FQBN" -p "$PORT" "$SKETCH"
echo ">> Listo. Leyendo la XIAO ..."
sleep 3
./leer_xiao.sh
