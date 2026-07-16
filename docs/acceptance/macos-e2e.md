# macOS 端到端验收记录

## 当前状态

状态：未完成。

原因：当前执行环境是 Windows，不能代表 Apple Silicon 或 Intel macOS；仓库已提供 `packaging/macos/build.sh`，但尚未在两类 macOS 目标机器上生成并验收安装包产物。因此不能把 T125 标记为完成。

## 完成 T125 仍需补齐

1. 分别在 Apple Silicon 与 Intel macOS 上执行 `packaging/macos/build.sh`。
2. 保存构建产物哈希、文件清单和 `tools/packaging_guard.py` 检查结果。
3. 验证安装、启动、升级、核心研究闭环和数据恢复。
4. 验证应用数据位于平台路径适配器定义的用户数据目录。
5. 验证安装包不包含用户凭据、行情缓存、预测快照或本地数据库。

固定风险提示：研究参考，不构成投资建议。
