"""End-to-end local check; isolated temp storage, no running server required."""
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from tower_kb.config import Settings
from tower_kb.main import create_app

with tempfile.TemporaryDirectory() as temp:
    settings=Settings(Path(temp),"smoke-token-not-for-production-1234")
    with TestClient(create_app(settings)) as client:
        client.headers["Authorization"]="Bearer "+settings.token
        payload={"title":"合成演示规范","source_id":"synthetic-demo","source_revision":1,
                 "content":"合成测试材料：RRU 告警应由授权人员核对告警码与设备状态。此材料仅用于软件测试，不是生产操作规范。"}
        response=client.post("/api/v1/documents",json=payload)
        assert response.status_code==202,response.text
        document=response.json()
        assert client.app.state.container.pipeline.run_once()
        job=client.get("/api/v1/jobs/"+document["job_id"]).json()
        assert job["state"]=="READY",job
        response=client.post(f"/api/v1/documents/{document['doc_id']}/versions/1/publish")
        assert response.status_code==200,response.text
        answer=client.post("/api/v1/chat",json={"query":"RRU 告警"}).json()
        assert answer["has_knowledge"] and answer["reference"],answer
        assert client.delete("/api/v1/documents/"+document["doc_id"]).status_code==200
        answer=client.post("/api/v1/chat",json={"query":"RRU 告警"}).json()
        assert answer["status"]=="no_knowledge",answer
        print("PASS: upload → durable job → dual index → publish → cited answer → revoke")
