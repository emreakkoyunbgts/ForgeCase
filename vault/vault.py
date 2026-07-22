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
    Open the database, creating the schema on first use.

    The E-R model lives in vault/er-model.md. Summary:
      - engagements: one row per record, scalar contract fields as columns
      - outcomes, technologies: one-to-many child tables, `position`
        preserves the original list order (round-trip must be identical)
      - eng-12's empty outcomes list is simply zero child rows
    """
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS engagements (
            id              TEXT PRIMARY KEY,
            client          TEXT    NOT NULL,
            client_type     TEXT    NOT NULL CHECK (client_type <> ''),
            may_be_named    INTEGER NOT NULL CHECK (may_be_named IN (0, 1)),
            domain          TEXT    NOT NULL,
            region          TEXT    NOT NULL
                            CHECK (region IN ('UK', 'DE', 'NL', 'TR', 'GCC')),
            challenge       TEXT    NOT NULL,
            solution        TEXT    NOT NULL,
            -- NULL in the three columns below means "key absent in the
            -- original record" — the read path omits the key entirely.
            outcome_missing INTEGER CHECK (outcome_missing IN (0, 1)),
            team_size       INTEGER,
            duration_months INTEGER
        );

        CREATE TABLE IF NOT EXISTS outcomes (
            engagement_id TEXT    NOT NULL
                          REFERENCES engagements(id) ON DELETE CASCADE,
            position      INTEGER NOT NULL,
            metric        TEXT    NOT NULL CHECK (metric <> ''),
            source_ref    TEXT    NOT NULL CHECK (source_ref <> ''),
            PRIMARY KEY (engagement_id, position)
        );

        CREATE TABLE IF NOT EXISTS technologies (
            engagement_id TEXT    NOT NULL
                          REFERENCES engagements(id) ON DELETE CASCADE,
            position      INTEGER NOT NULL,
            name          TEXT    NOT NULL,
            PRIMARY KEY (engagement_id, position)
        );
    """)
    conn.commit()
    return conn


def _optional_bool(record, key):
    """0/1 for a boolean the record has, NULL for a key it doesn't."""
    return None if key not in record else int(record[key])


def store(record):
    """Save a record. Storing the same id again replaces it completely."""
    conn = init_db()
    with conn:  # one transaction: the record is stored fully or not at all
        conn.execute("DELETE FROM engagements WHERE id = ?", (record["id"],))
        conn.execute(
            """
            INSERT INTO engagements
                (id, client, client_type, may_be_named, domain, region,
                 challenge, solution, outcome_missing, team_size,
                 duration_months)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"], record["client"], record["client_type"],
                int(record["may_be_named"]), record["domain"],
                record["region"], record["challenge"], record["solution"],
                _optional_bool(record, "outcome_missing"),
                record.get("team_size"), record.get("duration_months"),
            ),
        )
        conn.executemany(
            "INSERT INTO outcomes (engagement_id, position, metric, source_ref)"
            " VALUES (?, ?, ?, ?)",
            [(record["id"], i, o["metric"], o["source_ref"])
             for i, o in enumerate(record["outcomes"])],
        )
        conn.executemany(
            "INSERT INTO technologies (engagement_id, position, name)"
            " VALUES (?, ?, ?)",
            [(record["id"], i, name)
             for i, name in enumerate(record["technologies"])],
        )
    print(f"[vault] stored {record['id']}", file=sys.stderr)


def _row_to_record(conn, row):
    """Rebuild the exact contract dict from the relational tables."""
    record = {
        "id": row["id"],
        "client": row["client"],
        "client_type": row["client_type"],
        "may_be_named": bool(row["may_be_named"]),
        "domain": row["domain"],
        "region": row["region"],
        "challenge": row["challenge"],
        "solution": row["solution"],
        "technologies": [name for (name,) in conn.execute(
            "SELECT name FROM technologies"
            " WHERE engagement_id = ? ORDER BY position", (row["id"],))],
        "outcomes": [{"metric": metric, "source_ref": source_ref}
                     for metric, source_ref in conn.execute(
            "SELECT metric, source_ref FROM outcomes"
            " WHERE engagement_id = ? ORDER BY position", (row["id"],))],
    }
    # Optional keys: only put them back if the original record had them.
    # A NULL column must NOT become "key": null — that would break the
    # round-trip equality.
    if row["outcome_missing"] is not None:
        record["outcome_missing"] = bool(row["outcome_missing"])
    if row["team_size"] is not None:
        record["team_size"] = row["team_size"]
    if row["duration_months"] is not None:
        record["duration_months"] = row["duration_months"]
    return record


def get(engagement_id):
    """Fetch one record by id. Returns None if it isn't there."""
    conn = init_db()
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM engagements WHERE id = ?", (engagement_id,)
    ).fetchone()
    return _row_to_record(conn, row) if row else None


def list_all():
    """All stored records, ordered by id."""
    conn = init_db()
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM engagements ORDER BY id").fetchall()
    return [_row_to_record(conn, row) for row in rows]


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
