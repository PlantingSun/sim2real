"""项目内资源路径，避免脚本依赖当前工作目录或外部工作空间。"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_ROOT = PROJECT_ROOT / "assets"
MODEL_ROOT = PROJECT_ROOT / "models"
GO2W_SCENE = ASSET_ROOT / "go2w_description" / "mjcf" / "go2w_scene.xml"


def model_path(name: str) -> str:
    """返回项目内 checkpoint 路径；权重是否存在由调用方检查。"""
    return str(MODEL_ROOT / name)
