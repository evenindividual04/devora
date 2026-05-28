from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.models.contracts import AnalysisRecord


class InMemoryAnalysisStore:
    def __init__(self) -> None:
        self._data: dict[UUID, AnalysisRecord] = {}

    def create(self, record: AnalysisRecord) -> AnalysisRecord:
        self._data[record.analysis_id] = record
        return record

    def get(self, analysis_id: UUID) -> AnalysisRecord | None:
        return self._data.get(analysis_id)

    def update(self, record: AnalysisRecord) -> AnalysisRecord:
        record.updated_at = datetime.now(UTC)
        self._data[record.analysis_id] = record
        return record


store = InMemoryAnalysisStore()
