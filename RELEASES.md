# 下载 / Releases

当前正式版本：[v0.1.1](https://github.com/kadevin/ilab-gpt-conjure/releases/tag/v0.1.1)

## 版本说明

当前版本：`v0.1.1`。这个版本提供 Windows x64、macOS Apple Silicon、macOS Intel 三种免安装一键包；下载对应平台的 zip 后解压即可启动本地 WebUI。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.1.1.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.1.1/ilab-gpt-conjure_windows_portable_x64_0.1.1.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.1.1/ilab-gpt-conjure_windows_portable_x64_0.1.1.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.1.1.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.1.1/ilab-gpt-conjure_macos_portable_arm64_0.1.1.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.1.1/ilab-gpt-conjure_macos_portable_arm64_0.1.1.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.1.1.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.1.1/ilab-gpt-conjure_macos_portable_x64_0.1.1.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.1.1/ilab-gpt-conjure_macos_portable_x64_0.1.1.zip.sha256.txt) |

使用方式：

1. 下载对应平台的 zip。
2. 解压到普通用户目录，不要放在系统保护目录。
3. Windows 双击 `Start WebUI Portable.bat`；macOS 双击
   `Start WebUI Portable.command`。
4. 如果浏览器没有自动打开，访问 `http://127.0.0.1:8787/`。

macOS 包是未签名的 portable zip，不是已签名 `.app` 或 notarized DMG。
如果 macOS 拦截启动脚本，可以右键或 Control-click
`Start WebUI Portable.command`，选择 Open，并在系统安全提示中再次确认。
也可以对解压目录执行：

```bash
xattr -dr com.apple.quarantine /path/to/ilab-gpt-conjure_macos_portable_arm64
# 或：
xattr -dr com.apple.quarantine /path/to/ilab-gpt-conjure_macos_portable_x64
```

一键包内的 `data/` 目录会保存本地设置、公用图库、输入图、输出图、任务数据库和日志。
不要把这些本地数据、API key 或 OAuth 文件提交到 Git。

## Portable Packages

Current release: [v0.1.1](https://github.com/kadevin/ilab-gpt-conjure/releases/tag/v0.1.1)

| Platform | Device | Download | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.1.1.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.1.1/ilab-gpt-conjure_windows_portable_x64_0.1.1.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.1.1/ilab-gpt-conjure_windows_portable_x64_0.1.1.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.1.1.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.1.1/ilab-gpt-conjure_macos_portable_arm64_0.1.1.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.1.1/ilab-gpt-conjure_macos_portable_arm64_0.1.1.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.1.1.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.1.1/ilab-gpt-conjure_macos_portable_x64_0.1.1.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.1.1/ilab-gpt-conjure_macos_portable_x64_0.1.1.zip.sha256.txt) |

macOS packages are unsigned portable zips, not signed `.app` bundles or notarized
DMGs. Use Open from the context menu, or remove quarantine from the extracted
folder if macOS blocks the launcher.
