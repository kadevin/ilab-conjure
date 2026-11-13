# 下载 / Releases

当前正式版本：[v1.1.1](https://github.com/kadevin/ilab-conjure/releases/tag/v1.1.1)

## 版本说明

### v1.1.1

本版修复三项 WebUI 问题，涉及多行提示词、任务删除和最近参考图。建议遇到这些问题的 v1.1.0 用户升级。修复适用于 macOS、Windows 标准版与便携版的 WebUI。

升级前等待任务结束并退出旧实例，升级后重启应用并刷新页面。现有任务、图片和设置无需迁移。Windows 标准 ZIP 需手动替换应用文件。

### P1 · 重要

#### 修复

- **修复多行提示词的 `@` 图片引用。** 提示词同时包含换行和图片引用时，现在可以正常提交生成或编辑任务。感谢 [PR #53](https://github.com/kadevin/ilab-conjure/pull/53) 的贡献。

### P2 · 常规

#### 修复

- **右键删除任务直接打开确认。** 在左侧任务卡片的右键菜单选择「删除」，即可打开永久删除确认。取消后键盘焦点回到原任务卡片。删除请求进行中，同一任务只会提交一次。
- **最近参考图换序时保持缩略图可见。** 上传新参考图或复用靠后的最近参考图并点击生成后，列表会等可见缩略图就绪再换序，同时保留横向滚动位置。刷新超时时会保留旧列表并提供重试。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-1.1.1.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.1/iLab-GPT-CONJURE-macos-arm64-1.1.1.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.1/iLab-GPT-CONJURE-macos-arm64-1.1.1.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-1.1.1.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.1/iLab-GPT-CONJURE-macos-x64-1.1.1.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.1/iLab-GPT-CONJURE-macos-x64-1.1.1.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_1.1.1.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.1/iLab-GPT-CONJURE-windows-x64_1.1.1.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.1/iLab-GPT-CONJURE-windows-x64_1.1.1.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_1.1.1.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.1/ilab-gpt-conjure_windows_portable_x64_1.1.1.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.1/ilab-gpt-conjure_windows_portable_x64_1.1.1.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_1.1.1.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.1/ilab-gpt-conjure_macos_portable_arm64_1.1.1.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.1/ilab-gpt-conjure_macos_portable_arm64_1.1.1.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_1.1.1.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.1/ilab-gpt-conjure_macos_portable_x64_1.1.1.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.1/ilab-gpt-conjure_macos_portable_x64_1.1.1.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.1/latest.json)

使用方式：

1. 下载对应平台的 zip。
2. 解压到普通用户目录，不要放在系统保护目录。
3. Windows 双击 `Start iLab GPT CONJURE.exe`；macOS 双击
   `Start iLab GPT CONJURE.app`。旧的 `Start WebUI Portable.bat` /
   `Start WebUI Portable.command` 仍保留，用于终端调试。
4. 如果浏览器没有自动打开，访问 `http://127.0.0.1:8787/`。

一键包启动器不会后台自动访问 GitHub。更新已经解压的一键包时，可在托盘 / 菜单栏
菜单选择检查更新，并在发现新版本后确认 `安装更新`；也可以退出启动器后手动运行
Windows 的 `Update WebUI Portable.bat` 或 macOS 的 `Update WebUI Portable.command`。
更新脚本会读取带签名的 `latest.json`
manifest，先用启动器内置公钥校验 Ed25519 签名，再下载当前平台对应的最新
GitHub Release 资产，执行前显示所选资产和 manifest SHA256，校验下载 zip 的
SHA256，只替换一键包目录内由程序管理的文件，保留本地 `data/`，并把被替换文件备份到 `.backup/`。

macOS 标准 DMG 和 portable zip 都暂未使用 Apple Developer ID 签名，也未 notarize。如果 macOS
拦截启动，可以右键或 Control-click App，选择 Open，并在系统安全提示中再次确认。
portable zip 也可以对解压目录执行：

```bash
xattr -dr com.apple.quarantine /path/to/ilab-gpt-conjure_macos_portable_arm64
# 或：
xattr -dr com.apple.quarantine /path/to/ilab-gpt-conjure_macos_portable_x64
```

一键包内的 `data/` 目录会保存本地设置、公用图库、输入图、输出图、任务数据库和日志。
不要把这些本地数据、API key 或 OAuth 文件提交到 Git。
