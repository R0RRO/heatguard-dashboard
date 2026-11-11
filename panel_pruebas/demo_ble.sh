#!/usr/bin/env bash
# Abre la mini app de demostración (demo_ble/index.html) en http://localhost:8765
# Bluetooth web solo funciona en Chrome, Chromium o Edge, y desde localhost o https.
cd "$(dirname "$0")/demo_ble"
PORT=8765
URL="http://localhost:$PORT"
echo "Demo HeatGuard en $URL  (Ctrl+C para cerrar)"
(
  sleep 1
  for b in google-chrome google-chrome-stable chromium chromium-browser microsoft-edge brave-browser; do
    if command -v "$b" >/dev/null; then exec "$b" "$URL" >/dev/null 2>&1; fi
  done
  xdg-open "$URL" >/dev/null 2>&1 || echo "Abre $URL en Chrome"
) &
# Servidor local sin caché, para que el navegador siempre cargue la versión más nueva de la app
python3 -c '
import http.server, sys
class H(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
http.server.ThreadingHTTPServer(("127.0.0.1", int(sys.argv[1])), H).serve_forever()
' "$PORT"
