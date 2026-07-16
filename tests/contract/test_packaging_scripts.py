"""验证三平台打包脚本和打包安全守卫。"""

from pathlib import Path
from subprocess import run


def test_开发依赖包含打包工具() -> None:
    """项目依赖清单必须提供安装 PyInstaller 的明确入口。"""

    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "pyinstaller" in pyproject.lower()


def test_三平台打包脚本存在并调用统一安全守卫() -> None:
    """打包入口必须先经过测试门禁和统一打包清单安全检查。"""

    scripts = {
        "windows": Path("packaging/windows/build.ps1"),
        "macos": Path("packaging/macos/build.sh"),
        "linux": Path("packaging/linux/build.sh"),
    }

    for platform, script in scripts.items():
        content = script.read_text(encoding="utf-8")
        assert "packaging_guard.py" in content, platform
        assert "pytest" in content, platform
        assert "ruff" in content, platform
        assert "check_chinese_project_text.py" in content, platform
        assert "pyinstaller" in content.lower(), platform


def test_windows_打包脚本语法可被_powershell_解析() -> None:
    """Windows 打包脚本必须先通过 PowerShell 语法解析。"""

    command = (
        "$content = Get-Content -Raw packaging/windows/build.ps1; "
        "$null = [scriptblock]::Create($content)"
    )
    result = run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_打包守卫拒绝凭据本地数据和研究快照入包(tmp_path: Path) -> None:
    """安装包清单不得包含密钥、环境文件、本地数据库、行情缓存或预测快照。"""

    from tools.packaging_guard import PackagingGuard, PackagingGuardError

    manifest = tmp_path / "manifest.txt"
    manifest.write_text(
        "\n".join(
            [
                "dist/app/stock_agent.exe",
                "dist/app/.env",
                "dist/app/data/core.duckdb",
                "dist/app/prediction_snapshots/pred-1.json",
            ]
        ),
        encoding="utf-8",
    )

    try:
        PackagingGuard().validate_manifest(manifest)
    except PackagingGuardError as error:
        message = str(error)
    else:
        raise AssertionError("打包守卫必须拒绝敏感文件清单")

    assert ".env" in message
    assert "core.duckdb" in message
    assert "prediction_snapshots" in message


def test_打包守卫接受只包含程序资源的清单(tmp_path: Path) -> None:
    """只包含程序、库和只读资源的清单应允许通过。"""

    from tools.packaging_guard import PackagingGuard

    manifest = tmp_path / "manifest.txt"
    manifest.write_text(
        "\n".join(
            [
                "dist/app/stock_agent.exe",
                "dist/app/PySide6/QtCore.pyd",
                "dist/app/resources/app-icon.ico",
                "dist/app/README.md",
            ]
        ),
        encoding="utf-8",
    )

    PackagingGuard().validate_manifest(manifest)
