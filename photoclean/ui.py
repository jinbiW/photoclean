from __future__ import annotations

import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from .domain import Photo, SimilarGroup
from .utils import format_size


class WorkerSignals(QObject):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)


class ScanWorker(QRunnable):
    def __init__(
        self,
        folder: Path | None = None,
        source_kind: str = "local",
        dino_threshold: float = 0.84,
        lpips_threshold: float = 0.32,
    ) -> None:
        super().__init__()
        self.folder = folder
        self.source_kind = source_kind
        self.dino_threshold = dino_threshold
        self.lpips_threshold = lpips_threshold
        self.signals = WorkerSignals()

    def run(self) -> None:
        try:
            from .scanner import PhotoScanner

            scanner = PhotoScanner(
                dino_threshold=self.dino_threshold,
                lpips_threshold=self.lpips_threshold,
            )
            if self.source_kind == "iphone":
                from .iphone import IPhoneBridge

                bridge = IPhoneBridge()
                photos = bridge.import_photos(
                    lambda current, total, message: self.signals.progress.emit(
                        round(current / max(1, total) * 40), 100, message
                    )
                )
                groups = scanner.scan_photos(
                    photos,
                    lambda current, total, message: self.signals.progress.emit(
                        40 + round(current / max(1, total) * 60), 100, message
                    ),
                )
            else:
                if self.folder is None:
                    raise ValueError("没有选择照片目录")
                groups = scanner.scan(self.folder, self.signals.progress.emit)
            self.signals.completed.emit(groups)
        except Exception as error:  # Qt workers must surface model/runtime errors in UI.
            traceback.print_exc()
            self.signals.failed.emit(str(error))


