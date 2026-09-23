from __future__ import annotations
import io
import json
import socket
from llmcheck import web_demo


def request(path):
    handler=object.__new__(web_demo.Handler);handler.path=path;handler.wfile=io.BytesIO()
    status=[];handler.send_response=status.append;handler.send_header=lambda *a:None;handler.end_headers=lambda:None
    handler.do_GET()
    return status[0],handler.wfile.getvalue()


def test_finite_fixtures_never_require_network(monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('Unexpected network')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(socket,'create_connection',forbidden)
    web_demo.evaluate_case.cache_clear()
    assert len(web_demo.CASES)==12
    results=[web_demo.evaluate_case(k) for k in web_demo.CASES]
    assert sum(r['agreement'] for r in results)==4
    assert all('zero live model calls' in r['execution'] for r in results)


def test_unknown_input_and_paths_do_not_execute(monkeypatch):
    monkeypatch.setattr(web_demo,'evaluate_case',lambda *a:(_ for _ in ()).throw(AssertionError('must not execute')))
    for path,expected in [('/api/evaluate?case=../../.env',400),('/../../.env',404),('/api/evaluate?case='+('x'*2100),414)]:
        status,body=request(path)
        assert status==expected
        assert 'error' in json.loads(body)


def test_recorded_live_route_is_saved_evidence_only(monkeypatch):
    def forbidden(*a,**kw):raise AssertionError('No provider call allowed')
    monkeypatch.setattr(socket.socket,'connect',forbidden)
    monkeypatch.setattr(web_demo,'evaluate_case',forbidden)
    status,body=request('/api/live-evaluation')
    payload=json.loads(body)
    assert status==200 and payload['model']=='gpt-4o-mini-2024-07-18'
    assert payload['confusion_counts']==dict(true_positive=5,true_negative=6,false_positive=0,false_negative=1)
    assert len(payload['results'])==12
    assert 'modified working tree' in payload['provenance_note']
    assert payload['usage'] is None
    assert all('judge' in r for r in payload['results'])
