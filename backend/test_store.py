import json
from pathlib import Path
import pytest
from backend.store import Store
from scripts.demo_upload import make_batch

@pytest.fixture
def storage(tmp_path):
    inbox=tmp_path/'inbox';inbox.mkdir()
    return Store(tmp_path/'db',inbox)

def test_confirmation_completeness_and_failure_keep_published(storage):
    make_batch(storage.inbox,'a');storage.scan()
    for bid,state in [('b','pending'),('c','incomplete'),('d','failed')]:
        make_batch(storage.inbox,bid,'2026-09-28',state)
    storage.scan()
    assert storage.snapshot()['meta']['batch_id']=='a'
    assert {r['status'] for r in storage.batches()}=={'published','pending','incomplete','failed'}

def test_csv_dedup_immutable_and_older(storage):
    folder=make_batch(storage.inbox,'a',csv_stocks=True);storage.scan();storage.scan()
    assert len(storage.batches())==1
    assert storage.snapshot()['stocks'][0]['code']=='000001'
    m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'));m['as_of']='2026-10-01';(folder/'manifest.json').write_text(json.dumps(m),encoding='utf-8');storage.scan()
    assert storage.snapshot()['meta']['as_of']=='2026-09-24'
    make_batch(storage.inbox,'old','2026-09-01');storage.scan()
    assert storage.snapshot()['meta']['batch_id']=='a'

def test_pending_to_confirmed_and_recovery(storage):
    make_batch(storage.inbox,'a',state='pending');storage.scan();assert storage.snapshot() is None
    make_batch(storage.inbox,'a',state='published');storage.scan();assert storage.snapshot()
    storage.inbox=storage.inbox/'missing';storage.scan()
    assert storage.scan_error and storage.snapshot()

def test_path_escape_rejected(storage):
    folder=make_batch(storage.inbox,'a');m=json.loads((folder/'manifest.json').read_text(encoding='utf-8'));m['files']['market']['name']='../../outside.json';(folder/'manifest.json').write_text(json.dumps(m),encoding='utf-8');storage.scan()
    assert storage.snapshot() is None
    assert storage.batches()[0]['status']=='failed'

def test_new_batch_atomically_updates_all_views(storage):
    make_batch(storage.inbox,'a');storage.scan();make_batch(storage.inbox,'b','2026-09-28',csv_stocks=True);storage.scan()
    assert storage.snapshot()['meta']['batch_id']=='b'
    restarted=Store(storage.root,storage.inbox)
    assert restarted.snapshot()==storage.snapshot()

def test_api_contract(storage,monkeypatch):
    from fastapi.testclient import TestClient
    import backend.app as module
    monkeypatch.setattr(module,'store',storage)
    with TestClient(module.app) as client:
        assert client.get('/api/snapshot').json()['data'] is None
        assert client.get('/api/market').status_code==404
        make_batch(storage.inbox,'a');storage.scan()
        for kind in ('market','industries','stocks','reports'):
            assert client.get('/api/'+kind).json()['meta']['batch_id']=='a'
        assert client.get('/api/stocks/000001').json()['data']['code']=='000001'
        assert client.get('/api/stocks/missing').status_code==404
