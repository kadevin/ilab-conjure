# 下载 / Releases

当前正式版本：[v0.8.2](https://github.com/kadevin/ilab-conjure/releases/tag/v0.8.2)

## 版本说明

当前版本：`v0.8.2`。这是面向长耗时中转站和紧凑桌面布局的可靠性更新。建议遇到生图超过 10 分钟、瞬时网络失败，或“最近上传”溢出“参考输入”卡片的用户更新；其他 `v0.8.1` 用户可以按需升级。

受影响平台：macOS 与 Windows 的标准版和 portable 一键包。升级前请退出旧实例；Windows 标准版仍需手动解压替换，portable 可使用现有更新入口，支持更新助手的 macOS 标准版可按界面提示更新。

必要操作与数据迁移：无需迁移或重置数据。已有设置、任务数据库、历史图库、输入图和输出图会保留；新设置只影响后续开始执行的任务。

本版重点：系统设置新增全局单次生图超时和失败后重试控制，并修复短高度桌面布局中“最近上传”缩略图与删除按钮溢出的问题。

本版详情：

### P1 · 重要

#### 新增

- 可在“系统设置 → 网络”把单次生图请求超时设置为 `1–30` 分钟，默认仍为 `10` 分钟，避免响应较慢的兼容中转站被固定十分钟上限提前终止。
- 可独立设置可重试瞬时失败后的额外重试次数为 `0–5` 次，默认仍为 `2` 次；永久性请求错误不会因此重复发送。
- 超时与重试策略统一覆盖所有供应商的生成和编辑，并在任务开始执行时冻结；运行中修改不会改变该任务，每次自动重试都会获得新的完整超时窗口，原有队列级通道故障转移保持不变。
- 连接检测继续使用独立的 `10` 秒上限且不执行自动重试，避免网络检测被生图策略意外延长。

### P2 · 常规

#### 修复

- 修复短高度桌面布局中“最近上传”缩略图和删除按钮溢出“参考输入”卡片的问题；更新后缩略图会按底部可用高度收缩，触控删除目标和横向滚动仍然可用。

#### 兼容性/安装/打包/更新

- 默认值仍为单次请求 `10` 分钟、失败后重试 `2` 次；已有正数 `CODEX_IMAGE_REQUEST_TIMEOUT_SECONDS` 环境变量会继续生效，直到用户在界面中显式保存超时设置。
- 本版不新增依赖或数据库迁移。旧版本会忽略新增的本地请求策略字段；如需回退，无需转换已有任务与图片数据。

#### 已知问题

- macOS 标准 DMG 和 portable zip 仍未签名、未 notarize；如果系统拦截启动，请按下方说明使用右键或 Control-click 打开。Windows 标准 ZIP 仍需手动替换程序文件。

### P3 · 低影响

#### 工程与文档

- 同步全部 `14` 种界面语言的请求策略文案、用户文档和设计合同，并补充前后端、队列、缓存资源、响应式布局与无障碍自动验证；发布工作流会把升级建议、受影响平台和数据迁移信息完整带入 GitHub Release 正文。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-0.8.2.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.2/iLab-GPT-CONJURE-macos-arm64-0.8.2.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.2/iLab-GPT-CONJURE-macos-arm64-0.8.2.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-0.8.2.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.2/iLab-GPT-CONJURE-macos-x64-0.8.2.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.2/iLab-GPT-CONJURE-macos-x64-0.8.2.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_0.8.2.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.2/iLab-GPT-CONJURE-windows-x64_0.8.2.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.2/iLab-GPT-CONJURE-windows-x64_0.8.2.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.8.2.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.2/ilab-gpt-conjure_windows_portable_x64_0.8.2.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.2/ilab-gpt-conjure_windows_portable_x64_0.8.2.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.8.2.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.2/ilab-gpt-conjure_macos_portable_arm64_0.8.2.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.2/ilab-gpt-conjure_macos_portable_arm64_0.8.2.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.8.2.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.2/ilab-gpt-conjure_macos_portable_x64_0.8.2.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.2/ilab-gpt-conjure_macos_portable_x64_0.8.2.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.2/latest.json)

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
