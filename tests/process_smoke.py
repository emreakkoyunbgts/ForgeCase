"""Seven real OS processes, private stores, real HTTP, explicitly NO model calls.

This checks process isolation and fail-closed outages, not model acceptance.
Run separately: python -m tests.process_smoke
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from uuid import uuid4
import requests
from scripts.run_mesh import APPS, ROOT, stop_process
from tests.support import closeout_pdf, record
from generator.core import generate_mcs


def main():
    processes={}; logs=[]; evidence={'kind':'seven-process-no-model-smoke','checks':[]}
    output=ROOT/'out'/'acceptance'/'process-smoke.json'; output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cf105-process-') as temporary:
        env=os.environ.copy(); env['OPENAI_API_KEY']=''; env['CASEFORGE_TOKEN']='synthetic-process-token'
        env['CASEFORGE_VAULT_DB']=str(Path(temporary)/'vault-private'/'vault.db')
        env['CASEFORGE_ARTIFACT_DIR']=str(Path(temporary)/'publisher-private')
        addresses={}
        # Reserve distinct ephemeral ports while choosing the complete map.
        reservations=[]
        for name in APPS:
            sock=socket.socket(); sock.bind(('127.0.0.1',0)); reservations.append(sock)
            addresses[name]=f'http://127.0.0.1:{sock.getsockname()[1]}'
            env[name.upper()+'_URL']=addresses[name]
        for sock in reservations:sock.close()
        trace=str(uuid4()); headers={'Authorization':'Bearer synthetic-process-token','X-Correlation-ID':trace,
                                    'Idempotency-Key':str(uuid4())}
        def check(name, method, path, expected, **kwargs):
            response=requests.request(method,addresses[name]+path,headers=headers,timeout=20,**kwargs)
            assert response.status_code==expected,(name,path,response.status_code,response.text)
            assert response.headers.get('X-Correlation-ID')==trace,(name,'trace lost')
            evidence['checks'].append({'service':name,'path':path,'status':response.status_code,'correlation_id':trace})
            return response
        def stop(name):
            process=processes[name]
            stop_process(process)
        try:
            for name,(reference,factory) in APPS.items():
                log=(Path(temporary)/(name+'.log')).open('w',encoding='utf-8'); logs.append(log)
                command=[sys.executable,'-B','-m','uvicorn',reference,'--host','127.0.0.1',
                         '--port',addresses[name].rsplit(':',1)[1]]
                if factory:command.append('--factory')
                processes[name]=subprocess.Popen(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
            deadline=time.monotonic()+90
            pending=set(APPS)
            while pending and time.monotonic()<deadline:
                for name in list(pending):
                    if processes[name].poll() is not None:
                        raise RuntimeError(name+' failed to start: '+(Path(temporary)/(name+'.log')).read_text())
                    try:
                        if requests.get(addresses[name]+'/health',timeout=.5).status_code==200:pending.remove(name)
                    except requests.RequestException:pass
                if pending:time.sleep(.5)
            assert not pending, f'Services did not become ready: {pending}'
            for name in APPS:check(name,'GET','/health',200)
            source=record(); draft=generate_mcs(source)
            check('reader','POST','/extract',200,files={'document':('synthetic.pdf',closeout_pdf(source),'application/pdf')})
            check('vault','GET','/engagements/'+source['id'],200)
            check('analyst','GET','/coverage',200); check('analyst','GET','/gaps',200)
            check('librarian','POST','/match',200,json={'rfp_text':'Python payments','top_k':1})
            check('generator','POST','/generate',503,json={'record_id':source['id']})
            payload={'record_id':source['id'],'draft':draft,'language':'en'}
            check('verifier','POST','/verify',503,json=payload)
            check('publisher','POST','/publish',503,json=payload)
            stop('verifier')
            check('publisher','POST','/publish',503,json=payload)
            stop('librarian')
            check('generator','POST','/generator/mcs/query',503,params={'query':'Python payments'})
            stop('vault')
            check('generator','POST','/generate',503,json={'record_id':source['id']})
            assert not Path(env['CASEFORGE_ARTIFACT_DIR']).exists(), 'Outage created an artifact'
            evidence.update(complete=True,process_ids={name:p.pid for name,p in processes.items()})
            print(f'{len(evidence["checks"])} real HTTP checks passed across seven separate processes.',flush=True)
        except Exception as exc:
            evidence.update(complete=False,error=str(exc)); raise
        finally:
            for process in processes.values():
                stop_process(process)
            for log in logs:log.close()
            output.write_text(json.dumps(evidence,indent=2),encoding='utf-8')


if __name__=='__main__':main()
