# App Android del trabajador (HeatGuard Clip)

App nativa (Java, sin librerías externas) que vincula el clip por Bluetooth y sube cada lectura al servidor
aunque la app no esté en pantalla: un servicio en primer plano mantiene el enlace (notificación fija
«HeatGuard Clip»). También recibe del servidor las solicitudes de pausa del supervisor, los umbrales y el
factor personal, y se los pasa al clip.

## Instalar en el celular

1. Abre la carpeta `android/` en Android Studio (File → Open). La primera vez descarga Gradle y el SDK.
2. En el celular: Ajustes → Acerca del teléfono → toca 7 veces «Versión de MIUI/HyperOS» o «Número de compilación»
   para activar las opciones de desarrollador; ahí activa «Depuración USB» (en Xiaomi también «Instalar vía USB»).
3. Conecta el celular por USB, elígelo arriba en Android Studio y presiona Run (▶).

Sin cable: Build → Build APK(s) y copia `app/build/outputs/apk/debug/app-debug.apk` al celular.

## Uso

El supervisor también puede entrar: ve toda la cuadrilla (la simulación del servidor más los clips reales, que van primero) en tarjetas condensadas, con filtros «Requieren atención» y «Clips reales», las alertas activas, y puede pedir o retirar pausas y ubicar un clip real; gráficos, mapa y ajustes están en el panel web. El tema claro u oscuro se cambia con el botón ☀/☾ de la barra superior.

Entra con el usuario `trabajador` (el servidor viene escrito: https://fedora.tail18b1ba.ts.net), toca
«Vincular clip» y acepta los permisos de dispositivos cercanos y notificaciones. Toca también «Permitir
funcionar en segundo plano». En Xiaomi/HyperOS conviene además: Ajustes de la app → Ahorro de batería →
«Sin restricciones», y activar «Inicio automático»; si no, el sistema puede cerrar el servicio.

Código: `ClipService.java` (Bluetooth, subida de lecturas, comandos), `Telemetry.java` (contrato de datos v2,
igual a `src/lib/telemetry.js`), `Api.java` (servidor) y `MainActivity.java` (pantalla).
