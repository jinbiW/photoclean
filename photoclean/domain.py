from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class Photo:
    path: Path
    width: int
    height: int
    size: int
    captured_at: datetime
    source_kind: str = "local"
    source_id: str | None = None
    companion_ids: tuple[str, ...] = ()
    companion_sizes: tuple[int, ...] = ()

    @property
    def id(self) -> str:
        if self.source_id:
            return f"{self.source_kind}:{self.source_id}"
        return str(self.path.resolve())

    @property
    def reclaim_size(self) -> int:
        return self.size + sum(self.companion_sizes)


@dataclass
class SimilarGroup:
    id: str
    photos: list[Photo]
    similarity: float
    keep_ids: set[str] = field(default_factory=set)

    @property
    def delete_photos(self) -> list[Photo]:
        return [photo for photo in self.photos if photo.id not in self.keep_ids]

    @property
    def delete_size(self) -> int:
        return sum(photo.reclaim_size for photo in self.delete_photos)
