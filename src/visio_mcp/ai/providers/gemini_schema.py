"""Simplify a JSON schema into the OpenAPI subset Gemini accepts for function declarations."""

from __future__ import annotations

from typing import Any


# Keys Gemini's function-declaration schema accepts (an OpenAPI 3 subset).
GEMINI_KEYS = {"type", "description", "enum", "items", "properties", "required", "format", "nullable",
                "minimum", "maximum"}


def gemini_schema(schema: dict) -> dict:
    """Simplify a JSON schema for Gemini: inline $ref/$defs, collapse anyOf-with-null,
    turn const into enum, drop keys Gemini rejects (additionalProperties, title, default,
    pattern, $schema...)."""
    defs = schema.get("$defs") or schema.get("definitions") or {}

    def walk(node: Any, seen: tuple[str, ...]) -> Any:
        if isinstance(node, list):
            return [walk(x, seen) for x in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            name = str(node["$ref"]).split("/")[-1]
            if name in seen or name not in defs:
                return {"type": "object", "description": node.get("description", name)}
            merged = {**defs[name], **{k: v for k, v in node.items() if k != "$ref"}}
            return walk(merged, seen + (name,))
        for key in ("anyOf", "oneOf"):
            if key in node:
                options = [o for o in node[key] if not (isinstance(o, dict) and o.get("type") == "null")]
                base = {k: v for k, v in node.items() if k != key}
                if options:
                    picked = walk(options[0], seen)
                    if isinstance(picked, dict):
                        out = {**picked, **walk(base, seen)}
                        if "description" in picked and "description" in base:
                            out["description"] = base["description"]
                        return out
                return walk({**base, "type": "string"}, seen)
        if "allOf" in node and isinstance(node["allOf"], list) and node["allOf"]:
            merged: dict = {}
            for part in node["allOf"]:
                p = walk(part, seen)
                if isinstance(p, dict):
                    merged.update(p)
            rest = {k: v for k, v in node.items() if k != "allOf"}
            return {**merged, **walk(rest, seen)}
        out: dict[str, Any] = {}
        if "const" in node:
            out["enum"] = [node["const"]]
        typ = node.get("type")
        if isinstance(typ, list):  # ["string", "null"]
            non_null = [t for t in typ if t != "null"]
            typ = non_null[0] if non_null else "string"
        for k, v in node.items():
            if k not in GEMINI_KEYS:
                continue
            if k == "type":
                out["type"] = typ
            elif k == "properties":
                out["properties"] = {pk: walk(pv, seen) for pk, pv in v.items()}
            elif k == "items":
                out["items"] = walk(v, seen)
            elif k == "enum":
                out["enum"] = [str(x) for x in v if x is not None]
            else:
                out[k] = v
        if "enum" in out:
            out["type"] = "string"
        if "properties" in out:
            out.setdefault("type", "object")
            if "required" in out:
                out["required"] = [r for r in out["required"] if r in out["properties"]]
        if out.get("type") == "object" and not out.get("properties"):
            # Gemini rejects empty objects; an object with no fields is passed as free text.
            out.pop("required", None)
        if out.get("type") == "array" and "items" not in out:
            out["items"] = {"type": "string"}
        return out

    return walk({k: v for k, v in schema.items() if k not in ("$defs", "definitions")}, ())
