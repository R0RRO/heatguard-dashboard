package cl.heatguard.clip;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.EditText;
import android.widget.GridLayout;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** Pantalla del trabajador: inicio de sesión, vincular el clip y ver su estado. La interfaz se arma en código. */
public class MainActivity extends Activity {
    private static final int NAVY = 0xFF0F1B33, HEAT = 0xFFF97316;
    // colores del tema (claro u oscuro, se elige con el botón de la barra superior)
    private boolean dark;
    private int BG, INK, MUTED, CARD, BTN2, OK_BG, OK_INK;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private SharedPreferences prefs;
    private float dp;

    // vistas de la pantalla principal
    private TextView circlePct, stateLabel, instructions, ledLine, linkLine, serverLine, noticeView, errorView;
    private GradientDrawable circleBg;
    private TextView tTemp, tHum, tHi, tMov, tBat, tSig;
    private Button linkBtn, identifyBtn;

    @Override
    protected void onCreate(Bundle b) {
        prefs = getSharedPreferences("hg", MODE_PRIVATE);
        dark = prefs.getBoolean("dark", true);
        setTheme(dark ? android.R.style.Theme_Material_NoActionBar : android.R.style.Theme_Material_Light_NoActionBar);
        if (dark) { BG = 0xFF0B1220; INK = 0xFFE2E8F0; MUTED = 0xFF94A3B8; CARD = 0xFF1E293B; BTN2 = 0xFF334155; OK_BG = 0xFF14532D; OK_INK = 0xFFBBF7D0; }
        else { BG = Color.WHITE; INK = 0xFF0F172A; MUTED = 0xFF64748B; CARD = 0xFFF1F5F9; BTN2 = 0xFFE2E8F0; OK_BG = 0xFFDCFCE7; OK_INK = 0xFF166534; }
        dp = getResources().getDisplayMetrics().density;
        super.onCreate(b);
        getWindow().setNavigationBarColor(BG);
        getWindow().setStatusBarColor(NAVY);
        render();
    }

    @Override protected void onResume() { super.onResume(); ui.post(tick); }
    @Override protected void onPause() { super.onPause(); ui.removeCallbacks(tick); }

    private void render() {
        if (prefs.getString("token", null) == null) showLogin();
        else if ("supervisor".equals(prefs.getString("role", "")) || "admin".equals(prefs.getString("role", ""))) showSupervisor();
        else showMain();
    }

    private int px(int v) { return Math.round(v * dp); }