class PhotoTile(QFrame):
    def __init__(self, photo: Photo, checked: bool, on_change) -> None:
        super().__init__()
        self.photo = photo
        self.setObjectName("photoTile")
        self.setFixedWidth(210)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 10)
        image = QLabel()
        image.setFixedSize(192, 144)
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(photo.path))
        image.setPixmap(pixmap.scaled(image.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        image.setCursor(Qt.CursorShape.PointingHandCursor)
        image.mousePressEvent = lambda _: ImagePreview(photo.path).exec()
        checkbox = QCheckBox("保留这张")
        checkbox.setChecked(checked)
        checkbox.toggled.connect(lambda value: on_change(photo.id, value))
        name = QLabel(photo.path.name)
        name.setToolTip(str(photo.path))
        name.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        details = QLabel(f"{photo.width} × {photo.height}  ·  {format_size(photo.size)}")
        details.setObjectName("muted")
        layout.addWidget(image)
        layout.addWidget(checkbox)
        layout.addWidget(name)
        layout.addWidget(details)


class ImagePreview(QDialog):
    def __init__(self, path: Path) -> None:
        super().__init__()
        self.setWindowTitle(path.name)
        self.resize(1000, 720)
        layout = QVBoxLayout(self)
        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pixmap = QPixmap(str(path))
        image.setPixmap(pixmap.scaled(960, 650, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(image)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.folder: Path | None = None
        self.groups: list[SimilarGroup] = []
        self.thread_pool = QThreadPool.globalInstance()
        self.setWindowTitle("PhotoClean · 相似照片清理")
        self.resize(1180, 820)
        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)
        self.home = self._build_home()
        self.scanning = self._build_scanning()
        self.stack.addWidget(self.home)
        self.stack.addWidget(self.scanning)
        self.setStyleSheet(STYLESHEET)

    def _build_home(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(90, 90, 90, 90)
        layout.setSpacing(18)
        eyebrow = QLabel("PHOTOCLEAN")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("留下值得的照片")
        title.setObjectName("hero")
        subtitle = QLabel("自动找出重复与高度相似照片，由你决定保留哪些。\n原图只会在最终确认后移入系统回收站。")
        subtitle.setObjectName("subtitle")
        settings = QFrame()
        settings.setObjectName("settingsCard")
        settings_layout = QGridLayout(settings)
        settings_layout.setContentsMargins(18, 14, 18, 14)
        settings_layout.setHorizontalSpacing(18)
        settings_title = QLabel("相似度阈值")
        settings_title.setObjectName("cardTitle")
        self.dino_threshold = QDoubleSpinBox()
        self.dino_threshold.setRange(0.50, 0.99)
        self.dino_threshold.setSingleStep(0.01)
        self.dino_threshold.setDecimals(2)
        self.dino_threshold.setValue(0.84)
        self.dino_threshold.setToolTip("数值越低越宽松，会找到更多候选图片")
        self.lpips_threshold = QDoubleSpinBox()
        self.lpips_threshold.setRange(0.05, 0.60)
        self.lpips_threshold.setSingleStep(0.01)
        self.lpips_threshold.setDecimals(2)
        self.lpips_threshold.setValue(0.32)
        self.lpips_threshold.setToolTip("数值越高越宽松，允许更明显的视觉差异")
        dino_label = QLabel("DINO 最低相似度")
        lpips_label = QLabel("LPIPS 最大视觉差异")
        threshold_hint = QLabel("漏图较多：降低 DINO、提高 LPIPS  ·  误分较多：提高 DINO、降低 LPIPS")
        threshold_hint.setObjectName("muted")
        settings_layout.addWidget(settings_title, 0, 0, 1, 4)
        settings_layout.addWidget(dino_label, 1, 0)
        settings_layout.addWidget(self.dino_threshold, 1, 1)
        settings_layout.addWidget(lpips_label, 1, 2)
        settings_layout.addWidget(self.lpips_threshold, 1, 3)
        settings_layout.addWidget(threshold_hint, 2, 0, 1, 4)
        start = QPushButton("选择照片目录")
        start.setObjectName("primary")
        start.setFixedWidth(220)
        start.clicked.connect(self._choose_folder)
        iphone = QPushButton("扫描已连接的 iPhone")
        iphone.setFixedWidth(220)
        iphone.clicked.connect(self._scan_iphone)
        privacy = QLabel("本地处理  ·  照片不会上传  ·  支持 JPG / HEIC / PNG / WEBP / TIFF")
        privacy.setObjectName("muted")
        layout.addStretch()
        layout.addWidget(eyebrow)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(settings)
        layout.addSpacing(22)
        layout.addWidget(start)
        layout.addWidget(iphone)
        layout.addWidget(privacy)
        layout.addStretch(2)
        return page

    def _build_scanning(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(120, 140, 120, 140)
        title = QLabel("正在分析照片")
        title.setObjectName("sectionTitle")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.scan_status = QLabel("正在准备模型…")
        self.scan_status.setObjectName("muted")
        self.scan_count = QLabel("0%")
        self.scan_count.setObjectName("metric")
        layout.addStretch()
        layout.addWidget(title)
        layout.addWidget(self.scan_count)
        layout.addWidget(self.progress)
        layout.addWidget(self.scan_status)
        layout.addStretch()
        return page

    def _choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "选择照片目录")
        if not selected:
            return
        self.folder = Path(selected)
        self.stack.setCurrentWidget(self.scanning)
        worker = ScanWorker(
            self.folder,
            dino_threshold=self.dino_threshold.value(),
            lpips_threshold=self.lpips_threshold.value(),
        )
        worker.signals.progress.connect(self._scan_progress)
        worker.signals.completed.connect(self._scan_completed)
        worker.signals.failed.connect(self._scan_failed)
        self.thread_pool.start(worker)

    def _scan_iphone(self) -> None:
        self.folder = None
        self.scan_status.setText("正在连接 iPhone，请保持手机解锁…")
        self.progress.setValue(0)
        self.scan_count.setText("0%")
        self.stack.setCurrentWidget(self.scanning)
        worker = ScanWorker(
            source_kind="iphone",
            dino_threshold=self.dino_threshold.value(),
            lpips_threshold=self.lpips_threshold.value(),
        )
        worker.signals.progress.connect(self._scan_progress)
        worker.signals.completed.connect(self._scan_completed)
        worker.signals.failed.connect(self._scan_failed)
        self.thread_pool.start(worker)

    def _scan_progress(self, current: int, total: int, message: str) -> None:
        percent = round(current / max(1, total) * 100)
        self.progress.setValue(percent)
        self.scan_count.setText(f"{percent}%")
        self.scan_status.setText(message)

    def _scan_completed(self, groups: list[SimilarGroup]) -> None:
        self.groups = groups
        self.results = self._build_results()
        self.stack.addWidget(self.results)
        self.stack.setCurrentWidget(self.results)

    def _scan_failed(self, message: str) -> None:
        QMessageBox.critical(self, "扫描失败", f"无法完成照片分析：\n{message}")
        self.stack.setCurrentWidget(self.home)

    def _build_results(self) -> QWidget:
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(34, 28, 34, 24)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        eyebrow = QLabel("扫描完成")
        eyebrow.setObjectName("eyebrow")
        count = sum(len(group.photos) for group in self.groups)
        title = QLabel(f"发现 {len(self.groups)} 组相似照片")
        title.setObjectName("sectionTitle")
        self.summary = QLabel()
        self.summary.setObjectName("muted")
        heading.addWidget(eyebrow)
        heading.addWidget(title)
        heading.addWidget(self.summary)
        header.addLayout(heading)
        header.addStretch()
        self.review_button = QPushButton("查看待删除")
        self.review_button.setObjectName("primary")
        self.review_button.clicked.connect(self._show_delete_review)
        header.addWidget(self.review_button)
        outer.addLayout(header)

        if not self.groups:
            empty = QLabel("没有发现重复或高度相似的照片。\n可以换一个目录重新扫描。")
            empty.setObjectName("empty")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            outer.addWidget(empty, 1)
            retry = QPushButton("重新选择目录")
            retry.clicked.connect(self._choose_folder)
            outer.addWidget(retry, alignment=Qt.AlignmentFlag.AlignCenter)
            self.review_button.hide()
            self.summary.setText("本次扫描没有需要清理的照片")
            return page

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        groups_layout = QVBoxLayout(body)
        groups_layout.setSpacing(20)
        for index, group in enumerate(self.groups, start=1):
            card = QFrame()
            card.setObjectName("groupCard")
            card_layout = QVBoxLayout(card)
            group_title = QLabel(f"第 {index} 组  ·  {len(group.photos)} 张  ·  最低相似度 {group.similarity:.0%}")
            group_title.setObjectName("cardTitle")
            card_layout.addWidget(group_title)
            photos_layout = QHBoxLayout()
            photos_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
            for photo in group.photos:
                photos_layout.addWidget(PhotoTile(photo, photo.id in group.keep_ids, lambda photo_id, value, item=group: self._set_keep(item, photo_id, value)))
            card_layout.addLayout(photos_layout)
            groups_layout.addWidget(card)
        groups_layout.addStretch()
        scroll.setWidget(body)
        outer.addWidget(scroll)
        self._update_summary(count)
        return page

    def _set_keep(self, group: SimilarGroup, photo_id: str, keep: bool) -> None:
        if keep:
            group.keep_ids.add(photo_id)
        else:
            group.keep_ids.discard(photo_id)
        self._update_summary()

    def _update_summary(self, involved: int | None = None) -> None:
        if not hasattr(self, "summary"):
            return
        involved = involved if involved is not None else sum(len(group.photos) for group in self.groups)
        delete_photos = self._delete_photos()
        self.summary.setText(f"涉及 {involved} 张照片  ·  待删除 {len(delete_photos)} 张  ·  可释放 {format_size(sum(photo.reclaim_size for photo in delete_photos))}")
        if hasattr(self, "review_button"):
            self.review_button.setEnabled(bool(delete_photos))

    def _delete_photos(self) -> list[Photo]:
        seen: set[str] = set()
        result: list[Photo] = []
        for group in self.groups:
            for photo in group.delete_photos:
                if photo.id not in seen:
                    seen.add(photo.id)
                    result.append(photo)
        return result

    def _show_delete_review(self) -> None:
        photos = self._delete_photos()
        from .iphone import count_photo_companions

        companion_count = count_photo_companions(photos)
        dialog = QDialog(self)
        dialog.setWindowTitle("待删除照片")
        dialog.resize(760, 640)
        layout = QVBoxLayout(dialog)
        title = QLabel(f"准备删除 {len(photos)} 张照片")
        title.setObjectName("sectionTitle")
        size = sum(photo.reclaim_size for photo in photos)
        companion_text = f"，以及 {companion_count} 个配套 MOV/AAE 文件" if companion_count else ""
        subtitle = QLabel(
            f"预计释放 {format_size(size)}{companion_text}。取消勾选可保留对应照片。"
        )
        subtitle.setObjectName("muted")
        layout.addWidget(title)
        layout.addWidget(subtitle)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        grid = QGridLayout(body)
        checks: list[tuple[Photo, QCheckBox]] = []
        for index, photo in enumerate(photos):
            checkbox = QCheckBox(photo.path.name)
            checkbox.setChecked(True)
            checkbox.setToolTip(str(photo.path))
            checks.append((photo, checkbox))
            grid.addWidget(checkbox, index // 2, index % 2)
        scroll.setWidget(body)
        layout.addWidget(scroll)
        actions = QHBoxLayout()
        cancel = QPushButton("返回检查")
        cancel.clicked.connect(dialog.reject)
        confirm = QPushButton("确认清理")
        confirm.setObjectName("danger")
        confirm.clicked.connect(lambda: self._confirm_delete(dialog, checks))
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(confirm)
        layout.addLayout(actions)
        dialog.exec()

    def _confirm_delete(self, review: QDialog, checks: list[tuple[Photo, QCheckBox]]) -> None:
        selected = [photo for photo, checkbox in checks if checkbox.isChecked()]
        if not selected:
            return
        from .iphone import count_photo_companions

        companion_count = count_photo_companions(selected)
        companion_text = (
            f"\n同时会删除 {companion_count} 个同名 MOV/AAE 配套文件。"
            if companion_count
            else ""
        )
        answer = QMessageBox.warning(
            review,
            "确认移入回收站",
            f"确认清理 {len(selected)} 张照片？{companion_text}\n本机文件进入回收站；iPhone 文件由设备直接删除。",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Cancel,
        )
        if answer != QMessageBox.StandardButton.Ok:
            return
        failures: list[str] = []
        deleted_ids: set[str] = set()
        from send2trash import send2trash

        local_photos = [photo for photo in selected if photo.source_kind == "local"]
        iphone_photos = [photo for photo in selected if photo.source_kind == "iphone"]
        for photo in local_photos:
            try:
                send2trash(str(photo.path))
                deleted_ids.add(photo.id)
            except OSError as error:
                failures.append(f"{photo.path.name}: {error}")
                continue
            for companion_id in photo.companion_ids:
                try:
                    send2trash(companion_id)
                except OSError as error:
                    failures.append(f"{Path(companion_id).name}: {error}")
        if iphone_photos:
            from .iphone import IPhoneBridge

            source_ids = {
                source_id
                for photo in iphone_photos
                for source_id in ((photo.source_id,) + photo.companion_ids)
                if source_id
            }
            succeeded, iphone_failures = IPhoneBridge().delete_media(source_ids)
            failures.extend(iphone_failures)
            for photo in iphone_photos:
                if photo.source_id in succeeded:
                    deleted_ids.add(photo.id)
                    photo.path.unlink(missing_ok=True)
        review.accept()
        if failures:
            QMessageBox.warning(self, "部分照片未能清理", "\n".join(failures[:8]))
        else:
            QMessageBox.information(self, "清理完成", f"已清理 {len(deleted_ids)} 张照片及其配套 MOV/AAE 文件。")
        self.groups = [
            SimilarGroup(group.id, [photo for photo in group.photos if photo.id not in deleted_ids], group.similarity, group.keep_ids)
            for group in self.groups
            if any(photo.id not in deleted_ids for photo in group.photos)
        ]
        self.stack.setCurrentWidget(self.home)


STYLESHEET = """
QWidget { background: #f5f3ef; color: #1d211e; font-family: "Microsoft YaHei UI"; font-size: 14px; }
QLabel#hero { font-size: 46px; font-weight: 700; }
QLabel#sectionTitle { font-size: 28px; font-weight: 700; }
QLabel#subtitle { color: #60665f; font-size: 17px; line-height: 1.6; }
QLabel#muted { color: #777d76; font-size: 12px; }
QLabel#eyebrow { color: #54745e; font-size: 12px; font-weight: 700; letter-spacing: 2px; }
QLabel#metric { font-size: 40px; font-weight: 700; }
QLabel#cardTitle { font-size: 16px; font-weight: 700; }
QLabel#empty { color: #777d76; font-size: 17px; }
QPushButton { background: #e8e5df; border: 0; border-radius: 10px; padding: 12px 18px; font-weight: 600; }
QPushButton:hover { background: #dedad2; }
QPushButton#primary { background: #254f35; color: white; padding: 14px 22px; }
QPushButton#primary:hover { background: #1c402a; }
QPushButton#danger { background: #a33e35; color: white; }
QPushButton:disabled { background: #c8c7c2; color: #888; }
QFrame#groupCard { background: #ffffff; border: 1px solid #e5e1da; border-radius: 16px; padding: 8px; }
QFrame#photoTile { background: #f7f6f2; border-radius: 12px; }
QFrame#settingsCard { background: #ebe8e1; border-radius: 12px; }
QDoubleSpinBox { background: #ffffff; border: 1px solid #d8d4cc; border-radius: 8px; padding: 8px 10px; min-width: 72px; }
QScrollArea { border: 0; background: transparent; }
QProgressBar { height: 14px; border: 0; border-radius: 7px; background: #dedbd4; text-align: center; }
QProgressBar::chunk { border-radius: 7px; background: #527b5e; }
QCheckBox { spacing: 8px; font-weight: 600; }
"""
