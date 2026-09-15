# 下载 / Releases

当前正式版本：[v0.9.1](https://github.com/kadevin/ilab-conjure/releases/tag/v0.9.1)

## 版本说明

当前版本：`v0.9.1`。这是一次稳定性修复更新，重点解决 GPT Image 2 与 2.5 切换时的供应商、历史参数和模板兼容问题，并修复任务状态不一致与草稿误提醒。建议使用 GPT Image 2.5，或遇到供应商切换、历史参数恢复和队列显示异常的用户升级。

受影响平台：macOS 与 Windows 的标准版和 portable 一键包；本次 WebUI 修复适用于桌面和手机浏览器。

必要操作与数据迁移：升级前退出旧实例，升级后刷新已经打开的页面以加载新界面。无需数据库迁移或手动搬迁任务、图库、图片与设置；既有任务记录保留原始型号和生成配置。Codex 内置通道继续使用 GPT Image 2。

本版详情：

### P1 · 重要

#### 修复

- **修复供应商修改型号后保存失败、表单退回 Image 2 的问题。** 保存时正确维护各型号的默认供应商；保存失败时保留本次编辑内容，方便修改后重试。
- **修复修改供应商型号后，顶部供应商自动切走或原供应商从列表消失的问题。** 当前绑定从 Image 2 改为可用的 2.5 型号后，页面继续使用该供应商并沿用合法的共享参数；刷新或重新打开页面后也能恢复正确选择。
- **修复任务卡显示排队、预览却显示正在生成的状态矛盾。** 队列刷新与实时更新统一同步任务卡和预览，较晚返回的旧状态不会覆盖更新状态；快速完成或失败的任务也能及时更新。
- **修复选择另一 GPT 版本的历史任务后，输出设置突然变成通用参数表单的问题。** 未锁定时继续使用熟悉的 GPT 参数编辑器；锁定时保留只读摘要，查看历史任务不会切换当前供应商和型号。
- **修复锁定参数后点击“使用此任务参数”会把当前 2.5 切回历史 Image 2 配置的问题。** GPT 系列之间采纳历史参数时，保留当前型号、供应商与协议，只恢复共享输出参数。
- **修复从 Gemini 采纳 GPT 历史参数时，质量与数量恢复不完整的问题。** 例如历史任务为“高质量、3 张”时，参数草稿、按钮选中态、生成摘要与实际提交值保持一致。

### P2 · 常规

#### 修复

- **修复任务已成功提交，刷新页面仍提示草稿未保存的问题。** 成功提交的提示词与参考输入不再被当作未提交草稿；提交期间新增的编辑内容仍受保护。
- **修复提交失败、尚未形成生成快照的任务被误识别为 Image 2 的问题。** 任务查看与参数恢复优先使用请求中保存的规范型号、供应商绑定和参数，继续兼容旧格式历史任务。
- **修复本地提交失败的任务仍计入“等待中”的问题。** 失败任务进入对应历史时间分组，保留错误与请求信息；取消中的任务继续显示在运行分区。
- **修复新建模板总是标为 Image 2，以及编辑时覆盖原型号的问题。** 新模板记录当前图像型号，已有模板编辑后保留原型号；后端同步支持目录中的 GPT Image 2.5 与 Gemini 型号标识。
- **修复模板导入导出丢失型号的问题。** 模板包保留已知型号，同名同内容但型号不同的模板不会被误判为重复；没有型号标识的旧模板与社区模板继续按原有规则导入。

### P3 · 低影响

#### 工程与文档

- 补充供应商保存与刷新恢复、GPT 版本切换、跨系列历史参数采纳、任务状态同步、草稿保护和模板导入导出的回归验证，并更新对应交互说明。

### 已知问题与使用提示 · P2

- GPT Image 2.5 需要供应商实际支持，并配置正确的远端模型名。若通道不支持所请求型号，仍可能返回 `model_not_found`；界面兼容性修复不会改变上游通道的支持范围。
- 带有生成快照的历史任务在“仅重试失败图片”时继续沿用原任务的型号与配置。如果希望改用当前 2.5 供应商生成，应先采纳历史参数，再点击“开始生成”。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-0.9.1.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.1/iLab-GPT-CONJURE-macos-arm64-0.9.1.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.1/iLab-GPT-CONJURE-macos-arm64-0.9.1.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-0.9.1.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.1/iLab-GPT-CONJURE-macos-x64-0.9.1.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.1/iLab-GPT-CONJURE-macos-x64-0.9.1.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_0.9.1.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.1/iLab-GPT-CONJURE-windows-x64_0.9.1.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.1/iLab-GPT-CONJURE-windows-x64_0.9.1.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.9.1.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.1/ilab-gpt-conjure_windows_portable_x64_0.9.1.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.1/ilab-gpt-conjure_windows_portable_x64_0.9.1.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.9.1.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.1/ilab-gpt-conjure_macos_portable_arm64_0.9.1.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.1/ilab-gpt-conjure_macos_portable_arm64_0.9.1.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.9.1.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.1/ilab-gpt-conjure_macos_portable_x64_0.9.1.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.1/ilab-gpt-conjure_macos_portable_x64_0.9.1.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.1/latest.json)

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
