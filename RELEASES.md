# 下载 / Releases

当前正式版本：[v0.8.3](https://github.com/kadevin/ilab-conjure/releases/tag/v0.8.3)

## 版本说明

当前版本：`v0.8.3`。这是面向任务执行可靠性和高频浏览体验的修复更新。建议遇到提示词 chip 未展开、队列把任务失败误报为通道故障、启动器无法恢复损坏的虚拟环境、搜索栏被浏览器自动填充，或历史大图与侧栏加载出现跳闪的用户更新；其他 `v0.8.2` 用户可以按需升级。

受影响平台：macOS 与 Windows 的标准版和 portable 一键包。升级前请退出旧实例；Windows 标准版仍需手动解压替换，portable 可使用现有更新入口，支持更新助手的 macOS 标准版可按界面提示更新。

必要操作与数据迁移：无需迁移或重置数据。已有设置、任务数据库、历史图库、输入图和输出图会保留，本次更新不会改写既有任务或图片数据。

本版重点：修复任务级生成失败的分类与队列日志语义，恢复提示词 chip 在原始提示模式下的展开，并让任务侧栏分页和历史大图切换在连续浏览时保持无缝稳定。

本版详情：

### P1 · 重要

#### 修复

- 修复普通生成失败被记录为“Queue channel worker failure”的问题；更新后任务错误与真正的通道工作线程故障分别统计和记录，单个任务失败不会污染通道健康状态，队列仍按错误是否可重试执行既有故障转移。
- 修复供应商响应正文、提示词或任务标识中的 `400`、`401`、`403`、`422`、`429` 等数字被误判为 HTTP 状态码的问题；更新后只识别异常的显式状态字段或明确的 HTTP/status 表达，错误类型和重试判断不再被普通文本干扰。
- 修复 macOS 启动脚本遇到虚拟环境 Python 链接损坏时无法自愈的问题；启动器现在会清理并重建该虚拟环境，再继续依赖校验和启动。

### P2 · 常规

#### 修复

- 修复提示词 chip 在“原始提示”模式提交后未展开的问题，并支持相邻 chip 连续展开；chip 仍作为用户编写的宏，不会被当作应用附加提示词。
- 左侧任务列表改为接近组尾时自动加载下一页，并只追加新任务卡；加载中的旧卡、滚动位置和节点保持不变，不再闪一下或整组重绘，失败时才显示可点击的重试入口。
- 修复浏览器刷新后把历史地址或其他自动完成内容注入任务搜索栏的问题；搜索状态现在只接受明确的键盘、粘贴或拖放输入。
- 修复历史大图左右切换动画完成后中央图片再次轻微缩放、阴影闪烁和视口边缘出现细描边的问题；动画与真实图片按最终几何交接，中央收尾只保留一层稳定阴影。

#### 兼容性/安装/打包/更新

- 本版不新增依赖或数据库迁移。已有设置、请求策略、任务数据库和图片数据格式不变；如需回退到 `v0.8.2`，无需转换本地数据。

#### 已知问题

- macOS 标准 DMG 和 portable zip 仍未签名、未 notarize；如果系统拦截启动，请按下方说明使用右键或 Control-click 打开。Windows 标准 ZIP 仍需手动替换程序文件。

### P3 · 低影响

#### 工程与文档

- 同步全部 `14` 种界面的分页失败重试文案、设计合同和缓存版本，并补充提示词、供应商错误分类、队列恢复、启动器、大图交接、浏览器自动填充及侧栏无缝分页的自动验证。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-0.8.3.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.3/iLab-GPT-CONJURE-macos-arm64-0.8.3.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.3/iLab-GPT-CONJURE-macos-arm64-0.8.3.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-0.8.3.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.3/iLab-GPT-CONJURE-macos-x64-0.8.3.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.3/iLab-GPT-CONJURE-macos-x64-0.8.3.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_0.8.3.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.3/iLab-GPT-CONJURE-windows-x64_0.8.3.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.3/iLab-GPT-CONJURE-windows-x64_0.8.3.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.8.3.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.3/ilab-gpt-conjure_windows_portable_x64_0.8.3.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.3/ilab-gpt-conjure_windows_portable_x64_0.8.3.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.8.3.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.3/ilab-gpt-conjure_macos_portable_arm64_0.8.3.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.3/ilab-gpt-conjure_macos_portable_arm64_0.8.3.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.8.3.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.3/ilab-gpt-conjure_macos_portable_x64_0.8.3.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.3/ilab-gpt-conjure_macos_portable_x64_0.8.3.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.3/latest.json)

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
