import asyncio
import hashlib
import json
import logging
import os
import socket
import ipaddress
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .store import Store, KINDS

BASE = Path(__file__).resolve().parents[1]
store = Store(Path(os.getenv('BSDT_DATA_DIR',str(BASE/'runtime'))),Path(os.getenv('BSDT_INBOX',str(BASE/'test-upload'))))
logger=logging.getLogger('uvicorn.error')

async def monitor():
    while True:
        try:
            await asyncio.to_thread(store.scan)
        except Exception:
            logger.exception('模块扫描失败')
            store.scan_error='后台扫描失败，保留各模块已发布内容'
        await asyncio.sleep(15)

@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(store.scan)
    task=asyncio.create_task(monitor())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app=FastAPI(title='BSDT Internal Results API',version='0.4.3',lifespan=lifespan)
app.add_middleware(CORSMiddleware,allow_origins=['null','http://localhost:5173','http://127.0.0.1:5173'],allow_methods=['GET'],allow_headers=['*'],expose_headers=['ETag'])

def cached(request,data):
    body=json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
    etag='"'+hashlib.sha256(body).hexdigest()+'"'
    headers={'ETag':etag,'Cache-Control':'no-cache'}
    if request.headers.get('if-none-match')==etag:
        return Response(status_code=304,headers=headers)
    return Response(body,media_type='application/json',headers=headers)

@app.get('/api/health')
def health():
    return {'status':'degraded' if store.scan_error else 'ok','api_version':2,'scan_error':store.scan_error,'scan_interval_seconds':15,'scan_stats':store.last_scan_stats}

@app.get('/api/connection')
def connection(request:Request):
    addresses=[]
    try:
        for result in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
            value=result[4][0]
            ip=ipaddress.ip_address(value)
            if ip.is_private and not (ip.is_loopback or ip.is_link_local or ip.is_unspecified):
                url=f'http://{value}:{request.url.port or 8765}'
                if url not in addresses:
                    addresses.append(url)
    except OSError:
        pass
    return {'addresses':addresses,'server_version':'0.4.3','api_version':2,'verified_on_other_computer':False}
@app.get('/api/overview')
def overview(request:Request):
    return cached(request,store.overview())

@app.get('/api/batches')
def batches(request:Request,limit:int=Query(30,ge=1,le=100)):
    return cached(request,store.batches(limit))

@app.get('/api/snapshot')
def legacy_snapshot():
    data=store.snapshot()
    return {'data':data,'batches':store.batches(),'scan_error':store.scan_error or ('模块已独立更新，请升级至0.2.0客户端' if data is None and any(store.modules().values()) else None)}

@app.get('/api/market')
def market(request:Request,version:str|None=None):
    result=store.module('market',version)
    if result is None:
        raise HTTPException(404,'尚无已发布市场数据')
    return cached(request,result)

@app.get('/api/{kind}')
def listing(request:Request,kind:str,page:int=Query(1,ge=1),page_size:int=Query(12,ge=1,le=100),q:str=Query('',max_length=200),status:str=Query('',max_length=100),version:str|None=None,sort:str=Query('source',pattern='^(source|name|code|status)$'),direction:str=Query('asc',pattern='^(asc|desc)$')):
    if kind not in ('industries','stocks','reports'):
        raise HTTPException(404,'接口不存在')
    result=store.list_page(kind,page,page_size,q,status,version,sort,direction)
    if result is None:
        raise HTTPException(404,'尚无此模块发布数据')
    return cached(request,result)

@app.get('/api/{kind}/{key}')
def detail(request:Request,kind:str,key:str,version:str|None=None):
    if kind not in ('industries','stocks','reports'):
        raise HTTPException(404,'接口不存在')
    result=store.detail(kind,key,version)
    if result is None:
        raise HTTPException(404,'当前模块版本中该对象已移除或不存在')
    return cached(request,result)