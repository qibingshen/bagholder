# Linux 打包说明

## 目标

Linux 首期目标平台为 Ubuntu 22.04 与 Ubuntu 24.04。应用数据目录应遵循 XDG 目录约定或平台路径适配器定义的等效目录，安装包不得包含用户凭据、行情缓存或预测快照。

## 构建前门禁

```bash
python3.12 -m pytest
python3.12 -m ruff format --check src tests
python3.12 -m ruff check src tests
python3.12 tools/check_chinese_project_text.py
```

## 待接入构建命令

正式验收必须分别在 Ubuntu 22.04 与 Ubuntu 24.04 上构建、安装、启动、升级并恢复数据。当前 Windows 执行环境不能替代 Linux 实机或 CI 结果，因此不能把 T126 标记为完成。
