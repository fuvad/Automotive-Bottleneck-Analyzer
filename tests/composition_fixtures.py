"""Turn scripted test prose into the composer's internal structured parts."""

import re


def draft_parts(summary):
    return [
        [
            {"quantity": part[2:-2]}
            if part.startswith("{{") and part.endswith("}}")
            else {"text": part}
            for part in re.split(r"(\{\{[^{}]+\}\})", paragraph)
            if part
        ]
        for paragraph in summary.split("\n\n")
    ]
