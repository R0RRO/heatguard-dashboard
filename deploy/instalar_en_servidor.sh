#!/usr/bin/env bash
# Corre en rorro-server (lo llama subir_servidor.sh). Instala Node si falta, crea los usuarios la primera vez,
# deja el servidor como servicio de systemd en 127.0.0.1:8787 y lo publica con Tailscale Funnel (https).
set -euo pipefail
DIR="$HOME/heatguard"
PORT=8787
cd "$DIR"

ver=$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)
if [ "$ver" -lt 20 ]; then
  echo "Node 20+ no está instalado (versión actual: $ver). Instalándolo…"
  if command -v dnf >/dev/null; then
    sudo dnf install -y nodejs            # Fedora trae Node 20 o 22 en sus repositorios
  elif command -v apt-get >/dev/null; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
    sudo apt-get install -y nodejs
  else
    echo "Instala Node 20+ a mano y vuelve a correr el script."; exit 1
  fi
  ver=$(node -p 'process.versions.node.split(".")[0]')
  [ "$ver" -ge 20 ] || { echo "Quedó Node $ver; se necesita 20 o más."; exit 1; }
fi
NODE=$(command -v node)
# Si Node está dentro de la carpeta personal (nvm), SELinux no deja que systemd lo ejecute:
# se copia el binario a /usr/local/bin con la etiqueta del sistema.
case "$NODE" in
  "$HOME"/*)
    sudo install -m 755 "$NODE" /usr/local/bin/node-heatguard
    command -v restorecon >/dev/null && sudo restorecon /usr/local/bin/node-heatguard
    NODE=/usr/local/bin/node-heatguard ;;
esac

# Usuarios iniciales (solo si no existen) y luego se borran las contraseñas en texto plano del servidor
set -a; . deploy/credenciales.env; set +a
node server/usuarios.js inicial
rm -f deploy/credenciales.env

# Motor WBGT (Python, motor_termico_python): servicio local con clave compartida con Node
command -v python3 >/dev/null || { echo "Instalando python3…"; if command -v dnf >/dev/null; then sudo dnf install -y python3; else sudo apt-get install -y python3; fi; }
PYTHON=$(command -v python3)
# La clave va en /etc: con SELinux (Fedora), systemd no puede leer archivos de configuración en la carpeta personal
ENVF=/etc/heatguard/wbgt.env
sudo install -d -m 755 /etc/heatguard
if ! sudo test -f "$ENVF"; then
  if [ -f server/data/wbgt.env ]; then sudo cp server/data/wbgt.env "$ENVF"; rm -f server/data/wbgt.env
  else echo "HG_WBGT_KEY=$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')" | sudo tee "$ENVF" >/dev/null; fi
fi
sudo chmod 600 "$ENVF"
command -v restorecon >/dev/null && sudo restorecon -R /etc/heatguard
sudo tee /etc/systemd/system/heatguard-wbgt.service >/dev/null <<UNIT
[Unit]
Description=HeatGuard motor WBGT (Python)
After=network-online.target
Wants=network-online.target

[Service]
User=$(id -un)
WorkingDirectory=$DIR/motor_termico_python
EnvironmentFile=/etc/heatguard/wbgt.env
Environment=HG_WBGT_PORT=8790
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=$PYTHON -m integracion.servicio_wbgt
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT

sudo tee /etc/systemd/system/heatguard.service >/dev/null <<UNIT
[Unit]
Description=HeatGuard Clip (dashboard y servidor)
After=network-online.target
Wants=network-online.target

[Service]
User=$(id -un)
WorkingDirectory=$DIR
Environment=PORT=$PORT
Environment=HOST=127.0.0.1
EnvironmentFile=/etc/heatguard/wbgt.env
Environment=HG_WBGT_URL=http://127.0.0.1:8790
ExecStart=$NODE server/index.js
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable heatguard heatguard-wbgt >/dev/null 2>&1
sudo systemctl restart heatguard-wbgt heatguard || true
sleep 3
if curl -fsS -o /dev/null http://127.0.0.1:8790/health; then echo "Motor WBGT corriendo en 127.0.0.1:8790"; else
  echo "El motor WBGT no responde (el panel usará la sensación térmica):"; sudo journalctl -u heatguard-wbgt -n 15 --no-pager; fi
if curl -fsS -o /dev/null "http://127.0.0.1:$PORT/"; then echo "Servicio heatguard corriendo en 127.0.0.1:$PORT"; else
  echo "El servicio no responde:"; sudo journalctl -u heatguard -n 20 --no-pager; exit 1; fi

# Exposición pública con https (Funnel tiene que estar habilitado para tu tailnet; si no, tailscale te da el enlace para activarlo)
sudo tailscale funnel --bg "$PORT"
NOMBRE=$(tailscale status --json | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>console.log(JSON.parse(s).Self.DNSName.replace(/\.$/,"")))')
echo
echo "Listo: https://$NOMBRE"
echo "Logs: journalctl -u heatguard -f"
