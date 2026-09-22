"""Read-only literal search over a loaded entity registry."""

from .errors import LedgerError


_RESULT_FIELDS = ("id", "name", "status", "anchor", "parent", "supersedes", "legacy")


def _validate(query, limit):
    if not isinstance(query, str) or not query.strip():
        raise LedgerError("ERR_SEARCH_QUERY", "Search query must not be blank")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise LedgerError("ERR_SEARCH_LIMIT", "Search limit must be an integer from 1 through 100")


def _result(row):
    return {field: getattr(row, field) for field in _RESULT_FIELDS}


def search_entities(registry, query, limit=5):
    """Return entities whose ID, name, or legacy alias contains ``query``.

    Matching is case-insensitive through ``str.casefold`` and otherwise uses
    literal substring checks.  Registry rows remain in their ledger order and
    are never modified.
    """
    _validate(query, limit)
    needle = query.casefold()
    ranked = []

    for position, row in enumerate(registry.rows):
        fields = {field: getattr(row, field) for field in ("id", "name", "legacy")}
        folded = {field: value.casefold() for field, value in fields.items()}
        if not any(needle in value for value in folded.values()):
            continue

        if needle == folded["id"] or needle == folded["legacy"]:
            rank = 0
        elif needle == folded["name"]:
            rank = 1
        else:
            rank = 2
        ranked.append((rank, position, row))

    ranked.sort(key=lambda item: (item[0], item[1]))
    results = [_result(row) for _, _, row in ranked[:limit]]
    return {"query": query, "total": len(ranked), "limit": limit, "results": results}
