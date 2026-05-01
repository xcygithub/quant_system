"""阶段4测试：配置路径一致性校验。"""

from pathlib import Path

from config import CACHE_DIR, DATABASE_PATH, PROJECT_ROOT


def test_project_root_is_config_parent():
    assert PROJECT_ROOT == Path(__file__).resolve().parent.parent


def test_database_path_under_project_root():
    assert DATABASE_PATH == PROJECT_ROOT / "quant_data.db"
    assert DATABASE_PATH.parent == PROJECT_ROOT


def test_cache_dir_under_project_root():
    assert CACHE_DIR == PROJECT_ROOT / "data_cache"
