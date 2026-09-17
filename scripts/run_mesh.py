"""Start the seven real APIs, optionally both UIs, with one supported port map."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from common.services import ALL_SERVICES

APPS={
    'vault':('vault.vault:create_app',True), 'reader':('reader.api:create_app',True),
    'generator':('generator.GeneratorController:app',False),
    'verifier':('verifier.VerifierController:app',False),
    'publisher':('publisher.service:app',False), 'librarian':('librarian.service:app',False),
    'analyst':('analyst.api:app',False),
}


def stop_process(process):
    """Windows venv launchers own a child interpreter; stop the owned tree."""
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--with-ui',action='store_true')
    parser.add_argument('--isolated',action='store_true',help='Use new private temporary Vault/artifact stores')
    args=parser.parse_args()
    processes=[]; logs=[]
    temporary=tempfile.TemporaryDirectory(prefix='caseforge-mesh-') if args.isolated else None
    env=os.environ.copy()
    if temporary:
        env['CASEFORGE_VAULT_DB']=str(Path(temporary.name)/'vault.db')
        env['CASEFORGE_ARTIFACT_DIR']=str(Path(temporary.name)/'artifacts')
    log_dir=ROOT/'out'/'logs'; log_dir.mkdir(parents=True,exist_ok=True)
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0

    def start(name,command,cwd=ROOT):
        stream=(log_dir/(name+'.log')).open('a',encoding='utf-8')
        logs.append(stream)
        process=subprocess.Popen(command,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,
                                 creationflags=flags)
        processes.append((name,process))
    try:
        for name,(app,factory) in APPS.items():
            address=urlsplit(ALL_SERVICES[name])
            if address.hostname not in {'localhost','127.0.0.1'} or address.path not in {'','/'}:
                parser.error('The local launcher requires loopback service URLs without path prefixes')
            command=[sys.executable,'-m','uvicorn',app,'--host','127.0.0.1','--port',str(address.port)]
            if factory:command.append('--factory')
            start(name,command)
        if args.with_ui:
            start('console',[sys.executable,'-m','streamlit','run','console/console.py',
                             '--server.address','127.0.0.1','--server.port','8501','--server.headless','true'])
            node=shutil.which('node')
            if not node:raise RuntimeError('Node.js is required for the React UI')
            start('react',[node,'node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5173'],ROOT/'front-end')
        print('Mesh started. Logs: '+str(log_dir),flush=True)
        print('Press Ctrl+C to stop only these child processes.',flush=True)
        while True:
            for name,process in processes:
                if process.poll() is not None:raise RuntimeError(f'{name} exited; inspect {log_dir/name}.log')
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for _,process in processes:
            stop_process(process)
        for stream in logs:stream.close()
        if temporary:temporary.cleanup()


if __name__=='__main__':main()
