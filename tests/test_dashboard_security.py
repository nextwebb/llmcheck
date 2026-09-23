from __future__ import annotations
import io
import json
import re
import shutil
import subprocess
from pathlib import Path
import pytest
from llmcheck import pilot_dashboard as dashboard


def test_stored_text_is_escaped_in_all_dashboard_surfaces():
    node=shutil.which('node')
    if not node:
        pytest.skip('Node.js needed to execute dashboard rendering test')
    attack='<img src=x onerror="alert(1)">&\''
    payload={'summary':{'total_reviews':attack},'generated_at':attack,
             'reviews':[{k:attack for k in ['run_id','created_at','workflow','root_cause','missing_context_subtype','review_outcome','candidate_knowledge_type']}],
             'knowledge':[{'knowledge_type':attack,'title':attack,'confidence':attack,'usage_modes':[attack]}]}
    script=re.search(r'<script>(.*?)</script>',dashboard._build_index_html(),re.S).group(1)
    harness="const nodes={};const document={getElementById:id=>(nodes[id]??={innerHTML:''})};const setInterval=()=>{};const fetch=async()=>({json:async()=>("+json.dumps(payload)+")});\n"
    harness+=script+"\nrefresh().then(()=>console.log(JSON.stringify(nodes)));"
    result=subprocess.run([node,'-e',harness],text=True,capture_output=True,check=True)
    rendered=json.loads(result.stdout)
    for key in ['summary','reviews','knowledge','killtest']:
        html=rendered[key]['innerHTML']
        assert '<img' not in html
        assert '&lt;img' in html
        assert '&quot;' in html and '&#39;' in html and '&amp;' in html


def test_head_writes_no_body_but_get_does(monkeypatch,tmp_path):
    holders={}
    class FakeServer:
        def __init__(self,address,handler):holders['handler']=handler
        def serve_forever(self):pass
        def server_close(self):pass
    monkeypatch.setattr(dashboard,'ThreadingHTTPServer',FakeServer)
    monkeypatch.setattr(dashboard,'list_pilot_reviews',lambda *a,**kw:[])
    monkeypatch.setattr(dashboard,'list_knowledge_entries',lambda *a,**kw:[])
    dashboard.serve_pilot_dashboard(tmp_path/'unused.db','127.0.0.1',0)
    for path in ['/', '/api/pilot']:
        for method in ['HEAD','GET']:
            handler=object.__new__(holders['handler']);handler.path=path;handler.wfile=io.BytesIO()
            headers={};handler.send_response=lambda code:None
            handler.send_header=lambda k,v:headers.update({k:v})
            handler.end_headers=lambda:None
            getattr(handler,'do_'+method)()
            assert int(headers['Content-Length'])>0
            if method=='HEAD':assert handler.wfile.getvalue()==b''
            else:assert len(handler.wfile.getvalue())==int(headers['Content-Length'])
