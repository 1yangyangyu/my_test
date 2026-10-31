import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from tower_kb.adapters.search import LexicalIndex, VectorIndex, tokens
from tower_kb.adapters.generator import ExtractiveGenerator
from tower_kb.domain.errors import DomainError
from tower_kb.domain.policy import allowed, now
from tower_kb.rag.fusion import rrf
from tower_kb.rag.citation_validator import validate

NO_KNOWLEDGE = "当前知识库暂无对应处置规范，请联系后台支撑人员"

class RagService:
    def __init__(self, db, lexical=None, vector=None, generator=None):
        self.db = db
        self.lexical, self.vector = lexical or LexicalIndex(), vector or VectorIndex()
        self.generator = generator or ExtractiveGenerator()

    def session(self, db, sid, actor):
        row = db.execute("SELECT * FROM sessions WHERE id=?",(sid,)).fetchone()
        if not row or row["org_id"]!=actor.org_id or row["user_id"]!=actor.user_id:
            raise DomainError("not_found", "会话不存在",404)

    def visible(self, db, actor):
        rows = db.execute("SELECT v.*,d.org_id,d.deleted,d.current_version FROM versions v JOIN documents d ON d.id=v.doc_id WHERE d.org_id=? AND d.deleted=0 AND v.status='PUBLISHED' AND d.current_version=v.version",(actor.org_id,)).fetchall()
        result = {}
        for row in rows:
            v = dict(row)
            v["roles"],v["regions"] = json.loads(v["roles"]),json.loads(v["regions"])
            if allowed(v,actor):
                result[(v["doc_id"],v["version"])] = v
        return result

    def answer(self, req, actor):
        request_id = uuid.uuid4().hex
        sid = req.session_id
        with self.db.connect() as db:
            if sid:
                self.session(db,sid,actor)
            else:
                sid = uuid.uuid4().hex
                db.execute("INSERT INTO sessions VALUES(?,?,?)",(sid,actor.org_id,actor.user_id))
            scope = self.visible(db,actor)
            chunks = []
            # Only authorized current versions are loaded into either search branch.
            for (did,version),meta in scope.items():
                if req.filters.source_kind and meta["source_kind"] != req.filters.source_kind:
                    continue
                for row in db.execute("SELECT c.*,l.text AS indexed_text,v.vector FROM chunks c JOIN lexical_index l ON l.chunk_id=c.id JOIN vector_index v ON v.chunk_id=c.id WHERE c.doc_id=? AND c.version=? AND c.kind='child'",(did,version)):
                    chunk = dict(row);chunk["vector"] = json.loads(chunk["vector"]);chunks.append(chunk)
            warnings = ["本地检索与原文摘录基线，未接入 BGE/Qwen；结果需业务复核"]
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [pool.submit(index.search,req.query,chunks) for index in (self.lexical,self.vector)]
                rankings = [f.result(timeout=5) for f in futures]
            fused = rrf(rankings)
            by_id = {c["id"]:c for c in chunks}
            # Conservative token-overlap gate; semantic quality needs evaluation.
            qtokens = set(tokens(req.query))
            ranked = sorted(fused,key=lambda cid:(-len(qtokens & set(tokens(by_id[cid]["text"]))),fused.index(cid)))
            evidence,seen,budget = [],set(),4000
            # Effective standards precede case experience; cases remain clearly labeled.
            ranked.sort(key=lambda cid:scope[(by_id[cid]["doc_id"],by_id[cid]["version"])]["source_kind"] != "standard")
            for cid in ranked:
                c = by_id[cid]
                overlap = len(qtokens & set(tokens(c["text"]))) / max(1,len(qtokens))
                if overlap < .15 or c["parent_id"] in seen:
                    continue
                parent = db.execute("SELECT * FROM chunks WHERE id=? AND doc_id=? AND version=?",(c["parent_id"],c["doc_id"],c["version"])).fetchone()
                if not parent or len(parent["text"]) > budget:
                    continue
                meta = scope[(c["doc_id"],c["version"])]
                evidence.append({"citation_id":f"E{len(evidence)+1}","chunk_id":cid,"doc_id":c["doc_id"],"version":c["version"],"file_name":meta["title"],"pos":c["position"],"source_kind":meta["source_kind"],"text":c["text"],"parent_context":parent["text"]})
                seen.add(c["parent_id"]);budget-=len(parent["text"])
                if len(evidence)==3: break
            result = {"request_id":request_id,"trace_id":request_id,"session_id":sid,"query":req.query,"status":"no_knowledge","answer":NO_KNOWLEDGE,"reason_chain":"","reference":[],"has_knowledge":False,"degraded":True,"warnings":warnings}
            if evidence:
                draft = self.generator.generate(req.query,evidence)
                cited = validate(draft,evidence)
                result.update(status="answered",answer=draft["answer"],has_knowledge=True,reason_chain="证据：以下引用原文。可能原因及待验证事项需结合现场信息人工确认。",reference=[{k:v for k,v in e.items() if k not in ("text","parent_context")} for e in cited])
        # Recheck within the response-save transaction so concurrent revocation
        # cannot pass between the authoritative check and persistence.
        with self.db.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.session(db,sid,actor)
            current = self.visible(db,actor)
            if any((e["doc_id"],e["version"]) not in current for e in evidence):
                raise DomainError("scope_changed","知识权限或版本已变化，请重试",409,True)
            db.execute("INSERT INTO messages VALUES(?,?,?,?,?)",(request_id,sid,req.query,json.dumps(result,ensure_ascii=False),now()))
        return result
