"""
VAULT — Kaan

Stores Engagement Records and serves them over HTTP.

    python -m vault.vault store <record.json>
    python -m vault.vault get <engagement-id>
    python -m vault.vault serve

See the Project Specification, sections 3 and 5.
"""
import argparse
import hashlib
import json
import os
import secrets
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from common.contract import REQUIRED_FIELDS, load_record, load_corpus
from common.errors import die

DB_PATH = "vault/engagements.db"


def etag_for(record):
    """
    Content hash of a record — used as an ETag (CF-62).

    Two identical records always get the same tag; any field change
    produces a different tag. That is how we detect concurrent edits.
    """
    payload = json.dumps(record, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _now_iso():
    """UTC timestamp with Z suffix, e.g. 2026-08-06T18:30:00.123456Z"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_as_of(as_of):
    """
    Accept common ISO-8601 forms and return a comparable UTC string.

    Examples: 2026-08-06T12:00:00Z  |  2026-08-06T12:00:00+00:00
    """
    text = as_of.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def init_db():
    """
    Open the database, creating the schema on first use.

    The E-R model lives in vault/er-model.md. Summary:
      - engagements: one row per record, scalar contract fields as columns
      - outcomes, technologies: one-to-many child tables, `position`
        preserves the original list order (round-trip must be identical)
      - eng-12's empty outcomes list is simply zero child rows
      - engagement_versions (CF-63): append-only history for as-of reads
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

        -- CF-63: append-only snapshots. No FK to engagements so history
        -- survives DELETE of the current row.
        CREATE TABLE IF NOT EXISTS engagement_versions (
            engagement_id TEXT    NOT NULL,
            version       INTEGER NOT NULL,
            recorded_at   TEXT    NOT NULL,
            data          TEXT    NOT NULL,
            PRIMARY KEY (engagement_id, version)
        );
    """)
    conn.commit()
    return conn


def _optional_bool(record, key):
    """0/1 for a boolean the record has, NULL for a key it doesn't."""
    return None if key not in record else int(record[key])


def _append_version(conn, record, recorded_at=None):
    """Append an immutable snapshot for CF-63 as-of history."""
    next_ver = conn.execute(
        "SELECT COALESCE(MAX(version), 0) + 1 FROM engagement_versions"
        " WHERE engagement_id = ?",
        (record["id"],),
    ).fetchone()[0]
    conn.execute(
        """
        INSERT INTO engagement_versions
            (engagement_id, version, recorded_at, data)
        VALUES (?, ?, ?, ?)
        """,
        (
            record["id"],
            next_ver,
            recorded_at or _now_iso(),
            json.dumps(record, ensure_ascii=False),
        ),
    )
    return next_ver


def store(record, recorded_at=None):
    """
    Save a record. Storing the same id again replaces the *current* row
    and also appends a new version snapshot (CF-63).
    """
    conn = init_db()
    with conn:  # one transaction: current + version, or nothing
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
        _append_version(conn, record, recorded_at=recorded_at)
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


def get(engagement_id, as_of=None):
    """
    Fetch one record by id.

    as_of=None  -> current row in engagements
    as_of=ISO   -> newest snapshot at or before that time (CF-63)
    """
    conn = init_db()
    if as_of is not None:
        stamp = _normalize_as_of(as_of)
        row = conn.execute(
            """
            SELECT data FROM engagement_versions
            WHERE engagement_id = ? AND recorded_at <= ?
            ORDER BY recorded_at DESC, version DESC
            LIMIT 1
            """,
            (engagement_id, stamp),
        ).fetchone()
        return json.loads(row[0]) if row else None

    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM engagements WHERE id = ?", (engagement_id,)
    ).fetchone()
    return _row_to_record(conn, row) if row else None


def list_versions(engagement_id):
    """
    Version history for one engagement, oldest first (CF-63).

    Each item: version, recorded_at, etag (content hash of that snapshot).
    """
    conn = init_db()
    rows = conn.execute(
        """
        SELECT version, recorded_at, data FROM engagement_versions
        WHERE engagement_id = ?
        ORDER BY version ASC
        """,
        (engagement_id,),
    ).fetchall()
    out = []
    for version, recorded_at, data in rows:
        record = json.loads(data)
        out.append({
            "version": version,
            "recorded_at": recorded_at,
            "etag": etag_for(record),
        })
    return out


def exists(engagement_id):
    """True if a record with this id is already stored (current row)."""
    conn = init_db()
    row = conn.execute(
        "SELECT 1 FROM engagements WHERE id = ?", (engagement_id,)
    ).fetchone()
    return row is not None


