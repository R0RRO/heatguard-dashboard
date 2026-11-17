"""Modelo exploratorio de transferencia de calor y masa, NO Liljegren/ISO.

Motivación: obtener sensibilidades físicamente interpretables *sin hardware* ni
librerías externas. Un termómetro de globo y una mecha húmeda son VIRTUALES:
se resuelven balances estacionarios muy simplificados. Las hipótesis radiativas
no cubren sol directo/difuso, cielo frío, reflejos, paredes ni fuentes industriales.
No equivale a un método de medición, calibración ni umbrales normativos.

Referencia conceptual: Liljegren et al. (2008), NO implementación de sus ecuaciones.
"""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math

SIGMA = 5.670374419e-8  # W/m²/K^4
K_AIR = 0.026          # W/m/K - constante aproximada para análisis
NU_AIR = 1.6e-5        # m²/s - viscosidad cinemática aproximada
PR = 0.71
CP_AIR = 1006.0       # J/kg/K
R_AIR = 287.05
R_VAPOR = 461.5


@dataclass(frozen=True)
class BalanceAssumptions:
    globe_diameter_m: float = 0.15
    wick_diameter_m: float = 0.007
    globe_solar_absorptivity: float = 0.95
    wick_solar_absorptivity: float = 0.50
    projected_fraction: float = 0.25
    globe_lw_emissivity: float = 0.95
    wick_lw_emissivity: float = 0.95
    lewis_number: float = 0.87
    # Hipótesis estructurales: radiación térmica del entorno a T_aire;
    # la irradiancia global horizontal se proyecta con razón geométrica fija.
    # El viento de entrada se considera velocidad LOCAL a la altura del objeto.


def _check(t: float, rh: float, solar: float, wind: float, pressure: float) -> None:
    vals = (t, rh, solar, wind, pressure)
    if not all(math.isfinite(x) for x in vals):
        raise ValueError('Todas las entradas deben ser números finitos.')
    if not (10.0 <= t <= 48.0 and 10.0 <= rh <= 95.0 and
            0.0 <= solar <= 1200.0 and 0.1 <= wind <= 8.0 and
            800.0 <= pressure <= 1050.0):
        raise ValueError('Fuera del dominio exploratorio: T 10..48 °C, HR 10..95 %, '
                         'solar 0..1200 W/m², viento local 0.1..8 m/s, presión 800..1050 hPa.')


def _nusselt_sphere(wind: float, diameter: float) -> float:
    re = wind * diameter / NU_AIR
    return 2.0 + 0.6 * math.sqrt(re) * PR ** (1 / 3)


def _nusselt_cylinder(wind: float, diameter: float) -> float:
    """Churchill-Bernstein, estimación flujo transversal a cilindro."""
    re = wind * diameter / NU_AIR
    nu = (0.3 + (0.62 * math.sqrt(re) * PR ** (1/3)) /
          (1 + (0.4/PR)**(2/3))**0.25 *
          (1 + (re/282000)**(5/8))**(4/5))
    return max(2.0, nu)  # piso simplificado para no simular convección nula


def _saturated_vapor_density(temp_c: float) -> float:
    # Magnus-Tetens sobre agua; exploratorio dentro del dominio indicado.
    e_pa = 610.94 * math.exp(17.625 * temp_c / (temp_c + 243.04))
    return e_pa / (R_VAPOR * (temp_c + 273.15))


def _root_bisect(decreasing_function, lo: float, hi: float, *, n: int = 70) -> float:
    flo, fhi = decreasing_function(lo), decreasing_function(hi)
    if not (flo >= 0 and fhi <= 0):
        raise ArithmeticError('El balance no tiene raíz acotada para estas condiciones.')
    for _ in range(n):
        mid = (lo + hi) / 2.0
        if decreasing_function(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def experimental_balance_c(
    air_temperature_c: float,
    relative_humidity_pct: float,
    solar_w_m2: float,
    wind_speed_m_s: float,
    pressure_hpa: float,
    assumptions: BalanceAssumptions | None = None,
) -> dict:
    """Devuelve un *proxy físico*, NO un WBGT Liljegren o ISO medido.

    No aplicar parámetros de viento meteorológico a 10 m directamente: este
    prototipo conceptual exige la velocidad del aire *local* a altura de trabajo.
    """
    t, rh, s, v, p = (float(air_temperature_c), float(relative_humidity_pct),
                     float(solar_w_m2), float(wind_speed_m_s), float(pressure_hpa))
    _check(t, rh, s, v, p)
    a = assumptions or BalanceAssumptions()
    if not (0 < a.globe_diameter_m <= 0.3 and 0 < a.wick_diameter_m <= 0.02 and
            0 < a.projected_fraction <= 1 and 0 < a.lewis_number <= 2):
        raise ValueError('Parámetros geométricos/materiales fuera de dominio.')
    h_globe = K_AIR * _nusselt_sphere(v, a.globe_diameter_m) / a.globe_diameter_m
    h_wick = K_AIR * _nusselt_cylinder(v, a.wick_diameter_m) / a.wick_diameter_m
    ta_k = t + 273.15
    q_sw_globe = a.globe_solar_absorptivity * a.projected_fraction * s
    q_sw_wick = a.wick_solar_absorptivity * a.projected_fraction * s
    rho_air = p * 100.0 / (R_AIR * ta_k)
    rho_v_air = (rh / 100.0) * _saturated_vapor_density(t)
    hm_wick = h_wick / (rho_air * CP_AIR * a.lewis_number ** (2/3))

    def eq_globe(tg: float) -> float:
        tgk = tg + 273.15
        return (q_sw_globe + a.globe_lw_emissivity * SIGMA * (ta_k**4 - tgk**4)
                + h_globe * (t - tg))

    def eq_wick(tw: float) -> float:
        twk = tw + 273.15
        latent = 2.501e6 - 2370.0 * tw  # J/kg, aproximación
        evaporation = latent * hm_wick * (_saturated_vapor_density(tw) - rho_v_air)
        return (q_sw_wick + a.wick_lw_emissivity * SIGMA * (ta_k**4 - twk**4)
                + h_wick * (t - tw) - evaporation)

    tg = _root_bisect(eq_globe, t - 60.0, t + 70.0)
    tw = _root_bisect(eq_wick, t - 60.0, t + 70.0)
    wbgt_like = 0.7 * tw + 0.2 * tg + 0.1 * t
    return {
        'status': 'computed',
        'model': 'heatguard_simplified_energy_balance_v1',
        'wbgt_like_experimental_c': round(wbgt_like, 4),
        'virtual_natural_wet_bulb_c': round(tw, 4),
        'virtual_globe_c': round(tg, 4),
        'diagnostics': {
            'h_globe_w_m2k': round(h_globe, 3),
            'h_wick_w_m2k': round(h_wick, 3),
            'projected_shortwave_globe_w_m2': round(q_sw_globe, 2),
            'projected_shortwave_wick_w_m2': round(q_sw_wick, 2),
        },
        'assumptions': asdict(a),
        'normative_measurement': False,
        'risk_alerts_enabled': False,
        'limitations': [
            'PROXY EXPERIMENTAL no validado. No usar como medición WBGT de ISO 7243 ni para alarmas.',
            'Modelo estacionario: ignora respuesta temporal, geometría solar, radiación de superficies y fuentes industriales.',
            'El viento es LOCAL a altura de trabajo; no convertir automáticamente viento regional/10 m.',
            'No hay garantía de exactitud ni intervalo estadístico de confianza.',
        ],
    }
