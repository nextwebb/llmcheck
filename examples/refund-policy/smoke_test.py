"""Run the offline refund-policy, inspect artifacts, and verify overwrite protection."""
from pathlib import Path
import argparse,json,subprocess,sys,tempfile,os
p=argparse.ArgumentParser();p.add_argument('--repo',required=True,type=Path);args=p.parse_args()
root=Path(__file__).resolve().parent
with tempfile.TemporaryDirectory(prefix='refund-policy-smoke-') as tmp:
 out=Path(tmp)/'evidence'
 cmd=[sys.executable,str(root/'offline_demo.py'),'--repo',str(args.repo.resolve()),'--output',str(out)]
 env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'PYTHONDONTWRITEBYTECODE':'1'}
 first=subprocess.run(cmd,text=True,capture_output=True,env=env,check=True)
 provenance=json.loads((out/'provenance.json').read_text())
 results=json.loads((out/'replay-results.json').read_text())
 captured=json.loads((out/'captured-run.json').read_text())
 assert provenance['live_model_calls']==0
 assert len(results)==4 and [r['passed'] for r in results]==[False,True,False,False]
 assert all(r['passed']==r['expected_pass'] for r in results)
 assert captured['flagged'] and captured['tags']['workflow']=='SYNTHETIC-POC-DEMO'
 assert 'manager approval' in (out/'reviewed-case.yaml').read_text()
 assert (out/'generated-draft.yaml').read_text()!=(out/'reviewed-case.yaml').read_text()
 assert 'Your refund is instant.' in (out/'capture-cli.txt').read_text()
 before=(out/'replay-results.json').read_bytes()
 second=subprocess.run(cmd,text=True,capture_output=True,env=env)
 assert second.returncode!=0 and 'must be empty' in second.stderr
 assert before==(out/'replay-results.json').read_bytes()
 print(json.dumps({'status':'PASS','checks':['actual SDK capture and flag persisted','original generated draft retained separately','scripted atomic review retained','actual CLI show output','four injected-judge outcomes','existing evidence overwrite refused'],'live_model_calls':0,'source_commit':provenance['commit']},indent=2))
