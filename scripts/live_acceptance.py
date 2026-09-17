"""Real-model HTTP acceptance. Run against a NEW isolated production mesh."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.services import ALL_SERVICES, call_service, response_json
from console.workflow import Workflow
from evaluation.cf105_cases import sources, poisoned
from tests.support import closeout_pdf


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default='out/acceptance/live.json')
    args=parser.parse_args()
    evidence={'kind':'real-model-http-acceptance','started_at':datetime.now(timezone.utc).isoformat(),
              'commit':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
              'working_tree_dirty':bool(subprocess.check_output(['git','status','--porcelain'],text=True).strip()),
              'checks':[], 'complete':False, 'release_eligible':False}
    output=Path(args.output); output.parent.mkdir(parents=True,exist_ok=True)
    def save(): output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    try:
        if not os.getenv('OPENAI_API_KEY'):
            raise RuntimeError('OPENAI_API_KEY is missing; live acceptance was not executed')
        for name,url in ALL_SERVICES.items():
            call_service('GET',url+'/health',timeout=10)
        existing=response_json(call_service('GET',ALL_SERVICES['vault']+'/engagements'))
        if existing.get('total') != 0:
            raise RuntimeError('Live acceptance requires an empty, isolated Vault')
        for i,source in enumerate(sources(),1):
            loader=Workflow()
            # Reader is the only writer, including acceptance uploads.
            loader.extract(f'cf105-{i}.pdf',closeout_pdf(source))
            for language in ('en','de','tr'):
                flow=Workflow(language=language); flow.select(source['id'],language)
                flow.generate(); report=flow.verify()
                assert flow.verified, f'Clean source {source["id"]}/{language} did not PASS: {report}'
                flow.approve(True)
                format,layout=[('docx','full-case-study'),('pdf','full-case-study'),
                               ('pdf','one-pager'),('pdf','single-slide')][(i-1)%4]
                flow.publish(format,layout)
                body=flow.download(); provenance=json.loads(flow.download(True))
                assert body.startswith(b'PK' if format=='docx' else b'%PDF')
                assert provenance['source_records']==[source['id']]
                artifact=output.parent/f'{source["id"]}-{language}.{format}'
                artifact.write_bytes(body)
                evidence['checks'].append({'source':source['id'],'language':language,'expected':'PASS',
                    'verdict':report['verdict'],'correlation_id':flow.trace,'artifact':artifact.name})
                if i==1:
                    for label,draft in poisoned(flow.draft,source,language):
                        blocked=response_json(call_service('POST',ALL_SERVICES['verifier']+'/verify',timeout=80,
                            headers=flow.headers(),json={'record_id':source['id'],'draft':draft,'language':language}))
                        assert blocked.get('verdict')=='BLOCK' and blocked.get('problems'), f'{language}/{label} escaped BLOCK'
                        evidence['checks'].append({'source':source['id'],'language':language,'case':label,
                            'expected':'BLOCK','verdict':blocked['verdict'],'correlation_id':flow.trace})
                save()
                print(f'{source["id"]}/{language}: PASS; downloaded {format}',flush=True)
        for route in ('/coverage','/gaps'):
            response_json(call_service('GET',ALL_SERVICES['analyst']+route))
        matches=response_json(call_service('POST',ALL_SERVICES['librarian']+'/match',timeout=60,
                                           json={'rfp_text':'Python payment processing','top_k':1}))
        assert matches.get('requirements'), 'Librarian returned no requirement evaluation'
        evidence['complete']=True
        evidence['remaining_release_gates']=['Both UI live-model acceptance','Outage scenarios',
                                             'Visual document review','All evidence on the same clean commit']
    except Exception as exc:
        evidence['error']=str(exc)
        print(str(exc),file=sys.stderr)
    finally:
        save()
    return 0 if evidence['complete'] else 2


if __name__=='__main__':raise SystemExit(main())
