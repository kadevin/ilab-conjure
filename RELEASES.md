# 下载 / Releases

当前正式版本：[v0.3.5](https://github.com/kadevin/ilab-gpt-conjure/releases/tag/v0.3.5)

## 版本说明

当前版本：`v0.3.5`。这个版本提供 Windows x64、macOS Apple Silicon、macOS Intel 三种免安装一键包；下载对应平台的 zip 后解压即可启动本地 WebUI，并可在包内一键更新到后续版本。

本版重点：优化提示词颜色 chip 和取色弹层。颜色保存统一使用 HEX 值，取色器、HEX 输入和插入/更新按钮合并为紧凑操作区，导入/导出/保存/管理动作改为右侧 2×2 次级按钮，并修复色块换行和横向滚动条问题。本版同时把颜色管理删除按钮和预览大图关闭按钮改为 SVG 图标，补齐近期上传、短屏布局和预览交互的细节修复。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.3.5.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.3.5/ilab-gpt-conjure_windows_portable_x64_0.3.5.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.3.5/ilab-gpt-conjure_windows_portable_x64_0.3.5.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.3.5.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.3.5/ilab-gpt-conjure_macos_portable_arm64_0.3.5.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.3.5/ilab-gpt-conjure_macos_portable_arm64_0.3.5.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.3.5.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.3.5/ilab-gpt-conjure_macos_portable_x64_0.3.5.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.3.5/ilab-gpt-conjure_macos_portable_x64_0.3.5.zip.sha256.txt) |

使用方式：

1. 下载对应平台的 zip。
2. 解压到普通用户目录，不要放在系统保护目录。
3. Windows 双击 `Start WebUI Portable.bat`；macOS 双击
   `Start WebUI Portable.command`。
4. 如果浏览器没有自动打开，访问 `http://127.0.0.1:8787/`。

启动脚本会短暂检测最新 GitHub Release；发现新版本时只显示提醒，不会自动更新。
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
