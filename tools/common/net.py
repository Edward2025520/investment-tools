"""给 requests 兜一个默认超时。

背景：akshare 内部大量使用 requests 且普遍不设 timeout。已实证过一次后果——
screen_csi500 抓百度估值时，6 并发触发限流后某个请求被无限期挂起，整个任务
静默卡死 40 分钟（无报错、无输出、CPU 不动）。而 akshare 的调用点有十几处，
逐个自实现既繁琐又容易漏，所以从 Session.request 这一层统一兜底。

覆盖面：requests.get/post/put/delete/head/patch 以及所有 requests.Session 用法，
因为 requests.api 的每个函数最终都走 Session.request。

不影响：
- 项目自身代码里已显式设置 timeout 的调用（本补丁只在未指定时兜底）
- httpx（stock_reports 用它下载年报 PDF，已有独立的 timeout 配置）
"""

import requests.sessions

DEFAULT_TIMEOUT = 15.0

_orig_request = requests.sessions.Session.request
_installed = False
_timeout = DEFAULT_TIMEOUT


def _patched_request(self, method, url, **kwargs):
    if kwargs.get("timeout") is None:
        kwargs["timeout"] = _timeout
    return _orig_request(self, method, url, **kwargs)


def install_default_timeout(timeout: float = DEFAULT_TIMEOUT) -> None:
    """安装默认超时。

    重复调用不会重复替换方法，但会用新的 timeout 值（便于测试时收紧）。
    """
    global _installed, _timeout
    _timeout = timeout
    if _installed:
        return
    requests.sessions.Session.request = _patched_request
    _installed = True
