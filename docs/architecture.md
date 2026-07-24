# 架构说明

```text
TradingAgents-Astock 隔离进程
        ↓ ResearchDecision
主应用 SignalToOrderService
        ↓ OrderProposal
LiveRiskService
        ↓ RiskVerdict
ApprovalService
        ↓ OrderApproval
LiveExecutionService
        ↓ ExecutionRequest
带 HMAC 的本机 IPC
        ↓
vn.py + RiskManager + 私有 Gateway
        ↓
中信证券 / 国泰海通证券
```

研究进程、主应用和交易节点是三个不同的故障域。研究进程没有交易凭据；主应用不加载券商动态库；
交易节点不接受缺少风控、审批、幂等键和有效签名的请求。