def delete(engagement_id):
    """
    Delete the *current* record. Version history is kept (CF-63 as-of
    still works for times before the delete).
    """
    conn = init_db()
    with conn:
        # CASCADE removes child outcomes / technologies rows too.
        # engagement_versions has no FK — history survives.
        cur = conn.execute(
            "DELETE FROM engagements WHERE id = ?", (engagement_id,)
        )
    return cur.rowcount > 0


def list_all(domain=None, region=None, limit=None, offset=0):
    """
    Stored records, optionally filtered and paginated (CF-61).

    Returns (items, total) where total is the count *before* limit/offset,
    so callers can build pagination UIs.
    """
    conn = init_db()
    conn.row_factory = sqlite3.Row
    where = []
    params = []
    if domain is not None:
        where.append("domain = ?")
        params.append(domain)
    if region is not None:
        where.append("region = ?")
        params.append(region)
    clause = (" WHERE " + " AND ".join(where)) if where else ""

    total = conn.execute(
        f"SELECT COUNT(*) FROM engagements{clause}", params
    ).fetchone()[0]

    sql = f"SELECT * FROM engagements{clause} ORDER BY id"
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = list(params) + [limit, offset]
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_record(conn, row) for row in rows], total


def _require_fields(record):
    missing = [f for f in REQUIRED_FIELDS if f not in record]
    if missing:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail=f"missing required field(s): {', '.join(missing)}",
        )


def _validate_record(record):
    """
    Content validation at the API boundary.

    The SQLite CHECK constraints would reject this data anyway, but an
    unhandled IntegrityError surfaces as an opaque 500. Checking here
    turns it into a 422 that tells the caller exactly what is wrong.
    """
    from common.contract import VALID_REGIONS
    from fastapi import HTTPException

    problems = []
    if record.get("region") not in VALID_REGIONS:
        problems.append(
            f"region must be one of {', '.join(sorted(VALID_REGIONS))} "
            f"(got {record.get('region')!r})"
        )
    if not isinstance(record.get("client_type"), str) or not record["client_type"]:
        problems.append("client_type must be a non-empty string")
    if not isinstance(record.get("may_be_named"), bool):
        problems.append("may_be_named must be true or false")
    if not isinstance(record.get("technologies"), list):
        problems.append("technologies must be a list")
    outcomes = record.get("outcomes")
    if not isinstance(outcomes, list):
        problems.append("outcomes must be a list")
    else:
        for i, outcome in enumerate(outcomes):
            if not isinstance(outcome, dict):
                problems.append(f"outcomes[{i}] must be an object")
                continue
            if not outcome.get("metric"):
                problems.append(f"outcomes[{i}].metric must be non-empty")
            if not outcome.get("source_ref"):
                problems.append(f"outcomes[{i}].source_ref must be non-empty")
    if problems:
        raise HTTPException(status_code=422, detail="; ".join(problems))


def _normalize_etag(value):
    """Strip quotes and an optional W/ prefix so clients can send either form."""
    text = value.strip()
    if text[:2].upper() == "W/":
        text = text[2:].strip()
    return text.strip('"')


def _check_if_match(record, if_match):
    """
    Optimistic concurrency gate (CF-62, hardened CF-86).

    - no If-Match header  -> 428 Precondition Required
    - If-Match: *         -> ok (any current version)
    - wrong ETag          -> 412 Precondition Failed + current ETag
                             so the caller can retry without another GET
    - matching ETag       -> ok, proceed

    412, not 409: 409 is "this id already exists" on POST. A stale
    If-Match is a failed precondition (RFC 9110).
    """
    from fastapi import HTTPException

    current = etag_for(record)
    if if_match is None or not str(if_match).strip():
        raise HTTPException(
            status_code=428,
            detail="If-Match header required for this operation",
        )
    offered = _normalize_etag(if_match)
    if offered == "*":
        return
    if not secrets.compare_digest(offered, current):
        raise HTTPException(
            status_code=412,
            detail="ETag mismatch — record was changed by someone else",
            headers={"ETag": f'"{current}"'},
        )


TOKEN_ENV_VAR = "CASEFORGE_TOKEN"

# Shown on PUT/DELETE in /docs so callers see If-Match without reading the README.
IF_MATCH_DESCRIPTION = (
    "Required. ETag from GET, quoted. Missing → 428. Stale → 412 "
    "(not 409 — that is POST when the id already exists). "
    "`*` matches any current version."
)


def expected_token():
    """
    The shared service token, read from the environment (CF-85).

    Never from code or git — the secret lives only in the environment.
    Returns None when the variable is unset, which means "auth is not
    configured on this instance".
    """
    return os.environ.get(TOKEN_ENV_VAR) or None


