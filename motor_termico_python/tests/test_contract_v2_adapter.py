"""Compatibilidad mínima con los datos lógicos de contrato v2; sin hardware real."""
import pytest
from integracion.telemetry_v2_adapter import convert_v2_to_heatguard_event
from heatguard.pipeline import evaluate


@pytest.fixture
def packet():
    return {"v":2,"deviceId":"HeatGuard Clip","receivedAt":1794000000000,
      "seq":513,"env":{"ok":True,"tempC":31.42,"rhPct":48.5,"heatIndexC":33.1},
      "motion":{"ok":True,"index":37},"battery":{"pct":76,"mV":3960},
      "load":104,"state":2,"pauses":3,"button":{"pressed":False}}


def test_v2_without_solar_or_wind_does_not_invent_wbgt(packet):
    event=convert_v2_to_heatguard_event(packet,zone_id="zona_prueba",environment="outdoor")
    result=evaluate(event)
    assert result["environmental_estimator_v18"]["status"]=="missing_inputs"
    assert set(result["environmental_estimator_v18"]["missing"])=={"solar_w_m2","wind_speed_m_s"}
    assert event["transport_metadata"]["simulated"] is True
    assert result["metrics"]["heat_index_c"]["value_c"]>0


def test_bad_version_rejected(packet):
    packet["v"]=1
    with pytest.raises(ValueError,match="v2"):
        convert_v2_to_heatguard_event(packet)


def test_v2_work_state_unknown_and_motion_not_metabolic(packet):
    event=convert_v2_to_heatguard_event(packet,simulated=False,worker_pseudonym="w042")
    assert event["context"]["activity_class"]=="unknown"
    assert event["context"]["work_state"]=="unknown"
    assert event["context"]["worker_id"]=="w042"
    assert any(x["parameter"]=="motion_index_v2" and x["unit"]=="index_0_100" for x in event["observations"])
    assert not any(x["parameter"]=="activity_rms_g" for x in event["observations"])


def test_external_environment_requires_provenance(packet):
    with pytest.raises(ValueError):
        convert_v2_to_heatguard_event(packet,extra_environment=[{"parameter":"solar_w_m2","value":450,"unit":"W/m2"}])


def test_derived_external_scenario_remains_external_not_measured(packet):
    extra=[
      {"parameter":"solar_w_m2","value":450,"unit":"W/m2","kind":"external","source":"STATION_DEMO","timestamp":"2026-11-06T00:00:00+00:00"},
      {"parameter":"wind_speed_m_s","value":1.2,"unit":"m/s","kind":"external","source":"STATION_DEMO","timestamp":"2026-11-06T00:00:00+00:00"}
    ]
    event=convert_v2_to_heatguard_event(packet,environment="outdoor",extra_environment=extra)
    out=evaluate(event)
    # Depending on staleness the fusion will reject stale data; it MUST NOT invent it.
    assert out["environmental_estimator_v18"]["status"] in ("computed","missing_inputs")
    assert all(x["kind"]=="external" for x in event["observations"][-2:])
