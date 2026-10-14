"""Versioned module imports. No research or selection calculations."""
import csv
import hashlib
import io
import json
import sqlite3
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from .legacy_store import Store as LegacyStore

KINDS = ('market', 'industries', 'stocks', 'reports')

def now():
    return datetime.now(timezone.utc).isoformat()

def optional_text(value):
    if value is None or value == '':
        return None
    if isinstance(value, (dict, list, bool)):
        raise ValueError('文本字段类型错误')
    return str(value).strip() or None

def adapt(kind, data):
    """Required identities stay strict; absent research fields remain null."""
    if kind == 'market':
        if not isinstance(data, dict):
            raise ValueError('market 必须为对象')
        result = {'weather':optional_text(data.get('weather')), 'summary':optional_text(data.get('summary')), 'metrics':[]}
        metrics = data.get('metrics') or []
        if not isinstance(metrics, list):
            raise ValueError('metrics 必须为数组')
        for metric in metrics:
            if not isinstance(metric, dict) or not optional_text(metric.get('label')):
                raise ValueError('指标缺少 label')
            result['metrics'].append({'label':str(metric['label']), 'value':optional_text(metric.get('value'))})
        return result
    if not isinstance(data, list):
        raise ValueError(f'{kind} 必须为数组')
    result, ids = [], set()
    identifier = 'code' if kind == 'stocks' else 'id'
    label = 'title' if kind == 'reports' else 'name'
    fields = ('content',) if kind == 'reports' else ('industry','status','reason','next_check')
    for raw in data:
        if not isinstance(raw, dict):
            raise ValueError(f'{kind} 行必须为对象')
        # Identifiers must be strings: a numeric stock code may already have lost leading zeros.
        if not isinstance(raw.get(identifier), str) or not raw[identifier].strip():
            raise ValueError(f'{kind} 缺少文本标识 {identifier}')
        key = raw[identifier].strip()
        if key in ids:
            raise ValueError(f'{kind} 标识重复: {key}')
        ids.add(key)
        row = {identifier:key, label:optional_text(raw.get(label))}
        row.update({field:optional_text(raw.get(field)) for field in fields})
        result.append(row)
    return result

