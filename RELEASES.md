# 下载 / Releases

当前正式版本：[v0.8.5](https://github.com/kadevin/ilab-conjure/releases/tag/v0.8.5)

## 版本说明

当前版本：`v0.8.5`。这是一次存储路径兼容与生成界面更新。建议使用自定义目录、从 portable 迁入 macOS 标准版，或在手机及竖屏窗口中使用 WebUI 的用户升级；需要 GPT-6 Astra 主模型选项的用户也可更新。

受影响平台：macOS 与 Windows 的标准版和 portable 一键包。存储路径启动修复主要影响 macOS 标准版，其余 WebUI 改进适用于全部平台。升级前请退出旧实例；Windows 标准版仍需手动解压替换，portable 和支持更新助手的 macOS 标准版可使用现有更新入口。

必要操作与数据迁移：通常无需手动搬迁或重置数据，已有任务历史、输入图与输出图会保留。对于有可信 portable 复制迁移记录的标准版数据目录，首次启动会将配置中指向旧 portable 内部的路径一次性修正为已复制的新目录，并先备份原设置；外部自定义路径和旧源文件保留。本次修复不再次搬迁文件。手动修改存储目录仍需重启生效，且不会自动复制原目录中的文件。

本版重点：macOS 标准版启动时保留已保存的存储目录；Responses 通道可选 GPT-6 Astra；新任务提示词处理默认“自动”；修复竖屏下公用图库、提示词和生成按钮重叠等布局问题。

本版详情：

### P1 · 重要

#### 修复

- macOS 标准版启动时会读取并保留已保存的输入、输出、公用图库和任务数据目录，修复自定义路径被默认值覆盖、已有历史看似消失的问题。

#### 兼容性/安装/打包/更新

- 从 portable 复制数据到标准版后，原配置中的内部路径会依据迁移记录一次性修正，已经完成复制的旧安装也能补齐此修复。外部自定义目录不会被改写，原配置会备份到数据目录内的 `.migration/webui-settings-before-path-rebase.json`，旧 portable 数据继续保留。

### P2 · 常规

#### 新增

- Responses 通道的主模型列表新增 GPT-6 Astra（`gpt-6-astra`），支持搜索、选择与保存；实际可用性取决于所用账号或供应商的模型支持，默认主模型仍为 `gpt-5.4-mini`。

#### 变更与优化

- 新任务和未锁定参数重置后的提示词处理默认改为“自动”，API 请求省略该选项时也采用自动模式。明确选择的“原始”“保真”、已锁定参数和历史任务中的设置继续保留。

#### 修复

- 修复手机和竖屏窄窗口中公用图库撑出参考图面板、覆盖提示词与生成按钮的问题；面板会随内容自然展开，生成按钮可正常点击。
- 修复窄屏 API 直连说明与设置按钮重叠的问题，相关控件在空间不足时分行排列。
- 修复窄屏自定义像素与比例输入框被裁切的问题，输入框随可用空间缩放。
- 修复紧凑页头把状态信息挤出屏幕的问题；新任务按钮收为图标并保留可访问名称。
- 存储设置在当前路径与仍存在的原默认目录不同时提供“查看原默认目录”提示，方便定位旧数据，并明确说明改路径不会自动搬迁文件。

#### 兼容性/安装/打包/更新

- 不新增运行时依赖或数据库结构迁移，既有任务与图片格式保持兼容；存储路径修正仅在可信复制迁移记录下执行一次。

#### 已知问题

- macOS 标准 DMG 和 portable zip 仍未签名、未 notarize；如果系统拦截启动，请按下方说明使用右键或 Control-click 打开。Windows 标准 ZIP 仍需手动替换程序文件。

### P3 · 低影响

#### 工程与文档

- 补充存储路径兼容、主模型选择、提示词默认值和响应式布局的回归验证，同步用户文档、设计合同及前端缓存版本。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-0.8.5.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.5/iLab-GPT-CONJURE-macos-arm64-0.8.5.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.5/iLab-GPT-CONJURE-macos-arm64-0.8.5.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-0.8.5.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.5/iLab-GPT-CONJURE-macos-x64-0.8.5.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.5/iLab-GPT-CONJURE-macos-x64-0.8.5.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_0.8.5.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.5/iLab-GPT-CONJURE-windows-x64_0.8.5.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.5/iLab-GPT-CONJURE-windows-x64_0.8.5.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.8.5.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.5/ilab-gpt-conjure_windows_portable_x64_0.8.5.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.5/ilab-gpt-conjure_windows_portable_x64_0.8.5.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.8.5.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.5/ilab-gpt-conjure_macos_portable_arm64_0.8.5.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.5/ilab-gpt-conjure_macos_portable_arm64_0.8.5.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.8.5.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.5/ilab-gpt-conjure_macos_portable_x64_0.8.5.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.5/ilab-gpt-conjure_macos_portable_x64_0.8.5.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.5/latest.json)

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
