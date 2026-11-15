package cl.heatguard.clip;

import android.annotation.SuppressLint;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.bluetooth.BluetoothAdapter;
import android.bluetooth.BluetoothDevice;
import android.bluetooth.BluetoothGatt;
import android.bluetooth.BluetoothGattCallback;
import android.bluetooth.BluetoothGattCharacteristic;
import android.bluetooth.BluetoothGattDescriptor;
import android.bluetooth.BluetoothGattService;
import android.bluetooth.BluetoothManager;
import android.bluetooth.BluetoothProfile;
import android.bluetooth.le.BluetoothLeScanner;
import android.bluetooth.le.ScanCallback;
import android.bluetooth.le.ScanResult;
import android.bluetooth.le.ScanSettings;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Servicio en primer plano: mantiene el enlace Bluetooth con el clip, sube cada lectura al servidor y
 * le pasa al clip lo que llega del supervisor (pausas, umbrales, factor personal). Sigue funcionando con
 * la pantalla apagada o con otra app abierta.
 */
@SuppressLint("MissingPermission") // los permisos se piden en MainActivity antes de iniciar el servicio
public class ClipService extends Service {
    static final String ACTION_STOP = "stop", ACTION_IDENTIFY = "identify";
    private static final String CHANNEL = "clip";
    private static final int NOTIF_ID = 1;
    private static final long STALE_MS = 15000;

    // Estado que lee la pantalla (MainActivity lo consulta cada segundo)
    static volatile boolean running = false;
    static volatile String status = "off";       // off | scanning | connecting | connected | reconnecting
    static volatile JSONObject last = null;
    static volatile long lastAt = 0;
    static volatile String notice = null;
    static volatile long noticeAt = 0;
    static volatile String error = null;
    static volatile boolean streamOk = false;
    static volatile int sentOk = 0, sentFail = 0;
    static volatile String deviceName = null;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService http = Executors.newSingleThreadExecutor();
    private final ArrayDeque<byte[]> writes = new ArrayDeque<>();
    private boolean writing = false;

    private String base, token, workerId;
    private BluetoothAdapter adapter;
    private BluetoothGatt gatt;
    private BluetoothGattCharacteristic cmdChar;
    private String address;
    private boolean scanning = false;
    private PowerManager.WakeLock wakeLock;
    private Thread streamThread;
    private JSONObject config = null, profile = null;
    private long lastNotif = 0;

    @Override public IBinder onBind(Intent i) { return null; }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent != null ? intent.getAction() : null;
        if (ACTION_STOP.equals(action)) { shutdown(); stopSelf(); return START_NOT_STICKY; }
        if (ACTION_IDENTIFY.equals(action)) { if (running) send(Telemetry.CMD_IDENTIFY, 0); else stopSelf(); return START_NOT_STICKY; }
        if (running) return START_STICKY;

        SharedPreferences p = getSharedPreferences("hg", MODE_PRIVATE);
        base = p.getString("server", Api.DEFAULT_SERVER);
        token = p.getString("token", null);
        workerId = p.getString("workerId", null);
        address = p.getString("clipAddress", null);
        if (token == null || workerId == null) { stopSelf(); return START_NOT_STICKY; }

        createChannel();
        Notification n = notification("Buscando el clip…");
        if (Build.VERSION.SDK_INT >= 29) startForeground(NOTIF_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE);
        else startForeground(NOTIF_ID, n);

