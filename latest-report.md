# SourceLens 交叉验证报告

## 共同观点
- 异步请求使用 async/await 语法，并通过异步客户端或协程来发起。
  - 来源：[SOURCE_1](https://www.python-httpx.org/async/), [SOURCE_2](https://docs.python.org/3/library/asyncio-task.html)

## 冲突信息
- 暂无

## 未回答问题
- 异步请求相比同步请求的具体性能提升幅度未量化。
  - 来源：[SOURCE_1](https://www.python-httpx.org/async/)
- 异步请求在 WebSocket 等长连接场景下的具体实现细节未说明。
  - 来源：[SOURCE_1](https://www.python-httpx.org/async/)
- 协程调用后如何调度执行的具体机制未详细展开。
  - 来源：[SOURCE_2](https://docs.python.org/3/library/asyncio-task.html)

## 资料限制
- SOURCE_1 仅介绍 HTTPX 异步客户端的基本用法，未深入异步编程模型。
  - 来源：[SOURCE_1](https://www.python-httpx.org/async/)
- SOURCE_2 聚焦 asyncio 协程与任务，未涉及 HTTP 请求的具体实现。
  - 来源：[SOURCE_2](https://docs.python.org/3/library/asyncio-task.html)

## 来源
- SOURCE_1: https://www.python-httpx.org/async/
- SOURCE_2: https://docs.python.org/3/library/asyncio-task.html