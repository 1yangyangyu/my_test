"""Start real API and independent Worker, then exercise the HTTP workflow."""
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import httpx


def main():
    with tempfile.TemporaryDirectory() as directory:
        env={**os.environ,'TOWER_DATA_DIR':directory,'TOWER_DEV_TOKEN':secrets.token_urlsafe(32),'TOWER_MODE':'local'}
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0))
            port=sock.getsockname()[1]
        api=subprocess.Popen([sys.executable,'-m','uvicorn','tower_kb.main:app','--host','127.0.0.1','--port',str(port)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        worker=None
        try:
            with httpx.Client(base_url=f'http://127.0.0.1:{port}',trust_env=False,timeout=3,headers={'Authorization':'Bearer '+env['TOWER_DEV_TOKEN']}) as client:
                for _ in range(100):
                    if api.poll() is not None:
                        raise RuntimeError(api.stderr.read().decode())
                    try:
                        if client.get('/health/ready').status_code==200: break
                    except httpx.ConnectError: pass
                    time.sleep(.1)
                else: raise RuntimeError('API readiness timeout')
                upload=client.post('/api/v1/documents',json={'title':'合成测试','source_id':'live-smoke','source_revision':1,'content':'RRU 告警合成测试规范，仅供软件测试。'})
                upload.raise_for_status()
                d=upload.json()
                worker=subprocess.Popen([sys.executable,'-m','tower_kb.workers.tasks','--once'],env=env)
                if worker.wait(timeout=20)!=0: raise RuntimeError('worker failed')
                job=client.get('/api/v1/jobs/'+d['job_id']).json()
                assert job['state']=='READY',job
                client.post(f"/api/v1/documents/{d['doc_id']}/versions/1/publish").raise_for_status()
                answer=client.post('/api/v1/chat',json={'query':'RRU 告警'}).json()
                assert answer['status']=='answered' and answer['reference'],answer
                print('PASS: real Uvicorn HTTP + separate Worker + persistent SQLite + cited answer')
        finally:
            if worker is not None and worker.poll() is None:
                worker.terminate();worker.wait(timeout=5)
            api.terminate();api.wait(timeout=5)
            api.stderr.close()

if __name__=='__main__': main()
