# Windows x64 单文件发行版

在 Windows x64 上使用官方 CPython 3.13 x64、Node.js 22.12+、npm、Rust MSVC 工具链、Visual Studio C++ Build Tools 和 Windows SDK。从仓库根目录执行：

```powershell
.\tools\build-portable.ps1
.\.venv\Scripts\python.exe tools/check-portable.py deliverables/windows/GlassDownloader-0.1.1-windows-x64.exe
```

构建脚本先编译 Svelte 和 Tauri，然后由 PyInstaller 将 Python 下载服务、原生窗口和运行时资源合并为一个 GUI EXE。场景资源由 channels.json 枚举，只收录每个场景的 manifest 和两个 WebP；母图、个人图库、数据库和本机凭据均不参加打包。嵌入的 yt-dlp worker 在单独的进程里运行，可随任务一起中断。

输出在 `deliverables/windows/`。发布时将 EXE、同名 .sha256 和 THIRD-PARTY-NOTICES.zip 一起上传 GitHub Release。当前构建没有使用代码签名证书。比较 SHA-256 可使用：

```powershell
Get-FileHash .\GlassDownloader-0.1.1-windows-x64.exe -Algorithm SHA256
```

单文件程序每次从自身解包到临时目录；任务存储、API 令牌和下载产物使用持久目录。运行 `--headless` 可只启动本地服务，`--data`、`--output` 和 `--port` 可设置位置和端口。需要窗口的机器应安装 Microsoft Edge WebView2 Evergreen Runtime。

冒烟测试把单个 EXE 复制到独立临时目录，在仅有系统目录的 PATH 下启动真实 Tauri 窗口，确认 WebView2 渲染和本地 API 握手，通过页面提交测试文件并校验 SHA-256。它还检查 12 张内置场景、二次启动、关闭窗口后的服务退出，以及随包视频 worker 的可执行性。测试数据、浏览器配置和端口独立于日常使用的配置。
