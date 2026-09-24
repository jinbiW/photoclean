from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
import sys

import torch
import torch.nn.functional as functional
from PIL import Image, ImageOps
from torchvision import transforms

from .domain import Photo, SimilarGroup
from .grouping import SimilarPair, build_groups

SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".heic",
    ".heif",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
}
COMPANION_EXTENSIONS = {".mov", ".aae"}


class PhotoScanner:
    def __init__(
        self,
        dino_threshold: float = 0.84,
        lpips_threshold: float = 0.32,
        time_window_minutes: int = 30,
    ) -> None:
        self.dino_threshold = dino_threshold
        self.lpips_threshold = lpips_threshold
        self.time_window = timedelta(minutes=time_window_minutes)
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._dino = None
        self._lpips = None
        self._embedding_transform = transforms.Compose(
            [
                transforms.Resize(256),
                transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)
                ),
            ]
        )
        self._lpips_transform = transforms.Compose(
            [transforms.Resize((256, 256)), transforms.ToTensor()]
        )

    def scan(
        self, folder: Path, progress: Callable[[int, int, str], None] | None = None
    ) -> list[SimilarGroup]:
        photos = self._read_photos(folder)
        return self.scan_photos(photos, progress)

    def scan_photos(
        self,
        photos: list[Photo],
        progress: Callable[[int, int, str], None] | None = None,
    ) -> list[SimilarGroup]:
        total = max(1, len(photos) * 2)
        if len(photos) < 2:
            if progress:
                progress(total, total, "没有足够的照片用于比较")
            return []

        self._load_models()
        embeddings: list[torch.Tensor] = []
        for index, photo in enumerate(photos):
            embeddings.append(self._embedding(photo.path))
            if progress:
                progress(
                    index + 1,
                    total,
                    f"正在提取特征（{index + 1}/{len(photos)}）：{photo.path.name}",
                )

        pairs: list[SimilarPair] = []
        comparisons = sum(1 for i in range(len(photos)) for j in range(i + 1, len(photos)) if self._is_candidate(photos[i], photos[j]))
        compared = 0
        for left in range(len(photos)):
            for right in range(left + 1, len(photos)):
                if not self._is_candidate(photos[left], photos[right]):
                    continue
                compared += 1
                dino_score = float(functional.cosine_similarity(embeddings[left], embeddings[right]).item())
                if dino_score >= self.dino_threshold:
                    lpips_distance = self._lpips_distance(photos[left].path, photos[right].path)
                    if lpips_distance <= self.lpips_threshold:
                        lpips_score = 1 - min(1.0, lpips_distance)
                        pairs.append(SimilarPair(left, right, dino_score * 0.6 + lpips_score * 0.4))
                if progress:
                    position = len(photos) + round(compared / max(1, comparisons) * len(photos))
                    progress(
                        position,
                        total,
                        f"正在比较（{compared}/{comparisons}）：{photos[left].path.name} / {photos[right].path.name}",
                    )
        return build_groups(photos, pairs)

    def _load_models(self) -> None:
        if self._dino is None:
            self._dino = torch.hub.load(
                "facebookresearch/dinov2", "dinov2_vits14", trust_repo=True
            )
            self._dino.eval().to(self.device)
        if self._lpips is None:
            import lpips

            bundle_root = getattr(sys, "_MEIPASS", None)
            model_path = (
                str(Path(bundle_root) / "lpips" / "weights" / "v0.1" / "alex.pth")
                if bundle_root
                else None
            )
            self._lpips = lpips.LPIPS(net="alex", model_path=model_path).eval().to(self.device)

    def _read_photos(self, folder: Path) -> list[Photo]:
        photos: list[Photo] = []
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                companions = tuple(
                    str(candidate.resolve())
                    for candidate in path.parent.iterdir()
                    if candidate.is_file()
                    and candidate.stem.casefold() == path.stem.casefold()
                    and candidate.suffix.casefold() in COMPANION_EXTENSIONS
                )
                photos.append(
                    read_photo(
                        path,
                        companion_ids=companions,
                        companion_sizes=tuple(Path(item).stat().st_size for item in companions),
                    )
                )
            except (OSError, ValueError):
                continue
        return photos

    def _embedding(self, path: Path) -> torch.Tensor:
        image = _open_rgb(path)
        tensor = self._embedding_transform(image).unsqueeze(0).to(self.device)
        with torch.inference_mode():
            return functional.normalize(self._dino(tensor), dim=-1).cpu()

    def _lpips_distance(self, left: Path, right: Path) -> float:
        left_tensor = self._lpips_transform(_open_rgb(left)).mul(2).sub(1).unsqueeze(0).to(self.device)
        right_tensor = self._lpips_transform(_open_rgb(right)).mul(2).sub(1).unsqueeze(0).to(self.device)
        with torch.inference_mode():
            return float(self._lpips(left_tensor, right_tensor).item())

    def _is_candidate(self, left: Photo, right: Photo) -> bool:
        time_close = abs(left.captured_at - right.captured_at) <= self.time_window
        dimensions_close = _aspect_ratio_delta(left, right) <= 0.08
        exact_copy_shape = (
            left.size == right.size
            and left.width == right.width
            and left.height == right.height
        )
        return dimensions_close and (time_close or exact_copy_shape)


def _open_rgb(path: Path) -> Image.Image:
    with Image.open(path) as image:
        return ImageOps.exif_transpose(image).convert("RGB")


def _parse_capture_time(value: object, path: Path) -> datetime:
    if isinstance(value, str):
        try:
            return datetime.strptime(value, "%Y:%m:%d %H:%M:%S")
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime)


def read_photo(
    path: Path,
    source_kind: str = "local",
    source_id: str | None = None,
    companion_ids: tuple[str, ...] = (),
    companion_sizes: tuple[int, ...] = (),
) -> Photo:
    try:
        from pillow_heif import register_heif_opener

        register_heif_opener()
    except ImportError:
        pass
    with Image.open(path) as image:
        corrected = ImageOps.exif_transpose(image)
        width, height = corrected.size
        exif = image.getexif()
        captured_at = _parse_capture_time(exif.get(36867), path)
    return Photo(
        path=path,
        width=width,
        height=height,
        size=path.stat().st_size,
        captured_at=captured_at,
        source_kind=source_kind,
        source_id=source_id,
        companion_ids=companion_ids,
        companion_sizes=companion_sizes,
    )


def _aspect_ratio_delta(left: Photo, right: Photo) -> float:
    left_ratio = left.width / max(1, left.height)
    right_ratio = right.width / max(1, right.height)
    return abs(left_ratio - right_ratio) / max(left_ratio, right_ratio)
