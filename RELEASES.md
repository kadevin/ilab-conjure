# 下载 / Releases

当前正式版本：[v0.9.6](https://github.com/kadevin/ilab-conjure/releases/tag/v0.9.6)

## 版本说明

当前版本：`v0.9.6`。本版集中修复多图参考顺序、网络连接重试、批量生成与任务恢复，并完善历史图片操作和输出设置体验。建议使用多图参考、批量生成、失败重试或历史任务恢复的用户升级。

受影响平台：macOS 与 Windows 的标准版和 portable 一键包，以及桌面和手机 WebUI。

必要操作与数据迁移：升级前退出旧实例，升级后重启应用并刷新已打开的页面。无需手动迁移本地任务、图片或设置，旧任务继续兼容；Windows 标准 ZIP 仍需手动替换应用文件。

本版详情：

### P1 · 重要

#### 安全与必须操作

- **加强任务错误信息的隐私保护。** 任务和单张图片的错误信息统一脱敏；执行期间更换密钥后，原请求凭据仍受到保护。

#### 修复

- **多图参考始终按参考栏顺序使用。** 修复新上传、最近上传和图库图片混用时被按来源重新排序的问题。替换图片、删除后添加图片、同步图库提示词、提交生成或编辑，以及重新选择历史任务时，均保持同一顺序。
- **图库引用编号与实际图片对应。** 修复参考图去重后提示词编号错位的问题；重试不会重复追加引用说明，重复上传保留首次出现的文件名，旧任务和图库引用继续兼容。
- **连接建立失败可以自动有限重试。** 补齐包括 `All connection attempts failed` 在内的连接错误处理，按网络设置重试当前请求。图片下载、独立 DNS 查询和跳转目标连接失败时，不会因此重复提交生图；取消和超时能够停止重试。
- **恢复任务时保留已成功图片。** 取消后的任务可以重试失败图片，不重复生成已完成结果。接受已有结果时保留筛选状态、图片属性和正确缩略图，已删除图片不会重新出现。
- **批量生成只补齐剩余图片。** 修复 Gemini 等批量通道重试时多次提交整批请求的问题，按实际剩余数量补图，并正确处理批量请求的取消与超时。
- **任务操作不再覆盖较新的状态。** 修复删除等待任务与队列启动、筛选与删除输出、重试与接受结果之间的并发冲突，避免误操作正在执行的任务或丢失最新选择。
- **备份恢复保持图片对应关系。** 修复部分成功任务恢复后输出位置、筛选状态或参考图顺序错位的问题，恢复后仍可按原位置处理剩余图片。

### P2 · 常规

#### 变更与优化

- **参考文件可以保留后再切换通道。** 当前通道不支持参考文件时保留已添加输入，并提供兼容的 Responses 通道选择，减少重新上传操作。
- **历史图片操作更明确。** 筛选图片后仍可删除整个任务；只选中一张图片时可以直接下载，单张结果减少重复操作入口。
- **恢复输入与处理错误更易理解。** 明确“恢复输入”仅恢复提示词和参考输入，生成参数保持当前选择。失败任务优先显示恢复操作，详细错误按需展开，手机端可直接返回输入区修改。

#### 修复

- **历史参数与当前输出设置保持区分。** 浏览历史任务不会覆盖当前输出设置；明确采用历史参数后，锁定、恢复和解锁均保留所采用的值。
- **失败恢复入口与实际原因匹配。** 根据认证、额度、输入和临时故障提供相应操作；诊断信息中的普通数字不再导致重试入口被误隐藏。
- **Codex URL 图片下载使用正确认证。** 修复 Codex 返回图片地址时的下载异常，同源下载需要认证时使用正确的 OAuth 凭据，外部图片域名不会收到这些凭据。

### P3 · 低影响

#### 修复

- **输出设置控件与说明文字对齐。** 主模型与提示词处理控件底边对齐，切换非 Responses 供应商后的说明文字也保持对齐。
- **下拉组件描边保持稳定。** 移除悬停、展开和聚焦时突兀的高亮加粗描边，保留键盘操作能力。
- **历史详情的焦点行为更可靠。** 修复异步加载和窄屏切换时的焦点及背景交互状态，改善键盘浏览体验。

#### 兼容性/安装/打包/更新

- **离线应用缓存与本版界面同步。** 更新生成页、历史页和样式的资源版本，避免升级后继续使用旧界面缓存。

#### 工程与文档

- 补充多图顺序、任务恢复、批量请求、网络重试、取消和下载安全的关联回归，并同步中英文使用说明与设计合同。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-0.9.6.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.6/iLab-GPT-CONJURE-macos-arm64-0.9.6.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.6/iLab-GPT-CONJURE-macos-arm64-0.9.6.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-0.9.6.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.6/iLab-GPT-CONJURE-macos-x64-0.9.6.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.6/iLab-GPT-CONJURE-macos-x64-0.9.6.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_0.9.6.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.6/iLab-GPT-CONJURE-windows-x64_0.9.6.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.6/iLab-GPT-CONJURE-windows-x64_0.9.6.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.9.6.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.6/ilab-gpt-conjure_windows_portable_x64_0.9.6.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.6/ilab-gpt-conjure_windows_portable_x64_0.9.6.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.9.6.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.6/ilab-gpt-conjure_macos_portable_arm64_0.9.6.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.6/ilab-gpt-conjure_macos_portable_arm64_0.9.6.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.9.6.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.6/ilab-gpt-conjure_macos_portable_x64_0.9.6.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.6/ilab-gpt-conjure_macos_portable_x64_0.9.6.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.6/latest.json)

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
