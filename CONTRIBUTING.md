# 参与开发

欢迎提交可复现的 Bug、下载源适配和界面改进。在改动公共接口前，可先开一个 Issue 描述使用场景。

- 新的输入简写和来源解析放在 `core/resolver.py`，用 `tools/check_inputs.py` 补充成功、歧义及错误输入用例。
- 下载核心的适用频道和出口写入 `engines.json`。为暂停、取消和完成后发布文件的行为增加本地测试。代理线路失败时要将错误返回给调用方。
- 界面通过 REST / WebSocket 与核心交互。场景图片按频道加载，使用者自定义的壁纸保存在本机。引入第三方素材时请一并提交来源和可分发授权说明。

## 本地检查

在仓库根目录建立 `.venv` 并安装 Python 依赖，运行：

```powershell
npm.cmd ci
npm.cmd run build
.\.venv\Scripts\python.exe tools/check_inputs.py
.\.venv\Scripts\python.exe tools/check_interrupts.py
node tools/check-workbench.mjs
```

中断测试使用本机 cURL、HTTPX 和临时 HTTP 服务。若有 aria2，会追加外部进程测试。界面测试默认在 Edge 中运行，使用临时端口和临时数据目录。通过 `BROWSER_CHANNEL` 可以指定已安装的其他 Playwright 浏览器通道。

提交 PR 时写清改动影响了哪个频道、验证了哪些输入和平台。界面改动最好附上截图。涉及本机 API 凭据或未公开的安全问题，请通过 GitHub 私密漏洞报告（若已启用）联系维护者。普通 Bug 报告请使用公开可分享的资源或本地测试文件。