def create_app():
    """
    The REST API (L2 + L4 + L5), guarded by a service token (CF-85).

        POST   /engagements              -> create (201 / 409 / 422)
        GET    /engagements              -> list (+ filter / pagination)
        GET    /engagements/{id}         -> fetch one (?as_of= for history)
        GET    /engagements/{id}/versions -> version list (CF-63)
        PUT    /engagements/{id}         -> replace (200 / 404 / 412 / 428)
        DELETE /engagements/{id}         -> remove current (history kept)

    Writes are optimistic: If-Match must be the current ETag (CF-86).
    POST of an existing id is 409. A stale If-Match is 412.
    Every call above must present `Authorization: Bearer <token>` when
    CASEFORGE_TOKEN is set. /health and the docs stay open, otherwise the
    mesh dashboard could never poll us.

    OpenAPI docs: http://127.0.0.1:8000/docs
    """
    from typing import Optional

    from fastapi import (
        Depends, FastAPI, Header, HTTPException, Query, Response,
    )
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

    app = FastAPI(
        title="Vault — Engagement Record store",
        description=(
            "Stores Engagement Records and serves them over HTTP. "
            "L4: full REST, status codes, pagination, ETag concurrency. "
            "L5 (CF-63): record versioning with as-of reads. "
            "CF-85: service-to-service auth via a bearer token. "
            "CF-86: optimistic concurrency — If-Match on PUT/DELETE. "
            "CF-114: Vault is the only engagement store; smoke via "
            "`python -m vault.vault smoke`."
        ),
        version="0.9.0",
    )

    # HTTPBearer (not a raw Header) is what makes /docs show the padlock
    # and the Authorize button. auto_error=False: we return 401 ourselves
    # so the message matches the rest of the API, and so an unset
    # CASEFORGE_TOKEN can still let everyone through.
    bearer_scheme = HTTPBearer(auto_error=False)

    def require_token(
        creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    ):
        """
        Service-to-service authentication (CF-85).

        Staged rollout, on purpose: with CASEFORGE_TOKEN unset the Vault
        serves everyone and says so at startup. That keeps the migration
        additive — nobody's prototype breaks the moment this merges. Set
        the variable and the door is locked for every data endpoint.

        401 (not 403) because the caller is unidentified rather than
        forbidden; we have no roles yet, so 403 would be a lie.
        """
        expected = expected_token()
        if expected is None:
            return
        unauthenticated = HTTPException(
            status_code=401,
            detail="a valid 'Authorization: Bearer <token>' header is "
                   "required — the token comes from CASEFORGE_TOKEN",
            headers={"WWW-Authenticate": "Bearer"},
        )
        if creds is None or not creds.credentials.strip():
            raise unauthenticated
        # Constant-time comparison: a plain != leaks how many characters
        # matched through timing, which lets a caller guess the token.
        if not secrets.compare_digest(creds.credentials.strip(), expected):
            raise unauthenticated

    guarded = [Depends(require_token)]

    if expected_token() is None:
        print(f"[vault] WARNING: {TOKEN_ENV_VAR} is not set — serving "
              f"unauthenticated. Set it to require a bearer token.",
              file=sys.stderr)

    @app.get("/health")
    def health(response: Response):
        """
        Liveness + readiness for the service mesh (CF-84).

        Not just "the process is up": it proves the database is reachable,
        because a Vault that cannot reach its store is not healthy.
        """
        try:
            conn = init_db()
            count = conn.execute(
                "SELECT COUNT(*) FROM engagements"
            ).fetchone()[0]
        except sqlite3.Error as exc:
            response.status_code = 503
            return {
                "status": "unhealthy",
                "service": "vault",
                "detail": f"database unreachable: {exc}",
            }
        return {
            "status": "ok",
            "service": "vault",
            "version": app.version,
            "records": count,
        }

    @app.post("/engagements", status_code=201, dependencies=guarded)
    def create_engagement(record: dict, response: Response):
        """Create a new record. Fails with 409 if the id already exists."""
        _require_fields(record)
        _validate_record(record)
        if exists(record["id"]):
            raise HTTPException(
                status_code=409,
                detail=f"engagement '{record['id']}' already exists "
                       f"— use PUT to update",
            )
        try:
            store(record)
        except sqlite3.IntegrityError as exc:
            # Safety net: anything the validator missed but the schema
            # rejects still comes back as a clear 422, never a 500.
            raise HTTPException(
                status_code=422,
                detail=f"record violates the storage contract: {exc}",
            )
        tag = etag_for(record)
        response.headers["ETag"] = f'"{tag}"'
        response.headers["Location"] = f"/engagements/{record['id']}"
        return record

    @app.get("/engagements", dependencies=guarded)
    def list_engagements(
        domain: Optional[str] = Query(None, description="Filter by domain"),
        region: Optional[str] = Query(
            None, description="Filter by region (UK/DE/NL/TR/GCC)"
        ),
        limit: Optional[int] = Query(
            None, ge=1, description="Page size"
        ),
        offset: int = Query(0, ge=0, description="Page offset"),
    ):
        """List records. Optional domain/region filters and pagination."""
        items, total = list_all(
            domain=domain, region=region, limit=limit, offset=offset
        )
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    @app.get("/engagements/{engagement_id}/versions", dependencies=guarded)
    def get_engagement_versions(engagement_id: str):
        """
        List immutable version snapshots for this id (CF-63).
        Oldest first. Survives DELETE of the current row.
        """
        versions = list_versions(engagement_id)
        if not versions and not exists(engagement_id):
            raise HTTPException(
                status_code=404,
                detail=f"no engagement with id '{engagement_id}'",
            )
        return {"id": engagement_id, "versions": versions}

    @app.get("/engagements/{engagement_id}", dependencies=guarded)
    def get_engagement(
        engagement_id: str,
        response: Response,
        as_of: Optional[str] = Query(
            None,
            description=(
                "CF-63: ISO-8601 time. Return the record as it was at "
                "that moment (newest snapshot at or before as_of)."
            ),
        ),
    ):
        """Fetch one record. Optional as_of for historical read."""
        try:
            record = get(engagement_id, as_of=as_of)
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail="as_of must be a valid ISO-8601 datetime",
            )
        if record is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"no engagement with id '{engagement_id}'"
                    + (f" as of {as_of}" if as_of else "")
                ),
            )
        tag = etag_for(record)
        response.headers["ETag"] = f'"{tag}"'
        return record

    @app.put("/engagements/{engagement_id}", dependencies=guarded)
    def put_engagement(
        engagement_id: str,
        record: dict,
        response: Response,
        if_match: Optional[str] = Header(
            None, alias="If-Match", description=IF_MATCH_DESCRIPTION
        ),
    ):
        """
        Replace an existing record. Requires If-Match with the current ETag
        so two writers cannot silently overwrite each other.
        """
        _require_fields(record)
        _validate_record(record)
        if record.get("id") != engagement_id:
            raise HTTPException(
                status_code=422,
                detail="body id must match the path id",
            )
        current = get(engagement_id)
        if current is None:
            raise HTTPException(
                status_code=404,
                detail=f"no engagement with id '{engagement_id}'",
            )
        _check_if_match(current, if_match)
        try:
            store(record)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(
                status_code=422,
                detail=f"record violates the storage contract: {exc}",
            )
        tag = etag_for(record)
        response.headers["ETag"] = f'"{tag}"'
        return record

    @app.delete("/engagements/{engagement_id}", status_code=204,
                dependencies=guarded)
    def delete_engagement(
        engagement_id: str,
        if_match: Optional[str] = Header(
            None, alias="If-Match", description=IF_MATCH_DESCRIPTION
        ),
    ):
        """Delete current row. Version history is kept for as-of reads."""
        current = get(engagement_id)
        if current is None:
            raise HTTPException(
                status_code=404,
                detail=f"no engagement with id '{engagement_id}'",
            )
        _check_if_match(current, if_match)
        delete(engagement_id)
        return Response(status_code=204)

    return app


