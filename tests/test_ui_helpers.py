from photoclean.utils import format_size


def test_format_size() -> None:
    assert format_size(512) == "512 B"
    assert format_size(1536) == "2 KB"
    assert format_size(1024 * 1024 * 2) == "2.0 MB"
