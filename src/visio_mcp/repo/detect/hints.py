"""Name patterns that suggest a secret or a reference to another system."""

from __future__ import annotations

import re


SECRETISH = re.compile(r"pass|secret|token|key|pwd|credential|sas|signature", re.I)
HOSTISH = re.compile(r"url|host|endpoint|uri|server|broker|dsn|queue|topic|bucket|database|_api|service", re.I)
