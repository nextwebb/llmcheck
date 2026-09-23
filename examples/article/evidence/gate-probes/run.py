"""Offline probe of existing verdict logic; synthetic responses are not model evaluations."""
from pathlib import Path
import json, sys, subprocess
import os
ROOT=Path(os.environ['LLMCHECK_REPO']).expanduser().resolve()
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'src'))
from llmcheck.config import load_config
from llmcheck.suite_runner import run_suite,SuiteRunError
from llmcheck.generation import draft_regression_case
from llmcheck.storage.models import RunRecord
(OUT/'probe_runner.py').write_text('def answer(query):\n    return "Refunds require manager approval."\n')
(OUT/'config.yaml').write_text('storage:\n  path: probe.db\njudge:\n  provider: openai\n  model: unused-offline-probe\n')
(OUT/'suite.yaml').write_text('''runner:
  type: python
  callable: probe_runner:answer
tests:
  - id: gate_probe
    source_run_id: synthetic_001
    source_reason: synthetic architecture probe
    inputs:
      query: Can I get a refund?
    context: []
    expected:
      must_include: [manager approval]
      must_not_claim: []
    judge:
      type: rubric
      pass_if: Require manager approval.
''')
config=load_config(OUT/'config.yaml')
def payload(confidence='high',missing=None):
 return json.dumps({'missing_requirements':missing or [],'forbidden_claims_found':[],'unsupported_claims':[],'reason':'Injected synthetic probe response','confidence':confidence})
cases=[('high_confidence_empty_arrays',payload(),True),('low_confidence_empty_arrays',payload('low'),True),('one_reported_violation',payload(missing=['manager approval']),False),('malformed_json','{',None)]
results=[]
for name,response,expected in cases:
 try:
  result=run_suite(config,OUT/'suite.yaml',judge_transport=lambda *_args,r=response:r)
  row={'case':name,'injected_judge_response':response,'actual_status':'PASS' if result.passed else 'FAIL','actual_passed':result.passed,'expected_passed':expected}
  assert expected is not None and result.passed is expected,row
 except SuiteRunError as exc:
  row={'case':name,'injected_judge_response':response,'actual_status':'ERROR','error':str(exc),'expected_status':'ERROR'}
  assert expected is None and 'invalid JSON' in str(exc),row
 results.append(row)
commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
record={'source_commit':commit,'source_root':str(ROOT),'scope':'Existing run_suite with offline Python runner and injected synthetic judge responses; no network or model evaluation','results':results,'assertions_passed':4,'limits':['Deterministic gate behavior only, not semantic judge accuracy','Confidence is parsed but not used in verdict','One deliberately inconsistent judge response demonstrates trust in reported arrays']}
(OUT/'results.json').write_text(json.dumps(record,indent=2)+'\n')
run=RunRecord(id='synthetic_001',created_at='2026-09-23T00:00:00Z',input_json={'user_input':'Can I get a refund?'},output_text='Refunds are instant.',messages=[],context=[],tags={},metadata={},flagged=True,flag_reason='Synthetic failure')
correction='Include "manager approval".'
draft=draft_regression_case(run,correction)
assert draft['expected']['must_include']==[correction]
assert draft['expected']['must_not_claim']==['manager approval']
(OUT/'draft-probe.json').write_text(json.dumps({'source_commit':commit,'correction':correction,'generated_case':draft,'finding':'The whole correction is put in must_include; its quoted required phrase is also extracted as forbidden. Human editing is needed.','assertions_passed':2},indent=2)+'\n')
print(json.dumps({'gate_cases':len(results),'assertions_passed':6,'statuses':{r['case']:r['actual_status'] for r in results},'source_commit':commit},indent=2))
