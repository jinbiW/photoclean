from datetime import datetime
from pathlib import Path

from photoclean.domain import Photo
from photoclean.grouping import SimilarPair, build_groups


def photo(name: str) -> Photo:
    return Photo(Path(name), 100, 100, 10, datetime(2026, 1, 1))


def test_groups_complete_matches_and_selects_one_default_keep() -> None:
    photos = [photo("a.jpg"), photo("b.jpg"), photo("c.jpg")]
    groups = build_groups(
        photos,
        [SimilarPair(0, 1, 0.96), SimilarPair(1, 2, 0.95), SimilarPair(0, 2, 0.94)],
    )

    assert len(groups) == 1
    assert len(groups[0].photos) == 3
    assert groups[0].keep_ids == {photos[0].id}
    assert len(groups[0].delete_photos) == 2


def test_does_not_chain_unmatched_photos() -> None:
    photos = [photo("a.jpg"), photo("b.jpg"), photo("c.jpg")]
    groups = build_groups(photos, [SimilarPair(0, 1, 0.96), SimilarPair(1, 2, 0.95)])

    assert len(groups) == 1
    assert {item.path.name for item in groups[0].photos} == {"a.jpg", "b.jpg"}


def test_iphone_photo_identity_and_live_photo_companion() -> None:
    item = Photo(
        Path("cache/IMG_1849.JPG"),
        100,
        100,
        10,
        datetime(2026, 1, 1),
        source_kind="iphone",
        source_id="202605_a/IMG_1849.JPG",
        companion_ids=("202605_a/IMG_1849.MOV",),
        companion_sizes=(5,),
    )

    assert item.id == "iphone:202605_a/IMG_1849.JPG"
    assert item.companion_ids == ("202605_a/IMG_1849.MOV",)
    assert item.reclaim_size == 15
