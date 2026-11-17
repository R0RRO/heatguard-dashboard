"""Cálculos térmicos con límites de aplicación documentados.

Heat Index: NWS. Bulbo húmedo psicrométrico: aproximación de Stull (2011).
No confundir Tw psicrométrico con Tnwb NATURAL ni con un WBGT ISO 7243.
"""
from __future__ import annotations

import math


def heat_index_nws_c(t_c: float, rh_pct: float) -> float:
    """Algoritmo operativo NWS, entrada en °C y HR en porcentaje.

    El índice representa condiciones a la sombra (sin radiación solar directa).
    """
    t = t_c * 9.0 / 5.0 + 32.0
    hi_simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh_pct * 0.094)
    initial = (hi_simple + t) / 2.0
    if initial < 80.0:
        hi = initial
    else:
        hi = (
            -42.379 + 2.04901523 * t + 10.14333127 * rh_pct
            - 0.22475541 * t * rh_pct - 0.00683783 * t * t
            - 0.05481717 * rh_pct * rh_pct + 0.00122874 * t * t * rh_pct
            + 0.00085282 * t * rh_pct * rh_pct
            - 0.00000199 * t * t * rh_pct * rh_pct
        )
        if rh_pct < 13 and 80 <= t <= 112:
            hi -= ((13 - rh_pct) / 4) * math.sqrt((17 - abs(t - 95)) / 17)
        elif rh_pct > 85 and 80 <= t <= 87:
            hi += ((rh_pct - 85) / 10) * ((87 - t) / 5)
    return (hi - 32) * 5 / 9


def wet_bulb_stull_c(t_c: float, rh_pct: float) -> float | None:
    """Stull (2011), Tw psicrométrico a presión cercana a nivel del mar.

    Rango de uso conservador: -20 <= T <= 50 °C y 5 <= RH <= 99 %.
    No equivale al bulbo húmedo NATURAL que utiliza WBGT.
    """
    if not (-20 <= t_c <= 50 and 5 <= rh_pct <= 99):
        return None
    return (
        t_c * math.atan(0.151977 * math.sqrt(rh_pct + 8.313659))
        + math.atan(t_c + rh_pct)
        - math.atan(rh_pct - 1.676331)
        + 0.00391838 * rh_pct ** 1.5 * math.atan(0.023101 * rh_pct)
        - 4.686035
    )


def shade_proxy_c(t_c: float, tw_psychrometric_c: float) -> float:
    """Proxy experimental 0.7*Tw_psicrométrico + 0.3*T_aire.

    Asume T_globo=T_aire y Tnwb=Tw_psicrométrico (ambas hipótesis pueden fallar).
    NO es WBGT normativo ni se permite usarlo para decidir condiciones seguras.
    """
    return 0.7 * tw_psychrometric_c + 0.3 * t_c
