from __future__ import annotations
from pathlib import Path
from typing import Any, Iterable
import json, sqlite3
from shared.protocol.observability import LogRecord

class SQLiteObservabilityStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def initialize(self):
        with self._connect() as c:
            self._create_logs_table(c)
            columns = {row[1]: row for row in c.execute("PRAGMA table_info(logs)")}
            if columns["session_id"][3] or columns["request_id"][3]:
                self._migrate_nullable_request_columns(c)
            for col in ["timestamp","ct","level","kind","event","session_id","request_id","trace_id","span_id"]:
                c.execute(f"CREATE INDEX IF NOT EXISTS idx_logs_{col} ON logs({col})")

    @staticmethod
    def _create_logs_table(c, table_name: str = "logs"):
        c.execute(f'''CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            schema_version INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            ct TEXT NOT NULL, level TEXT NOT NULL, kind TEXT NOT NULL, event TEXT NOT NULL,
            session_id TEXT, request_id TEXT, trace_id TEXT NOT NULL, span_id TEXT NOT NULL,
            parent_span_id TEXT, origin_request_id TEXT, operation TEXT, result TEXT, message TEXT,
            session_elapsed_ms REAL, request_elapsed_ms REAL, trace_elapsed_ms REAL, span_elapsed_ms REAL,
            params_json TEXT NOT NULL, payload_json TEXT
        )''')

    def _migrate_nullable_request_columns(self, c):
        c.execute("DROP TABLE IF EXISTS logs_v1_nullable")
        self._create_logs_table(c, "logs_v1_nullable")
        columns = [row[1] for row in c.execute("PRAGMA table_info(logs)")]
        names = ",".join(columns)
        c.execute(f"INSERT INTO logs_v1_nullable ({names}) SELECT {names} FROM logs")
        c.execute("DROP TABLE logs")
        c.execute("ALTER TABLE logs_v1_nullable RENAME TO logs")

    def insert_logs(self, records: Iterable[LogRecord]):
        rows=[]
        for r in records:
            d=r.model_dump(mode="json")
            rows.append((d["schema_version"], d["timestamp"], d["ct"], d["level"], d["kind"], d["event"],
                d["session_id"],d["request_id"],d["trace_id"],d["span_id"],d["parent_span_id"],d["origin_request_id"],
                d["operation"],d["result"],d["message"],d["session_elapsed_ms"],d["request_elapsed_ms"],
                d["trace_elapsed_ms"],d["span_elapsed_ms"],json.dumps(d["params"],ensure_ascii=False),json.dumps(d["payload"],ensure_ascii=False)))
        with self._connect() as c:
            c.executemany('''INSERT INTO logs(schema_version,timestamp,ct,level,kind,event,session_id,request_id,trace_id,span_id,
            parent_span_id,origin_request_id,operation,result,message,session_elapsed_ms,request_elapsed_ms,trace_elapsed_ms,span_elapsed_ms,params_json,payload_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', rows)

    def query_logs(self, filters: dict[str, Any] | None=None):
        filters=filters or {}; clauses=[]; args=[]
        mapping={"ct":"ct","level":"level","kind":"kind","event":"event","session_id":"session_id","request_id":"request_id","trace_id":"trace_id","span_id":"span_id","result":"result"}
        for k,col in mapping.items():
            if filters.get(k): clauses.append(f"{col}=?"); args.append(str(filters[k]))
        if filters.get("from_ts"): clauses.append("timestamp>=?"); args.append(filters["from_ts"])
        if filters.get("to_ts"): clauses.append("timestamp<=?"); args.append(filters["to_ts"])
        if filters.get("q"):
            clauses.append("(event LIKE ? OR message LIKE ? OR operation LIKE ? OR result LIKE ? OR params_json LIKE ? OR payload_json LIKE ?)")
            pat=f"%{filters['q']}%"; args.extend([pat]*6)
        sql="SELECT * FROM logs" + (" WHERE "+" AND ".join(clauses) if clauses else "") + " ORDER BY timestamp DESC,id DESC LIMIT ? OFFSET ?"
        args.extend([min(int(filters.get("limit",100)),500), max(int(filters.get("offset",0)),0)])
        with self._connect() as c: rows=c.execute(sql,args).fetchall()
        return [self._decode(r) for r in rows]

    def _decode(self,row):
        d=dict(row); d["params"]=json.loads(d.pop("params_json") or "{}"); d["payload"]=json.loads(d.pop("payload_json") or "null"); return d

    def _summary(self, key: str, value: str):
        logs=self.query_logs({key:value,"limit":500})
        if not logs: return None
        chronological=sorted(logs,key=lambda x:(x["timestamp"],x["id"]))
        return {key:value,"start_time":chronological[0]["timestamp"],"end_time":chronological[-1]["timestamp"],
                "result":next((x["result"] for x in reversed(chronological) if x["result"]),None),"logs":chronological}
    def get_request(self,id): return self._summary("request_id",id)
    def get_session(self,id): return self._summary("session_id",id)
    def get_trace(self,id): return self._summary("trace_id",id)
    def get_span(self,id): return self._summary("span_id",id)

    def _group(self,key: str, filters=None):
        logs=self.query_logs({**(filters or {}),"limit":500})
        groups={}
        for row in sorted(logs,key=lambda x:x["timestamp"]):
            if row[key] is None:
                continue
            groups.setdefault(row[key],[]).append(row)
        out=[]
        for ident, rs in groups.items():
            out.append({key:ident,"start_time":rs[0]["timestamp"],"end_time":rs[-1]["timestamp"],"count":len(rs),
                "result":next((x["result"] for x in reversed(rs) if x["result"]),None),
                "elapsed_ms":next((x.get({"request_id":"request_elapsed_ms","session_id":"session_elapsed_ms","trace_id":"trace_elapsed_ms"}[key]) for x in reversed(rs) if x.get({"request_id":"request_elapsed_ms","session_id":"session_elapsed_ms","trace_id":"trace_elapsed_ms"}[key]) is not None),None)})
        return sorted(out,key=lambda x:x["start_time"], reverse=True)
    def list_requests(self,filters=None): return self._group("request_id",filters)
    def list_sessions(self,filters=None): return self._group("session_id",filters)
    def list_traces(self,filters=None): return self._group("trace_id",filters)
