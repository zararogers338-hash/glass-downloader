# 本地 API

服务默认绑定 `127.0.0.1:17846`。Python 启动参数 `--port`、`--data` 和 `--output` 分别设置端口、数据目录和初始下载目录。Windows 默认数据目录为 `%LOCALAPPDATA%\GlassDownloader`，其他平台使用 `$XDG_STATE_HOME/GlassDownloader` 或 `~/.local/state/GlassDownloader`。REST 请求使用 `Authorization: Bearer <token>`。token 位于数据目录中的 `api-token` 文件。
 
## 从计划到下载

以下 PowerShell 示例先查看解析结果，再提交一个很小的公开仓库。幂等键由调用方选择，同一次操作的重试复用同一键。

```powershell
$api = 'http://127.0.0.1:17846/api/v1'
$token = (Get-Content (Join-Path $env:LOCALAPPDATA 'GlassDownloader/api-token') -Raw).Trim()
$headers = @{ Authorization = "Bearer $token" }
$body = @{
  channel = 'github'
  url = 'octocat/Hello-World'
  idempotency_key = 'hello-world-demo-1'
} | ConvertTo-Json
Invoke-RestMethod "$api/plan" -Method Post -Headers $headers -ContentType 'application/json' -Body $body
$job = Invoke-RestMethod "$api/jobs" -Method Post -Headers $headers -ContentType 'application/json' -Body $body
Invoke-RestMethod "$api/jobs/$($job.id)" -Headers $headers
```

`channel` 接受 [channels.json](../channels.json) 的 ID。`url` 可填写当前频道支持的简写。`prefer_engine` 和 `prefer_proxy` 用于覆盖频道策略，请按 [engines.json](../engines.json) 的能力矩阵组合。普通文件可附 `expected_sha256`。整仓使用上游文件清单与可用的逐文件摘要。

## 接口

下表均以 `/api/v1` 为前缀。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/config`、`/state` | 频道、组件、设置及本机遥测 |
| POST | `/plan`、`/jobs` | 解析计划或创建任务。仓库短名有歧义时返回 409 及候选项 |
| GET | `/jobs`、`/jobs/{id}` | 任务列表或单个任务 |
| POST | `/jobs/{id}/pause`、`/jobs/{id}/resume` | 暂停，或继续暂停／失败的任务 |
| POST | `/jobs/{id}/cancel` | 停止任务并清理该任务的临时分片，保留记录 |
| POST | `/jobs/{id}/delete` | 停止并移除任务，保留已发布的文件 |
| POST | `/jobs/{id}/folder` | 在本机文件管理器打开任务目录 |
| POST | `/bilibili/formats` | 传入 `{"url":"BV…"}`，取得核心实际可见的画质选项 |
| PATCH | `/settings` | 更新部分设置，例如 `{"speed_profile":"low"}` |
| POST | `/components/rescan` | 重新检测本机组件 |
| POST | `/submissions/{op}/stop` | 中断带对应 `submission_id`（UUID）的提交解析 |

B 站创建任务可传 `"media":{"mode":"audio","quality":"auto"}`；视频的 `mode` 为 `video`，`quality` 接受 `auto` 或画质接口返回的 ID。WebSocket 路径是 `/events`，连接后第一条文本消息发送 token，随后接收状态快照。

## 接入注意事项

API 适合本机脚本、编辑器和 AI 工具。请将 token 视为下载器的本机控制凭据。截图、日志及问题报告中应隐去 token、Cookie、带签名的 URL 和私人路径。HTTP 文件的 `done`、`total` 与分块偏移使用字节，`speed` 使用字节／秒；长度或遥测未知时，调用方应允许空值。

