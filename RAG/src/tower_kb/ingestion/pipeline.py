import json
import time
import uuid
from tower_kb.adapters.search import vector
from tower_kb.ingestion.chunking import chunk_document

class Pipeline:
    def __init__(self, db, objects):
        self.db, self.objects = db, objects

    def run_once(self):
        token = uuid.uuid4().hex
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute("SELECT * FROM jobs WHERE (state='RECEIVED' OR (state NOT IN ('READY','PUBLISHED','FAILED') AND lease < ?)) AND attempts < 3 ORDER BY rowid LIMIT 1",(time.time(),)).fetchone()
            if not job:
                db.execute("UPDATE jobs SET state='FAILED',error='lease exhausted' WHERE lease < ? AND attempts>=3 AND state NOT IN ('READY','PUBLISHED','FAILED')",(time.time(),))
                return False
            db.execute("UPDATE jobs SET state='PARSING',attempts=attempts+1,lease=?,lease_token=? WHERE id=?",(time.time()+120,token,job["id"]))
        try:
            with self.db.connect() as db:
                version = db.execute("SELECT * FROM versions WHERE doc_id=? AND version=?",(job["doc_id"],job["version"])).fetchone()
            text = (self.objects/version["object_key"]).read_text(encoding="utf-8")
            rows = chunk_document(job["doc_id"],job["version"],text)
            if not rows:
                raise ValueError("empty document")
            # Local indexes share one SQLite transaction. Production adapters must
            # implement independent visibility verification before setting READY.
            with self.db.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                owned = db.execute("SELECT lease_token FROM jobs WHERE id=?",(job["id"],)).fetchone()
                if owned[0] != token:
                    return True  # stale worker is fenced out
                for stage in ("CHUNKING","EMBEDDING","INDEXING"):
                    db.execute("UPDATE jobs SET state=? WHERE id=?",(stage,job["id"]))
                db.executemany("INSERT OR REPLACE INTO chunks VALUES(?,?,?,?,?,?,?,?)",rows)
                children = [r for r in rows if r[4]=="child"]
                for child in children:
                    db.execute("INSERT OR REPLACE INTO lexical_index VALUES(?,?)",(child[0],child[6]))
                    db.execute("INSERT OR REPLACE INTO vector_index VALUES(?,?)",(child[0],json.dumps(vector(child[6]))))
                db.execute("UPDATE jobs SET state='VERIFYING' WHERE id=?",(job["id"],))
                count = db.execute("SELECT COUNT(*) FROM chunks c JOIN lexical_index l ON l.chunk_id=c.id JOIN vector_index v ON v.chunk_id=c.id WHERE c.doc_id=? AND c.version=? AND c.kind='child'",(job["doc_id"],job["version"])).fetchone()[0]
                if count != len(children):
                    raise ValueError("dual index verification failed")
                db.execute("UPDATE versions SET status='READY' WHERE doc_id=? AND version=? AND status='STAGING'",(job["doc_id"],job["version"]))
                db.execute("UPDATE jobs SET state='READY',lease=NULL,error=NULL WHERE id=?",(job["id"],))
        except Exception as exc:
            with self.db.connect() as db:
                db.execute("UPDATE jobs SET state='FAILED',error=?,lease=NULL WHERE id=? AND lease_token=?",(type(exc).__name__,job["id"],token))
                db.execute("UPDATE versions SET status='FAILED' WHERE doc_id=? AND version=? AND status='STAGING'",(job["doc_id"],job["version"]))
        return True
