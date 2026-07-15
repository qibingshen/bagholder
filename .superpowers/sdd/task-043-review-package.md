# T043 审查包

## 提交

fcf9a71 feat: add desktop market page states

## 统计

 .superpowers/sdd/task-043-report.md            | 30 +++++++++++++++
 src/stock_agent/desktop/pages/market_page.py   | 53 ++++++++++++++++++++++++++
 src/stock_agent/desktop/pages/security_page.py | 52 +++++++++++++++++++++++++
 3 files changed, 135 insertions(+)

## 差异

```diff
diff --git a/.superpowers/sdd/task-043-report.md b/.superpowers/sdd/task-043-report.md
new file mode 100644
index 0000000..8c20a5b
--- /dev/null
+++ b/.superpowers/sdd/task-043-report.md
@@ -0,0 +1,30 @@
+# T043 市场与证券页面状态模型报告
+
+## 实现
+
+- 新增 `MarketPageState` 与 `SecurityPageState`，均支持 `EMPTY`、`LOADING`、`OFFLINE`、`PERMISSION_DENIED`、`STALE`、`READY`、`RECOVERED`，并额外支持本地交易日历的 `CLOSED` 状态。
+- 每个状态保留原始状态标识和简体中文用户说明。
+- `OFFLINE`、`STALE`、`CLOSED`、`PERMISSION_DENIED` 的 `shows_realtime` 与 `current_prediction_allowed` 均为 `False`；同时保留渲染层兼容属性 `show_realtime_data` 和 `allow_current_prediction`。
+- 页面模型仅接收脱敏状态，不包含网络请求、预测数值生成或交易能力。
+
+## TDD 记录
+
+先执行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_desktop_state_contract.py -v
+```
+
+红灯结果：测试收集失败，`ModuleNotFoundError: No module named 'stock_agent.desktop.pages.market_page'`。随后新增最小页面状态模型，同一命令转绿。
+
+## 验证
+
+- 页面状态合约：34 passed。
+- 页面文件 Ruff：`All checks passed!`。
+- 页面文件编译：`py -3.12 -m compileall -q src/stock_agent/desktop/pages` 成功。
+- 中文检查：人工检查新增模块的文档字符串、注释与用户可见文案均为简体中文；英文仅用于状态标识和代码标识符。
+- 全量 pytest：309 passed，10 failed。失败均位于既有市场新鲜度、公司行动与港股代码规则实现，未涉及本任务新增页面状态文件。
+
+## 已知关注项
+
+全量失败包括当前预测拒绝、`CompanyAction` 参数和公司行动辅助函数缺失，以及港股六位代码校验；这些为任务范围外的既有失败，未在 T043 中修改。
diff --git a/src/stock_agent/desktop/pages/market_page.py b/src/stock_agent/desktop/pages/market_page.py
new file mode 100644
index 0000000..c680aef
--- /dev/null
+++ b/src/stock_agent/desktop/pages/market_page.py
@@ -0,0 +1,53 @@
+"""定义市场总览页面的本地事实状态模型，不发起网络访问。"""
+
+from __future__ import annotations
+
+from dataclasses import dataclass, field
+
+_状态说明 = {
+    "EMPTY": "暂无可显示的本地市场事实。",
+    "LOADING": "正在加载已选择范围内的本地市场事实。",
+    "OFFLINE": "当前处于离线状态，无法显示实时数据。",
+    "PERMISSION_DENIED": "数据源权限受限，当前范围不可读取。",
+    "STALE": "本地市场事实已过期，不能作为实时数据使用。",
+    "CLOSED": "市场已闭市，不能显示实时数据或进行当前预测。",
+    "READY": "本地市场事实可用。",
+    "RECOVERED": "已恢复：本地市场事实已重新验证并可用。",
+}
+
+_不可实时状态 = frozenset({"OFFLINE", "PERMISSION_DENIED", "STALE", "CLOSED"})
+_可用状态 = frozenset({"READY", "RECOVERED"})
+
+
+@dataclass(frozen=True, slots=True)
+class MarketPageState:
+    """市场总览仅渲染脱敏状态或已验证的本地市场事实。"""
+
+    status: str
+    user_message: str = field(init=False)
+    shows_realtime: bool = field(init=False)
+    current_prediction_allowed: bool = field(init=False)
+    is_available: bool = field(init=False)
+
+    def __post_init__(self) -> None:
+        """锁定状态语义，避免将降级状态误标为实时或可预测。"""
+
+        if self.status not in _状态说明:
+            raise ValueError(f"不支持的市场页面状态：{self.status}")
+        object.__setattr__(self, "user_message", _状态说明[self.status])
+        available = self.status in _可用状态
+        object.__setattr__(self, "is_available", available)
+        object.__setattr__(self, "shows_realtime", self.status == "READY")
+        object.__setattr__(self, "current_prediction_allowed", self.status == "READY")
+
+    @property
+    def show_realtime_data(self) -> bool:
+        """兼容页面渲染层对实时展示开关的既有命名。"""
+
+        return self.shows_realtime
+
+    @property
+    def allow_current_prediction(self) -> bool:
+        """兼容页面渲染层对当前预测入口开关的既有命名。"""
+
+        return self.current_prediction_allowed
diff --git a/src/stock_agent/desktop/pages/security_page.py b/src/stock_agent/desktop/pages/security_page.py
new file mode 100644
index 0000000..dab44a9
--- /dev/null
+++ b/src/stock_agent/desktop/pages/security_page.py
@@ -0,0 +1,52 @@
+"""定义个股研究页面的本地事实状态模型，不发起网络访问。"""
+
+from __future__ import annotations
+
+from dataclasses import dataclass, field
+
+_状态说明 = {
+    "EMPTY": "暂无可显示的本地证券研究事实。",
+    "LOADING": "正在加载已选择证券的本地研究事实。",
+    "OFFLINE": "当前处于离线状态，无法显示实时数据。",
+    "PERMISSION_DENIED": "数据源权限受限，当前证券事实不可读取。",
+    "STALE": "本地证券研究事实已过期，不能作为实时数据使用。",
+    "CLOSED": "市场已闭市，不能显示实时数据或进行当前预测。",
+    "READY": "本地证券研究事实可用。",
+    "RECOVERED": "已恢复：本地证券研究事实已重新验证并可用。",
+}
+
+_可用状态 = frozenset({"READY", "RECOVERED"})
+
+
+@dataclass(frozen=True, slots=True)
+class SecurityPageState:
+    """个股研究页面仅接受脱敏状态或本地研究视图模型。"""
+
+    status: str
+    user_message: str = field(init=False)
+    shows_realtime: bool = field(init=False)
+    current_prediction_allowed: bool = field(init=False)
+    is_available: bool = field(init=False)
+
+    def __post_init__(self) -> None:
+        """锁定降级页面的展示与预测权限，禁止伪装为实时。"""
+
+        if self.status not in _状态说明:
+            raise ValueError(f"不支持的证券页面状态：{self.status}")
+        object.__setattr__(self, "user_message", _状态说明[self.status])
+        available = self.status in _可用状态
+        object.__setattr__(self, "is_available", available)
+        object.__setattr__(self, "shows_realtime", self.status == "READY")
+        object.__setattr__(self, "current_prediction_allowed", self.status == "READY")
+
+    @property
+    def show_realtime_data(self) -> bool:
+        """兼容页面渲染层对实时展示开关的既有命名。"""
+
+        return self.shows_realtime
+
+    @property
+    def allow_current_prediction(self) -> bool:
+        """兼容页面渲染层对当前预测入口开关的既有命名。"""
+
+        return self.current_prediction_allowed

```

