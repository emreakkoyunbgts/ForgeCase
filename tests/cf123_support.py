"""Shared helpers for the CF-123 OpenAPI checks. Never reaches the network."""

import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOTS = ROOT / "docs" / "openapi"
SERVICES = ("generator", "verifier")


def snapshot(name):
    return json.loads((SNAPSHOTS / f"{name}.json").read_text(encoding="utf-8"))


def standalone(document, schema):
    """A sub-schema that still resolves the document's own `#/components/...` pointers.

    `components` is not a JSON Schema keyword, so carrying it along changes nothing
    about validation while keeping every local pointer resolvable offline.
    """
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        **schema,
        "components": document["components"],
    }


def validate(document, schema, value):
    Draft202012Validator(standalone(document, schema)).validate(value)


def dereference(document, node, section):
    """Follow one `#/components/<section>/<name>` hop, if there is one."""
    if "$ref" in node:
        return document["components"][section][node["$ref"].rsplit("/", 1)[-1]]
    return node


def json_block(document, response):
    return dereference(document, response, "responses").get("content", {}).get(
        "application/json"
    )


def documented_examples(document):
    """Yield every declared example with the schema its own operation promises."""
    for path, methods in document["paths"].items():
        for method, operation in methods.items():
            blocks = [json_block(document, response)
                      for response in operation["responses"].values()]
            request = operation.get("requestBody", {}).get("content", {})
            blocks.append(request.get("application/json"))
            for block in filter(None, blocks):
                for name, example in block.get("examples", {}).items():
                    yield path, method, name, block["schema"], example["value"]
