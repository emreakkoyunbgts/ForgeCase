"""Export the seven actual app contracts without starting servers or calling models."""
import importlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.run_mesh import APPS

if __name__=='__main__':
    output=Path(__file__).resolve().parents[1]/'docs'/'openapi'
    output.mkdir(parents=True,exist_ok=True)
    for name,(reference,factory) in APPS.items():
        module,attribute=reference.split(':')
        app=getattr(importlib.import_module(module),attribute)
        if factory:app=app()
        (output/f'{name}.json').write_text(json.dumps(app.openapi(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Exported seven OpenAPI contracts.')
