# 本地量化股票分析智能体

这是一个仅用于股票研究、模拟预测和历史验证的本地桌面应用。第一阶段不连接券商、不执行真实交易，
所有预测和报告均应显示“研究参考，不构成投资建议”。

## 开发环境

需要 Python 3.12。安装开发依赖：

```powershell
py -3.12 -m pip install -e ".[dev]"
```

运行测试：

```powershell
py -3.12 -m pytest
```

运行中文说明检查：

```powershell
py -3.12 tools/check_chinese_project_text.py .
```

Windows、macOS 和 Linux 的正式打包、安装、升级与恢复验收将在跨平台交付阶段分别完成。
