"""Mask secrets (private keys, tokens, URL credentials, secret-looking assignments) in text shown to an AI."""

from __future__ import annotations

import re

MASK = "***REDACTED***"


_PRIVATE_KEY = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|\Z)", re.S)

_TOKEN_FORMATS = re.compile(
    r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"
    r"|\bgh[pousr]_[A-Za-z0-9]{30,}\b|\bgithub_pat_[A-Za-z0-9_]{30,}\b"
    r"|\bsk-(?:ant-|proj-)?[A-Za-z0-9_\-]{20,}\b|\b[sr]k_(?:live|test)_[A-Za-z0-9]{16,}\b"
    r"|\bxox[abprs]-[A-Za-z0-9\-]{10,}\b|\bAIza[0-9A-Za-z_\-]{35}\b"
    r"|\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{5,}\b"
    r"|\bglpat-[A-Za-z0-9_\-]{20,}\b|\bSG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}\b"
)

_URL_CREDS = re.compile(r"(://[^/\s:@\"']+):([^@\s\"'/]+)@")

_CONN_KV = re.compile(
    r"(?i)\b(password|pwd|accountkey|sharedaccesskey|sharedaccesssignature|secret|client_?secret|apikey|api_key)\s*=\s*"
    r"([^;\"'\s][^;\"'\n]*)"
)

_SECRET_NAME = (
    r"password|passwd|pwd|secret|token|api[_-]?key|apikey|access[_-]?key|private[_-]?key|client[_-]?secret|"
    r"credential|connection[_-]?string|conn[_-]?str|connectionstring|dsn|authorization|sas[_-]?token|signing[_-]?key|"
    r"encryption[_-]?key|master[_-]?key|account[_-]?key"
)

_ASSIGN = re.compile(
    r"(?P<k>[\w.\-]*(?:" + _SECRET_NAME + r")[\w.\-]*)(?P<sep>[\"']?\s*[:=]\s*)"
    r"(?P<v>\"[^\"\n]*\"|'[^'\n]*'|[^\s,;#\"'\n][^\s,;#\n]*)",
    re.I,
)

_REFERENCE_HINTS = (
    "${", "$(", "{{", "<", "%", "os.environ", "process.env", "getenv", "var.", "secrets.", "self.", "settings.",
    "config.", "env(", "environ", "keyvault", "@microsoft.keyvault", "!ref", "!sub", "!getatt", "ref:", "parameters(",
    "secretkeyref", "fn::", "args.", "params.", "props.", "input(", "getpass", "kwargs",
)

_SAFE_WORDS = {"true", "false", "none", "null", "nil", "str", "string", "int", "bool", "required", "optional",
               "secret", "token", "password", "undefined", "changeme", "xxx", "x", "yes", "no", "env", "field",
               "secretstr", "text", "any", "dict", "list", "bytes", "false,", "true,"}


def _assign_repl(m: re.Match[str]) -> str:
    raw = m.group("v")
    val = raw.strip("\"'")
    low = val.lower()
    if (
        len(val) < 4
        or low in _SAFE_WORDS
        or val.isdigit()
        or any(h in low for h in _REFERENCE_HINTS)
        or val.endswith(("(", "[", "{"))
        or re.fullmatch(r"[A-Za-z_][\w.]*\(.*", val)  # function call, e.g. Field(...)
        or re.fullmatch(r"[A-Z_][A-Z0-9_]*", val)  # SOME_CONSTANT_NAME (a reference, not a value)
        or val.startswith(("http://", "https://")) and "@" not in val
    ):
        return m.group(0)
    quote = raw[0] if raw[0] in "\"'" else ""
    return f"{m.group('k')}{m.group('sep')}{quote}{MASK}{quote}"


def redact(text: str, mask_all_values: bool = False) -> str:
    """Mask private keys, well-known token formats, URL credentials and secret-looking assignments."""
    if mask_all_values:  # .env style files: keep names, hide every value
        out = []
        for line in text.splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, _, v = line.partition("=")
                out.append(f"{k}={MASK}" if v.strip() else line)
            else:
                out.append(line)
        return "\n".join(out)
    text = _PRIVATE_KEY.sub("[REDACTED PRIVATE KEY]", text)
    text = _TOKEN_FORMATS.sub(MASK, text)
    text = _URL_CREDS.sub(lambda m: f"{m.group(1)}:{MASK}@", text)
    text = _CONN_KV.sub(lambda m: f"{m.group(1)}={MASK}" if m.group(2).lower() not in _SAFE_WORDS else m.group(0), text)
    text = _ASSIGN.sub(_assign_repl, text)
    return text
