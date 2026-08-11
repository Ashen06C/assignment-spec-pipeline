"""Robust JSON extraction from LLM responses.

LLMs frequently wrap JSON inside markdown code fences or add preamble text.
This module strips that away and returns a parsed Python object.
"""

from __future__ import annotations

import json
import re
from typing import Any


def parse_llm_json(raw: str) -> dict[str, Any] | list[Any]:
    """Extract and parse JSON from an LLM response string.

    Handles the following common LLM output patterns:

    1. Clean JSON — ``{ ... }`` or ``[ ... ]``
    2. Fenced JSON — ````json\\n{ ... }\\n````
    3. Fenced (no lang tag) — ````\\n{ ... }\\n````
    4. Preamble + JSON — ``Here is the plan:\\n{ ... }``
    5. Trailing commentary — ``{ ... }\\nLet me know if …``

    Raises
    ------
    ValueError
        If no valid JSON object or array can be extracted.
    """
    # 1. Try direct parse first (fast path).
    stripped = raw.strip()
    try:
        return json.loads(stripped)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        pass

    # 2. Strip markdown code fences.
    fenced = re.search(
        r"```(?:json)?\s*\n?(.*?)\n?\s*```",
        raw,
        re.DOTALL,
    )
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

    # 3. Find the outermost { … } or [ … ] via bracket matching.
    extracted = _extract_balanced(stripped, "{", "}")
    if extracted is None:
        extracted = _extract_balanced(stripped, "[", "]")
    if extracted is not None:
        try:
            return json.loads(extracted)  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not extract valid JSON from LLM response:\n{raw[:500]}")


def _extract_balanced(text: str, open_char: str, close_char: str) -> str | None:
    """Return the first balanced ``open_char…close_char`` substring."""
    start = text.find(open_char)
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]

        if escape:
            escape = False
            continue

        if ch == "\\":
            escape = True
            continue

        if ch == '"':
            in_string = not in_string
            continue

        if in_string:
            continue

        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]

    return None
