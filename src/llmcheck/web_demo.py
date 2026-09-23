"""Public synthetic case explorer. No keys, uploads, visitor storage or live calls."""
from __future__ import annotations
import argparse
from dataclasses import asdict
from functools import lru_cache
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit, parse_qs
import yaml
from . import __version__
from .storage.models import AppConfig, StorageConfig, JudgeConfig
from .suite_runner import run_suite

ASSETS = files('llmcheck').joinpath('demo_assets')
DATA = json.loads(ASSETS.joinpath('cases.json').read_text())
CASES = {c['id']: c for c in DATA['cases']}
LIVE_EVALUATION = json.loads(ASSETS.joinpath('live-evaluation.json').read_text())

def fixture_answer(query: str, response: str) -> str:
    return response

def literal_judge(_config, prompt: str) -> str:
    # Supplied per-case closure below; this name prevents accidental live fallback.
    raise RuntimeError('a per-case fixture transport is required')

@lru_cache(maxsize=12)
def evaluate_case(case_id: str) -> dict:
    case = CASES[case_id]
    text = case['response'].lower()
    payload = {'missing_requirements': [s for s in ['manager approval', '3-5 business days'] if s not in text],
               'forbidden_claims_found': ['instant'] if 'instant' in text else [],
               'unsupported_claims': [], 'reason': 'Literal fixture judge; no semantic assessment.', 'confidence': 'high'}
    suite = {'runner': {'type': 'python', 'callable': 'llmcheck.web_demo:fixture_answer'}, 'tests': [{
        'id': case_id, 'source_run_id': 'synthetic', 'source_reason': 'Public teaching fixture',
        'inputs': {'query': 'Can I get a $150 refund today?', 'response': case['response']},
        'context': [{'id': 'policy', 'text': DATA['policy']}],
        'expected': {'must_include': ['manager approval', '3-5 business days'], 'must_not_claim': ['instant']},
        'judge': {'type': 'rubric', 'pass_if': 'Follow the approved refund policy.'}}]}
    with tempfile.TemporaryDirectory(prefix='llmcheck-public-') as td:
        root = Path(td); path = root/'suite.yaml'; path.write_text(yaml.safe_dump(suite))
        config = AppConfig(root, StorageConfig(root/'unused.db'), JudgeConfig('openai', 'not-used'))
        result = run_suite(config, path, judge_transport=lambda *_: json.dumps(payload))
    return {'case': case, 'passed': result.passed, 'agreement': result.passed == case['expected_policy_compliant'],
            'evidence': asdict(result.results[0].judge_result), 'version': __version__,
            'execution': 'Actual LLMCheck runner and parser; injected literal judge; zero live model calls.'}

