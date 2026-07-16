"""打包清单安全守卫。"""

from __future__ import annotations

from pathlib import Path


class PackagingGuardError(ValueError):
    """表示安装包清单包含禁止入包的本地数据或凭据。"""


class PackagingGuard:
    """检查安装包不会携带凭据、本地研究数据或不可变快照。"""

    _blocked_fragments = (
        ".env",
        ".key",
        "credential",
        "credentials",
        "core.duckdb",
        ".duckdb",
        ".sqlite",
        "market-data-raw",
        "market-data-normalized",
        "prediction_snapshots",
        "prediction-snapshots",
        "backup-manifest",
    )

    def validate_manifest(self, manifest_path: Path) -> None:
        """读取清单并拒绝敏感路径。"""

        entries = manifest_path.read_text(encoding="utf-8").splitlines()
        violations = [
            entry for entry in entries if self._is_blocked(entry.strip().replace("\\", "/").lower())
        ]
        if violations:
            joined = "；".join(violations)
            raise PackagingGuardError(f"安装包清单包含禁止入包路径：{joined}")

    def _is_blocked(self, normalized_entry: str) -> bool:
        """判断单个路径是否命中禁止片段。"""

        return any(fragment in normalized_entry for fragment in self._blocked_fragments)


def main() -> int:
    """命令行入口，参数为安装包文件清单路径。"""

    import argparse

    parser = argparse.ArgumentParser(description="检查安装包清单是否包含禁止入包的本地数据。")
    parser.add_argument("manifest", type=Path)
    args = parser.parse_args()
    PackagingGuard().validate_manifest(args.manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
