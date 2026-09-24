# PhotoClean

本地相似照片清理桌面应用。DINOv2 负责检索整体视觉结构接近的照片，LPIPS 负责确认人眼感知差异；用户在分组中选择保留照片，剩余照片经过待删除复核与二次确认后移入系统回收站。

## 运行

建议使用 Python 3.10–3.12。首次启动会安装较大的 PyTorch 依赖，并从官方仓库下载 DINOv2 与 LPIPS 权重。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
photoclean
```

NVIDIA CUDA 环境需要按 [PyTorch 官方安装说明](https://pytorch.org/get-started/locally/) 替换对应的 `torch` / `torchvision` 包；没有 CUDA 时自动使用 CPU。

## 当前 MVP

- 选择本机照片目录并递归扫描
- 直接扫描 Windows 已识别并解锁的 USB iPhone，无需盘符
- 读取尺寸、文件大小、EXIF 拍摄时间与方向
- DINOv2 特征提取 + LPIPS 精排
- 首页可调整 DINO 最低相似度和 LPIPS 最大视觉差异阈值
- 依据拍摄时间和画幅预筛候选，避免无意义的全量模型比较
- 保守的完整连接分组，避免相似关系链式误合并
- 分组缩略图、原图预览、任意数量保留
- 自动汇总待删除照片和可释放空间
- 两次人工确认后移入系统回收站
- 删除 iPhone 照片时，同时删除同目录、同名的 `.MOV` Live Photo 视频和 `.AAE` 编辑信息
- 用户在 PhotoClean 最终确认后，iPhone 文件使用 Windows 静默批量删除，不再逐文件弹出系统确认框

默认阈值为 DINOv2 `0.84`、LPIPS `0.32`、候选拍摄间隔 `30` 分钟。DINO 越低、LPIPS 越高，识别越宽松；反向调整则更严格。这些是 MVP 起始值，应使用真实照片标注集调优后再发布。

## 测试

```powershell
python -m pip install -e ".[dev]"
pytest
```

## 打包 Windows 可执行程序

```powershell
.\build.ps1
```

产物位于 `dist\PhotoClean\PhotoClean.exe`。发布时需要分发整个 `dist\PhotoClean` 目录；DINOv2 和 AlexNet 模型在首次扫描时下载到用户的 Torch 缓存，后续启动复用缓存。

构建后可用 `dist\PhotoClean\PhotoClean.exe --self-test-models` 验证打包版本是否能够加载 DINOv2 和 LPIPS；成功时退出码为 `0`。

## 安全边界

- 照片只在本机处理，不上传。
- 应用不会自动删除照片。
- 清理操作使用系统回收站；若系统或挂载设备不支持回收站，文件会保留并在界面中报告失败。
- iPhone 属于 WPD 便携设备，删除由手机直接执行，通常不会进入 Windows 回收站；确认页会明确提示这一差异。
