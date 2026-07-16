"""验证桌面实时行情后台刷新器。"""


def test_后台刷新器将成功报价交给界面回调() -> None:
    """网络读取必须由后台工作单元执行，界面只接收结果。"""

    from stock_agent.desktop.live_quote_refresh import LiveQuoteRefresh

    received: list[object] = []
    refresh = LiveQuoteRefresh(lambda: "本地报价事实")
    refresh.succeeded.connect(received.append)

    refresh.run()

    assert received == ["本地报价事实"]
