"""Export or check the actual app contracts without starting servers or calling models."""
import argparse
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_mesh import APPS

OUTPUT = ROOT / 'docs' / 'openapi'


def contract(name):
    """Import one app and return its generated document; no other service is imported."""
    reference, factory = APPS[name]
    module, attribute = reference.split(':')
    app = getattr(importlib.import_module(module), attribute)
    if factory:
        app = app()
    return app.openapi()


def serialize(document):
    return json.dumps(document, ensure_ascii=False, indent=2) + '\n'


def snapshot(name):
    return OUTPUT / f'{name}.json'


def label(path):
    """Repository-relative where that makes sense, absolute otherwise."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def check(names):
    """Report drift without creating or changing any file."""
    drift = []
    for name in names:
        path = snapshot(name)
        if not path.is_file():
            drift.append(f'{name}: {label(path)} is missing')
            continue
        try:
            stored = json.loads(path.read_text(encoding='utf-8'))
        except ValueError as exc:
            drift.append(f'{name}: snapshot is not valid JSON ({exc})')
            continue
        # Compare documents rather than bytes: reformatting alone is not drift.
        if stored != contract(name):
            drift.append(f'{name}: snapshot does not match the live contract')
    return drift


def export(names):
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for name in names:
        snapshot(name).write_text(serialize(contract(name)), encoding='utf-8')
    return names


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--services', nargs='+', metavar='NAME', default=list(APPS),
        help='export only these services (default: ' + ', '.join(APPS) + ')',
    )
    parser.add_argument(
        '--check', action='store_true',
        help='compare with the versioned snapshots and change nothing',
    )
    args = parser.parse_args(argv)
    unknown = [name for name in args.services if name not in APPS]
    if unknown:
        parser.error('unknown service(s): ' + ', '.join(unknown)
                     + '. Valid names: ' + ', '.join(APPS))
    # Keep the declared order however the selection was spelled.
    selected = set(args.services)
    names = [name for name in APPS if name in selected]

    if args.check:
        drift = check(names)
        for line in drift:
            print(line, file=sys.stderr)
        if drift:
            print(f'{len(drift)} of {len(names)} contracts differ; '
                  'run without --check to update them.', file=sys.stderr)
            return 1
        print(f'{len(names)} OpenAPI contracts match their snapshots.')
        return 0

    export(names)
    print(f'Exported {len(names)} OpenAPI contracts.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
