"""WBGT exterior Ono et al. (2014), ecuación publicada por Japón MOE.

No es el WBGT ISO ni una medición instrumental. Entradas:
Ta en °C, RH en %, GHI en kW/m², viento promedio en m/s.
https://www.wbgt.env.go.jp/wbgt_detail.php
"""
from __future__ import annotations
import math


def wbgt_ono(air_temperature_c: float, relative_humidity_pct: float,
             solar_w_m2: float, wind_speed_m_s: float) -> float:
    t, rh, solar, wind = map(float, (air_temperature_c, relative_humidity_pct, solar_w_m2, wind_speed_m_s))
    if not (all(map(math.isfinite, (t, rh, solar, wind))) and
            -40 <= t <= 60 and 0 <= rh <= 100 and 0 <= solar <= 1600 and 0 <= wind <= 50):
        raise ValueError('Valores ambientales inválidos o fuera del rango de admisión del laboratorio')
    sr = solar / 1000.0  # ¡kilowatts! no W/m²
    return 0.735*t + 0.0374*rh + 0.00292*t*rh + 7.619*sr - 4.557*sr**2 - 0.0572*wind - 4.064