def serve():
    """Run the API on http://127.0.0.1:8000 (interactive docs at /docs)."""
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8000)


def main():
    parser = argparse.ArgumentParser(description="Engagement Record store")
    sub = parser.add_subparsers(dest="command", required=True)

    p_store = sub.add_parser("store")
    p_store.add_argument("record", help="path to a record.json")

    p_get = sub.add_parser("get")
    p_get.add_argument("id", help="engagement id, e.g. eng-01")

    sub.add_parser("serve")
    sub.add_parser("load-all", help="load all 12 records from the corpus")
    sub.add_parser(
        "smoke",
        help="CF-114: prove the corpus is reachable only via HTTP",
    )

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
    elif args.command == "smoke":
        from fastapi.testclient import TestClient

        from vault.smoke import SmokeFailed, run_smoke

        try:
            result = run_smoke(TestClient(create_app()))
        except SmokeFailed as exc:
            print(f"[vault] smoke FAILED: {exc}", file=sys.stderr)
            sys.exit(1)
        print(
            f"[vault] smoke OK — {result['records']} records over HTTP "
            f"({result['created']} created, "
            f"{result['already_stored']} already stored)",
            file=sys.stderr,
        )
    elif args.command == "serve":
        serve()


if __name__ == "__main__":
    main()
