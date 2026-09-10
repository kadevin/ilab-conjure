# 下载 / Releases

当前正式版本：[v0.8.6](https://github.com/kadevin/ilab-conjure/releases/tag/v0.8.6)

## 版本说明

当前版本：`v0.8.6`。这是一次 GPT Image API 模型支持与生成设置修复更新。建议使用支持 Image 2.5 的 API 中转站，或遇到历史入口消失、方向设置无法切换的用户升级。

受影响平台：macOS 与 Windows 的标准版和 portable 一键包。WebUI 改进适用于全部平台。升级前请退出旧实例；Windows 标准版仍需手动解压替换，portable 和支持更新助手的 macOS 标准版可使用现有更新入口。

必要操作与数据迁移：无需数据库迁移或手动搬迁图片，已有历史、绑定和明确保存的参数继续保留。使用 Image 2.5 时，需要在 API 设置中配置供应商支持的版本及实际远端模型名；不会自动升级已有 Image 2 绑定。默认主模型改为 `gpt-5.6-luna`，已保存的主模型选择不会被覆盖；需要使用新默认值的用户可手动切换。

本版重点：API 中转站支持 GPT Image 2.5 Flare、Sunburst，复用 GPT Image 参数面板；切换绑定型号时默认模型名自动跟随；修复历史入口与输出方向设置。

本版详情：

### P1 · 重要

#### 新增

- API 模型绑定新增 GPT Image 2.5 Flare 和 Sunburst，支持 Images、Responses 协议及自定义远端模型名。各版本共用 GPT Image 输出参数，配置多个版本后可在生成页通过紧凑下拉框切换，历史任务保留所选版本、供应商及远端模型名。

### P2 · 常规

#### 变更与优化

- Responses 通道的默认主模型改为 GPT-5.6 Luna（`gpt-5.6-luna`），适用于未指定主模型的新请求与默认设置；已有明确选择和历史参数继续保留。Images 直连通道不使用主模型。

#### 修复

- 修复最近 7 天没有已结束任务、仅有进行中任务或搜索时，桌面侧栏完整历史库入口消失的问题；入口保持可访问。
- 修复输出设置中方向切换不生效的问题；切换横图、竖图和方形时，比例与像素尺寸正确联动。
- 修复 API 设置切换绑定型号后仍沿用旧默认模型名的问题。名称为空或仍为上一个型号的默认值时自动更新，用户填写的自定义中转站名称保留，连续切换也能正确跟随。

#### 兼容性/安装/打包/更新

- 不新增运行时依赖或数据库结构迁移；既有 Image 2、Gemini 绑定和历史数据继续兼容。Codex 内置通道仍保留现有 Image 2 绑定，Image 2.5 支持在本版通过 API 供应商配置使用。

#### 已知问题

- Image 2.5 的实际可用性和远端模型名取决于 API 供应商。本版已验证请求构造及界面流程，未对所有中转站进行真实生成验证。
- macOS 标准 DMG 和 portable zip 仍未签名、未 notarize；如果系统拦截启动，请按下方说明使用右键或 Control-click 打开。Windows 标准 ZIP 仍需手动替换程序文件。

### P3 · 低影响

#### 工程与文档

- 补充模型绑定、共享参数、历史入口和方向切换的回归验证，更新用户文档及前端缓存版本。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-0.8.6.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.6/iLab-GPT-CONJURE-macos-arm64-0.8.6.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.6/iLab-GPT-CONJURE-macos-arm64-0.8.6.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-0.8.6.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.6/iLab-GPT-CONJURE-macos-x64-0.8.6.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.6/iLab-GPT-CONJURE-macos-x64-0.8.6.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_0.8.6.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.6/iLab-GPT-CONJURE-windows-x64_0.8.6.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.6/iLab-GPT-CONJURE-windows-x64_0.8.6.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.8.6.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.6/ilab-gpt-conjure_windows_portable_x64_0.8.6.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.6/ilab-gpt-conjure_windows_portable_x64_0.8.6.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.8.6.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.6/ilab-gpt-conjure_macos_portable_arm64_0.8.6.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.6/ilab-gpt-conjure_macos_portable_arm64_0.8.6.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.8.6.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.6/ilab-gpt-conjure_macos_portable_x64_0.8.6.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.6/ilab-gpt-conjure_macos_portable_x64_0.8.6.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.6/latest.json)

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

macOS 标准 DMG 和 portable zip 都暂未签名、未 notarize。如果 macOS
拦截启动，可以右键或 Control-click App，选择 Open，并在系统安全提示中再次确认。
portable zip 也可以对解压目录执行：

```bash
xattr -dr com.apple.quarantine /path/to/ilab-gpt-conjure_macos_portable_arm64
# 或：
xattr -dr com.apple.quarantine /path/to/ilab-gpt-conjure_macos_portable_x64
```

一键包内的 `data/` 目录会保存本地设置、公用图库、输入图、输出图、任务数据库和日志。
不要把这些本地数据、API key 或 OAuth 文件提交到 Git。
