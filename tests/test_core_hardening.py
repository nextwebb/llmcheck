"""Regression checks for observed draft/parser/gate failure boundaries."""
import json
from types import SimpleNamespace

import pytest
import yaml

from llmcheck.judge import JudgeError, _call_openai_judge, parse_judge_response
from llmcheck.config import load_config
from llmcheck.suite_runner import SuiteRunError, run_suite


@pytest.mark.parametrize('confidence', [[], {}, None, 1])
def test_malformed_confidence_is_a_judge_error(confidence):
    payload = dict(missing_requirements=[], forbidden_claims_found=[],
                   unsupported_claims=[], reason='fixture', confidence=confidence)
    with pytest.raises(JudgeError, match='confidence'):
        parse_judge_response(json.dumps(payload))


def test_non_text_transport_is_a_judge_error():
    with pytest.raises(JudgeError, match='JSON text'):
        parse_judge_response(None)


@pytest.mark.parametrize('body', ['{', '[]', '{"choices":{}}', '{"choices":[null]}', '{"choices":[{"message":[]}]}'])
def test_malformed_provider_envelope_is_a_judge_error(monkeypatch, body):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return body.encode()
    monkeypatch.setenv('OPENAI_API_KEY', 'fake-test-key')
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: Response())
    config = SimpleNamespace(judge=SimpleNamespace(provider='openai', model='fake'))
    with pytest.raises(JudgeError):
        _call_openai_judge(config, 'fixture')


def test_provider_timeout_is_a_judge_error(monkeypatch):
    def timeout(*a, **k): raise TimeoutError('fixture timeout')
    monkeypatch.setenv('OPENAI_API_KEY', 'fake-test-key')
    monkeypatch.setattr('urllib.request.urlopen', timeout)
    config = SimpleNamespace(judge=SimpleNamespace(provider='openai', model='fake'))
    with pytest.raises(JudgeError, match='network error'):
        _call_openai_judge(config, 'fixture')


def make_suite(tmp_path, monkeypatch, function, tests):
    module = SimpleNamespace(answer=function)
    monkeypatch.setattr('llmcheck.suite_runner.import_callable', lambda *a, **k: module.answer)
    config_path = tmp_path / 'config.yaml'
    config_path.write_text('{}')
    path = tmp_path / 'suite.yaml'
    path.write_text(yaml.safe_dump({'runner': {'type': 'python', 'callable': 'fixture:answer'}, 'tests': tests}))
    return load_config(config_path), path


def case():
    return dict(id='probe', source_run_id='synthetic', source_reason='regression', inputs={'query':'hi'}, context=[], expected={}, judge={})


def test_empty_suite_cannot_report_success(tmp_path, monkeypatch):
    config, path = make_suite(tmp_path, monkeypatch, lambda **k: 'hi', [])
    with pytest.raises(SuiteRunError, match='no tests'):
        run_suite(config, path)


def test_async_runner_cannot_be_judged_as_coroutine_text(tmp_path, monkeypatch):
    async def answer(query): return query
    config, path = make_suite(tmp_path, monkeypatch, answer, [case()])
    with pytest.raises(SuiteRunError, match='synchronous adapter'):
        run_suite(config, path)


def test_import_time_failure_is_a_suite_error(tmp_path):
    from llmcheck.suite_runner import import_callable
    (tmp_path / 'broken_import_probe.py').write_text('raise RuntimeError("import fixture failure")')
    with pytest.raises(SuiteRunError, match='could not import module'):
        import_callable('broken_import_probe:answer', working_dir=tmp_path)


def test_low_confidence_remains_backward_compatible(tmp_path, monkeypatch):
    config, path = make_suite(tmp_path, monkeypatch, lambda query: query, [case()])
    payload = dict(missing_requirements=[], forbidden_claims_found=[],
                   unsupported_claims=[], reason='fixture uncertainty', confidence='low')
    result = run_suite(config, path, judge_transport=lambda *args: json.dumps(payload))
    assert result.passed is True
    assert result.results[0].judge_result.confidence == 'low'