        running = true; error = null; sentOk = 0; sentFail = 0; last = null;
        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "heatguard:clip");
        wakeLock.acquire();

        adapter = ((BluetoothManager) getSystemService(Context.BLUETOOTH_SERVICE)).getAdapter();
        if (adapter == null || !adapter.isEnabled()) { error = "Activa el Bluetooth del celular."; setStatus("off"); stopSelf(); return START_NOT_STICKY; }
        if (address != null) connect(adapter.getRemoteDevice(address), false); else scan();
        startStream();
        main.postDelayed(watchdog, 5000);
        return START_STICKY;
    }

    @Override public void onDestroy() { shutdown(); super.onDestroy(); }

    private void shutdown() {
        if (!running) return;
        running = false;
        main.removeCallbacksAndMessages(null);
        stopScan();
        if (gatt != null) { gatt.disconnect(); gatt.close(); gatt = null; }
        cmdChar = null;
        setStatus("off");
        if (streamThread != null) streamThread.interrupt();
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        stopForeground(true);
    }

    // ───────── Bluetooth ─────────
    static volatile int seen = 0;   // dispositivos Bluetooth vistos en la búsqueda (diagnóstico)
    private final java.util.Set<String> seenSet = java.util.concurrent.ConcurrentHashMap.newKeySet();

    // Se busca sin filtro y se compara el nombre aquí: algunos celulares no aplican bien el filtro por nombre
    // cuando el clip lo envía en la respuesta de escaneo.
    private final ScanCallback scanCb = new ScanCallback() {
        @Override public void onScanResult(int type, ScanResult r) {
            if (!scanning) return;
            if (seenSet.add(r.getDevice().getAddress())) seen = seenSet.size();
            String name = r.getScanRecord() != null ? r.getScanRecord().getDeviceName() : null;
            if (name == null) name = r.getDevice().getName();
            if (!Telemetry.NAME.equals(name)) return;
            main.post(() -> { if (scanning) { stopScan(); connect(r.getDevice(), false); } });
        }
        @Override public void onBatchScanResults(java.util.List<ScanResult> list) { for (ScanResult r : list) onScanResult(0, r); }
        @Override public void onScanFailed(int code) {
            error = "No se pudo buscar el clip (código " + code + ").";
            scanning = false;
            main.postDelayed(() -> { if (running && gatt == null) scan(); }, 5000);
        }
    };

    private void scan() {
        BluetoothLeScanner s = adapter.getBluetoothLeScanner();
        if (s == null) return;
        setStatus("scanning");
        scanning = true;
        seenSet.clear(); seen = 0;
        ScanSettings st = new ScanSettings.Builder().setScanMode(ScanSettings.SCAN_MODE_LOW_LATENCY).build();
        try { s.startScan(null, st, scanCb); }
        catch (Exception e) { error = "No se pudo buscar: " + e.getMessage(); scanning = false; return; }
        main.postDelayed(() -> {   // sin resultado: se reintenta
            if (running && scanning) {
                stopScan();
                error = seen == 0
                        ? "No se encuentra el clip."
                        : "No se encuentra el clip.";
                main.postDelayed(this::scan, 3000);
            }
        }, 20000);
    }

    private void stopScan() {
        if (!scanning) return;
        scanning = false;
        BluetoothLeScanner s = adapter != null ? adapter.getBluetoothLeScanner() : null;
        if (s != null) try { s.stopScan(scanCb); } catch (Exception ignored) { }
    }

    private void connect(BluetoothDevice d, boolean auto) {
        if (!running) return;
        setStatus(lastAt > 0 ? "reconnecting" : "connecting");
        deviceName = d.getName() != null ? d.getName() : Telemetry.NAME;
        gatt = d.connectGatt(this, auto, gattCb, BluetoothDevice.TRANSPORT_LE);
    }

    private void reconnectLater() {
        if (!running) return;
        setStatus("reconnecting");
        main.postDelayed(() -> {
            if (!running || gatt != null) return;
            if (address != null) connect(adapter.getRemoteDevice(address), true); else scan();
        }, 2000);
    }

    private final BluetoothGattCallback gattCb = new BluetoothGattCallback() {
        @Override public void onConnectionStateChange(BluetoothGatt g, int st, int state) {
            main.post(() -> {
                if (g != gatt) { g.close(); return; }
                if (state == BluetoothProfile.STATE_CONNECTED) {
                    address = g.getDevice().getAddress();
                    getSharedPreferences("hg", MODE_PRIVATE).edit().putString("clipAddress", address).apply();
                    g.requestConnectionPriority(BluetoothGatt.CONNECTION_PRIORITY_BALANCED);
                    g.discoverServices();
                } else if (state == BluetoothProfile.STATE_DISCONNECTED) {
                    g.close();
                    gatt = null; cmdChar = null;
                    synchronized (writes) { writes.clear(); writing = false; }
                    reconnectLater();
                }
            });
        }

        @Override public void onServicesDiscovered(BluetoothGatt g, int st) {
            main.post(() -> {
                BluetoothGattService s = g.getService(Telemetry.SERVICE);
                if (s == null) { error = "El clip no tiene el firmware heatguard_clip."; g.disconnect(); return; }
                BluetoothGattCharacteristic tele = s.getCharacteristic(Telemetry.TELEMETRY);
                if (tele == null) { error = "El clip no tiene el firmware heatguard_clip."; g.disconnect(); return; }
                cmdChar = s.getCharacteristic(Telemetry.COMMAND);
                g.setCharacteristicNotification(tele, true);
                BluetoothGattDescriptor d = tele.getDescriptor(Telemetry.CCCD);
                if (d != null) {
                    writing = true;   // la escritura del descriptor ocupa la cola hasta onDescriptorWrite
                    if (Build.VERSION.SDK_INT >= 33) g.writeDescriptor(d, BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE);
                    else { d.setValue(BluetoothGattDescriptor.ENABLE_NOTIFICATION_VALUE); g.writeDescriptor(d); }
                } else onLinked();
            });
        }

        @Override public void onDescriptorWrite(BluetoothGatt g, BluetoothGattDescriptor d, int st) {
            main.post(() -> { synchronized (writes) { writing = false; } onLinked(); });
        }

        @Override public void onCharacteristicWrite(BluetoothGatt g, BluetoothGattCharacteristic c, int st) {
            main.post(() -> { synchronized (writes) { writing = false; } nextWrite(); });
        }

        @Override public void onCharacteristicChanged(BluetoothGatt g, BluetoothGattCharacteristic c, byte[] value) {
            onPacket(value);
        }

        @SuppressWarnings("deprecation")
        @Override public void onCharacteristicChanged(BluetoothGatt g, BluetoothGattCharacteristic c) {
            if (Build.VERSION.SDK_INT < 33) onPacket(c.getValue());
        }
    };

    private void onLinked() {
        lastAt = System.currentTimeMillis();
        error = null;
        setStatus("connected");
        sendConfig();
        sendProfile();
    }

    private void onPacket(byte[] value) {
        JSONObject m = Telemetry.decode(value, deviceName);
        if (m == null) return;
        last = m;
        lastAt = System.currentTimeMillis();
        if (!"connected".equals(status)) setStatus("connected");
        http.execute(() -> {
            try {
                Api.Result r = Api.request(base, "POST", "/api/telemetry", token, new JSONObject().put("workerId", workerId).put("msg", m));
                if (r.ok()) sentOk++; else { sentFail++; if (r.code == 401) sessionExpired(); }
            } catch (Exception e) { sentFail++; }
        });
        if (lastAt - lastNotif > 5000) {
            lastNotif = lastAt;
            int s = m.optInt("state");
            updateNotification(Telemetry.STATE_LABEL[s] + " · exposición " + m.optInt("load") + " %");
        }
    }

    // Sin paquetes por un rato: se fuerza la reconexión
    private final Runnable watchdog = new Runnable() {
        @Override public void run() {
            if (!running) return;
            if (gatt != null && "connected".equals(status) && System.currentTimeMillis() - lastAt > STALE_MS) gatt.disconnect();
            main.postDelayed(this, 5000);
        }
    };

    // ───────── Comandos al clip (Android permite una escritura a la vez) ─────────
    void send(int cmd, int arg) {
        synchronized (writes) { writes.add(Telemetry.command(cmd, arg)); }
        main.post(this::nextWrite);
    }

    @SuppressWarnings("deprecation")
    private void nextWrite() {
        byte[] v;
        synchronized (writes) {
            if (writing || cmdChar == null || gatt == null || !"connected".equals(status)) return;
            v = writes.poll();
            if (v == null) return;
            writing = true;
        }
        boolean ok;
        if (Build.VERSION.SDK_INT >= 33) {
            ok = gatt.writeCharacteristic(cmdChar, v, BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT) == 0;
        } else {
            cmdChar.setWriteType(BluetoothGattCharacteristic.WRITE_TYPE_DEFAULT);
            cmdChar.setValue(v);
            ok = gatt.writeCharacteristic(cmdChar);
        }
        if (!ok) { synchronized (writes) { writing = false; } main.postDelayed(this::nextWrite, 200); }
    }

    private void sendConfig() {
        JSONObject c = config;
        if (c == null) return;
        send(Telemetry.CMD_LOAD_LIMIT, Math.min(250, c.optInt("loadLimit", 120)));
        send(Telemetry.CMD_TIRED_PCT, c.optInt("tiredPct", 70));
        send(Telemetry.CMD_PAUSE_MINUTES, c.optInt("pauseMinutes", 15));
        send(Telemetry.CMD_AUTO_PAUSE, c.optBoolean("autoPause", true) ? 1 : 0);
    }

    private void sendProfile() {
        JSONObject p = profile;
        if (p == null) return;
        send(Telemetry.CMD_PERSONAL, Telemetry.personalFactor100(p.optDouble("heightCm", 0), p.optDouble("weightKg", 0)));
    }

    // ───────── Servidor ─────────
    private void setStatus(String s) {
        status = s;
        if (token == null) return;
        String link = s.equals("scanning") ? "connecting" : s;
        String dev = deviceName != null ? deviceName : "";
        http.execute(() -> {
            try { Api.request(base, "POST", "/api/link", token, new JSONObject().put("workerId", workerId).put("link", link).put("device", dev)); }
            catch (Exception ignored) { }
        });
        if (running) updateNotification(statusText(s));
    }

    static String statusText(String s) {
        switch (s) {
            case "scanning": return "Buscando el clip…";
            case "connecting": return "Conectando con el clip…";
            case "connected": return "Clip vinculado";
            case "reconnecting": return "Se perdió el clip, reconectando…";
            default: return "Clip sin vincular";
        }
    }

    private void sessionExpired() {
        error = "La sesión venció. Vuelve a entrar.";
        main.post(() -> { shutdown(); stopSelf(); });
    }

    // Flujo de eventos del servidor (/api/stream): comandos del supervisor, umbrales y datos personales
    private void startStream() {
        streamThread = new Thread(() -> {
            while (running) {
                HttpURLConnection c = null;
                try {
                    String q = "?token=" + URLEncoder.encode(token, "UTF-8") + "&workerId=" + URLEncoder.encode(workerId, "UTF-8");
                    c = (HttpURLConnection) new URL(base + "/api/stream" + q).openConnection();
                    c.setConnectTimeout(10000);
                    c.setReadTimeout(60000);   // el servidor manda un latido cada 20 s
                    c.setRequestProperty("Accept", "text/event-stream");
                    if (c.getResponseCode() == 401) { sessionExpired(); return; }
                    if (c.getResponseCode() != 200) throw new Exception("HTTP " + c.getResponseCode());
                    streamOk = true;
                    BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8));
                    String line, event = "message";
                    StringBuilder data = new StringBuilder();
                    while (running && (line = r.readLine()) != null) {
                        if (line.isEmpty()) {
                            if (data.length() > 0) onEvent(event, data.toString());
                            event = "message"; data.setLength(0);
                        } else if (line.startsWith("event:")) event = line.substring(6).trim();
                        else if (line.startsWith("data:")) data.append(line.substring(5).trim());
                    }
                } catch (Exception ignored) {
                } finally {
                    streamOk = false;
                    if (c != null) c.disconnect();
                }
                try { Thread.sleep(5000); } catch (InterruptedException e) { return; }
            }
        }, "hg-stream");
        streamThread.start();
    }

    private void onEvent(String event, String data) {
        try {
            JSONObject d = new JSONObject(data);
            switch (event) {
                case "state": {
                    config = d.optJSONObject("config");
                    JSONObject profiles = d.optJSONObject("profiles");
                    if (profiles != null && profiles.has(workerId)) profile = profiles.getJSONObject(workerId);
                    main.post(() -> { sendConfig(); sendProfile(); });
                    break;
                }
                case "config": config = d; main.post(this::sendConfig); break;
                case "profile": if (workerId.equals(d.optString("workerId"))) { profile = d; main.post(this::sendProfile); } break;
                case "command": {
                    int cmd = d.optInt("cmd"), arg = d.optInt("arg");
                    send(cmd, arg);
                    String txt = cmd == Telemetry.CMD_PAUSE_REQUEST ? "El supervisor pidió una pausa de hidratación y descanso."
                            : cmd == Telemetry.CMD_CANCEL_PAUSE ? "El supervisor retiró la solicitud de pausa."
                            : cmd == Telemetry.CMD_IDENTIFY ? "El supervisor está ubicando tu clip." : null;
                    if (txt != null) { notice = txt; noticeAt = System.currentTimeMillis(); main.post(() -> updateNotification(txt)); }
                    break;
                }
                default: break;
            }
        } catch (Exception ignored) { }
    }

    // ───────── Notificación ─────────
    private void createChannel() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        NotificationChannel ch = new NotificationChannel(CHANNEL, "Enlace con el clip", NotificationManager.IMPORTANCE_LOW);
        ch.setDescription("Estado del clip HeatGuard mientras sube datos");
        nm.createNotificationChannel(ch);
    }

    private Notification notification(String text) {
        Intent open = new Intent(this, MainActivity.class).setFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP);
        PendingIntent pi = PendingIntent.getActivity(this, 0, open, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        return new Notification.Builder(this, CHANNEL)
                .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
                .setContentTitle("HeatGuard Clip")
                .setContentText(text)
                .setContentIntent(pi)
                .setOngoing(true)
                .setOnlyAlertOnce(true)
                .build();
    }

    private void updateNotification(String text) {
        if (!running) return;
        getSystemService(NotificationManager.class).notify(NOTIF_ID, notification(text));
    }
}
