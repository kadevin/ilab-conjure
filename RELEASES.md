# 下载 / Releases

当前正式版本：[v0.3.7](https://github.com/kadevin/ilab-gpt-conjure/releases/tag/v0.3.7)

## 版本说明

当前版本：`v0.3.7`。这个版本提供 Windows x64、macOS Apple Silicon、macOS Intel 三种免安装一键包；下载对应平台的 zip 后解压即可启动本地 WebUI，并可在包内一键更新到后续版本。

本版重点：这一版集中完成历史库大屏浏览、任务详情预览、生成页队列交互和一键包更新提醒四组体验升级，同时修复多处前端布局、主题色、按钮溢出和任务状态细节问题。

本版详情：

- 历史库：三栏布局支持左右拖拽调宽；中间任务库改为更接近 Eagle 的缩略图浏览方式，支持双向窗口化加载、滚动回到顶部恢复最新任务、当前查看任务保持焦点。
- 历史详情：结果图支持多图自适应排列、双击/点击打开大图、翻页浏览和鼠标滚轮缩放；输入参考图会在详情中弱化展示，不抢结果图焦点。
- 历史操作：缩略图选中态、右键菜单、单选/多选动作、归档/删除/下载/复制提示词/复制任务 ID 等交互做了区分；多选菜单不再出现只适合单任务的复制项。
- 生成页任务栏：等待任务的拖拽预览限制在侧栏内，队列动作按钮改为 SVG 图标并修复溢出；任务选中态、图生图双图缩略图、时间分组 sticky 和部分失败任务状态显示继续收口。
- 前端细节修复：颜色 chip、上传缩略图标签、预览大图关闭按钮、预览图浮层、滚动条主题色、短屏布局、历史库筛选图标和多图排列等可见 UI 问题进行了修补。
- 一键包更新：生成页左下角显示真实一键包版本；启动脚本检测到新 GitHub Release 时在 WebUI 内给出提醒；点击版本提示可查看最新版本、打开 Release 页面，并在一键包环境中启动更新器。更新脚本继续保留下载校验、备份和本地 data 保留流程，避免自动更新打断当前工作。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.3.7.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.3.7/ilab-gpt-conjure_windows_portable_x64_0.3.7.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.3.7/ilab-gpt-conjure_windows_portable_x64_0.3.7.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.3.7.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.3.7/ilab-gpt-conjure_macos_portable_arm64_0.3.7.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.3.7/ilab-gpt-conjure_macos_portable_arm64_0.3.7.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.3.7.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.3.7/ilab-gpt-conjure_macos_portable_x64_0.3.7.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.3.7/ilab-gpt-conjure_macos_portable_x64_0.3.7.zip.sha256.txt) |

使用方式：

1. 下载对应平台的 zip。
2. 解压到普通用户目录，不要放在系统保护目录。
3. Windows 双击 `Start WebUI Portable.bat`；macOS 双击
   `Start WebUI Portable.command`。
4. 如果浏览器没有自动打开，访问 `http://127.0.0.1:8787/`。

启动脚本会短暂检测最新 GitHub Release；发现新版本时会在 WebUI 左下角版本入口显示提醒，不会自动更新。
更新已经解压的一键包时，先关闭 WebUI 服务窗口，然后运行 Windows 的
`Update WebUI Portable.bat` 或 macOS 的 `Update WebUI Portable.command`。
更新脚本会下载当前平台对应的最新 GitHub Release 资产，校验 SHA256，保留本地 `data/`，并把被替换文件备份到 `.backup/`。如果不希望启动时检查版本，可在启动前设置
`ILAB_SKIP_VERSION_CHECK=1`。

macOS 包是未签名的 portable zip，不是已签名 `.app` 或 notarized DMG。
启动脚本会尝试在启动前移除当前解压目录内的 quarantine 标记。如果 macOS
仍然拦截启动脚本，可以右键或 Control-click `Start WebUI Portable.command`，
选择 Open，并在系统安全提示中再次确认。也可以对解压目录执行：

```bash
xattr -dr com.apple.quarantine /path/to/ilab-gpt-conjure_macos_portable_arm64
# 或：
xattr -dr com.apple.quarantine /path/to/ilab-gpt-conjure_macos_portable_x64
```

一键包内的 `data/` 目录会保存本地设置、公用图库、输入图、输出图、任务数据库和日志。
不要把这些本地数据、API key 或 OAuth 文件提交到 Git。
