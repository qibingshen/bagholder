# Windows 打包说明

## 目标

Windows 目标平台为 Windows 10/11。安装包必须只包含应用程序与只读资源，不得内置行情数据、预测快照、用户凭据或本地研究数据库。

## 构建前门禁

```powershell
py -3.12 -m pytest
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
py -3.12 tools/check_chinese_project_text.py
```

## 构建命令

```powershell
packaging\windows\build.ps1
```

脚本会执行测试、格式、静态和中文规范门禁，使用 PyInstaller 输出到 `dist/windows/`，生成安装包文件清单，并调用 `tools/packaging_guard.py` 拒绝凭据、本地数据库、行情缓存和预测快照入包。

当前仍不能把 T124 标记为完成：脚本已存在，但还缺少 Windows 10/11 干净环境中的真实安装、启动、升级、核心流程和数据恢复验收记录。
