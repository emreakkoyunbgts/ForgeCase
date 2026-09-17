"""Explicit offline UI test server. Never used by the production launcher.

Run: python -m tests.ui_mesh --port 18880
All business APIs are real; translation, semantic and retrieval providers are
labelled synthetic test doubles. This is not live model acceptance evidence.
"""
import argparse
import os
import tempfile


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=18880)
    parser.add_argument('--with-ui',action='store_true',help='Also start isolated QA UIs on 15173 and 18501')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='caseforge-ui-test-') as directory:
        os.environ['CASEFORGE_VAULT_DB']=os.path.join(directory,'vault.db')
        os.environ['CASEFORGE_ARTIFACT_DIR']=os.path.join(directory,'artifacts')
        os.environ['CASEFORGE_TOKEN']='cf105-ui-test-token'
        for name in ('vault','generator','verifier','reader','publisher','librarian','analyst'):
            os.environ[name.upper()+'_URL']=f'http://127.0.0.1:{args.port}/{name}'
        from fastapi import FastAPI
        from common.drafts import rendered_spans
        from generator import GeneratorController as generator
        from generator.translation import get_translator
        from verifier import VerifierController as verifier
        from verifier.semantic import get_semantic_checker
        from vault import vault
        from publisher.service import app as publisher
        from reader.api import create_app as reader_app
        from librarian import service as librarian
        from analyst.api import app as analyst
        from tests.support import record,translated
        import uvicorn

        async def translate(draft,source,language,trace):
            return translated(source,language)
        async def check(draft,source,language,trace):
            expected={item['text'] for item in rendered_spans(translated(source,language))}
            return [{'type':'unsupported_claim','why':'Synthetic test fixture rejects changed source facts',
                     'value':item['text']} for item in rendered_spans(draft) if item['text'] not in expected]
        def match(rfp_text,corpus,**kwargs):
            return {'requirements':[{'requirement':rfp_text,'best_match':
                {'engagement_id':corpus[0]['id']} if corpus else None}]}
        generator.app.dependency_overrides[get_translator]=lambda:translate
        verifier.app.dependency_overrides[get_semantic_checker]=lambda:check
        librarian.evaluate_rfp_requirements=match
        librarian.librarian_search=lambda query,corpus,**kwargs:[{'engagement_id':r['id']} for r in corpus[:3]]
        for i in range(1,13):vault.store(record(i))
        root=FastAPI(title='CF-105 OFFLINE TEST MESH — synthetic providers')
        for name,app in {'vault':vault.create_app(),'reader':reader_app(),'generator':generator.app,
                         'verifier':verifier.app,'publisher':publisher,'librarian':librarian.app,'analyst':analyst}.items():
            root.mount('/'+name,app)
        processes=[]; logs=[]
        try:
            if args.with_ui:
                import subprocess
                import sys
                import shutil
                from pathlib import Path
                from scripts.run_mesh import ROOT, stop_process
                log_dir=ROOT/'out'/'logs'; log_dir.mkdir(parents=True,exist_ok=True)
                commands={
                    'console-qa':([sys.executable,'-B','-m','streamlit','run','console/console.py',
                        '--server.address','127.0.0.1','--server.port','18501','--server.headless','true',
                        '--browser.gatherUsageStats','false'],ROOT),
                    'react-qa':([shutil.which('node'),'node_modules/vite/bin/vite.js','--host','127.0.0.1',
                                '--port','15173','--strictPort'],ROOT/'front-end'),
                }
                for name,(command,cwd) in commands.items():
                    log=(log_dir/(name+'.log')).open('w',encoding='utf-8'); logs.append(log)
                    processes.append(subprocess.Popen(command,cwd=cwd,env=os.environ.copy(),stdout=log,
                        stderr=subprocess.STDOUT,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
            print('OFFLINE SYNTHETIC PROVIDERS. React:15173 Console:18501 when --with-ui is set.',flush=True)
            uvicorn.run(root,host='127.0.0.1',port=args.port,log_level='warning')
        finally:
            for process in processes:stop_process(process)
            for log in logs:log.close()


if __name__=='__main__':main()
