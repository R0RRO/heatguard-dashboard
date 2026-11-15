package cl.heatguard.clip;

import org.json.JSONException;
import org.json.JSONObject;

import java.util.UUID;

/** Contrato de datos v2 del clip (mismo formato que src/lib/telemetry.js y docs/contrato-datos.md). */
final class Telemetry {
    static final String NAME = "HeatGuard Clip";
    static final UUID SERVICE = UUID.fromString("7a1e0100-4865-6174-4775-617264436c70");
    static final UUID TELEMETRY = UUID.fromString("7a1e0101-4865-6174-4775-617264436c70");
    static final UUID COMMAND = UUID.fromString("7a1e0102-4865-6174-4775-617264436c70");
    static final UUID CCCD = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb");

    static final int VERSION = 2;
    static final int CMD_PAUSE_REQUEST = 2, CMD_PAUSE_MINUTES = 4, CMD_IDENTIFY = 5, CMD_CANCEL_PAUSE = 6,
            CMD_LOAD_LIMIT = 7, CMD_TIRED_PCT = 8, CMD_AUTO_PAUSE = 9, CMD_PERSONAL = 10;

    static final String[] STATE_LABEL = {"Óptimo", "Cansancio", "Toca descanso", "En pausa", "Pausa cumplida"};
    static final int[] STATE_COLOR = {0xFF16A34A, 0xFFCA8A04, 0xFFDC2626, 0xFF2563EB, 0xFF1D4ED8};
    static final String[] STATE_LED = {"verde parpadeante", "amarillo", "rojo + vibración", "azul fijo", "azul parpadeante + vibración"};

    private Telemetry() {}

    private static int u8(byte[] b, int i) { return b[i] & 0xff; }
    private static int u16(byte[] b, int i) { return (b[i] & 0xff) | ((b[i + 1] & 0xff) << 8); }
    private static int i16(byte[] b, int i) { return (short) u16(b, i); }

    /** Decodifica un paquete de 20 bytes. Devuelve null si no corresponde al contrato. */
    static JSONObject decode(byte[] b, String deviceId) {
        if (b == null || b.length < 20 || u8(b, 0) != VERSION) return null;
        try {
            int flags = u8(b, 1);
            boolean envOk = (flags & 1) != 0;
            int hiRaw = i16(b, 8);
            JSONObject env = new JSONObject()
                    .put("ok", envOk)
                    .put("tempC", envOk ? i16(b, 4) / 100.0 : JSONObject.NULL)
                    .put("rhPct", envOk ? u16(b, 6) / 100.0 : JSONObject.NULL)
                    .put("heatIndexC", envOk && hiRaw != -32768 ? hiRaw / 100.0 : JSONObject.NULL);
            int rssi = b[17];
            JSONObject m = new JSONObject()
                    .put("v", VERSION)
                    .put("deviceId", deviceId)
                    .put("receivedAt", System.currentTimeMillis())
                    .put("seq", u16(b, 2))
                    .put("env", env)
                    .put("motion", new JSONObject().put("ok", (flags & 2) != 0).put("index", u8(b, 10)))
                    .put("battery", new JSONObject().put("pct", u8(b, 11)).put("mV", u16(b, 12)))
                    .put("load", u8(b, 14))
                    .put("state", u8(b, 15))
                    .put("pauses", u8(b, 16))
                    .put("stateS", u16(b, 18))
                    .put("rssi", rssi == 0 ? JSONObject.NULL : rssi)
                    .put("button", new JSONObject().put("pressed", (flags & 4) != 0))
                    .put("requestBySupervisor", (flags & 8) != 0);
            // mismos rangos que valida el panel
            if (u8(b, 15) > 4 || u8(b, 11) > 100 || u8(b, 10) > 100) return null;
            if (envOk && (i16(b, 4) < -2000 || i16(b, 4) > 7000 || u16(b, 6) > 10000)) return null;
            return m;
        } catch (JSONException e) {
            return null;
        }
    }

    /** Movimiento 0–100 → Bajo / Medio / Alto (mismo corte que el panel web). */
    static String movLevel(int index) { return index < 34 ? "Bajo" : index < 67 ? "Medio" : "Alto"; }

    /** Señal Bluetooth en dBm → Alta / Media / Baja. */
    static String signalLevel(int dbm) { return dbm >= -67 ? "Alta" : dbm >= -80 ? "Media" : "Baja"; }

    static byte[] command(int cmd, int arg) { return new byte[]{(byte) cmd, (byte) arg}; }

    /** Factor personal por IMC (regla del prototipo, sin validar; igual que src/lib/risk.js), en centésimas. */
    static int personalFactor100(double heightCm, double weightKg) {
        if (!(heightCm >= 120 && heightCm <= 230 && weightKg >= 35 && weightKg <= 250)) return 100;
        double bmi = weightKg / Math.pow(heightCm / 100.0, 2);
        return bmi < 25 ? 100 : bmi < 30 ? 110 : 120;
    }
}
