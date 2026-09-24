from __future__ import annotations

import hashlib
import os
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from .domain import Photo
from .scanner import COMPANION_EXTENSIONS, SUPPORTED_EXTENSIONS, read_photo


class IPhoneError(RuntimeError):
    pass


@dataclass(frozen=True)
class DeviceMedia:
    folder: str
    name: str
    size: int
    shell_item: object
    companion_ids: tuple[str, ...] = ()
    companion_sizes: tuple[int, ...] = ()

    @property
    def source_id(self) -> str:
        return f"{self.folder}/{self.name}"


class IPhoneBridge:
    """Read and delete iPhone DCIM media through the Windows Shell WPD provider."""

    def __init__(self) -> None:
        if os.name != "nt":
            raise IPhoneError("iPhone 直连目前仅支持 Windows。")

    def import_photos(
        self, progress: Callable[[int, int, str], None] | None = None
    ) -> list[Photo]:
        pythoncom, shell, device, storage = self._connect()
        try:
            media = self._list_media(storage)
            photos = [item for item in media if Path(item.name).suffix.casefold() in SUPPORTED_EXTENSIONS]
            if not photos:
                raise IPhoneError("iPhone 中没有找到支持的照片，请确认手机已解锁并允许访问照片。")
            device_key = hashlib.sha256(str(device.Path).encode("utf-8")).hexdigest()[:12]
            cache_root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "PhotoClean" / "iphone-cache" / device_key
            imported: list[Photo] = []
            total = len(photos)
            for index, item in enumerate(photos, start=1):
                if progress:
                    progress(index - 1, total, f"正在读取 iPhone（{index}/{total}）：{item.name}")
                destination = cache_root / item.folder
                destination.mkdir(parents=True, exist_ok=True)
                local_path = destination / item.name
                self._copy_item(shell, item.shell_item, local_path, item.size)
                try:
                    imported.append(
                        read_photo(
                            local_path,
                            source_kind="iphone",
                            source_id=item.source_id,
                            companion_ids=item.companion_ids,
                            companion_sizes=item.companion_sizes,
                        )
                    )
                except (OSError, ValueError):
                    continue
                if progress:
                    progress(index, total, f"已读取 iPhone（{index}/{total}）：{item.name}")
            if not imported:
                raise IPhoneError("照片已发现，但无法读取。请保持 iPhone 解锁后重试。")
            return imported
        finally:
            pythoncom.CoUninitialize()

    def delete_media(self, source_ids: Iterable[str]) -> tuple[set[str], list[str]]:
        pythoncom, _, _, storage = self._connect()
        succeeded: set[str] = set()
        failures: list[str] = []
        try:
            from win32com.shell import shell

            wanted = set(source_ids)
            items = {item.source_id: item for item in self._list_media(storage) if item.source_id in wanted}
            operation = pythoncom.CoCreateInstance(
                shell.CLSID_FileOperation,
                None,
                pythoncom.CLSCTX_ALL,
                shell.IID_IFileOperation,
            )
            operation.SetOperationFlags(silent_delete_flags())
            queued: set[str] = set()
            for source_id in wanted:
                item = items.get(source_id)
                if item is None:
                    failures.append(f"{source_id}: 在 iPhone 中未找到")
                    continue
                try:
                    pidl = shell.SHGetIDListFromObject(item.shell_item)
                    shell_item = shell.SHCreateItemFromIDList(pidl, shell.IID_IShellItem)
                    operation.DeleteItem(shell_item, None)
                    queued.add(source_id)
                except Exception as error:
                    failures.append(f"{source_id}: {error}")
            if queued:
                try:
                    operation.PerformOperations()
                    if operation.GetAnyOperationsAborted():
                        failures.append("iPhone 删除操作被系统中止")
                except Exception as error:
                    failures.append(f"iPhone 批量删除失败: {error}")
            remaining = queued.copy()
            deadline = time.monotonic() + 60
            while remaining and time.monotonic() < deadline:
                current_ids = {item.source_id for item in self._list_media(storage)}
                remaining &= current_ids
                if remaining:
                    time.sleep(0.5)
            succeeded = queued - remaining
            failures.extend(f"{source_id}: iPhone 未完成删除" for source_id in sorted(remaining))
            return succeeded, failures
        finally:
            pythoncom.CoUninitialize()

    def _connect(self):
        import pythoncom
        import win32com.client

        pythoncom.CoInitialize()
        shell = win32com.client.Dispatch("Shell.Application")
        computer = shell.Namespace(17)
        device = next((item for item in computer.Items() if item.Name == "Apple iPhone"), None)
        if device is None:
            pythoncom.CoUninitialize()
            raise IPhoneError("没有检测到 Apple iPhone，请连接并解锁手机后重试。")
        storage = next((item for item in device.GetFolder.Items() if item.IsFolder), None)
        if storage is None:
            pythoncom.CoUninitialize()
            raise IPhoneError("无法访问 iPhone 存储，请在手机上点击“信任”或“允许”。")
        return pythoncom, shell, device, storage

    def _list_media(self, storage) -> list[DeviceMedia]:
        result: list[DeviceMedia] = []
        for folder in storage.GetFolder.Items():
            if not folder.IsFolder:
                continue
            items = list(folder.GetFolder.Items())
            companions_by_stem: dict[str, list[object]] = {}
            for item in items:
                if item.IsFolder or Path(item.Name).suffix.casefold() not in COMPANION_EXTENSIONS:
                    continue
                companions_by_stem.setdefault(Path(item.Name).stem.casefold(), []).append(item)
            for item in items:
                if item.IsFolder:
                    continue
                suffix = Path(item.Name).suffix.casefold()
                if suffix not in SUPPORTED_EXTENSIONS and suffix not in COMPANION_EXTENSIONS:
                    continue
                companions = companions_by_stem.get(Path(item.Name).stem.casefold(), [])
                companion_ids = ()
                companion_sizes = ()
                if suffix in SUPPORTED_EXTENSIONS and companions:
                    companion_ids = tuple(
                        f"{folder.Name}/{companion.Name}" for companion in companions
                    )
                    companion_sizes = tuple(
                        int(companion.ExtendedProperty("System.Size") or 0)
                        for companion in companions
                    )
                size = item.ExtendedProperty("System.Size") or 0
                result.append(
                    DeviceMedia(
                        folder=folder.Name,
                        name=item.Name,
                        size=int(size),
                        shell_item=item,
                        companion_ids=companion_ids,
                        companion_sizes=companion_sizes,
                    )
                )
        return result

    def _copy_item(self, shell, item, destination: Path, expected_size: int) -> None:
        if destination.exists() and (not expected_size or destination.stat().st_size == expected_size):
            return
        destination.unlink(missing_ok=True)
        destination_folder = shell.Namespace(str(destination.parent))
        if destination_folder is None:
            raise IPhoneError(f"无法创建本地缓存目录：{destination.parent}")
        destination_folder.CopyHere(item, 4 | 16 | 1024)
        deadline = time.monotonic() + 180
        previous_size = -1
        stable_checks = 0
        while time.monotonic() < deadline:
            if destination.exists():
                current_size = destination.stat().st_size
                stable_checks = stable_checks + 1 if current_size == previous_size else 0
                if current_size > 0 and (
                    (expected_size and current_size == expected_size)
                    or (not expected_size and stable_checks >= 3)
                ):
                    return
                previous_size = current_size
            time.sleep(0.2)
        raise IPhoneError(f"从 iPhone 读取 {item.Name} 超时，请保持手机解锁。")


def count_photo_companions(photos: Iterable[Photo]) -> int:
    return len({source_id for photo in photos for source_id in photo.companion_ids})


def silent_delete_flags() -> int:
    from win32com.shell import shellcon

    return shellcon.FOF_SILENT | shellcon.FOF_NOCONFIRMATION | shellcon.FOF_NOERRORUI
