"""Generate explicit simulations in a dedicated upload folder."""
import argparse
import csv
import hashlib
import io
import json
import sys
from pathlib import Path

BASE=Path(__file__).resolve().parents[1]
def make_batch(inbox, bid, as_of='2026-09-24', state='published', csv_stocks=False):
    folder=inbox/bid
    folder.mkdir(parents=True,exist_ok=True)
    industries=[{'id':f'SIM-{i:02}','name':name,'status':status,'reason':reason,'next_check':'等待上游更新并核对证据'} for i,(name,status,reason) in enumerate([
        ('电力设备','修复观察','示例：近期研究范围内出现修复迹象'),('半导体','待补证据','示例：行业与个股证据尚不一致'),('医药生物','持续观察','示例：保留历史观察状态'),('机械设备','修复观察','示例：下一批次需复核'),('计算机','风险复核','示例：已有反证尚未解除'),('食品饮料','持续观察','示例：等待新增证据')],1)]
    stocks=[{'code':f'{i:06}','name':f'演示标的 {i:02}','industry':industries[(i-1)%6]['name'],'status':['持续观察','待补证据','风险复核'][i%3],'reason':'模拟结论：由上游确认的观察信息在此展示，不代表真实证券研究结果。','next_check':'核对下一交易日已确认输入、原始依据及失效条件。'} for i in range(1,26)]
    data={'market':{'weather':'防御观察（模拟）','summary':'以参考界面的历史日期构造演示。所有数值与结论均为模拟，未接入真实输出。','metrics':[{'label':'模拟上涨占比','value':'20.2%'},{'label':'示例行业覆盖','value':'6 个'},{'label':'示例观察标的','value':'25 个'}]},'industries':industries,'stocks':stocks,'reports':[{'id':'SIM-REPORT-01','title':'盘后研究交接演示','content':f'数据日期：{as_of}\n\n此报告为模拟样例。\n\n市场、行业与个股页面均来自同一已确认批次。后台不进行选股计算，也不生成交易指令。\n\n下一步：丁总与 William 提供真实 JSON/CSV 后，按接口契约调整后台适配并逐项核对。'}]}
    files={}
    for kind,content in data.items():
        name=kind+'.json'
        if kind=='stocks' and csv_stocks:
            name='stocks.csv'
            stream=io.StringIO(newline='');writer=csv.DictWriter(stream,fieldnames=list(stocks[0]));writer.writeheader();writer.writerows(stocks);raw=stream.getvalue().encode('utf-8-sig')
        else:
            raw=json.dumps(content,ensure_ascii=False,indent=2).encode('utf-8')
        (folder/name).write_bytes(raw)
        files[kind]={'name':name,'sha256':hashlib.sha256(raw).hexdigest()}
    manifest={'schema_version':1,'batch_id':bid,'as_of':as_of,'sample':True,'source':'BSDT 模拟文件上传','complete':state!='incomplete','confirmed':state=='published','confirmed_by':'演示确认人（模拟）' if state=='published' else '', 'files':files}
    temporary=folder/'manifest.json.tmp';temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');temporary.replace(folder/'manifest.json')
    if state=='failed':
        (folder/'industries.json').write_text('invalid upload',encoding='utf-8')
        manifest['confirmed']=True;manifest['confirmed_by']='模拟';(folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
    return folder

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--batch',default='demo-20260924-001');p.add_argument('--date',default='2026-09-24');p.add_argument('--state',choices=['published','pending','incomplete','failed'],default='published');p.add_argument('--csv',action='store_true');args=p.parse_args()
    if Path(args.batch).name!=args.batch or args.batch in ('.','..'):
        sys.exit('批次编号必须是单层目录名')
    destination=BASE/'test-upload'/args.batch
    if destination.exists():
        sys.exit('批次已存在，请使用新编号')
    print(make_batch(BASE/'test-upload',args.batch,args.date,args.state,args.csv))
