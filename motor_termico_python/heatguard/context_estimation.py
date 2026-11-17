"""Contexto cinemático opcional; NO estima viento a partir del MPU6050."""


def relative_airflow_scenario(inputs: dict[str, dict]) -> dict:
    """Rango geométrico condicionado a dos magnitudes escalares.

    No es una medición de viento real. Tampoco corrige la altura del pronóstico.
    Se mantiene FUERA del modelo físico Liljegren hasta calibración.
    """
    wind = inputs.get('wind_speed_m_s')
    speed = inputs.get('gps_speed_m_s')
    if not wind or not speed:
        return {'status': 'missing_inputs', 'required': ['wind_speed_m_s', 'gps_speed_m_s'],
                'used_in_wbgt': False}
    w, v = float(wind['value']), float(speed['value'])
    return {
        'status': 'illustrative_vector_range',
        'minimum_m_s': round(abs(w-v), 3), 'maximum_m_s': round(w+v, 3),
        'wind_source': wind['source'], 'worker_speed_source': speed['source'],
        'used_in_wbgt': False,
        'notes': 'Rango de geometría vectorial si ambas magnitudes se refirieran al mismo lugar; '
                 'viento a 10 m o regional NO representa necesariamente al trabajador. '
                 'El acelerómetro no puede medir el viento por sí solo.',
    }
