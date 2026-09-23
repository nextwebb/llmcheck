"""Hand-authored adversarial experiment for an INJECTED literal judge, not the default semantic judge."""
from pathlib import Path
import sys,socket,json,csv,subprocess,tempfile
from dataclasses import asdict
ROOT=Path(__file__).resolve().parent
import os
REPO=Path(os.environ['LLMCHECK_REPO']).expanduser().resolve()
sys.path.insert(0,str(REPO/'src'))
def blocked(*a,**kw):raise RuntimeError('Network disabled for synthetic fixture experiment')
socket.socket.connect=blocked
socket.create_connection=blocked
from llmcheck.config import load_config
from llmcheck.suite_runner import run_suite
POLICY='Refunds above $100 require manager approval and take 3-5 business days. Approval is not guaranteed and no cash bonus is promised.'
# These policy labels and reasons are authored BEFORE invoking any runner or judge.
CASES=[
 ('literal_clear','compliant_literal','Refunds above $100 require manager approval and take 3-5 business days.',True,'States both requirements; no contradictory or unsupported promise.'),
 ('literal_no_guarantee','compliant_literal','Manager approval is required. Processing takes 3-5 business days; approval is not guaranteed.',True,'States both requirements and accurately denies guaranteed approval.'),
 ('paraphrase_supervisor','compliant_paraphrase','For a refund over $100, a manager must approve it, and processing takes three to five business days.',True,'Faithful paraphrase preserves approval and processing window.'),
 ('paraphrase_both','compliant_paraphrase','A refund above $100 needs approval from a manager and takes between three and five business days.',True,'Both policy facts expressed without literal required phrases.'),
 ('negated_instant','compliant_negation','Refunds above $100 require manager approval and take 3-5 business days. They are not instant.',True,'Explicitly denies instant refund; does not promise one.'),
 ('negated_claim','compliant_negation','Manager approval is required and processing takes 3-5 business days. Do not expect an instant refund.',True,'Required facts plus denial of immediacy are compliant.'),
 ('missing_approval','missing_fact','Refunds above $100 take 3-5 business days.',False,'Omits required manager approval.'),
 ('missing_timing','missing_fact','Refunds above $100 require manager approval.',False,'Omits required processing window.'),
 ('contradiction_approval','contradiction_with_keywords','Manager approval is not required for refunds above $100; processing takes 3-5 business days.',False,'Contains approval words but expressly contradicts required approval.'),
 ('contradiction_timing','contradiction_with_keywords','Refunds above $100 require manager approval, but do not take 3-5 business days; the money arrives today.',False,'Contains timing words but contradicts processing window.'),
 ('unsupported_guarantee','unsupported_extra','Refunds above $100 require manager approval and take 3-5 business days. Approval is guaranteed.',False,'Adds an unsupported guarantee directly excluded by policy.'),
 ('unsupported_bonus','unsupported_extra','Refunds above $100 require manager approval and take 3-5 business days. You also receive a guaranteed $25 cash bonus.',False,'Adds a guaranteed cash benefit not promised by policy.'),
]
cases=[dict(id=i,category=c,response=t,expected_policy_compliant=e,expected_reason=r) for i,c,t,e,r in CASES]
(ROOT/'cases.json').write_text(json.dumps({'policy':POLICY,'label_provenance':'Hand-authored expectations defined before runner invocation; not live-model labels or independent adjudication.','cases':cases},indent=2)+'\n')
# Requirements exactly match the earlier demo. Unsupported claims are deliberately not checked.
required=['manager approval','3-5 business days'];forbidden=['instant']
def literal_fixture_judge(config,prompt):
 output=prompt.split('Output:\n',1)[1].split('\nMust include:',1)[0].lower()
 return json.dumps({'missing_requirements':[x for x in required if x not in output],'forbidden_claims_found':[x for x in forbidden if x in output],'unsupported_claims':[],'reason':'Injected demo literal judge; substring matching only, no semantic assessment.','confidence':'high'})
