import hashlib
import json
import sqlite3
import time
import pytest
from pathlib import Path
from backend.store import Store
from scripts.demo_upload import make_batch
from scripts.demo_modules import make_modules
from fastapi.testclient import TestClient

@pytest.fixture
def storage(tmp_path):
    inbox=tmp_path/'inbox';inbox.mkdir()
    return Store(tmp_path/'db',inbox)

def test_module_only_date_and_confirmation(storage):
    make_modules(storage.inbox,'weekly',['reports'],as_of='2026-09-24');storage.scan()
    make_modules(storage.inbox,'daily',['stocks'],as_of='2026-09-28',state='pending');storage.scan()
    assert storage.modules()['reports']['as_of']=='2026-09-24'
    assert storage.modules()['stocks'] is None
    make_modules(storage.inbox,'daily',['stocks'],as_of='2026-09-28');storage.scan()
    assert storage.modules()['stocks']['as_of']=='2026-09-28'
    assert storage.modules()['reports']['batch_id']=='weekly'
    assert storage.snapshot() is None  # Old client must not invent a common date.

def test_partial_module_failure_does_not_block_other_module(storage):
    folder=make_modules(storage.inbox,'a',['stocks','reports'])
    (folder/'reports.json').write_text('unfinished upload',encoding='utf-8');storage.scan()
    assert storage.modules()['stocks']
    assert storage.modules()['reports'] is None
    assert any(r['module']=='reports' and r['status']=='failed' for r in storage.batches())

def test_optional_missing_and_actual_zero(storage):
    folder=make_modules(storage.inbox,'a',['stocks','market'],missing=True,csv_stocks=True)
    m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    data=json.loads((folder/'market.json').read_text(encoding='utf-8'));data['metrics'].append({'label':'actual zero','value':0})
    content=json.dumps(data).encode();(folder/'market.json').write_bytes(content);m['modules']['market']['file']['sha256']=hashlib.sha256(content).hexdigest();(folder/'manifest.json').write_text(json.dumps(m),encoding='utf-8');storage.scan()
    row=storage.detail('stocks','000001')['data']
    assert row['industry'] is None and row['reason'] is None and row['next_check'] is None
    assert storage.module('market')['data']['metrics'][0]['value'] is None
    assert storage.module('market')['data']['metrics'][-1]['value']=='0'

def test_required_identity_invalid_and_duplicate(storage):
    folder=make_modules(storage.inbox,'a',['stocks']);m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    content=json.dumps([{'code':1}]).encode();(folder/'stocks.json').write_bytes(content);m['modules']['stocks']['file']['sha256']=hashlib.sha256(content).hexdigest();(folder/'manifest.json').write_text(json.dumps(m),encoding='utf-8');storage.scan()
    assert storage.modules()['stocks'] is None
    assert storage.batches()[0]['status']=='failed'

def test_revision_order_and_repeated_revision(storage):
    make_modules(storage.inbox,'z-new',['stocks'],revision=3);storage.scan()
    make_modules(storage.inbox,'a-old',['stocks'],revision=2);storage.scan()
    make_modules(storage.inbox,'other',['stocks'],revision=3);storage.scan()
    assert storage.modules()['stocks']['batch_id']=='z-new'
    assert any(r['status']=='archived' for r in storage.batches())
    assert any(r['status']=='failed' and '重复' in r['message'] for r in storage.batches())
    make_modules(storage.inbox,'newest',['stocks'],revision=4);storage.scan()
    assert storage.modules()['stocks']['revision']==4

def test_immutable_published_and_restart(storage):
    folder=make_modules(storage.inbox,'a',['stocks']);storage.scan()
    m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'));m['modules']['stocks']['revision']=99;(folder/'manifest.json').write_text(json.dumps(m),encoding='utf-8');storage.scan()
    assert storage.modules()['stocks']['revision']==1
    assert Store(storage.root,storage.inbox).modules()==storage.modules()

def test_unchanged_scan_skips_all_file_reads(storage,monkeypatch):
    make_modules(storage.inbox,'a',['stocks'],stock_count=5000);storage.scan()
    original=Path.read_bytes
    def fail_for_import(path):
        if storage.inbox in path.parents:
            raise AssertionError('Unchanged upload should not be reread')
        return original(path)
    monkeypatch.setattr(Path,'read_bytes',fail_for_import)
    storage.scan()
    assert storage.last_scan_stats=={'manifests_read':0,'files_read':0,'unchanged':1}

