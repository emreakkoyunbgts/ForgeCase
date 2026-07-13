"""
VAULT — Kaan

Stores Engagement Records and serves them over HTTP.

    python -m vault.vault store <record.json>
    python -m vault.vault get <engagement-id>
    python -m vault.vault serve

See the Project Specification, sections 3 and 5.
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path

from common.contract import load_record, load_corpus
from common.errors import die

DB_PATH = "vault/engagements.db"


def init_db():
    """
    TODO(Kaan) L1: design the schema properly.

    Draw the E-R model FIRST (it is your strength — use it). Think about:
      - which fields are columns, which are JSON blobs?
      - outcomes is a LIST. One-to-many table, or a JSON column?
      - eng-12 has an EMPTY outcomes list. Do not let that break you.
    """
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    # --- STUB: a single JSON blob. Works, but you can do better. -----------
    conn.execute("""
        CREATE TABLE IF NOT EXISTS engagements (
            id   TEXT PRIMARY KEY,
            data TEXT NOT NULL
        )
    """)
    conn.commit()
    return conn


def store(record):
    """Save a record. TODO(Kaan): make this survive a restart, provably."""
    conn = init_db()
    conn.execute(
        "INSERT OR REPLACE INTO engagements (id, data) VALUES (?, ?)",
        (record["id"], json.dumps(record, ensure_ascii=False)),
    )
    conn.commit()
    print(f"[vault] stored {record['id']}", file=sys.stderr)


def get(engagement_id):
    """Fetch one record by id. Returns None if it isn't there."""
    conn = init_db()
    row = conn.execute(
        "SELECT data FROM engagements WHERE id = ?", (engagement_id,)
    ).fetchone()
    return json.loads(row[0]) if row else None


def serve():
    """
    TODO(Kaan) L2: the REST API.

        POST /engagements        -> save a record
        GET  /engagements/{id}   -> fetch one (404 if missing!)
        GET  /engagements        -> list them all

    Use FastAPI. Then write TWO tests: one that works, one that 404s.
    The 404 test is the one that matters.
    """
    die("not implemented yet — this is your L2 ticket, Kaan")


def main():
    parser = argparse.ArgumentParser(description="Engagement Record store")
    sub = parser.add_subparsers(dest="command", required=True)

    p_store = sub.add_parser("store")
    p_store.add_argument("record", help="path to a record.json")

    p_get = sub.add_parser("get")
    p_get.add_argument("id", help="engagement id, e.g. eng-01")

    sub.add_parser("serve")
    sub.add_parser("load-all", help="load all 12 records from the corpus")

    args = parser.parse_args()

    if args.command == "store":
        store(load_record(args.record))
    elif args.command == "get":
        record = get(args.id)
        if record is None:
            die(f"no engagement with id '{args.id}'")
        json.dump(record, sys.stdout, indent=2, ensure_ascii=False)
        print()
    elif args.command == "load-all":
        for record in load_corpus():
            store(record)
    elif args.command == "serve":
        serve()


if __name__ == "__main__":
    main()