import yaml
with tempfile.TemporaryDirectory(prefix='isolated-',dir=ROOT) as td:
 work=Path(td);(work/'fixture_app.py').write_text("OUTPUT=''\ndef answer_user(query):\n    return OUTPUT\n")
 sys.path.insert(0,str(work));import fixture_app
 configpath=work/'config.yaml';configpath.write_text('storage:\n  path: unused-isolated.db\njudge:\n  provider: openai\n  model: unused-injected-judge\n')
 suitepath=work/'suite.yaml'
 suite={'runner':{'type':'python','callable':'fixture_app:answer_user'},'tests':[{'id':'refund_policy','source_run_id':'synthetic-authored-fixture','source_reason':'Controlled fixture experiment','metadata':{'reviewed_by':'hand-authored experiment; not independent adjudication'},'inputs':{'query':'Can I get a refund above $100?'},'context':[{'id':'policy','text':POLICY}],'expected':{'must_include':required,'must_not_claim':forbidden},'judge':{'type':'rubric','pass_if':'State required approval and processing window without contradictions, guaranteed approval or cash bonus.'}}]}
 suitepath.write_text(yaml.safe_dump(suite,sort_keys=False));results=[]
 for case in cases:
  fixture_app.OUTPUT=case['response'];result=run_suite(load_config(configpath),suitepath,judge_transport=literal_fixture_judge)
  exp=case['expected_policy_compliant'];got=result.passed
  outcome='true_positive' if exp and got else 'false_negative' if exp else 'false_positive' if got else 'true_negative'
  results.append({**case,'literal_judge_passed':got,'classification':outcome,'agreement':got==exp,'runner_result':asdict(result)})
counts={k:sum(r['classification']==k for r in results) for k in ['true_positive','true_negative','false_positive','false_negative']}
categorycounts={}
for r in results:
 d=categorycounts.setdefault(r['category'],{'count':0,'expected_compliant':0,'judge_pass':0,'agreement':0,'false_positive':0,'false_negative':0})
 d['count']+=1;d['expected_compliant']+=int(r['expected_policy_compliant']);d['judge_pass']+=int(r['literal_judge_passed']);d['agreement']+=int(r['agreement'])
 if r['classification'] in ['false_positive','false_negative']:d[r['classification']]+=1
commit=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip()
summary={'subject':'Injected demo literal-match judge ONLY; not LLMCheck default semantic judge','positive_class':'policy compliant / judge PASS','policy':POLICY,'source_repository':str(REPO),'source_commit':commit,'case_count':len(results),'expected_compliant':sum(r['expected_policy_compliant'] for r in results),'expected_noncompliant':sum(not r['expected_policy_compliant'] for r in results),'agreement_count':sum(r['agreement'] for r in results),'disagreement_count':sum(not r['agreement'] for r in results),'confusion_counts':counts,'category_counts':categorycounts,'live_model_calls':0,'network':'blocked during fixture execution','label_provenance':'Transparent hand-authored policy expectations, fixed before runner invocation. Not independent human evaluation.','judge_rules':{'required_substrings':required,'forbidden_substrings':forbidden,'unsupported_claims':'Always empty; limitation deliberately preserved from earlier demo'},'limitations':['Twelve deliberately selected adversarial fixtures, not representative or random sampling.','No estimate of real-world accuracy, generalization, production reliability or default semantic-judge performance.','Actual LLMCheck suite_runner and judge-response parser used; fake application outputs and injected literal judge.','No runtime or latency performance claim.']}
assert len(results)==12 and counts=={'true_positive':2,'true_negative':2,'false_positive':4,'false_negative':4}
(ROOT/'results.json').write_text(json.dumps(results,indent=2)+'\n')
(ROOT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
with (ROOT/'results.csv').open('w',newline='') as f:
 fields=['id','category','response','expected_policy_compliant','expected_reason','literal_judge_passed','classification','agreement'];writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows({k:r[k] for k in fields} for r in results)
print(json.dumps({'case_count':12,'confusion_counts':counts,'agreement_count':summary['agreement_count'],'subject':summary['subject']},indent=2))
