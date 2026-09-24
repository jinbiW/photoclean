from photoclean.scanner import PhotoScanner


def test_relaxed_default_thresholds() -> None:
    scanner = PhotoScanner()

    assert scanner.dino_threshold == 0.84
    assert scanner.lpips_threshold == 0.32


def test_custom_thresholds_are_kept() -> None:
    scanner = PhotoScanner(dino_threshold=0.80, lpips_threshold=0.40)

    assert scanner.dino_threshold == 0.80
    assert scanner.lpips_threshold == 0.40
