from heatguard.release_acceptance import run_release_acceptance


def test_release_acceptance_matrix(tmp_path):
    report=run_release_acceptance(tmp_path/'out',tmp_path/'acceptance.sqlite')
    assert report['status']=='passed'
    assert report['scenario_count']==11
    assert report['physical_hardware_used'] is False
    assert all(check['passed'] for check in report['checks'])
