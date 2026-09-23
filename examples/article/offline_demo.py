"""Reproducible POC demo: real LLMCheck code, synthetic provider, injected judge.
No credentials, network requests, or existing user databases are used.
"""
from pathlib import Path
from types import SimpleNamespace
from dataclasses import asdict
from contextlib import redirect_stdout
from argparse import Namespace
import sys, json, io, socket, html, subprocess

import argparse
parser = argparse.ArgumentParser(description='Offline fixture demo using real LLMCheck APIs; not semantic model evaluation.')
parser.add_argument('--repo', required=True, type=Path, help='Local LLMCheck checkout (tested at commit6d101ae)')
parser.add_argument('--output', required=True, type=Path, help='New or empty output directory; existing evidence is never overwritten')
args = parser.parse_args()
REPO = args.repo.resolve()
ROOT = args.output.resolve()
if ROOT.exists() and any(ROOT.iterdir()):
    raise SystemExit('Output directory must be empty; choose a new directory.')
if not (REPO / 'src/llmcheck/suite_runner.py').is_file():
    raise SystemExit('Not an LLMCheck source checkout: ' + str(REPO))
ROOT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(REPO / 'src'))
sys.path.insert(0, str(ROOT))
# Deny network use during the fixture execution, even if a dependency changes.
def blocked(*args, **kwargs):
    raise RuntimeError('Network disabled for synthetic POC demo')
socket.socket.connect = blocked
socket.create_connection = blocked

from llmcheck import instrument_openai, add_context, add_tags, flag
from llmcheck.storage.sqlite import list_runs, save_pilot_review
from llmcheck.generation import draft_regression_case, dump_regression_case, initialize_suite_file, append_case_to_suite
from llmcheck.config import load_config
from llmcheck.suite_runner import run_suite
from llmcheck.cli import _show_command
from llmcheck.pilot import build_pilot_review
import yaml

db = ROOT / 'fixture.db'
if db.exists():
    raise SystemExit('Refusing to overwrite previous evidence database; use a fresh directory.')
policy = 'Refunds above $100 require manager approval and take 3-5 business days.'
class SyntheticCompletions:
    def create(self, **kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='Your refund is instant.'))])
client = SimpleNamespace(chat=SimpleNamespace(completions=SyntheticCompletions()))
client = instrument_openai(client, storage_path=db)
add_context([{'id':'synthetic-policy', 'text':policy}])
add_tags({'workflow':'SYNTHETIC-POC-DEMO', 'source':'scripted provider; no live model'})
client.chat.completions.create(model='synthetic-fixture-not-a-model', messages=[{'role':'user','content':'Can I get a $150 refund today?'}])
flag(reason='Scripted failure: claims instant refund and omits approval requirement')
run = list_runs(db)[0]
assert run.flagged and run.output_text == 'Your refund is instant.'
(ROOT/'captured-run.json').write_text(json.dumps(asdict(run), indent=2))
(ROOT/'llmcheck.yaml').write_text('storage:\n  path: fixture.db\njudge:\n  provider: openai\n  model: unused-in-fixture-demo\n')
log = io.StringIO()
with redirect_stdout(log):
    assert _show_command(Namespace(config=str(ROOT/'llmcheck.yaml'),run_id=run.id)) == 0
(ROOT/'capture-cli.txt').write_text(log.getvalue())

case = draft_regression_case(run, 'Require manager approval and 3-5 business days; do not claim "instant".')
(ROOT/'generated-draft.yaml').write_text(dump_regression_case(case))
# Explicit reviewer edit: split the broad generated correction into atomic criteria.
case['expected'] = {'must_include':['manager approval','3-5 business days'], 'must_not_claim':['instant']}
case['metadata']['reviewed_by'] = 'scripted demo review; synthetic data'
(ROOT/'reviewed-case.yaml').write_text(dump_regression_case(case))
(ROOT/'fixture_app.py').write_text("OUTPUT = ''\ndef answer_user(query):\n    return OUTPUT\n")
suite = ROOT/'fixture-suite.yaml'
initialize_suite_file(suite, runner_callable='fixture_app:answer_user')
append_case_to_suite(suite,case)

def literal_fixture_judge(config, prompt):
    # A deliberately narrow injected test double, NOT LLMCheck's semantic judge.
    output = prompt.split('Output:\n',1)[1].split('\nMust include:',1)[0].lower()
    return json.dumps({'missing_requirements':[s for s in case['expected']['must_include'] if s not in output],
        'forbidden_claims_found':[s for s in case['expected']['must_not_claim'] if s in output],
        'unsupported_claims':[], 'reason':'Synthetic fixture judge: literal matching only; no semantic grounding assessment.', 'confidence':'high'})

import fixture_app
scenarios = [
    ('Incorrect scripted response', 'Your refund is instant.', False),
    ('Corrected scripted response', policy, True),
    ('Missing timing requirement', 'You need manager approval.', False),
    ('Contradictory promise', policy+' It is instant.', False),
]
results=[]
for name, output, expected in scenarios:
    fixture_app.OUTPUT=output
    result=run_suite(load_config(ROOT/'llmcheck.yaml'),suite,judge_transport=literal_fixture_judge)
    assert result.passed is expected, name
    results.append({'scenario':name,'synthetic_output':output,'expected_pass':expected,**asdict(result)})
(ROOT/'replay-results.json').write_text(json.dumps(results,indent=2))
review=build_pilot_review(run,severity='low',root_cause='prompt_or_instruction_failure',review_outcome='confirmed_failure',business_impact='low',candidate_knowledge_type='none',reviewer_note='SYNTHETIC POC fixture; scripted failure and scripted classification, not a customer incident.')
save_pilot_review(db,review)
commit=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip()
(ROOT/'provenance.json').write_text(json.dumps({'repository':str(REPO),'commit':commit,'live_model_calls':0,'network_during_demo':'TCP connect functions blocked','fixture_scenarios':len(results),'tested_reference_commit':'6d101ae90781b8dc06965f57313445f8878cf6d6','reference_commit_matches':commit=='6d101ae90781b8dc06965f57313445f8878cf6d6','expected_outcomes_verified':True,'review':'scripted; generated draft explicitly edited to atomic checks','limits':['No live model or semantic judge evaluated','No production/adoption/performance claims','Captured latency measures local fake execution only','Dashboard metrics represent one synthetic incident']},indent=2))

print('PASS: capture, SQLite persistence, generated/reviewed YAML and four expected replay outcomes.')
print('Synthetic provider and injected literal judge; no live model calls.')
print('Evidence directory:', ROOT)
