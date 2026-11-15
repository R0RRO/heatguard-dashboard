package cl.heatguard.clip;

import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** Llamadas al servidor HeatGuard (server/index.js). Siempre fuera del hilo principal. */
final class Api {
    static final String DEFAULT_SERVER = "https://fedora.tail18b1ba.ts.net";

    static final class Result {
        final int code; final JSONObject body;
        Result(int code, JSONObject body) { this.code = code; this.body = body; }
        boolean ok() { return code >= 200 && code < 300; }
        String error() { return body != null ? body.optString("error", "Error " + code) : (code == 0 ? "Sin conexión con el servidor" : "Error " + code); }
    }

    private Api() {}

    static Result request(String base, String method, String path, String token, JSONObject body) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(base + path).openConnection();
            c.setRequestMethod(method);
            c.setConnectTimeout(10000);
            c.setReadTimeout(15000);
            if (token != null) c.setRequestProperty("Authorization", "Bearer " + token);
            if (body != null) {
                byte[] data = body.toString().getBytes(StandardCharsets.UTF_8);
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/json");
                c.setFixedLengthStreamingMode(data.length);
                try (OutputStream o = c.getOutputStream()) { o.write(data); }
            }
            int code = c.getResponseCode();
            InputStream in = code < 400 ? c.getInputStream() : c.getErrorStream();
            JSONObject res = null;
            if (in != null) {
                ByteArrayOutputStream buf = new ByteArrayOutputStream();
                byte[] tmp = new byte[4096];
                int n;
                while ((n = in.read(tmp)) > 0) buf.write(tmp, 0, n);
                in.close();
                try { res = new JSONObject(buf.toString("UTF-8")); } catch (Exception ignored) { }
            }
            return new Result(code, res);
        } catch (Exception e) {
            return new Result(0, null);
        } finally {
            if (c != null) c.disconnect();
        }
    }
}
