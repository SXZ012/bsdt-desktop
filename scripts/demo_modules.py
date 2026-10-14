"""Schema v2 simulation: independently publish one or more result modules."""
import argparse
import csv
import hashlib
import io
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from scripts.demo_upload import make_batch
BASE=Path(__file__).resolve().parents[1]

def make_modules(inbox,bid,modules=None,as_of='2026-09-28',revision=1,state='published',csv_stocks=False,stock_count=25,missing=False):
    modules=modules or ['market','industries','stocks','reports']
    folder=inbox/bid;folder.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        seed=make_batch(Path(temporary),'seed',as_of)
        contents={kind:json.loads((seed/(kind+'.json')).read_text(encoding='utf-8')) for kind in modules}
    if 'stocks' in contents:
        template=contents['stocks'][0]
        contents['stocks']=[{**template,'code':f'{i:06}','name':f'演示标的 {i:02}'} for i in range(1,stock_count+1)]
        if missing and contents['stocks']:
            for key in ('industry','status','reason','next_check'):
                contents['stocks'][0].pop(key,None)
    if missing and 'market' in contents:
        contents['market']['metrics'][0]['value']=None
    manifest={'schema_version':2,'batch_id':bid,'modules':{}}
    for kind,data in contents.items():
        name=kind+'.json'
        if csv_stocks and kind=='stocks' and data:
            name='stocks.csv';stream=io.StringIO(newline='')
            writer=csv.DictWriter(stream,fieldnames=['code','name','industry','status','reason','next_check']);writer.writeheader();writer.writerows(data);content=stream.getvalue().encode('utf-8-sig')
        else:
            content=json.dumps(data,ensure_ascii=False,indent=2).encode('utf-8')
        (folder/name).write_bytes(content)
        manifest['modules'][kind]={'as_of':as_of,'revision':revision,'generated_at':datetime.now(timezone.utc).isoformat(),'sample':True,'source':'BSDT模块独立更新模拟','complete':state!='incomplete','confirmed':state=='published','confirmed_by':'模拟确认人' if state=='published' else '', 'file':{'name':name,'sha256':hashlib.sha256(content).hexdigest()}}
    temp=folder/'manifest.json.tmp';temp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');temp.replace(folder/'manifest.json')
    return folder

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--batch',required=True);p.add_argument('--modules',nargs='+',choices=['market','industries','stocks','reports'],default=['stocks']);p.add_argument('--date',default='2026-09-28');p.add_argument('--revision',type=int,default=1);p.add_argument('--state',choices=['published','pending','incomplete'],default='published');p.add_argument('--count',type=int,default=25);p.add_argument('--csv',action='store_true');p.add_argument('--missing',action='store_true');args=p.parse_args()
    if Path(args.batch).name!=args.batch or args.batch in ('.','..'):
        p.error('批次编号必须是单层目录名')
    if (BASE/'test-upload'/args.batch).exists():
        p.error('批次已存在，请使用新编号')
    print(make_modules(BASE/'test-upload',args.batch,args.modules,args.date,args.revision,args.state,args.csv,args.count,args.missing))