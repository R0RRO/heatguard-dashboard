#!/usr/bin/env bash
# Lee durante 15 s lo que la XIAO envía por USB y lo guarda en xiao_serial.txt (solo lectura).
cd "$(dirname "$0")"
OUT=xiao_serial.txt
PORT=$(ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | head -n 1)
{
  echo "fecha: $(date)"
  echo "puertos: $(ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null | tr '\n' ' ')"
  if [ -z "$PORT" ]; then
    echo "ERROR: no hay ningun puerto serie. Revisa el cable USB (que sea de datos) y la XIAO."
    lsusb 2>/dev/null
  elif [ ! -r "$PORT" ]; then
    echo "ERROR: sin permiso para leer $PORT ($(ls -l "$PORT"))."
    echo "Solucion: sudo usermod -aG dialout \$USER  (y reiniciar sesion), o ejecutar: sudo ./leer_xiao.sh"
  else
    echo "puerto: $PORT"
    stty -F "$PORT" 115200 raw -echo -hupcl 2>&1
    echo "----- datos (15 s) -----"
    timeout 15 cat "$PORT" 2>&1
    echo
    echo "----- fin -----"
  fi
} > "$OUT" 2>&1
cat "$OUT"
