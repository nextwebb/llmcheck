from pathlib import Path
import importlib.util
import json
import pytest

spec = importlib.util.spec_from_file_location('live_evaluation', Path(__file__).parents[1] / 'scripts/live_evaluation.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


def clean(_config, _prompt):
    return json.dumps(dict(missing_requirements=[], forbidden_claims_found=[], unsupported_claims=[], reason='test fixture', confidence='high'))


def test_opt_in_and_cap_precede_transport(tmp_path):
    def forbidden(*args):
        pytest.fail('transport must not run')
    for args in [dict(opt_in=False, limit=12), dict(opt_in=True, limit=13), dict(opt_in=True, limit=0)]:
        with pytest.raises(ValueError):
            live.evaluate(model='test', output=tmp_path/'out.json', transport=forbidden, **args)
    assert not (tmp_path/'out.json').exists()


def test_max_twelve_calls_counts_and_no_usage_invention(tmp_path):
    calls=[]
    def transport(config,prompt):
        calls.append(prompt)
        return clean(config,prompt)
    result=live.evaluate(model='test', output=tmp_path/'out.json', opt_in=True, transport=transport)
    assert len(calls)==12
    assert result['confusion_counts']==dict(true_positive=6,true_negative=0,false_positive=6,false_negative=0)
    assert result['usage'] is None and result['transport']=='injected_test_double'
    assert json.loads((tmp_path/'out.json').read_text())==result


def test_provider_error_stops_and_does_not_log_body(tmp_path):
    def transport(*args):
        raise RuntimeError('sensitive-provider-body-and-secret')
    result=live.evaluate(model='test', output=tmp_path/'out.json', opt_in=True, transport=transport)
    assert result['attempted_requests']==1 and result['errors']==1
    assert result['evaluated_cases']==0
    assert 'sensitive-provider' not in (tmp_path/'out.json').read_text()


def test_existing_evidence_not_overwritten(tmp_path):
    path=tmp_path/'out.json';path.write_text('original')
    with pytest.raises(FileExistsError):
        live.evaluate(model='test', output=path, opt_in=True, transport=clean)
    assert path.read_text()=='original'


def test_missing_key_is_local_error(monkeypatch,tmp_path):
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    with pytest.raises(ValueError,match='OPENAI_API_KEY'):
        live.evaluate(model='test', output=tmp_path/'out.json', opt_in=True)
    assert not (tmp_path/'out.json').exists()


def test_archive_provenance_does_not_require_git(monkeypatch, tmp_path):
    monkeypatch.setattr(live, "REPO", tmp_path)
    def forbidden(*args, **kwargs):
        pytest.fail("archive must not borrow a parent repository revision")
    monkeypatch.setattr(live.subprocess, "check_output", forbidden)
    assert live.source_commit() is None
