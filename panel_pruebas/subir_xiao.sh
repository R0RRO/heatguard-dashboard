#!/usr/bin/env bash
# Compila y sube un programa a la XIAO ESP32-C3 sin Arduino IDE (usa arduino-cli).
# Uso: ./subir_xiao.sh [carpeta_del_programa]
#   Sin argumento sube el firmware del clip (firmware/heatguard_clip, en la raíz del repositorio).
#   La carpeta puede darse relativa a donde estás parado o relativa a panel_pruebas/.
set -e
AQUI="$(cd "$(dirname "$0")" && pwd)"
SKETCH="${1:-$AQUI/../firmware/heatguard_clip}"
if [ -d "$SKETCH" ]; then SKETCH="$(cd "$SKETCH" && pwd)"; else SKETCH="$AQUI/$SKETCH"; fi
if [ ! -d "$SKETCH" ]; then echo "ERROR: no existe la carpeta $SKETCH"; exit 1; fi
cd "$AQUI"
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