HTML = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>LLMCheck · Inspect the verdict</title>
<style>
:root{font-family:Inter,system-ui,sans-serif;color:#dce7f6;background:#0c1422;line-height:1.6}*{box-sizing:border-box}body{margin:0}nav,main,footer{max-width:1160px;margin:auto;padding:24px}nav{display:flex;justify-content:space-between;border-bottom:1px solid #253348}a{color:#9ec7ff;text-underline-offset:4px}nav strong{font-size:23px;color:white;letter-spacing:-1px}nav span{color:#93a6bf;font-size:13px}h1{font-size:clamp(36px,6vw,64px);line-height:1.08;letter-spacing:-2px;max-width:790px;margin:24px 0}h2{font-size:22px;margin-top:0}p{color:#aebed2;max-width:760px}.eyebrow{text-transform:uppercase;letter-spacing:2px;font-size:12px;color:#83b5fa;margin-top:38px}.links{display:flex;gap:22px;flex-wrap:wrap;margin:26px 0 36px}.badge{display:inline-block;padding:5px 10px;border-radius:5px;background:#20334a;font-size:12px}.workspace{display:grid;grid-template-columns:310px 1fr;gap:18px}.panel{border:1px solid #2b3c51;border-radius:14px;background:#111d2d;padding:24px}.cases{display:grid;gap:8px}button{font:inherit;text-align:left;color:#dce7f6;background:#17263a;border:1px solid #31445d;padding:12px;border-radius:8px;cursor:pointer}button:hover,button[aria-pressed=true]{border-color:#81b5fa;background:#213a57}button:focus-visible,a:focus-visible{outline:3px solid #b7d3ff;outline-offset:3px}.small{font-size:13px;color:#aebed2}.answer{font-size:20px;border-left:3px solid #85b8ff;padding:4px 0 4px 18px;margin:24px 0}.outcomes{display:grid;grid-template-columns:1fr 1fr;gap:12px}.outcome{background:#0c1422;border-radius:8px;padding:16px}.outcome strong{display:block;font-size:25px}.pass{color:#85ddbf}.fail{color:#ffb797}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#0c1422;padding:18px;border-radius:8px;color:#bfd7fa;font-size:13px}details{margin:24px 0}summary{cursor:pointer}footer{font-size:13px;color:#8ca0ba;border-top:1px solid #253348;margin-top:40px}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin-top:30px}.cards h2{font-size:17px}.cards p{font-size:14px}#status{min-height:28px} @media(max-width:760px){.workspace,.cards{grid-template-columns:1fr}.cases{grid-template-columns:1fr 1fr}.panel{padding:18px}nav span{display:none}} </style>
<nav><strong>LLMCheck<span> / by NextWebb</span></strong><a href="https://github.com/nextwebb/llmcheck">Source on GitHub ↗</a></nav>
<main><div class="eyebrow">Capture · Review · Replay</div><h1>A passing check deserves an explanation.</h1><p>Turn a bad LLM response into a reviewed regression case. Inspect the answer, the judge's evidence, and the rule that produced the verdict.</p><div class="links"><a href="#explorer">Explore 12 cases ↓</a><a href="/downloads/companion.zip">Download article companion</a><a href="https://github.com/nextwebb/llmcheck#quick-start">Run locally</a></div>
<p class="small"><span class="badge">SYNTHETIC CASE EXPLORER</span> Compare a literal fixture with a recorded OpenAI evaluation. No provider calls or API key required when using this explorer.</p>
<div class="links" role="group" aria-label="Evaluation mode"><button id="mode-literal" aria-pressed="true">Literal fixture</button><button id="mode-recorded" aria-pressed="false">Recorded OpenAI run</button></div><p id="mode-note" class="small"></p><div class="workspace" id="explorer"><section class="panel"><h2>Pick a response</h2><p class="small">The same policy, with different ways to get the answer right or wrong.</p><div class="cases" id="cases"></div></section><section class="panel" aria-label="Case evidence"><div id="status" role="status">Loading cases…</div><h2 id="case-title">Inspect a case</h2><p class="small">APPROVED TEACHING POLICY</p><p id="policy"></p><div class="answer" id="answer"></div><div class="outcomes"><div class="outcome">Runner verdict<strong id="verdict">—</strong></div><div class="outcome">Policy label<strong id="expected">—</strong></div></div><p id="explanation"></p><details open><summary>Judge evidence</summary><pre id="evidence"></pre></details><p class="small" id="execution"></p></section></div>
<div class="cards"><section class="panel"><h2>01 / Keep the failure</h2><p>Capture inputs, output and context in your own SQLite workspace. Flag a response worth reviewing.</p></section><section class="panel"><h2>02 / Review the expectation</h2><p>Write criteria a colleague can inspect. Approve the YAML before it becomes a check.</p></section><section class="panel"><h2>03 / Challenge the judge</h2><p>Rerun your application. Inspect false passes and false failures, not only an aggregate score.</p></section></div>
<details><summary>What this demo proves, and what it does not</summary><p>Twelve selected fixtures demonstrate the local runner, structured evidence parser and aggregation rule. The literal judge rejects valid paraphrases and can accept contradictions. The recorded OpenAI mode shows one completed twelve-request evaluation from 23 September 2026, not a live service or a repeated benchmark. Policy labels were authored for these examples; this is not a population benchmark or a general estimate of semantic-judge accuracy.</p><p>The local product can run a live OpenAI judge with your own environment key. This public explorer has no key and does not accept customer prompts or uploads. It is not the private local pilot dashboard.</p></details>
<details><summary>Privacy and deployment</summary><p>No accounts, cookies, analytics scripts or visitor prompt storage are used by this application. The hosting provider may process ordinary request logs. Render's free service may sleep when idle; its filesystem is temporary. Demo state is reconstructed from bundled synthetic fixtures.</p></details></main><footer>Built by Peterson Oaikhenah / NextWebb · <a href="https://github.com/nextwebb/llmcheck/issues">Report an issue</a> · <a href="https://github.com/nextwebb/llmcheck/blob/main/SECURITY.md">Security</a></footer>
<script>
const el=id=>document.getElementById(id);let active=0,mode='literal',selected=null,recorded=null;
function updateMode(){el('mode-literal').setAttribute('aria-pressed',String(mode==='literal'));el('mode-recorded').setAttribute('aria-pressed',String(mode==='recorded'));if(mode==='recorded'&&recorded){const c=recorded.confusion_counts;const agree=c.true_positive+c.true_negative;el('mode-note').textContent=`Saved ${recorded.model} run · ${recorded.started_at.slice(0,10)} · ${agree}/${recorded.evaluated_cases} agree · ${c.false_positive} false passes · ${c.false_negative} false failures. Selected synthetic fixtures, not representative accuracy. No live call on click.`;}else{el('mode-note').textContent='Injected literal-match judge: selected synthetic fixtures, no semantic model assessment.';}}
el('mode-literal').onclick=()=>{mode='literal';updateMode();if(selected)choose(selected)};
el('mode-recorded').onclick=()=>{mode='recorded';updateMode();if(selected)choose(selected)};
async function choose(id){selected=id;const token=++active;el('status').textContent='Running the selected fixture…';try{let d;if(mode==='recorded'){if(!recorded){const response=await fetch('/api/live-evaluation');if(!response.ok)throw Error('Request failed');recorded=await response.json();}const result=recorded.results.find(r=>r.id===id);if(!result||result.status!=='evaluated')throw Error('Unavailable result');d={case:result,passed:result.passed,agreement:result.passed===result.expected_policy_compliant,evidence:result.judge,execution:`Recorded ${recorded.model} response from ${recorded.started_at}. Saved evidence only; no live request on click. ${recorded.provenance_note}`};}else{const response=await fetch('/api/evaluate?case='+encodeURIComponent(id));if(!response.ok)throw Error('Request failed');d=await response.json();}if(token!==active)return;updateMode();document.querySelectorAll('.cases button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.id===id)));el('case-title').textContent=d.case.category.replaceAll('_',' ');el('answer').textContent=d.case.response;el('verdict').textContent=d.passed?'PASS':'FAIL';el('verdict').className=d.passed?'pass':'fail';el('expected').textContent=d.case.expected_policy_compliant?'Compliant':'Not compliant';el('explanation').textContent=d.case.expected_reason;el('evidence').textContent=JSON.stringify(d.evidence,null,2);el('execution').textContent=d.execution;el('status').textContent=d.agreement?'Judge agrees with the authored policy label.':'Disagreement: inspect this judge’s reported evidence.';}catch(e){el('status').textContent='Could not load this case. Please try again.'}}
async function start(){try{const r=await fetch('/api/cases');if(!r.ok)throw Error();const d=await r.json();el('policy').textContent=d.policy;d.cases.forEach(c=>{const b=document.createElement('button');b.type='button';b.dataset.id=c.id;b.textContent=c.id.replaceAll('_',' ');b.setAttribute('aria-pressed','false');b.onclick=()=>choose(c.id);el('cases').appendChild(b)});choose(d.cases[0].id)}catch(e){el('status').textContent='Could not load the demo. Refresh to retry.'}}start();
</script></html>'''

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass  # Provider access logs remain outside the application's control.
    def respond(self, status, body, kind='application/json; charset=utf-8'):
        self.send_response(status)
        for k,v in {'Content-Type':kind,'Content-Length':str(len(body)),'X-Content-Type-Options':'nosniff',
                    'Referrer-Policy':'no-referrer','Cache-Control':'no-store',
                    'Content-Security-Policy':"default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'"}.items(): self.send_header(k,v)
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        url=urlsplit(self.path)
        if len(self.path)>2048:return self.respond(414,b'{"error":"request too long"}')
        if url.path=='/':return self.respond(200,HTML.encode(),'text/html; charset=utf-8')
        if url.path=='/healthz':return self.respond(200,json.dumps({'status':'ok','version':__version__}).encode())
        if url.path=='/api/cases':return self.respond(200,json.dumps(DATA).encode())
        if url.path=='/api/live-evaluation':return self.respond(200,json.dumps(LIVE_EVALUATION).encode())
        if url.path=='/downloads/companion.zip':return self.respond(200,ASSETS.joinpath('companion.zip').read_bytes(),'application/zip')
        if url.path=='/api/evaluate':
            case_id=parse_qs(url.query).get('case',[''])[0]
            if case_id not in CASES:return self.respond(400,b'{"error":"unknown fixture"}')
            return self.respond(200,json.dumps(evaluate_case(case_id)).encode())
        return self.respond(404,b'{"error":"not found"}')

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--host',default='127.0.0.1');parser.add_argument('--port',type=int,default=int(os.getenv('PORT','8766')));args=parser.parse_args()
    # Evaluate finite fixtures before accepting requests, avoiding concurrent sys.path mutation.
    for case_id in CASES:evaluate_case(case_id)
    with ThreadingHTTPServer((args.host,args.port),Handler) as server:
        print(f'LLMCheck synthetic demo on {args.host}:{args.port}',flush=True)
        try:server.serve_forever()
        except KeyboardInterrupt:pass
if __name__=='__main__':main()
