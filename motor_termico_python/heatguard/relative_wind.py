"""Viento relativo: relaciones vectoriales, sin inferir viento desde IMU sola."""
from math import cos, sin, radians, hypot, isfinite


def relative_wind(wind_speed_m_s: float, worker_speed_m_s: float,
                  wind_bearing_deg: float | None = None,
                  walking_bearing_deg: float | None = None) -> dict:
    """Rumbos 0=N, 90=E; wind_bearing es dirección HACIA donde se mueve el aire.

    Meteorología suele informar dirección DESDE donde viene: convertir +180°.
    """
    if not all(isfinite(float(x)) and 0 <= x <= 60 for x in (wind_speed_m_s, worker_speed_m_s)):
        raise ValueError('Velocidades inválidas.')
    lower = abs(wind_speed_m_s - worker_speed_m_s)
    upper = wind_speed_m_s + worker_speed_m_s
    if (wind_bearing_deg is None) != (walking_bearing_deg is None):
        raise ValueError('Se requieren ambas direcciones, o ninguna.')
    speed = None
    if wind_bearing_deg is not None:
        if not (isfinite(wind_bearing_deg) and isfinite(walking_bearing_deg)):
            raise ValueError('Rumbos inválidos.')
        a = radians(wind_bearing_deg); b = radians(walking_bearing_deg)
        speed = hypot(wind_speed_m_s * sin(a) - worker_speed_m_s * sin(b),
                      wind_speed_m_s * cos(a) - worker_speed_m_s * cos(b))
    return {'relative_speed_m_s': None if speed is None else round(speed, 4),
            'possible_speed_range_m_s': [round(lower, 4), round(upper, 4)],
            'wind_direction_convention': 'direction_towards; meteorological FROM must rotate +180',
            'measured_local_airflow': False,
            'limitations': 'La IMU no mide el viento ni la velocidad absoluta; viento regional no equivale al viento de faena.'}
