"""OpenCV Qt 窗口初始化辅助；不处理或修改深度数据。"""

import os
from pathlib import Path


# opencv-python 的 Linux Qt wheel 可能把 QT_QPA_FONTDIR 指向一个未打包的
# cv2/qt/fonts 目录。优先使用系统现有字体，不在运行时下载或复制文件。
_SYSTEM_FONT_DIRS = (
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation2"),
    Path("/usr/share/fonts"),
)


def load_cv2_for_gui():
    """导入 cv2，并在创建 Qt 窗口前修正不存在的字体目录。"""
    import cv2

    configured = os.environ.get("QT_QPA_FONTDIR", "")
    if not configured or not Path(configured).is_dir():
        for candidate in _SYSTEM_FONT_DIRS:
            if candidate.is_dir():
                os.environ["QT_QPA_FONTDIR"] = str(candidate)
                break
    return cv2
