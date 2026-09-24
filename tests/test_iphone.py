from datetime import datetime
from pathlib import Path

from photoclean.domain import Photo
from win32com.shell import shellcon

from photoclean.iphone import count_photo_companions, silent_delete_flags


def test_counts_unique_photo_companions() -> None:
    photos = [
        Photo(
            Path("one.jpg"),
            100,
            100,
            10,
            datetime(2026, 1, 1),
            companion_ids=("folder/one.mov",),
        ),
        Photo(
            Path("two.jpg"),
            100,
            100,
            10,
            datetime(2026, 1, 1),
            companion_ids=("folder/one.mov", "folder/two.aae"),
        ),
    ]

    assert count_photo_companions(photos) == 2


def test_iphone_delete_suppresses_duplicate_system_prompts() -> None:
    flags = silent_delete_flags()

    assert flags & shellcon.FOF_SILENT
    assert flags & shellcon.FOF_NOCONFIRMATION
    assert flags & shellcon.FOF_NOERRORUI
