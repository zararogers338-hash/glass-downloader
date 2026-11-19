# 场景、角色与第三方组件

[MIT](LICENSE) 适用于本项目的程序代码和技术文档。场景插画、包含场景的截图、第三方角色及商标单独说明；项目对第三方权利不作再许可。

仓库分发 12 张定稿插画的运行时 WebP 和预览图。作者使用图像生成和局部重绘制作场景，再用 Upscayl 放大定稿。界面所需的两个文件是每个场景目录中的 `wallpaper.webp` 和 `preview.webp`。部分 `scene.json` 的 `master` 字段记录存档母图的尺寸与哈希；该 PNG 由作者本地保存。

| 场景 | 形象及参考 |
| --- | --- |
| HF 日间合影、魔搭夜间合影 | 各模型的社区拟人形象。逐角色页面记录在 [HF 清单](scene-packs/hf-station-day/scene.json) 和 [魔搭清单](scene-packs/modelscope-station-night/scene.json) 的 credits 中 |
| 哔哩哔哩 | 22、33 及原始构图参考来自[哔哩哔哩生日活动页](https://www.bilibili.com/blackboard/era/2233birthday.html) |
| GitHub | Octocat 造型参考 [GitHub Octodex](https://octodex.github.com/original/)；电脑画面出现 Ubuntu 标志 |
| arXiv、Java、C/C++、磁力、Tor、视频 | 猫的轮廓参考 [Clash for Windows 应用图标](https://github.com/flathub/io.github.Fndroid.clash_for_windows)。Java 场景中包含 Java 标志 |
| Python、Linux | 双蛇节日插画与南极企鹅插画。Linux 场景含 Linus Torvalds 的插画形象 |

各平台名称用来标识下载来源。发行衍生版本时可以在设置里导入自己的壁纸，或在保留场景 ID 的前提下替换两个 WebP 文件。有关素材署名的反馈，可在仓库 Issues 中提供场景名及原始来源。

Python、npm 和 Cargo 依赖分别按各自的上游许可证提供。aria2、BBDown、FFmpeg、Mihomo 与 Tor 的二进制文件由用户安装。可选的 Windows 安装脚本从上游 Releases 下载 aria2 和 BBDown，并使用指定版本的 WinGet 清单哈希校验。
