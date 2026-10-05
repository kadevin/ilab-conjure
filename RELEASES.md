# 下载 / Releases

当前正式版本：[v0.9.5](https://github.com/kadevin/ilab-conjure/releases/tag/v0.9.5)

## 版本说明

当前版本：`v0.9.5`。本版更新主模型选项与默认值，整理输出设置布局，并修复尺寸切换和紧凑窗口中的显示问题。建议经常调整输出参数、使用键盘操作或在窄屏工作台生成图片的用户升级。

受影响平台：macOS 与 Windows 的标准版和 portable 一键包，以及桌面和手机 WebUI。

必要操作与数据迁移：升级前退出旧实例，升级后重启应用并刷新已打开的页面。无需迁移本地任务、图片或设置。未保存主模型选择时默认使用 GPT 6 Luna，已有保存值和自定义模型输入继续保留；Windows 标准 ZIP 仍需手动替换应用文件。

本版详情：

### P2 · 常规

#### 变更与优化

- **更新主模型选项与默认值。** 新增 GPT 6.1 SOL、GPT 6 SOL 和 GPT 6 Luna，默认主模型改为 GPT 6 Luna；内置候选列表移除 GPT 5.5、5.4、5.4 mini、5.3 Codex 和 5.2，保留自定义模型输入及已有选择。
- **透明背景与输出格式就近设置。** 透明开关移到输出格式标签旁。选择 JPEG 时显示“不支持透明”并关闭透明输出，当前页面切回 PNG 或 WebP 时恢复最近的透明偏好；用户主动关闭后保持关闭。
- **输出选项支持完整的键盘单选操作。** Tab 进入每组当前选项，方向键在可用选项之间循环切换。JPEG 和 WebP 的压缩率增加可聚焦的图标入口，保留双击格式按钮的方式；Escape 关闭浮层并返回入口。

#### 修复

- **尺寸模式切换保持等高。** 预设和自定义尺寸共用同一编辑区域，输入校验错误、手机布局及窗口变化时，下方控件的位置保持稳定；隐藏的尺寸控件不再参与键盘导航。
- **公用库底部完整显示。** 修复紧凑桌面窗口下分类按钮和空状态边框被截断的问题，保持管理按钮完整可见。

### P3 · 低影响

#### 变更与优化

- **输出设置更易扫描。** 主模型与提示词处理在桌面并排，联网搜索紧邻主模型标签；通过字段标签、间距和轻量分隔线组织选项，减少重复分组标题。质量与数量保持并排，比例保留方图跨两行及竖横配对布局。
- **手机参数面板减少重复标题。** 锁定入口合并到面板标题栏，保留原有锁定摘要和解锁操作。

#### 修复

- **输出像素提示与控件描边保持一致。** 输出像素文字水平、垂直居中；主模型默认描边与相邻选项保持相同视觉强度，悬停和键盘聚焦时提供清晰强调。

#### 兼容性/安装/打包/更新

- **离线应用缓存与本版界面同步。** 更新生成页、历史页和样式的资源版本，避免升级后继续使用旧界面缓存。

#### 工程与文档

- 补充格式与透明背景联动、方向键操作、尺寸区域等高和公用库布局的回归检查，并同步中英文使用说明与设计合同。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-0.9.5.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.5/iLab-GPT-CONJURE-macos-arm64-0.9.5.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.5/iLab-GPT-CONJURE-macos-arm64-0.9.5.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-0.9.5.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.5/iLab-GPT-CONJURE-macos-x64-0.9.5.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.5/iLab-GPT-CONJURE-macos-x64-0.9.5.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_0.9.5.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.5/iLab-GPT-CONJURE-windows-x64_0.9.5.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.5/iLab-GPT-CONJURE-windows-x64_0.9.5.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.9.5.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.5/ilab-gpt-conjure_windows_portable_x64_0.9.5.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.5/ilab-gpt-conjure_windows_portable_x64_0.9.5.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.9.5.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.5/ilab-gpt-conjure_macos_portable_arm64_0.9.5.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.5/ilab-gpt-conjure_macos_portable_arm64_0.9.5.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.9.5.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.5/ilab-gpt-conjure_macos_portable_x64_0.9.5.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.5/ilab-gpt-conjure_macos_portable_x64_0.9.5.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.5/latest.json)

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
