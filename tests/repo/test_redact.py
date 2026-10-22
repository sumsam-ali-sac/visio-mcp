"""Secret redaction."""

from __future__ import annotations

from visio_mcp.repo import redact


def test_redaction():
    src = '''\
DB_PASSWORD = "hunter2hunter2"
api_key: abcdef123456
conn = "Server=tcp:x.database.windows.net;Database=d;User Id=u;Password=Sup3rS3cret!;"
url = "postgresql://app:s3cretpw@db:5432/app"
token = os.environ["TOKEN"]
password: ${DB_PASSWORD}
aws = "AKIAABCDEFGHIJKLMNOP"
key = "sk-abcdefghijklmnopqrstuvwxyz123456"
max_tokens: 4096
name: public-value
-----BEGIN RSA PRIVATE KEY-----
MIIEowIBAAKCAQEA
-----END RSA PRIVATE KEY-----
'''
    out = redact(src)
    for leaked in ("hunter2hunter2", "abcdef123456", "Sup3rS3cret", "s3cretpw", "AKIAABCDEFGHIJKLMNOP",
                   "abcdefghijklmnopqrstuvwxyz123456", "MIIEowIBAAKCAQEA"):
        assert leaked not in out, leaked
    assert 'os.environ["TOKEN"]' in out and "${DB_PASSWORD}" in out
    assert "max_tokens: 4096" in out and "name: public-value" in out
    assert "postgresql://app:" in out and "@db:5432/app" in out
