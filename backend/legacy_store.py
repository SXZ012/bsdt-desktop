"""File adapter only: imports confirmed upstream results, never computes strategy."""
import csv
import hashlib
import io
import json
import sqlite3
import threading
from datetime import date, datetime, timezone
from pathlib import Path

KINDS = ('market', 'industries', 'stocks', 'reports')

class Store:
    def __init__(self, root: Path, inbox: Path):
        self.root, self.inbox = root, inbox
        root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.db = root / 'bsdt.sqlite3'
        with self.connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS batches (id TEXT PRIMARY KEY, digest TEXT, status TEXT, message TEXT, as_of TEXT, imported_at TEXT, payload TEXT)')
            con.execute('CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT)')
        self.scan_error = None

    def connect(self):
        return sqlite3.connect(self.db, timeout=15)

    def scan(self):
        with self.lock:
            if not self.inbox.is_dir():
                self.scan_error = '上传目录不可访问，保留已发布内容'
                return
            try:
                manifests = sorted(self.inbox.glob('*/manifest.json'))
                for path in manifests:
                    self.import_batch(path)
                self.scan_error = None
            except OSError as exc:
                self.scan_error = f'读取失败：{exc}'

    def import_batch(self, path):
        # Folder identity is stable even while an upstream manifest is incomplete.
        bid = path.parent.name
        status, message, as_of, payload, digest = 'failed', '', '', None, ''
        try:
            raw = path.read_bytes()
            m = json.loads(raw.decode('utf-8-sig'))
            if not isinstance(m,dict) or m.get('schema_version') != 1:
                raise ValueError('仅接受 schema_version=1 的批次清单')
            digest = hashlib.sha256(raw).hexdigest()
            if m['batch_id'] != bid:
                raise ValueError('batch_id 必须与目录名一致')
            as_of = m['as_of']
            date.fromisoformat(as_of)
            if type(m.get('sample')) is not bool or not m.get('source'):
                raise ValueError('缺少样例标识或来源')
            if m.get('complete') is not True:
                status, message = 'incomplete', '上传未完成，保留上一版'
            elif m.get('confirmed') is not True or not m.get('confirmed_by'):
                status, message = 'pending', '待上游人工确认，保留上一版'
            else:
                data = {}
                for kind in KINDS:
                    spec = m['files'][kind]
                    target = (path.parent / spec['name']).resolve()
                    if target.parent != path.parent.resolve() or target.suffix not in ('.json', '.csv'):
                        raise ValueError('仅接受批次目录内的 JSON/CSV 文件')
                    content = target.read_bytes()
                    if hashlib.sha256(content).hexdigest() != spec['sha256']:
                        raise ValueError(f'{kind} 文件校验失败或尚未上传完整')
                    text = content.decode('utf-8-sig')
                    data[kind] = json.loads(text) if target.suffix == '.json' else list(csv.DictReader(io.StringIO(text)))
                self.validate(data)
                if path.read_bytes() != raw:
                    raise ValueError('读取期间清单变化，等待下次扫描')
                payload = json.dumps({'meta': {k:m[k] for k in ('batch_id','as_of','sample','source','confirmed_by')}, **data}, ensure_ascii=False)
                status, message = 'ready', '完整且已确认'
        except (ValueError, KeyError, TypeError, OSError) as exc:
            message = str(exc)
        with self.connect() as con:
            existing = con.execute('SELECT digest,status FROM batches WHERE id=?', (bid,)).fetchone()
            if existing and existing[1] in ('published', 'archived'):
                if existing[0] != digest:
                    con.execute('UPDATE batches SET message=? WHERE id=?', ('已发布批次被修改，已忽略；更正请使用新批次编号', bid))
                return
            current = con.execute("SELECT b.as_of,b.imported_at FROM batches b JOIN state s ON b.id=s.value WHERE s.key='published'").fetchone()
            now = datetime.now(timezone.utc).isoformat()
            if status == 'ready':
                if current and as_of < current[0]:
                    status, message = 'archived', '历史批次已保存，不替换较新日期'
                else:
                    status, message = 'published', '已发布'
                    con.execute("INSERT OR REPLACE INTO state VALUES ('published',?)", (bid,))
            con.execute('INSERT OR REPLACE INTO batches VALUES (?,?,?,?,?,?,?)', (bid,digest,status,message,as_of,now,payload))

    @staticmethod
    def validate(data):
        from .store import adapt
        for kind in KINDS:
            adapt(kind, data[kind])

    def snapshot(self):
        with self.connect() as con:
            row = con.execute("SELECT payload FROM batches WHERE id=(SELECT value FROM state WHERE key='published')").fetchone()
        return json.loads(row[0]) if row else None

    def batches(self):
        with self.connect() as con:
            con.row_factory = sqlite3.Row
            return [dict(r) for r in con.execute('SELECT id,status,message,as_of,imported_at FROM batches ORDER BY imported_at DESC')]
