#!/usr/bin/env bash
# Sube el dashboard y el servidor a rorro-server y lo deja corriendo y expuesto con Tailscale Funnel.
# Se ejecuta desde tu PC, en la carpeta del repo:   bash deploy/subir_servidor.sh [host-ssh]
# Requiere: ssh a rorro-server (por Tailscale) y Node 20+ en tu PC para compilar.
set -euo pipefail
HOST="${1:-rorro-server}"
cd "$(dirname "$0")/.."

if [ ! -f deploy/credenciales.env ]; then
  echo "Falta deploy/credenciales.env (contraseñas iniciales). Créalo con:"
  echo "  HG_SUPERVISOR_PASS=...   y   HG_TRABAJADOR_PASS=..."
  exit 1
fi

echo "== 1/3 Compilando el dashboard"
[ -d node_modules ] || npm ci
npm run build

echo "== 2/3 Copiando a $HOST:~/heatguard"
tar czf - --exclude='__pycache__' dist server/index.js server/usuarios.js src/lib src/data deploy/instalar_en_servidor.sh deploy/credenciales.env package.json \
    motor_termico_python/heatguard motor_termico_python/integracion \
  | ssh "$HOST" 'mkdir -p ~/heatguard && rm -rf ~/heatguard/dist && tar xzf - -C ~/heatguard'

echo "== 3/3 Instalando el servicio en $HOST (puede pedir tu contraseña de sudo)"
ssh -t "$HOST" 'bash ~/heatguard/deploy/instalar_en_servidor.sh'