    private TextView text(String s, int sp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT_BOLD);
        return t;
    }

    private LinearLayout column(int pad) {
        LinearLayout l = new LinearLayout(this);
        l.setOrientation(LinearLayout.VERTICAL);
        l.setPadding(px(pad), px(pad), px(pad), px(pad));
        return l;
    }

    private GradientDrawable rounded(int color, int radius) {
        GradientDrawable g = new GradientDrawable();
        g.setColor(color);
        g.setCornerRadius(px(radius));
        return g;
    }

    private Button button(String s, boolean primary) {
        Button btn = new Button(this);
        btn.setText(s);
        btn.setAllCaps(false);
        btn.setTextSize(16);
        btn.setTextColor(primary ? Color.WHITE : INK);
        btn.setBackground(rounded(primary ? HEAT : BTN2, 12));
        return btn;
    }

    private void space(LinearLayout l, int h) { l.addView(new View(this), new LinearLayout.LayoutParams(1, px(h))); }

    private View header(LinearLayout root, String subtitle) {
        LinearLayout h = new LinearLayout(this);
        h.setBackgroundColor(NAVY);
        h.setPadding(px(18), px(16), px(12), px(16));
        h.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout titles = new LinearLayout(this);
        titles.setOrientation(LinearLayout.VERTICAL);
        titles.addView(text("HEATGUARD CLIP", 20, Color.WHITE, true));
        if (subtitle != null) titles.addView(text(subtitle, 13, 0xFFC7D2FE, false));
        h.addView(titles, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        TextView theme = text(dark ? "☀" : "☾", 22, Color.WHITE, false);
        theme.setPadding(px(12), px(4), px(12), px(4));
        theme.setContentDescription(dark ? "Tema claro" : "Tema oscuro");
        theme.setOnClickListener(v -> { stopPick(); prefs.edit().putBoolean("dark", !dark).apply(); recreate(); });
        h.addView(theme);
        root.addView(h);
        return h;
    }

    // ───────── Inicio de sesión ─────────
    private void showLogin() {
        LinearLayout root = column(0);
        root.setBackgroundColor(BG);
        header(root, "App del trabajador");
        LinearLayout f = column(20);
        root.addView(f);

        f.addView(text("Servidor", 13, MUTED, true));
        EditText server = new EditText(this);
        server.setText(prefs.getString("server", Api.DEFAULT_SERVER));
        server.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        server.setTextSize(14);
        f.addView(server);
        space(f, 8);
        f.addView(text("Usuario", 13, MUTED, true));
        EditText user = new EditText(this);
        user.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        f.addView(user);
        space(f, 8);
        f.addView(text("Contraseña", 13, MUTED, true));
        EditText pass = new EditText(this);
        pass.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        f.addView(pass);
        space(f, 12);
        TextView err = text("", 14, 0xFFDC2626, false);
        f.addView(err);
        Button go = button("Entrar", true);
        f.addView(go, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(52)));

        go.setOnClickListener(v -> {
            String base = server.getText().toString().trim().replaceAll("/+$", "");
            String u = user.getText().toString().trim().toLowerCase(Locale.ROOT);
            String c = pass.getText().toString();
            go.setEnabled(false);
            err.setText("Entrando…");
            new Thread(() -> {
                Api.Result r;
                try { r = Api.request(base, "POST", "/api/login", null, new JSONObject().put("usuario", u).put("clave", c)); }
                catch (Exception e) { r = new Api.Result(0, null); }
                Api.Result res = r;
                ui.post(() -> {
                    go.setEnabled(true);
                    if (!res.ok()) { err.setText(res.error()); return; }
                    JSONObject usr = res.body.optJSONObject("user");
                    if (usr == null) { err.setText("Respuesta inválida del servidor."); return; }
                    ClipService.error = null;
                    prefs.edit().putString("server", base).putString("token", res.body.optString("token"))
                            .putString("workerId", usr.optString("workerId")).putString("name", usr.optString("name"))
                            .putString("role", usr.optString("role")).apply();
                    render();
                });
            }).start();
        });
        setContentView(root);
    }

    // ───────── Pantalla principal ─────────
    private void showMain() {
        ScrollView sv = new ScrollView(this);
        LinearLayout root = column(0);
        root.setBackgroundColor(BG);
        sv.addView(root);
        header(root, prefs.getString("name", ""));
        LinearLayout c = column(16);
        root.addView(c);

        noticeView = text("", 15, Color.WHITE, true);
        noticeView.setBackground(rounded(0xFFDC2626, 12));
        noticeView.setPadding(px(14), px(12), px(14), px(12));
        noticeView.setVisibility(View.GONE);
        c.addView(noticeView);
        space(c, 8);

        circleBg = new GradientDrawable();
        circleBg.setShape(GradientDrawable.OVAL);
        circleBg.setColor(0xFF94A3B8);
        LinearLayout circle = column(0);
        circle.setGravity(Gravity.CENTER);
        circle.setBackground(circleBg);
        circlePct = text("—", 40, Color.WHITE, true);
        circlePct.setGravity(Gravity.CENTER);
        circle.addView(circlePct);
        TextView sub = text("exposición acumulada", 12, Color.WHITE, false);
        sub.setGravity(Gravity.CENTER);
        circle.addView(sub);
        LinearLayout.LayoutParams cp = new LinearLayout.LayoutParams(px(170), px(170));
        cp.gravity = Gravity.CENTER_HORIZONTAL;
        c.addView(circle, cp);
        space(c, 10);

        stateLabel = text("Clip sin vincular", 24, INK, true);
        stateLabel.setGravity(Gravity.CENTER);
        c.addView(stateLabel);
        instructions = text("", 16, INK, false);
        instructions.setGravity(Gravity.CENTER);
        c.addView(instructions);
        ledLine = text("", 13, MUTED, false);
        ledLine.setGravity(Gravity.CENTER);
        c.addView(ledLine);
        space(c, 12);

        GridLayout grid = new GridLayout(this);
        grid.setColumnCount(2);
        tTemp = tile(grid, "Temperatura"); tHum = tile(grid, "Humedad");
        tHi = tile(grid, "Sensación térmica"); tMov = tile(grid, "Movimiento");
        tBat = tile(grid, "Batería del clip"); tSig = tile(grid, "Señal");
        c.addView(grid);
        space(c, 12);

        linkLine = text("", 15, INK, true);
        c.addView(linkLine);
        errorView = text("", 13, 0xFFDC2626, false);
        c.addView(errorView);
        space(c, 6);
        linkBtn = button("Vincular clip", true);
        c.addView(linkBtn, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(54)));
        linkBtn.setOnClickListener(v -> {
            try { if (ClipService.running) stopClip(); else startClip(); }
            catch (Exception e) { errorView.setText("Error: " + e); }
        });
        space(c, 8);
        identifyBtn = button("Ubicar clip (parpadea y vibra)", false);
        c.addView(identifyBtn, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(48)));
        identifyBtn.setOnClickListener(v -> startService(new Intent(this, ClipService.class).setAction(ClipService.ACTION_IDENTIFY)));
        space(c, 8);
        Button battery = button("Permitir funcionar en segundo plano", false);
        c.addView(battery, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(48)));
        battery.setOnClickListener(v -> askBatteryExemption());
        space(c, 10);
        serverLine = text("", 12, MUTED, false);
        c.addView(serverLine);
        space(c, 14);
        Button logout = button("Cerrar sesión", false);
        c.addView(logout, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(44)));
        logout.setOnClickListener(v -> logout());

        setContentView(sv);
        ui.removeCallbacks(tick);
        ui.post(tick);
    }

    private TextView tile(GridLayout g, String label) {
        LinearLayout t = column(10);
        t.setBackground(rounded(CARD, 12));
        t.addView(text(label, 12, MUTED, false));
        TextView v = text("—", 20, INK, true);
        t.addView(v);
        GridLayout.LayoutParams lp = new GridLayout.LayoutParams(GridLayout.spec(GridLayout.UNDEFINED), GridLayout.spec(GridLayout.UNDEFINED, 1f));
        lp.width = 0;
        lp.setMargins(px(4), px(4), px(4), px(4));
        g.addView(t, lp);
        return v;
    }

    // Refresco de la pantalla con el estado del servicio
    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (prefs.getString("token", null) == null) return;
            if (supList != null) { drawSupervisor(); ui.postDelayed(this, 1000); return; }
            if (stateLabel == null) return;
            refresh();
            ui.postDelayed(this, 1000);
        }
    };

    private void refresh() {
        JSONObject m = ClipService.last;
        long age = System.currentTimeMillis() - ClipService.lastAt;
        boolean fresh = ClipService.running && m != null && age < 10000;
        if (fresh) {
            int s = Math.max(0, Math.min(4, m.optInt("state")));
            circleBg.setColor(Telemetry.STATE_COLOR[s]);
            circlePct.setText(m.optInt("load") + "%");
            stateLabel.setText(Telemetry.STATE_LABEL[s]);
            stateLabel.setTextColor(Telemetry.STATE_COLOR[s]);
            instructions.setText(instructionsFor(s, m));
            ledLine.setText("Pausas hoy: " + m.optInt("pauses")
                    + (s == 2 && m.optBoolean("requestBySupervisor") ? "\nPausa pedida por el supervisor" : ""));
            JSONObject env = m.optJSONObject("env");
            boolean envOk = env != null && env.optBoolean("ok");
            tTemp.setText(envOk ? String.format(Locale.US, "%.1f °C", env.optDouble("tempC")) : "sin sensor");
            tHum.setText(envOk ? Math.round(env.optDouble("rhPct")) + " %" : "sin sensor");
            tHi.setText(envOk && !env.isNull("heatIndexC") ? String.format(Locale.US, "%.1f °C", env.optDouble("heatIndexC")) : "—");
            JSONObject mov = m.optJSONObject("motion");
            tMov.setText(mov != null && mov.optBoolean("ok") ? Telemetry.movLevel(mov.optInt("index")) : "sin sensor");
            JSONObject bat = m.optJSONObject("battery");
            tBat.setText(bat != null ? bat.optInt("pct") + " %" : "—");
            tSig.setText(m.isNull("rssi") ? "—" : Telemetry.signalLevel(m.optInt("rssi")));
        } else {
            circleBg.setColor(0xFF94A3B8);
            circlePct.setText("—");
            stateLabel.setText(ClipService.statusText(ClipService.running ? ClipService.status : "off"));
            stateLabel.setTextColor(INK);
            instructions.setText("");
            ledLine.setText("");
        }
        linkLine.setText(ClipService.statusText(ClipService.running ? ClipService.status : "off")
                + (ClipService.running && ClipService.deviceName != null ? " · " + ClipService.deviceName : "")
);
        linkBtn.setText(ClipService.running ? "Desvincular clip" : "Vincular clip");
        identifyBtn.setEnabled(ClipService.running && "connected".equals(ClipService.status));
        errorView.setText(ClipService.error != null ? ClipService.error : "");
        boolean showNotice = ClipService.notice != null && System.currentTimeMillis() - ClipService.noticeAt < 15000;
        noticeView.setVisibility(showNotice ? View.VISIBLE : View.GONE);
        if (showNotice) noticeView.setText(ClipService.notice);
        serverLine.setText("Servidor " + (ClipService.running ? (ClipService.streamOk ? "en línea" : "reconectando…") : "—")
                + (ClipService.running ? " · " + ClipService.sentOk + " lecturas enviadas" + (ClipService.sentFail > 0 ? ", " + ClipService.sentFail + " fallidas" : "") : ""));
        if (ClipService.error != null && ClipService.error.startsWith("La sesión venció")) logout();
    }

    private String instructionsFor(int s, JSONObject m) {
        switch (s) {
            case 0: return "";
            case 1: return "";
            case 2: return "Mantén el botón 2 s para comenzar la pausa";
            case 3: return "En pausa hace " + (m.optInt("stateS") / 60) + " min";
            default: return "Mantén el botón 2 s para volver al trabajo";
        }
    }

    // ───────── Lista de dispositivos Bluetooth para elegir el clip ─────────
    private android.bluetooth.le.BluetoothLeScanner pickScanner;
    private android.bluetooth.le.ScanCallback pickCb;
    private final java.util.LinkedHashMap<String, String[]> found = new java.util.LinkedHashMap<>(); // dirección → {nombre, rssi}

    @SuppressLint("MissingPermission")
    private void showPicker() {
        android.bluetooth.BluetoothAdapter ad = ((android.bluetooth.BluetoothManager) getSystemService(BLUETOOTH_SERVICE)).getAdapter();
        if (ad == null) { ClipService.error = "Este celular no tiene Bluetooth."; return; }
        if (!ad.isEnabled()) {
            try { startActivity(new Intent(android.bluetooth.BluetoothAdapter.ACTION_REQUEST_ENABLE)); } catch (Exception ignored) { }
            ClipService.error = "Activa el Bluetooth y vuelve a tocar «Vincular clip».";
            if (errorView != null) errorView.setText(ClipService.error);
            return;
        }
        stateLabel = null;   // detiene el refresco de la pantalla principal
        LinearLayout root = column(0);
        root.setBackgroundColor(BG);
        header(root, "Elige tu clip");
        LinearLayout c = column(16);
        root.addView(c, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        TextView info = text("Buscando dispositivos…", 14, MUTED, false);
        c.addView(info);
        space(c, 8);
        ScrollView sv = new ScrollView(this);
        LinearLayout list = column(0);
        sv.addView(list);
        c.addView(sv, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));
        space(c, 8);
        Button cancel = button("Cancelar", false);
        c.addView(cancel, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(48)));
        cancel.setOnClickListener(v -> { stopPick(); showMain(); });
        setContentView(root);

        found.clear();
        pickScanner = ad.getBluetoothLeScanner();
        pickCb = new android.bluetooth.le.ScanCallback() {
            @Override public void onScanResult(int type, android.bluetooth.le.ScanResult r) {
                String name = r.getScanRecord() != null ? r.getScanRecord().getDeviceName() : null;
                if (name == null) name = r.getDevice().getName();
                String n = name, addr = r.getDevice().getAddress(), rssi = String.valueOf(r.getRssi());
                ui.post(() -> {
                    boolean isNew = !found.containsKey(addr);
                    String[] prev = found.get(addr);
                    found.put(addr, new String[]{n != null ? n : (prev != null ? prev[0] : null), rssi});
                    if (isNew || (prev != null && prev[0] == null && n != null)) drawList(list);
                    info.setText(found.size() + " dispositivos");
                });
            }
            @Override public void onScanFailed(int code) { ui.post(() -> info.setText("No se pudo buscar (código " + code + "). " + diagnostics())); }
        };
        try {
            pickScanner.startScan(null, new android.bluetooth.le.ScanSettings.Builder()
                    .setScanMode(android.bluetooth.le.ScanSettings.SCAN_MODE_LOW_LATENCY).build(), pickCb);
        } catch (Exception e) { info.setText("No se pudo buscar: " + e); }
        ui.postDelayed(() -> { if (pickCb != null && found.isEmpty()) info.setText("Sin dispositivos. " + diagnostics()); }, 8000);
    }

    private void drawList(LinearLayout list) {
        list.removeAllViews();
        List<java.util.Map.Entry<String, String[]>> items = new ArrayList<>(found.entrySet());
        // primero el clip, luego los que tienen nombre
        items.sort((a, b) -> rank(a.getValue()[0]) - rank(b.getValue()[0]));
        for (java.util.Map.Entry<String, String[]> e : items) {
            String name = e.getValue()[0];
            boolean clip = Telemetry.NAME.equals(name);
            LinearLayout row = column(12);
            row.setBackground(rounded(clip ? OK_BG : CARD, 10));
            row.addView(text(name != null ? name : "(sin nombre)", 16, clip ? OK_INK : INK, true));
            row.addView(text("Señal " + Telemetry.signalLevel(Integer.parseInt(e.getValue()[1])).toLowerCase(), 12, MUTED, false));
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
            lp.setMargins(0, 0, 0, px(6));
            list.addView(row, lp);
            row.setOnClickListener(v -> {
                stopPick();
                prefs.edit().putString("clipAddress", e.getKey()).apply();
                showMain();
                launchService();
            });
        }
    }

    private static int rank(String name) { return Telemetry.NAME.equals(name) ? 0 : name != null ? 1 : 2; }

    @SuppressLint("MissingPermission")
    private void stopPick() {
        if (pickScanner != null && pickCb != null) try { pickScanner.stopScan(pickCb); } catch (Exception ignored) { }
        pickCb = null;
    }

    private String diagnostics() {
        android.location.LocationManager lm = (android.location.LocationManager) getSystemService(LOCATION_SERVICE);
        boolean loc = Build.VERSION.SDK_INT >= 28 ? lm.isLocationEnabled() : true;
        return (missingBluetooth().isEmpty() ? "" : "Faltan permisos de Bluetooth. ") + (loc ? "" : "Activa la ubicación.");
    }

    @Override protected void onStop() { super.onStop(); if (pickCb != null) { stopPick(); showMain(); } }

    // ───────── Vista del supervisor: toda la cuadrilla (simulada + clips reales), condensada ─────────
    private LinearLayout supList, supAlerts;
    private TextView supSummary, supConfig, supServer;
    private Thread supThread;
    private volatile boolean supRunning = false, supOnline = false;
    private volatile JSONObject supData = null;     // último «simlite» del servidor
    private String supOrder = "";
    private final java.util.Map<String, SupCard> supCards = new java.util.HashMap<>();
    private String supFilter = "todos";
    // criterios de orden de la lista del supervisor (el clip real siempre va primero)
    private static final String[][] SORTS = {{"urgencia", "Urgencia"}, {"exposicion", "Exposición"}, {"sensacion", "Sensación"}, {"nombre", "Nombre"}};
    private int supSort = 0;
    private List<String> supIds = new ArrayList<>();   // orden mostrado; se recalcula cada 10 s
    private long supSortedAt = 0;
    private String supRealKey = "";

    private static final java.util.Map<String, Integer> STATUS_COLOR = new java.util.HashMap<>();
    private static final java.util.Map<String, String> STATUS_LABEL = new java.util.HashMap<>();
    private static final java.util.Map<String, Integer> STATUS_RANK = new java.util.HashMap<>();
    static {
        String[] k = {"descanso", "finPausa", "cansancio", "pausa", "normal", "offline"};
        int[] c = {0xFFDC2626, 0xFF1D4ED8, 0xFFCA8A04, 0xFF2563EB, 0xFF16A34A, 0xFF64748B};
        String[] l = {"Toca descanso", "Pausa cumplida", "Cansancio", "En pausa", "Óptimo", "Sin señal"};
        for (int i = 0; i < k.length; i++) { STATUS_COLOR.put(k[i], c[i]); STATUS_LABEL.put(k[i], l[i]); STATUS_RANK.put(k[i], i); }
    }

    private final class SupCard {
        LinearLayout root; GradientDrawable bg; TextView name, badge, line1, line2, extra; Button pause, locate;
    }

    private void showSupervisor() {
        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(BG);
        LinearLayout root = column(0);
        root.setBackgroundColor(BG);
        sv.addView(root);
        header(root, prefs.getString("name", "") + ("admin".equals(prefs.getString("role", "")) ? " · administrador" : " · supervisor"));
        LinearLayout c = column(14);
        root.addView(c);
        supSummary = text("Conectando con el servidor…", 18, INK, true);
        c.addView(supSummary);
        supConfig = text("", 12, MUTED, false);
        c.addView(supConfig);
        space(c, 8);

        LinearLayout filters = new LinearLayout(this);
        String[][] fs = {{"todos", "Todos"}, {"atencion", "Requieren atención"}};
        List<Button> fbs = new ArrayList<>();
        for (String[] f : fs) {
            Button b = button(f[1], f[0].equals(supFilter));
            b.setTextSize(12);
            b.setOnClickListener(v -> {
                supFilter = f[0];
                for (int i = 0; i < fbs.size(); i++) {
                    boolean on = fs[i][0].equals(supFilter);
                    fbs.get(i).setBackground(rounded(on ? HEAT : BTN2, 12));
                    fbs.get(i).setTextColor(on ? Color.WHITE : INK);
                }
                supOrder = "";
                drawSupervisor();
            });
            fbs.add(b);
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, px(38), 1f);
            lp.setMargins(0, 0, px(6), 0);
            filters.addView(b, lp);
        }
        // botón que alterna el criterio de orden
        supSort = Math.max(0, Math.min(SORTS.length - 1, prefs.getInt("supSort", 0)));
        Button sortBtn = button("⇅ " + SORTS[supSort][1], false);
        sortBtn.setTextSize(12);
        sortBtn.setSingleLine(true);
        sortBtn.setEllipsize(android.text.TextUtils.TruncateAt.END);
        sortBtn.setPadding(px(6), 0, px(6), 0);
        sortBtn.setOnClickListener(v -> {
            supSort = (supSort + 1) % SORTS.length;
            prefs.edit().putInt("supSort", supSort).apply();
            sortBtn.setText("⇅ " + SORTS[supSort][1]);
            supOrder = "";
            drawSupervisor();
        });
        filters.addView(sortBtn, new LinearLayout.LayoutParams(0, px(38), 1f));
        c.addView(filters);
        space(c, 8);

        supAlerts = column(0);
        c.addView(supAlerts);
        supList = column(0);
        c.addView(supList);
        space(c, 6);
        supServer = text("", 12, MUTED, false);
        c.addView(supServer);
        space(c, 10);
        Button web = button("Abrir panel completo", false);
        c.addView(web, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(46)));
        web.setOnClickListener(v -> startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(prefs.getString("server", Api.DEFAULT_SERVER)))));
        space(c, 8);
        Button out = button("Cerrar sesión", false);
        c.addView(out, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, px(44)));
        out.setOnClickListener(v -> logout());
        setContentView(sv);
        supOrder = "";
        supCards.clear();
        startSupStream();
        ui.removeCallbacks(tick);
        ui.post(tick);
    }

    private void startSupStream() {
        if (supRunning) return;
        supRunning = true;
        String base = prefs.getString("server", Api.DEFAULT_SERVER), token = prefs.getString("token", "");
        supThread = new Thread(() -> {
            while (supRunning) {
                java.net.HttpURLConnection c = null;
                try {
                    c = (java.net.HttpURLConnection) new java.net.URL(base + "/api/stream?lite=1&token=" + java.net.URLEncoder.encode(token, "UTF-8")).openConnection();
                    c.setConnectTimeout(10000);
                    c.setReadTimeout(60000);
                    if (c.getResponseCode() == 401) { ui.post(this::logout); return; }
                    java.io.BufferedReader r = new java.io.BufferedReader(new java.io.InputStreamReader(c.getInputStream(), java.nio.charset.StandardCharsets.UTF_8));
                    supOnline = true;
                    String line, ev = "message";
                    StringBuilder data = new StringBuilder();
                    while (supRunning && (line = r.readLine()) != null) {
                        if (line.isEmpty()) {
                            if (data.length() > 0 && ev.equals("simlite")) { try { supData = new JSONObject(data.toString()); } catch (Exception ignored) { } }
                            ev = "message"; data.setLength(0);
                        }
                        else if (line.startsWith("event:")) ev = line.substring(6).trim();
                        else if (line.startsWith("data:")) data.append(line.substring(5).trim());
                    }
                } catch (Exception ignored) {
                } finally { supOnline = false; if (c != null) c.disconnect(); }
                try { Thread.sleep(4000); } catch (InterruptedException e) { return; }
            }
        }, "hg-sup");
        supThread.start();
    }

    private void stopSupStream() {
        supRunning = false;
        if (supThread != null) supThread.interrupt();
    }

    private void drawSupervisor() {
        supServer.setText("Servidor " + (supOnline ? "en línea" : "reconectando…"));
        JSONObject d = supData;
        if (d == null) return;
        org.json.JSONArray arr = d.optJSONArray("workers");
        if (arr == null) return;
        List<JSONObject> ws = new ArrayList<>();
        int rest = 0, tired = 0, paused = 0, real = 0;
        for (int i = 0; i < arr.length(); i++) {
            JSONObject w = arr.optJSONObject(i);
            String st = w.optString("status");
            if (st.equals("descanso") || st.equals("finPausa")) rest++;
            if (st.equals("cansancio")) tired++;
            if (st.equals("pausa")) paused++;
            if (w.optBoolean("real")) real++;
            boolean show = supFilter.equals("todos") || w.optBoolean("real")   // el clip real se muestra siempre
                    || (supFilter.equals("atencion") && (st.equals("descanso") || st.equals("finPausa") || st.equals("cansancio") || st.equals("offline")));
            if (show) ws.add(w);
        }
        String crit = SORTS[supSort][0];
        ws.sort((a, b) -> {
            if (a.optBoolean("real") != b.optBoolean("real")) return a.optBoolean("real") ? -1 : 1;   // clip real primero
            switch (crit) {
                case "exposicion": return b.optInt("load") - a.optInt("load");
                case "sensacion": return Double.compare(b.optDouble("hi", -99), a.optDouble("hi", -99));
                case "nombre": return a.optString("name").compareToIgnoreCase(b.optString("name"));
                default: {
                    int r = STATUS_RANK.getOrDefault(a.optString("status"), 9) - STATUS_RANK.getOrDefault(b.optString("status"), 9);
                    return r != 0 ? r : b.optInt("load") - a.optInt("load");
                }
            }
        });
        // los valores se actualizan en vivo; el orden de las tarjetas solo cada 10 s (o al cambiar filtro u orden)
        long nowMs = System.currentTimeMillis();
        StringBuilder realKey = new StringBuilder();
        for (JSONObject w : ws) if (w.optBoolean("real")) realKey.append(w.optString("id")).append(',');
        boolean realChanged = !realKey.toString().equals(supRealKey);   // un clip real que se conecta sube al tiro
        supRealKey = realKey.toString();
        if (supOrder.isEmpty() || realChanged || nowMs - supSortedAt >= 10000) {
            supIds = new ArrayList<>();
            for (JSONObject w : ws) supIds.add(w.optString("id"));
            supSortedAt = nowMs;
        } else {
            java.util.Map<String, JSONObject> byId = new java.util.HashMap<>();
            for (JSONObject w : ws) byId.put(w.optString("id"), w);
            List<JSONObject> stable = new ArrayList<>();
            List<String> kept = new ArrayList<>();
            for (String id : supIds) if (byId.containsKey(id)) { stable.add(byId.remove(id)); kept.add(id); }
            for (JSONObject w : ws) if (byId.containsKey(w.optString("id"))) { stable.add(w); kept.add(w.optString("id")); }
            ws = stable;
            supIds = kept;
        }
        JSONObject ctl = d.optJSONObject("ctl");
        supSummary.setText(arr.length() + " trabajadores · " + rest + " toca descanso · " + tired + " cansancio · " + paused + " en pausa");
        supConfig.setText((real > 0 ? real + " con clip real · " : "") + "hora simulada " + clockText(d.optInt("clock"))
                + (ctl != null && ctl.optInt("heatOffset") != 0 ? " · ola de calor " + (ctl.optInt("heatOffset") > 0 ? "+" : "") + ctl.optInt("heatOffset") + " °C" : "")
                + (ctl != null && !ctl.optBoolean("running", true) ? " · simulación pausada" : ""));

        // alertas activas
        supAlerts.removeAllViews();
        org.json.JSONArray al = d.optJSONArray("alerts");
        if (al != null) for (int i = 0; i < Math.min(3, al.length()); i++) {
            JSONObject a = al.optJSONObject(i);
            TextView t = text("⚠ " + a.optString("name") + ": " + a.optString("reason"), 13, Color.WHITE, false);
            t.setBackground(rounded("alerta".equals(a.optString("level")) ? 0xFFB91C1C : 0xFFB45309, 10));
            t.setPadding(px(12), px(8), px(12), px(8));
            supAlerts.addView(t, cardLp(6));
        }

        // tarjetas: se reconstruyen solo si cambia el orden; si no, se actualizan en su lugar
        StringBuilder order = new StringBuilder();
        for (JSONObject w : ws) order.append(w.optString("id")).append(',');
        if (!order.toString().equals(supOrder)) {
            supOrder = order.toString();
            supList.removeAllViews();
            for (JSONObject w : ws) {
                SupCard sc = supCards.get(w.optString("id"));
                if (sc == null) { sc = newCard(w.optString("id")); supCards.put(w.optString("id"), sc); }
                if (sc.root.getParent() != null) ((ViewGroup) sc.root.getParent()).removeView(sc.root);
                supList.addView(sc.root, cardLp(8));
            }
        }
        int pauseMin = d.optInt("pauseMinutes", 15);
        for (JSONObject w : ws) updateCard(supCards.get(w.optString("id")), w, pauseMin);
    }

    private static String clockText(int minutes) {
        int m = ((minutes % 1440) + 1440) % 1440;
        return String.format(Locale.US, "%02d:%02d", m / 60, m % 60);
    }

    private LinearLayout.LayoutParams cardLp(int bottom) {
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, 0, 0, px(bottom));
        return lp;
    }

    private SupCard newCard(String id) {
        SupCard sc = new SupCard();
        sc.root = column(10);
        sc.bg = rounded(CARD, 12);
        sc.root.setBackground(sc.bg);
        LinearLayout top = new LinearLayout(this);
        top.setGravity(Gravity.CENTER_VERTICAL);
        sc.name = text("", 16, INK, true);
        top.addView(sc.name, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        sc.badge = text("", 12, Color.WHITE, true);
        sc.badge.setPadding(px(9), px(2), px(9), px(2));
        top.addView(sc.badge);
        sc.root.addView(top);
        sc.line1 = text("", 14, INK, false);
        sc.root.addView(sc.line1);
        sc.line2 = text("", 12, MUTED, false);
        sc.root.addView(sc.line2);
        sc.extra = text("", 12, 0xFFF87171, true);
        sc.root.addView(sc.extra);
        LinearLayout actions = new LinearLayout(this);
        actions.setPadding(0, px(6), 0, 0);
        sc.pause = button("Pedir pausa", true);
        sc.pause.setTextSize(13);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(0, px(38), 1f);
        lp.setMargins(0, 0, px(6), 0);
        actions.addView(sc.pause, lp);
        sc.locate = button("Ubicar clip", false);
        sc.locate.setTextSize(13);
        actions.addView(sc.locate, new LinearLayout.LayoutParams(0, px(38), 1f));
        sc.root.addView(actions);
        sc.locate.setOnClickListener(v -> simAction(new String[]{"identify", id}, sc.locate));
        return sc;
    }

    private void updateCard(SupCard sc, JSONObject w, int pauseMin) {
        String id = w.optString("id"), st = w.optString("status");
        int color = STATUS_COLOR.getOrDefault(st, 0xFF64748B);
        boolean real = w.optBoolean("real");
        sc.bg.setStroke(px(real ? 3 : 1), real ? 0xFF10B981 : color);
        sc.name.setText((real ? "● " : "") + w.optString("name"));
        sc.badge.setText(STATUS_LABEL.getOrDefault(st, st));
        sc.badge.setBackground(rounded(color, 20));
        sc.line1.setText("Exposición " + w.optInt("load") + " %"
                + (w.optBoolean("ok") && !w.isNull("hi") ? String.format(Locale.US, " · sensación térmica (HI) %.1f °C · %.1f °C · %d %%", w.optDouble("hi"), w.optDouble("t"), w.optInt("rh")) : " · sin sensor ambiental"));
        sc.line2.setText(w.optString("trade") + " · " + w.optString("crew") + " · " + w.optString("zone") + "\n"
                + "movimiento " + w.optInt("mov") + " (" + Telemetry.movLevel(w.optInt("mov")).toLowerCase() + ") · batería " + w.optInt("bat") + " %" + (w.isNull("sig") ? "" : " · señal " + w.optInt("sig") + " dBm (" + Telemetry.signalLevel(w.optInt("sig")).toLowerCase() + ")")
                + " · pausas " + w.optInt("pauses") + (real ? " · CLIP REAL" : ""));
        String extra = "";
        if (w.optBoolean("req") && (st.equals("descanso"))) extra = w.optBoolean("reqSup") ? "Pausa pedida por ti" : "Pausa pedida por el clip";
        if (st.equals("pausa") && !w.isNull("pauseMin")) extra = "En pausa hace " + w.optInt("pauseMin") + " min";
        sc.extra.setText(extra);
        sc.extra.setTextColor(st.equals("pausa") ? 0xFF60A5FA : 0xFFF87171);
        sc.extra.setVisibility(extra.isEmpty() ? View.GONE : View.VISIBLE);

        boolean cancel = w.optBoolean("req") && w.optBoolean("reqSup");
        boolean canPause = st.equals("normal") || st.equals("cansancio");
        sc.pause.setVisibility(cancel || canPause ? View.VISIBLE : View.GONE);
        sc.pause.setText(cancel ? "Retirar pausa" : "Pedir pausa");
        sc.pause.setBackground(rounded(cancel ? BTN2 : HEAT, 12));
        sc.pause.setTextColor(cancel ? INK : Color.WHITE);
        sc.pause.setOnClickListener(v -> simAction(cancel ? new String[]{"cancelPause", id} : new String[]{"orderPause", id, String.valueOf(pauseMin)}, sc.pause));
        sc.locate.setVisibility(real ? View.VISIBLE : View.GONE);
    }

    private void simAction(String[] a, Button b) {
        b.setEnabled(false);
        String base = prefs.getString("server", Api.DEFAULT_SERVER), token = prefs.getString("token", null);
        new Thread(() -> {
            Api.Result r;
            try {
                JSONObject body = new JSONObject().put("action", a[0]).put("workerId", a[1]);
                if (a.length > 2) body.put("minutes", Integer.parseInt(a[2]));
                r = Api.request(base, "POST", "/api/sim", token, body);
            } catch (Exception e) { r = new Api.Result(0, null); }
            Api.Result res = r;
            ui.post(() -> {
                b.setEnabled(true);
                supSummary.setText(res.ok() ? ("orderPause".equals(a[0]) ? "Pausa pedida"
                        : "cancelPause".equals(a[0]) ? "Pausa retirada" : "Ubicando clip") : res.error());
            });
        }).start();
    }

    @Override protected void onDestroy() { stopSupStream(); super.onDestroy(); }

    // ───────── Acciones ─────────
    private List<String> missingBluetooth() {
        List<String> need = new ArrayList<>();
        if (Build.VERSION.SDK_INT >= 31) { need.add(Manifest.permission.BLUETOOTH_SCAN); need.add(Manifest.permission.BLUETOOTH_CONNECT); }
        else need.add(Manifest.permission.ACCESS_FINE_LOCATION);
        List<String> missing = new ArrayList<>();
        for (String p : need) if (checkSelfPermission(p) != PackageManager.PERMISSION_GRANTED) missing.add(p);
        return missing;
    }

    private void startClip() {
        List<String> ask = missingBluetooth();
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED
                && !prefs.getBoolean("askedNotif", false)) {
            ask.add(Manifest.permission.POST_NOTIFICATIONS);
            prefs.edit().putBoolean("askedNotif", true).apply();
        }
        if (!ask.isEmpty()) { requestPermissions(ask.toArray(new String[0]), 1); return; }
        showPicker();
    }

    private void launchService() {
        ClipService.error = null;
        if (linkLine != null) linkLine.setText("Iniciando…");
        startForegroundService(new Intent(this, ClipService.class));
    }

    @Override
    public void onRequestPermissionsResult(int code, String[] perms, int[] res) {
        super.onRequestPermissionsResult(code, perms, res);
        if (!missingBluetooth().isEmpty()) {
            ClipService.error = "Sin permiso de Bluetooth (dispositivos cercanos) no se puede vincular el clip. Actívalo en Ajustes → Apps → HeatGuard → Permisos.";
            if (errorView != null) errorView.setText(ClipService.error);
            return;
        }
        showPicker();
    }

    private void stopClip() {
        startService(new Intent(this, ClipService.class).setAction(ClipService.ACTION_STOP));
    }

    private void askBatteryExemption() {
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        try {
            if (!pm.isIgnoringBatteryOptimizations(getPackageName())) {
                startActivity(new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).setData(Uri.parse("package:" + getPackageName())));
            } else {
                startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).setData(Uri.parse("package:" + getPackageName())));
            }
        } catch (Exception e) {
            startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS).setData(Uri.parse("package:" + getPackageName())));
        }
    }

    private void logout() {
        String base = prefs.getString("server", Api.DEFAULT_SERVER), token = prefs.getString("token", null);
        if (ClipService.running) stopClip();
        if (token != null) new Thread(() -> Api.request(base, "POST", "/api/logout", token, null)).start();
        stopSupStream();
        prefs.edit().remove("token").remove("workerId").remove("name").remove("clipAddress").remove("role").apply();
        stateLabel = null;
        supList = null;
        render();
    }
}
