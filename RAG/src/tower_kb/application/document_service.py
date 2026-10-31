import hashlib
import json
import uuid
from tower_kb.domain.errors import DomainError
from tower_kb.domain.policy import now

class DocumentService:
    def __init__(self, db, objects):
        self.db, self.objects = db, objects
        objects.mkdir(parents=True, exist_ok=True)

    def upload(self, req, actor, doc_id=None):
        if "admin" not in actor.roles:
            raise DomainError("forbidden", "需要知识管理员权限", 403)
        if not set(req.roles) <= set(actor.roles) or not set(req.regions) <= set(actor.regions):
            raise DomainError("forbidden", "元数据超出管理员授权范围", 403)
        digest = hashlib.sha256(req.content.encode()).hexdigest()
        # Content-addressed storage; original titles never become paths.
        key = digest + ".txt"
        path = self.objects / key
        if not path.exists():
            temp = self.objects / (uuid.uuid4().hex + ".tmp")
            temp.write_text(req.content, encoding="utf-8")
            temp.replace(path)
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if doc_id:
                doc = db.execute("SELECT * FROM documents WHERE id=? AND org_id=? AND deleted=0", (doc_id,actor.org_id)).fetchone()
                if not doc:
                    raise DomainError("not_found", "文档不存在", 404)
                if doc["source_id"] != req.source_id:
                    raise DomainError("source_mismatch", "版本必须使用相同 source_id", 409)
            else:
                doc = db.execute("SELECT * FROM documents WHERE org_id=? AND source_id=?", (actor.org_id,req.source_id)).fetchone()
                if doc and doc["deleted"]:
                    raise DomainError("revoked", "来源已撤销，请使用新的来源标识", 409)
            did = doc["id"] if doc else uuid.uuid4().hex
            previous = db.execute("SELECT * FROM versions WHERE doc_id=? AND revision=?", (did,req.source_revision)).fetchone()
            if previous:
                metadata = (req.title,req.source_kind,json.dumps(req.roles),json.dumps(req.regions),req.effect_start,req.effect_end)
                stored = tuple(previous[k] for k in ("title","source_kind","roles","regions","effect_start","effect_end"))
                if previous["hash"] != digest or metadata != stored:
                    raise DomainError("revision_conflict", "同一来源版本对应的内容或元数据不同", 409)
                job = db.execute("SELECT id FROM jobs WHERE doc_id=? AND version=?", (did,previous["version"])).fetchone()
                return {"doc_id":did,"version":previous["version"],"job_id":job["id"]}
            latest = db.execute("SELECT MAX(revision),MAX(version) FROM versions WHERE doc_id=?", (did,)).fetchone()
            if latest[0] is not None and req.source_revision <= latest[0]:
                raise DomainError("stale_revision", "拒绝乱序来源版本", 409)
            version = (latest[1] or 0)+1
            db.execute("INSERT OR IGNORE INTO documents(id,org_id,source_id) VALUES(?,?,?)", (did,actor.org_id,req.source_id))
            db.execute("INSERT INTO versions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (did,version,req.source_revision,digest,req.title,req.source_kind,json.dumps(req.roles),json.dumps(req.regions),req.effect_start,req.effect_end,"STAGING",key))
            jid = uuid.uuid4().hex
            db.execute("INSERT INTO jobs(id,doc_id,version,state) VALUES(?,?,?,?)", (jid,did,version,"RECEIVED"))
            db.execute("INSERT INTO audit_events(actor,action,target,created_at) VALUES(?,?,?,?)", (actor.user_id,"upload",did,now()))
            return {"doc_id":did,"version":version,"job_id":jid}

    def publish(self, did, version, actor):
        if "admin" not in actor.roles:
            raise DomainError("forbidden", "需要知识管理员权限", 403)
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT v.*, d.org_id,d.deleted,d.current_version FROM versions v JOIN documents d ON d.id=v.doc_id WHERE v.doc_id=? AND v.version=? AND d.org_id=?",(did,version,actor.org_id)).fetchone()
            if not row or row["deleted"]:
                raise DomainError("not_found", "文档不存在",404)
            if row["status"] == "PUBLISHED" and row["current_version"] == version:
                return {"status":"PUBLISHED"}
            if row["status"] != "READY":
                raise DomainError("not_ready", "双索引验证完成后才能发布",409)
            max_revision = db.execute("SELECT MAX(revision) FROM versions WHERE doc_id=?",(did,)).fetchone()[0]
            if row["revision"] != max_revision:
                raise DomainError("stale_revision", "存在更新版本，拒绝发布旧来源版本",409)
            db.execute("UPDATE versions SET status='REVOKED' WHERE doc_id=? AND status='PUBLISHED'",(did,))
            db.execute("UPDATE versions SET status='PUBLISHED' WHERE doc_id=? AND version=?",(did,version))
            db.execute("UPDATE documents SET current_version=? WHERE id=?",(version,did))
            db.execute("UPDATE jobs SET state='PUBLISHED' WHERE doc_id=? AND version=?",(did,version))
            db.execute("INSERT INTO audit_events(actor,action,target,created_at) VALUES(?,?,?,?)",(actor.user_id,"publish",did,now()))
        return {"status":"PUBLISHED"}

    def revoke(self, did, actor):
        if "admin" not in actor.roles:
            raise DomainError("forbidden", "需要知识管理员权限",403)
        with self.db.connect() as db:
            changed = db.execute("UPDATE documents SET deleted=1 WHERE id=? AND org_id=?",(did,actor.org_id)).rowcount
            if not changed:
                raise DomainError("not_found","文档不存在",404)
            db.execute("UPDATE versions SET status='REVOKED' WHERE doc_id=?",(did,))
            db.execute("INSERT INTO audit_events(actor,action,target,created_at) VALUES(?,?,?,?)",(actor.user_id,"revoke",did,now()))
        return {"status":"REVOKED"}
