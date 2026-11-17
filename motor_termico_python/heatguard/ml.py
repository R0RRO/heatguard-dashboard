"""Entrenamiento FUTURO del residuo WBGT con pares físicos reales y referencia.

No contiene dataset inventado ni se entrena automáticamente con telemetría.
Emplea grupos independientes de sesión para evitar fugas temporales.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path

FEATURES = ('air_temperature_c', 'relative_humidity_pct', 'solar_w_m2',
            'wind_speed_m_s', 'pressure_hpa', 'wbgt_physical_c')
TARGET = 'wbgt_reference_c'
GROUP = 'session_id'


def _imports():
    try:
        import joblib
        import numpy as np
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.model_selection import GroupShuffleSplit
        from sklearn.metrics import mean_absolute_error
    except ImportError as exc:
        raise RuntimeError('Instala dependencias: python -m pip install -e ".[ml]"') from exc
    return joblib, np, RandomForestRegressor, GroupShuffleSplit, mean_absolute_error


def train_csv(input_csv: str, out_path: str, *, min_samples: int = 40,
              min_sessions: int = 4, seed: int = 42) -> dict:
    joblib, np, RandomForestRegressor, GroupShuffleSplit, mae = _imports()
    with open(input_csv, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    required = set(FEATURES) | {TARGET, GROUP}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f'CSV debe contener columnas: {sorted(required)}')
    if len(rows) < min_samples or len(set(r[GROUP] for r in rows)) < min_sessions:
        raise ValueError('Mínimo 40 pares y 4 sesiones independientes de referencia (configurable para investigación).')
    # Rechazamos etiquetas no observadas: registro de referencia y sus metadatos.
    for r in rows:
        if r.get('reference_instrument_id', '').strip() == '' or r.get('reference_measured', '').strip().lower() != 'true':
            raise ValueError('Cada etiqueta WBGT requiere reference_instrument_id y reference_measured=true.')
    x = np.array([[float(r[k]) for k in FEATURES] for r in rows])
    y = np.array([float(r[TARGET]) - float(r['wbgt_physical_c']) for r in rows])
    groups = np.array([r[GROUP] for r in rows])
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError('No se admiten NaN ni infinitos en datos de calibración.')
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed)
    tr, te = next(splitter.split(x, y, groups))
    # Modelo no sirve si una sola sesión termina en test.
    model = RandomForestRegressor(n_estimators=120, min_samples_leaf=3, random_state=seed, n_jobs=1)
    model.fit(x[tr], y[tr])
    baseline_mae = float(mae(y[te], np.zeros_like(y[te])))
    predicted_residual = model.predict(x[te])
    corrected_mae = float(mae(y[te], predicted_residual))
    # Ajuste final con todos los datos disponibles, tras evaluar con sesiones separadas.
    final = RandomForestRegressor(n_estimators=120, min_samples_leaf=3, random_state=seed, n_jobs=1)
    final.fit(x, y)
    metadata = {
        'status': 'research_trained_not_safety_validated', 'features': list(FEATURES),
        'training_rows': int(len(rows)), 'training_sessions': int(len(set(groups))),
        'holdout_rows': int(len(te)), 'holdout_sessions': int(len(set(groups[te]))),
        'baseline_mae_c': round(baseline_mae, 4), 'corrected_mae_c': round(corrected_mae, 4),
        'trained_utc': datetime.now(timezone.utc).isoformat(),
        'warning': 'No equivale a validación externa ni certificación ISO; evaluar en faenas no vistas.',
    }
    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # joblib utiliza pickle: cargar SOLO archivos entrenados localmente y confiables.
    joblib.dump({'model': final, 'metadata': metadata}, path)
    metadata['artifact_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_suffix(path.suffix + '.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    return metadata


class ResidualModel:
    def __init__(self, path: str, *, expected_sha256: str | None = None):
        joblib, *_ = _imports()
        artifact = Path(path)
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if expected_sha256 is not None and not hmac.compare_digest(digest, expected_sha256.lower()):
            raise ValueError('SHA-256 del modelo ML no coincide; se bloquea la carga pickle/joblib')
        bundle = joblib.load(artifact)  # SOLO artefactos confiables, nunca subida del usuario.
        if bundle['metadata']['features'] != list(FEATURES):
            raise ValueError('Incompatibilidad de versión del modelo/factores')
        self.bundle = bundle
        self.artifact_sha256 = digest
        self.integrity_verified = expected_sha256 is not None

    def predict(self, selected_values: dict[str, float]) -> dict:
        missing = [k for k in FEATURES if k not in selected_values]
        if missing:
            return {'status': 'missing_inputs', 'missing': missing}
        x = [[float(selected_values[k]) for k in FEATURES]]
        correction = float(self.bundle['model'].predict(x)[0])
        corrected = float(selected_values['wbgt_physical_c']) + correction
        return {'status': 'research_prediction', 'wbgt_hybrid_c': round(corrected, 2),
                'residual_c': round(correction, 2), 'model_metadata': self.bundle['metadata'],
                'artifact_sha256': self.artifact_sha256,
                'artifact_integrity_verified': self.integrity_verified,
                'normative_measurement': False, 'safety_alert_enabled': False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--csv', required=True)
    p.add_argument('--output', default='models/wbgt_residual.joblib')
    args = p.parse_args()
    print(json.dumps(train_csv(args.csv, args.output), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
