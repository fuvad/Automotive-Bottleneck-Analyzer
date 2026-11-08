"""Preserve short records/sections; fallback spans never create source rows."""

from dataclasses import dataclass
from uuid import UUID, uuid5


@dataclass(frozen=True)
class Chunk:
    evidence_id: str
    text: str
    start: int
    end: int


def chunks(
    source_id: UUID,
    text: str,
    *,
    sop: bool = False,
    section: bool = False,
    maximum_chars: int = 2000,
) -> list[Chunk]:
    if maximum_chars < 100:
        raise ValueError("maximum_chars must be at least 100")
    # Section sources already own their identity; whole short records stay whole.
    if section or not sop or len(text) <= maximum_chars:
        return [Chunk(str(source_id), text, 0, len(text))]
    result = []
    start = 0
    while start < len(text):
        end = min(len(text), start + maximum_chars)
        if end < len(text):
            boundary = text.rfind("\n", start + maximum_chars // 2, end)
            if boundary >= 0:
                end = boundary + 1
        identifier = str(uuid5(source_id, f"fallback-v1/{start}/{end}"))
        result.append(Chunk(identifier, text[start:end], start, end))
        start = end
    return result
