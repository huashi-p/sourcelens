# SourceLens

SourceLens 读取多个公开网址，提取正文，比较共同观点和冲突，
并返回带来源链接和限制说明的报告。

## 当前能力

- 同时读取 2–5 个网址，最多并发 2 个。
- 单个来源超时、被限流或返回错误时，不影响其他来源。
- 只允许 HTTP 和 HTTPS，以及 80、443 或默认端口。
- 拒绝账号密码 URL、内网 IP 和解析到内网地址的域名。
- 手动检查每次重定向，最多 3 次。
- 原始响应最多 2 MB，提取正文最多 20000 字符。
- 对超时、网络错误、429 和 5xx 最多重试 2 次。
- 至少两个来源成功时才生成交叉验证报告。
- 本地验证模型返回的来源 ID，再附加真实 URL。

## 安装

```powershell
cd D:\code\sourcelens
D:\code\sourcelens\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

复制 `.env.example` 并在 `.env` 中配置自己的 Key，不要提交 `.env`。

## 运行

```powershell
cd D:\code\sourcelens
D:\code\sourcelens\.venv\Scripts\python.exe compare_demo.py
```

## 当前限制

- 不执行 JavaScript，因此动态页面可能提取不到正文。
- URL 校验与实际连接会分别解析 DNS，仍存在 DNS 重绑定风险。
- 不使用向量检索，交叉验证质量依赖模型和页面正文质量。
- 报告只比较用户提供的来源，不自动搜索全网。

