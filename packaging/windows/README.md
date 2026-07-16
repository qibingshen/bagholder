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

## 待接入构建命令

正式安装包构建应使用 PyInstaller 或等效平台工具，并把可变数据目录放在平台路径适配器解析出的用户数据目录中。当前仓库尚未加入可执行的 Windows 安装包构建脚本，因此不能把 T124 标记为完成。