def test_5000_sql_pagination_and_detail_isolation(storage):
    make_modules(storage.inbox,'a',['stocks'],stock_count=5000);storage.scan()
    page=storage.list_page('stocks',400,12)
    assert page['total']==5000 and len(page['data'])==12
    assert 'next_check' not in page['data'][0]
    assert len(json.dumps(page,ensure_ascii=False).encode())<9000
    assert storage.detail('stocks','005000')['data']['next_check']
    make_modules(storage.inbox,'b',['stocks'],revision=2,stock_count=3);storage.scan()
    shrunk=storage.list_page('stocks',400,12)
    assert shrunk['page']==1 and shrunk['total']==3
    assert storage.detail('stocks','005000') is None
    assert storage.detail('stocks','005000',version='a:stocks') is not None

def test_legacy_database_migrates_without_reimport(storage):
    make_batch(storage.inbox,'legacy');storage.legacy.scan()
    restarted=Store(storage.root,storage.inbox)
    assert all(restarted.modules().values())
    assert restarted.snapshot()['meta']['batch_id']=='legacy'

def test_api_etags_query_limits_and_version_pin(storage,monkeypatch):
    import backend.app as module
    monkeypatch.setattr(module,'store',storage)
    with TestClient(module.app) as client:
        make_modules(storage.inbox,'a',['stocks','reports'],stock_count=5000);storage.scan()
        response=client.get('/api/overview');assert response.json()['api_version']==2
        assert '005000' not in response.text
        assert client.get('/api/overview',headers={'If-None-Match':response.headers['ETag']}).status_code==304
        page=client.get('/api/stocks?page=2&page_size=12');assert len(page.json()['data'])==12
        assert client.get('/api/stocks',params={'page_size':1000}).status_code==422
        assert client.get('/api/stocks',params={'q':'005000'}).json()['total']==1
        reports=client.get('/api/reports').json();assert 'content' not in reports['data'][0]
        assert client.get('/api/reports/SIM-REPORT-01').json()['data']['content']
        make_modules(storage.inbox,'b',['stocks'],revision=2,stock_count=2);storage.scan()
        assert client.get('/api/stocks/005000').status_code==404
        assert client.get('/api/stocks/005000?version=a:stocks').status_code==200
        assert client.get('/api/snapshot').json()['scan_error']=='模块已独立更新，请升级至0.2.0客户端'
def test_new_manifest_path_escape_and_timezone(storage):
    folder=make_modules(storage.inbox,'a',['stocks','market'])
    m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'));m['modules']['stocks']['file']['name']='../../outside.json';m['modules']['market']['generated_at']='2026-09-28T10:00:00';(folder/'manifest.json').write_text(json.dumps(m),encoding='utf-8');storage.scan()
    assert not any(storage.modules().values())
    assert {r['status'] for r in storage.batches()}=={'failed'}

def test_new_manifest_incomplete_and_duplicate_ids(storage):
    make_modules(storage.inbox,'a',['stocks'],state='incomplete');storage.scan()
    assert storage.modules()['stocks'] is None
    assert storage.batches()[0]['status']=='incomplete'
    folder=make_modules(storage.inbox,'b',['stocks']);m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    content=json.dumps([{'code':'000001'},{'code':'000001'}]).encode();(folder/'stocks.json').write_bytes(content);m['modules']['stocks']['file']['sha256']=hashlib.sha256(content).hexdigest();(folder/'manifest.json').write_text(json.dumps(m),encoding='utf-8');storage.scan()
    assert storage.modules()['stocks'] is None
    assert any('重复' in r['message'] for r in storage.batches())
def test_sorting_is_server_side_and_allowlisted(storage,monkeypatch):
    import backend.app as module
    from fastapi.testclient import TestClient
    from scripts.demo_modules import make_modules
    make_modules(storage.inbox,'sorted',['stocks'],stock_count=25);storage.scan()
    descending=storage.list_page('stocks',1,12,sort='code',direction='desc')
    assert descending['data'][0]['code']=='000025'
    ascending=storage.list_page('stocks',1,12,sort='code',direction='asc')
    assert ascending['data'][0]['code']=='000001'
    monkeypatch.setattr(module,'store',storage)
    with TestClient(module.app) as client:
        assert client.get('/api/stocks?sort=code&direction=desc').json()['data'][0]['code']=='000025'
        assert client.get('/api/stocks?sort=payload;DROP&direction=asc').status_code==422
        assert client.get('/api/stocks?direction=invalid').status_code==422

def test_connection_addresses_are_candidates_not_verification(storage,monkeypatch):
    import backend.app as module
    from fastapi.testclient import TestClient
    monkeypatch.setattr(module,'store',storage)
    monkeypatch.setattr(module.socket,'getaddrinfo',lambda *args:[(2,1,0,'',('127.0.0.1',0)),(2,1,0,'',('10.0.0.3',0)),(2,1,0,'',('10.0.0.3',0)),(2,1,0,'',('169.254.1.1',0))])
    with TestClient(module.app) as client:
        data=client.get('/api/connection').json()
        assert data['addresses']==['http://10.0.0.3:8765']
        assert data['verified_on_other_computer'] is False
        assert data['api_version']==2