from pathlib import Path
import json
import sys
import argparse
from scripts.demo_modules import make_modules
p=argparse.ArgumentParser();p.add_argument('folder');p.add_argument('phase');a=p.parse_args()
inbox=Path(a.folder);inbox.mkdir(parents=True,exist_ok=True)
if a.phase=='seed':
    make_modules(inbox,'market-a',['market'],as_of='2026-09-24',missing=True)
    industry_folder=make_modules(inbox,'industry-a',['industries'],as_of='2026-09-25')
    rows=json.loads((industry_folder/'industries.json').read_text(encoding='utf-8'))
    rows=[{**rows[i%6],'id':f'SIM-{i:03}','name':f'演示行业 {i:03}'} for i in range(80)]
    payload=json.dumps(rows,ensure_ascii=False).encode('utf-8');(industry_folder/'industries.json').write_bytes(payload)
    import hashlib
    m=json.loads((industry_folder/'manifest.json').read_text(encoding='utf-8'));m['modules']['industries']['file']['sha256']=hashlib.sha256(payload).hexdigest();(industry_folder/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
    make_modules(inbox,'stocks-a',['stocks'],as_of='2026-09-28',stock_count=5000,missing=True,csv_stocks=True)
    make_modules(inbox,'report-a',['reports'],as_of='2026-09-21')
elif a.phase=='pending':
    make_modules(inbox,'stocks-b',['stocks'],as_of='2026-09-28',revision=2,state='pending',stock_count=3)
elif a.phase=='publish':
    make_modules(inbox,'stocks-b',['stocks'],as_of='2026-09-28',revision=2,stock_count=3,missing=True)
elif a.phase=='remove-report':
    folder=make_modules(inbox,'report-b',['reports'],as_of='2026-09-21',revision=2)
    (folder/'reports.json').write_text('[]',encoding='utf-8')
    import hashlib
    m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'));m['modules']['reports']['file']['sha256']=hashlib.sha256(b'[]').hexdigest();(folder/'manifest.json').write_text(json.dumps(m),encoding='utf-8')