class Store:
    def __init__(self, root: Path, inbox: Path):
        self.root, self.inbox = root, inbox
        self.legacy = LegacyStore(root, inbox)
        self.db = self.legacy.db
        self.lock = threading.Lock()
        self.signatures = {}
        self.watch_files = {}
        self.scan_error = None
        self.last_scan_stats = {'manifests_read':0, 'files_read':0, 'unchanged':0}
        with self.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS module_versions (
                    id TEXT PRIMARY KEY, batch_id TEXT, module TEXT, digest TEXT,
                    status TEXT, message TEXT, as_of TEXT, revision INTEGER,
                    received_at TEXT, meta TEXT, payload TEXT);
                CREATE TABLE IF NOT EXISTS module_current (module TEXT PRIMARY KEY, version_id TEXT);
                CREATE TABLE IF NOT EXISTS module_rows (
                    version_id TEXT, item_id TEXT, position INTEGER, name TEXT,
                    status TEXT, search_text TEXT, summary TEXT, payload TEXT,
                    PRIMARY KEY(version_id,item_id));
                CREATE INDEX IF NOT EXISTS rows_version_position ON module_rows(version_id,position);
                CREATE INDEX IF NOT EXISTS rows_version_status ON module_rows(version_id,status);
            ''')
        # Existing 0.1.x database is preserved; importing it once populates per-module storage.
        previous = self.legacy.snapshot()
        if previous:
            self.import_legacy_snapshot(previous)

    def connect(self):
        con = sqlite3.connect(self.db, timeout=15)
        con.row_factory = sqlite3.Row
        return con

    @staticmethod
    def stamp(path):
        try:
            info = path.stat()
            return (str(path), info.st_mtime_ns, info.st_size, info.st_ctime_ns)
        except OSError:
            return (str(path), None)

    def scan(self):
        with self.lock:
            stats = {'manifests_read':0, 'files_read':0, 'unchanged':0}
            self.last_scan_stats = stats
            if not self.inbox.is_dir():
                self.scan_error = '上传目录不可访问，保留各模块已发布内容'
                return
            try:
                for path in sorted(self.inbox.glob('*/manifest.json')):
                    signature = tuple(self.stamp(p) for p in [path,*self.watch_files.get(str(path),[])])
                    if self.signatures.get(str(path)) == signature:
                        stats['unchanged'] += 1
                        continue
                    self.import_batch(path)
                    stats['manifests_read'] += 1
                    # Record the signature only after import; importer compares manifest/file stability.
                    self.signatures[str(path)] = tuple(self.stamp(p) for p in [path,*self.watch_files.get(str(path),[])])
                self.scan_error = None
            except OSError as exc:
                self.scan_error = f'读取失败：{exc}'

    def import_batch(self, path):
        bid = path.parent.name
        try:
            raw = path.read_bytes()
            manifest = json.loads(raw.decode('utf-8-sig'))
            if not isinstance(manifest,dict) or manifest.get('batch_id') != bid:
                raise ValueError('batch_id 必须与目录名一致')
            schema = manifest.get('schema_version')
            if schema == 1:
                files = manifest.get('files',{})
                self.watch_files[str(path)] = self.safe_files(path,files)
                self.legacy.import_batch(path)
                previous = self.legacy.snapshot()
                if previous:
                    self.import_legacy_snapshot(previous)
                return
            if schema != 2 or not isinstance(manifest.get('modules'),dict) or not manifest['modules']:
                raise ValueError('清单应为 schema_version=1 或带 modules 的版本2')
            if set(manifest['modules']) - set(KINDS):
                raise ValueError('存在未知模块')
            watched = []
            for kind,spec in manifest['modules'].items():
                if isinstance(spec,dict) and isinstance(spec.get('file'),dict):
                    watched.extend(self.safe_files(path,{kind:spec['file']}))
            self.watch_files[str(path)] = watched
            for kind,spec in manifest['modules'].items():
                self.import_module(path,raw,bid,kind,spec)
        except (ValueError,TypeError,KeyError,OSError) as exc:
            self.record(bid,'manifest','', 'failed',str(exc),'',0,None,None)

    @staticmethod
    def safe_files(path, files):
        watched = []
        if not isinstance(files,dict):
            return watched
        for spec in files.values():
            if isinstance(spec,dict) and isinstance(spec.get('name'),str):
                target = (path.parent/spec['name']).resolve()
                if target.parent == path.parent.resolve():
                    watched.append(target)
        return watched

    def import_module(self, path, raw, bid, kind, spec):
        digest = hashlib.sha256(json.dumps(spec,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        status,message,as_of,revision,meta,payload = 'failed','', '',0,None,None
        try:
            if not isinstance(spec,dict):
                raise ValueError('模块清单必须为对象')
            as_of = spec['as_of']; date.fromisoformat(as_of)
            revision = spec['revision']
            if type(revision) is not int or revision < 1:
                raise ValueError('revision 必须是当日正整数版本号')
            generated = datetime.fromisoformat(spec['generated_at'].replace('Z','+00:00'))
            if generated.tzinfo is None:
                raise ValueError('generated_at 必须包含时区')
            if type(spec.get('sample')) is not bool or not optional_text(spec.get('source')):
                raise ValueError('缺少样例标识或来源')
            if spec.get('complete') is not True:
                status,message = 'incomplete','上传未完成，保留此模块上一版'
            elif spec.get('confirmed') is not True or not optional_text(spec.get('confirmed_by')):
                status,message = 'pending','待上游确认，保留此模块上一版'
            else:
                file = spec['file']
                target = (path.parent/file['name']).resolve()
                if target.parent != path.parent.resolve() or target.suffix.lower() not in ('.json','.csv'):
                    raise ValueError('仅接受批次目录内的 JSON/CSV')
                initial_stamp = self.stamp(target)
                content = target.read_bytes()
                self.last_scan_stats['files_read'] += 1
                if hashlib.sha256(content).hexdigest() != file['sha256']:
                    raise ValueError(f'{kind} 文件校验失败或上传不完整')
                text = content.decode('utf-8-sig')
                source = json.loads(text) if target.suffix.lower()=='.json' else list(csv.DictReader(io.StringIO(text)))
                payload = adapt(kind,source)
                if path.read_bytes()!=raw or self.stamp(target)!=initial_stamp:
                    raise ValueError('读取期间文件变化，等待重新上传完整清单')
                meta = {k:spec[k] for k in ('as_of','revision','generated_at','sample','source','confirmed_by')}
                meta.update({'batch_id':bid,'module':kind,'version_id':f'{bid}:{kind}'})
                status,message = 'ready','完整且已确认'
        except (ValueError,TypeError,KeyError,OSError,AttributeError) as exc:
            message = str(exc)
        self.record(bid,kind,digest,status,message,as_of,revision,meta,payload)

    def import_legacy_snapshot(self, previous):
        m = previous['meta']
        bid = m['batch_id']
        for kind in KINDS:
            vid = f'{bid}:{kind}'
            with self.connect() as con:
                if con.execute('SELECT 1 FROM module_versions WHERE id=?',(vid,)).fetchone():
                    continue
            data = adapt(kind,previous[kind])
            meta = dict(m,module=kind,version_id=vid,revision=1,generated_at=None,legacy=True)
            digest = hashlib.sha256(json.dumps(previous[kind],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            self.record(bid,kind,digest,'ready','兼容旧版整批清单',m['as_of'],1,meta,data)

    def record(self,bid,kind,digest,status,message,as_of,revision,meta,payload):
        vid = f'{bid}:{kind}'
        with self.connect() as con:
            existing = con.execute('SELECT digest,status,message FROM module_versions WHERE id=?',(vid,)).fetchone()
            if existing and existing['status'] in ('published','archived'):
                if existing['digest']!=digest or status=='failed':
                    con.execute('UPDATE module_versions SET message=? WHERE id=?',('已发布编号不可修改，请使用新批次编号',vid))
                return
            if existing and existing['digest']==digest and existing['status']==status and existing['message']==message:
                return
            stamp = now()
            if status == 'ready':
                current = con.execute('SELECT v.as_of,v.revision FROM module_versions v JOIN module_current c ON c.version_id=v.id WHERE c.module=?',(kind,)).fetchone()
                incoming = (as_of,revision)
                if current and incoming < (current['as_of'],current['revision']):
                    status,message = 'archived','较旧日期或版本已归档，不覆盖当前结果'
                elif current and incoming == (current['as_of'],current['revision']):
                    status,message,payload = 'failed','同日版本号重复，请增加 revision 并使用新批次编号',None
                else:
                    status,message = 'published','已发布'
                    meta.update(published_at=stamp)
            if meta:
                meta.setdefault('published_at',None)
                meta['received_at'] = stamp
                meta['count'] = len(payload) if isinstance(payload,list) else 1
            con.execute('INSERT OR REPLACE INTO module_versions VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                        (vid,bid,kind,digest,status,message,as_of,revision,stamp,json.dumps(meta,ensure_ascii=False) if meta else None,json.dumps(payload,ensure_ascii=False) if payload is not None else None))
            if payload is not None and isinstance(payload,list):
                con.execute('DELETE FROM module_rows WHERE version_id=?',(vid,))
                values=[]
                for i,row in enumerate(payload):
                    key=row.get('code',row.get('id'))
                    title=row.get('name',row.get('title'))
                    summary={k:row.get(k) for k in ('code','id','name','title','industry','status') if k in row}
                    if kind!='reports':
                        summary['reason']=(row.get('reason') or '')[:120] or None
                    search=' '.join(str(v) for v in row.values() if v is not None).casefold()
                    values.append((vid,key,i,title,row.get('status'),search,json.dumps(summary,ensure_ascii=False),json.dumps(row,ensure_ascii=False)))
                con.executemany('INSERT INTO module_rows VALUES (?,?,?,?,?,?,?,?)',values)
            if status=='published':
                con.execute('INSERT OR REPLACE INTO module_current VALUES (?,?)',(kind,vid))

    def modules(self):
        with self.connect() as con:
            rows = con.execute('SELECT v.module,v.meta FROM module_versions v JOIN module_current c ON c.version_id=v.id').fetchall()
        found={r['module']:json.loads(r['meta']) for r in rows}
        return {kind:found.get(kind) for kind in KINDS}

    def module(self,kind,version=None):
        with self.connect() as con:
            if version:
                row=con.execute("SELECT meta,payload FROM module_versions WHERE id=? AND module=? AND status IN ('published','archived')",(version,kind)).fetchone()
            else:
                row=con.execute('SELECT v.meta,v.payload FROM module_versions v JOIN module_current c ON c.version_id=v.id WHERE c.module=?',(kind,)).fetchone()
        return {'meta':json.loads(row['meta']),'data':json.loads(row['payload'])} if row and row['payload'] else None

    def list_page(self,kind,page=1,page_size=12,q='',status='',version=None,sort='source',direction='asc'):
        with self.connect() as con:
            if version:
                row=con.execute("SELECT id,meta FROM module_versions WHERE id=? AND module=? AND status IN ('published','archived')",(version,kind)).fetchone()
            else:
                row=con.execute('SELECT v.id,v.meta FROM module_versions v JOIN module_current c ON c.version_id=v.id WHERE c.module=?',(kind,)).fetchone()
            if not row:
                return None
            vid=row['id']; where='version_id=?'; args=[vid]
            if q:
                where+=' AND instr(search_text,?)>0'; args.append(q.casefold())
            if status:
                where+=' AND COALESCE(status,\'待补充\')=?'; args.append(status)
            total=con.execute('SELECT COUNT(*) FROM module_rows WHERE '+where,args).fetchone()[0]
            actual_page=min(page,max(1,(total+page_size-1)//page_size))
            column={'source':'position','name':'name','code':'item_id','status':'status'}.get(sort,'position')
            order='DESC' if direction=='desc' else 'ASC'
            rows=con.execute('SELECT summary FROM module_rows WHERE '+where+f' ORDER BY {column} IS NULL, {column} {order}, position LIMIT ? OFFSET ?',(*args,page_size,(actual_page-1)*page_size)).fetchall()
            statuses=[r[0] or '待补充' for r in con.execute('SELECT DISTINCT status FROM module_rows WHERE version_id=? ORDER BY status',(vid,))]
        return {'meta':json.loads(row['meta']),'data':[json.loads(r['summary']) for r in rows],'page':actual_page,'page_size':page_size,'total':total,'statuses':statuses}

    def detail(self,kind,key,version=None):
        with self.connect() as con:
            if version:
                row=con.execute("SELECT id,meta FROM module_versions WHERE id=? AND module=? AND status IN ('published','archived')",(version,kind)).fetchone()
            else:
                row=con.execute('SELECT v.id,v.meta FROM module_versions v JOIN module_current c ON c.version_id=v.id WHERE c.module=?',(kind,)).fetchone()
            if not row:
                return None
            item=con.execute('SELECT payload FROM module_rows WHERE version_id=? AND item_id=?',(row['id'],key)).fetchone()
        return {'meta':json.loads(row['meta']),'data':json.loads(item['payload'])} if item else None

    def batches(self,limit=30):
        with self.connect() as con:
            new=[dict(r) for r in con.execute('SELECT batch_id AS id,module,status,message,as_of,revision,received_at AS imported_at FROM module_versions ORDER BY received_at DESC LIMIT ?',(limit,))]
        old=self.legacy.batches()[:limit]
        old_ids={r['id'] for r in old}
        new=[r for r in new if r['id'] not in old_ids]
        for row in old:
            row['module']='legacy';row['revision']=1
        return sorted(new+old,key=lambda r:r['imported_at'],reverse=True)[:limit]

    def overview(self):
        modules=self.modules(); receipts=self.batches()
        warnings=[r for r in receipts if r['status'] in ('pending','incomplete','failed')]
        return {'api_version':2,'modules':modules,'alerts':warnings[:8],'scan_error':self.scan_error}

    def snapshot(self):
        # 0.1.x compatibility is safe only while all modules still share one batch/date.
        modules=self.modules()
        if any(v is None for v in modules.values()) or len({v['batch_id'] for v in modules.values()})!=1:
            return None
        data={kind:self.module(kind,meta['version_id'])['data'] for kind,meta in modules.items()}
        first=modules['market']
        return {'meta':first,**data}