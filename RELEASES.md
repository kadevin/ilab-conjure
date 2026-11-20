# 下载 / Releases

正式版本见 [GitHub 最新正式版](https://github.com/kadevin/ilab-conjure/releases/latest)。下方 v1.2.1 下载链接在该版本发布后生效。

## 版本说明

### v1.2.1

本补丁版修复 OpenAI 官方项目使用 GPT Image 2.6 生成和编辑 SVG 时的模型兼容性。建议遇到 `svg.model` 缺失或绘制模型权限错误的 v1.2.0 用户升级。适用于 macOS 和 Windows 的标准版及便携版。

升级前等待任务结束并退出旧实例，升级后重新打开应用。现有任务、图片和设置无需迁移。Windows 标准 ZIP 仍需手动替换应用文件。

### P2 · 常规

#### 新增

- **每个官方 OpenAI 连接可指定 SVG 绘制模型。** 在生成页或历史库打开「API 设置 → 编辑供应商」，填写 OpenAI 项目允许的模型 ID。留空时使用 `gpt-6-luna`。

#### 修复

- **官方项目要求 `svg.model` 时自动补参。** 纯提示词和参考图编辑均支持，官方地址显式填写 `:443` 也能工作。感谢 [PR #58](https://github.com/kadevin/ilab-conjure/pull/58) 的贡献。
- **批量 SVG 避免重复探测。** 同一任务首次补参成功后复用绘制模型，其余图片可直接生成，带参考图的任务也会减少重复上传。
- **绘制模型权限错误提供恢复入口。** 官方项目拒绝所选模型时，任务停止自动重试。可从失败预览打开供应商设置，修改模型后手动重试。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-1.2.1.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.1/iLab-GPT-CONJURE-macos-arm64-1.2.1.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.1/iLab-GPT-CONJURE-macos-arm64-1.2.1.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-1.2.1.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.1/iLab-GPT-CONJURE-macos-x64-1.2.1.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.1/iLab-GPT-CONJURE-macos-x64-1.2.1.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_1.2.1.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.1/iLab-GPT-CONJURE-windows-x64_1.2.1.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.1/iLab-GPT-CONJURE-windows-x64_1.2.1.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_1.2.1.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.1/ilab-gpt-conjure_windows_portable_x64_1.2.1.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.1/ilab-gpt-conjure_windows_portable_x64_1.2.1.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_1.2.1.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.1/ilab-gpt-conjure_macos_portable_arm64_1.2.1.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.1/ilab-gpt-conjure_macos_portable_arm64_1.2.1.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_1.2.1.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.1/ilab-gpt-conjure_macos_portable_x64_1.2.1.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.1/ilab-gpt-conjure_macos_portable_x64_1.2.1.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.1/latest.json)

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
