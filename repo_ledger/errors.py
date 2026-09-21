"""Stable, machine-readable diagnostics."""
from dataclasses import asdict, dataclass

@dataclass
class Issue:
    code: str
    location: str
    entity: str
    reason: str
    suggestion: str
    category: str = "violation"

    def to_dict(self):
        return asdict(self)

class LedgerError(Exception):
    def __init__(self, code, reason, location="ledger.toml:1:1", entity="", category="violation"):
        self.issue = Issue(code, location, entity, reason,
                           "Inspect the source; lookup existing entities before correcting or explicitly allocating.",
                           category)
        super().__init__(reason)
