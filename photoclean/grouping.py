from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .domain import Photo, SimilarGroup


@dataclass(frozen=True)
class SimilarPair:
    left: int
    right: int
    score: float


def build_groups(photos: list[Photo], pairs: Iterable[SimilarPair]) -> list[SimilarGroup]:
    """Build connected groups while requiring every new member to match the group.

    Pure connected components can incorrectly chain A~B and B~C when A and C are
    different. The complete-link check keeps MVP groups conservative.
    """
    scores: dict[tuple[int, int], float] = {}
    candidates: list[SimilarPair] = []
    for pair in pairs:
        key = tuple(sorted((pair.left, pair.right)))
        scores[key] = pair.score
        candidates.append(pair)

    candidates.sort(key=lambda item: item.score, reverse=True)
    groups: list[list[int]] = []
    for pair in candidates:
        left_group = next((group for group in groups if pair.left in group), None)
        right_group = next((group for group in groups if pair.right in group), None)
        if left_group is right_group and left_group is not None:
            continue
        if left_group is None and right_group is None:
            groups.append([pair.left, pair.right])
            continue
        if left_group is None:
            if _matches_all(pair.left, right_group, scores):
                right_group.append(pair.left)
            continue
        if right_group is None:
            if _matches_all(pair.right, left_group, scores):
                left_group.append(pair.right)
            continue
        if all(_score(a, b, scores) is not None for a in left_group for b in right_group):
            left_group.extend(right_group)
            groups.remove(right_group)

    result: list[SimilarGroup] = []
    for number, indexes in enumerate(groups, start=1):
        group_scores = [
            _score(indexes[i], indexes[j], scores)
            for i in range(len(indexes))
            for j in range(i + 1, len(indexes))
        ]
        similarity = min(score for score in group_scores if score is not None)
        grouped_photos = sorted((photos[index] for index in indexes), key=lambda p: p.captured_at)
        result.append(
            SimilarGroup(
                id=f"group_{number:03d}",
                photos=grouped_photos,
                similarity=similarity,
                keep_ids={grouped_photos[0].id},
            )
        )
    return sorted(result, key=lambda group: group.photos[0].captured_at, reverse=True)


def _score(left: int, right: int, scores: dict[tuple[int, int], float]) -> float | None:
    return scores.get(tuple(sorted((left, right))))


def _matches_all(index: int, group: list[int], scores: dict[tuple[int, int], float]) -> bool:
    return all(_score(index, other, scores) is not None for other in group)

