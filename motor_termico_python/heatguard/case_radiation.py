"""Laboratorio de superficie térmica para un futuro termistor de carcasa.

NO es un termómetro de globo, un piránometro, ni un modelo WBGT validado.
Se usa un balance energético *por unidad de área* con coeficiente convectivo
EMPÍRICO HIPOTÉTICO y radiación de onda larga del entorno a T_a.

La inversión T_superficie -> irradiancia no es identificable sin viento,
absorptividad, geometría, emisión LW y calor interno conocidos.
"""
from __future__ import annotations
from dataclasses import dataclass, asdict
from math import isfinite, sqrt

STEFAN_BOLTZMANN = 5.670374419e-8

@dataclass(frozen=True)
class CaseAssumptions:
    solar_absorptivity: float = 0.35   # experimento: material/claro (sin medir)
    infrared_emissivity: float = 0.90  # experimento
    h_still_w_m2k: float = 5.0         # convección natural (valor hipotético)
    h_wind_factor_w_m2k: float = 4.0   # h = h_still + factor*sqrt(v)
    internal_heat_w_m2: float = 0.0    # fuga de la electrónica / contacto
    effective_incidence_fraction: float = 1.0  # radiación sobre superficie; sin modelo geométrico
    heat_capacity_area_j_m2k: float = 250.0    # respuesta dinámica hipotética


def _check(t_air: float, t_surface: float, wind: float, a: CaseAssumptions) -> None:
    if not all(isfinite(float(x)) for x in (t_air, t_surface, wind, *asdict(a).values())):
        raise ValueError('Todos los parámetros deben ser finitos.')
    if not (-15 <= t_air <= 70 and -30 <= t_surface <= 100 and 0 <= wind <= 25):
        raise ValueError('Fuera del dominio de estudio.')
    if not (0 < a.solar_absorptivity <= 1 and 0 < a.infrared_emissivity <= 1 and
            0 < a.effective_incidence_fraction <= 1 and a.h_still_w_m2k > 0 and
            a.h_wind_factor_w_m2k >= 0 and a.heat_capacity_area_j_m2k > 0):
        raise ValueError('Supuestos físicos inválidos.')


def h_convection(wind_m_s: float, a: CaseAssumptions) -> float:
    if not isfinite(wind_m_s) or wind_m_s < 0:
        raise ValueError('Velocidad no válida.')
    return a.h_still_w_m2k + a.h_wind_factor_w_m2k * sqrt(wind_m_s)


def net_surface_heat_flux_w_m2(t_surface_c: float, t_air_c: float,
                                absorbed_solar_w_m2: float, wind_m_s: float,
                                a: CaseAssumptions = CaseAssumptions()) -> float:
    _check(t_air_c, t_surface_c, wind_m_s, a)
    if not isfinite(absorbed_solar_w_m2) or absorbed_solar_w_m2 < 0:
        raise ValueError('Irradiancia absorbida inválida.')
    # Modelo LW deliberadamente simplificado: entorno radiante a T_aire.
    q_lw = a.infrared_emissivity * STEFAN_BOLTZMANN * ((t_air_c + 273.15)**4 - (t_surface_c + 273.15)**4)
    q_cv = h_convection(wind_m_s, a) * (t_air_c - t_surface_c)
    return absorbed_solar_w_m2 + q_lw + q_cv + a.internal_heat_w_m2


def surface_equilibrium_c(t_air_c: float, solar_w_m2: float, wind_m_s: float,
                          a: CaseAssumptions = CaseAssumptions()) -> float:
    _check(t_air_c, t_air_c, wind_m_s, a)
    if not isfinite(solar_w_m2) or not 0 <= solar_w_m2 <= 2000:
        raise ValueError('solar_w_m2 inválido.')
    absorbed = a.solar_absorptivity * a.effective_incidence_fraction * solar_w_m2
    lo, hi = max(-30, t_air_c - 70), min(100, t_air_c + 80)
    if net_surface_heat_flux_w_m2(lo, t_air_c, absorbed, wind_m_s, a) < 0 or net_surface_heat_flux_w_m2(hi, t_air_c, absorbed, wind_m_s, a) > 0:
        raise ArithmeticError('La raíz del balance sale del dominio de estudio.')
    for _ in range(75):
        mid = (lo + hi) / 2
        if net_surface_heat_flux_w_m2(mid, t_air_c, absorbed, wind_m_s, a) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def inferred_solar_for_wind(t_surface_c: float, t_air_c: float, wind_m_s: float,
                           a: CaseAssumptions = CaseAssumptions()) -> float:
    """Retorna irradiancia REQUERIDA por el modelo, no una observación de radiación.

    Permite resultados negativos: corresponden a incoherencia con los supuestos;
    no corregirlos silenciosamente a cero.
    """
    _check(t_air_c, t_surface_c, wind_m_s, a)
    q_with_solar_zero = net_surface_heat_flux_w_m2(t_surface_c, t_air_c, 0.0, wind_m_s, a)
    return -q_with_solar_zero / (a.solar_absorptivity * a.effective_incidence_fraction)


def ambiguity_study(t_surface_c: float, t_air_c: float, wind_min_m_s: float,
                    wind_max_m_s: float, *, points: int = 15,
                    assumptions: CaseAssumptions = CaseAssumptions()) -> dict:
    if not (2 <= points <= 500 and 0 <= wind_min_m_s < wind_max_m_s <= 25):
        raise ValueError('Rango de viento/puntos inválido.')
    readings = []
    for i in range(points):
        w = wind_min_m_s + i * (wind_max_m_s - wind_min_m_s) / (points - 1)
        readings.append({'wind_m_s_assumed': round(w, 4),
                         'required_incident_solar_w_m2': round(inferred_solar_for_wind(t_surface_c, t_air_c, w, assumptions), 3)})
    solar = [r['required_incident_solar_w_m2'] for r in readings]
    return {
        'purpose': 'research_only', 'temperature_surface_c': t_surface_c,
        'temperature_air_c': t_air_c, 'case_assumptions': asdict(assumptions),
        'conditional_results': readings,
        'spread_of_conditional_solar_w_m2': round(max(solar) - min(solar), 3),
        'solar_is_measured': False, 'wbgt_is_measured': False,
        'identified': False,
        'interpretation': 'Una temperatura superficial sola NO determina radiación si viento, orientación, absorptividad y calor interno son desconocidos.',
    }


def relative_brightness(local_lux: float, reference_lux: float) -> dict:
    """Señal óptica relativa para buscar sombra; NO convierte lux a W/m²."""
    if not all(isfinite(float(x)) for x in (local_lux, reference_lux)) or local_lux < 0 or reference_lux <= 0:
        raise ValueError('Iluminancia inválida.')
    return {'brightness_fraction': round(local_lux / reference_lux, 4),
            'unit': 'ratio', 'solar_irradiance_w_m2': None,
            'status': 'context_only', 'notes': 'Requiere referencia óptica comparable en hora, orientación y espectro; no mide calor radiante industrial.'}
