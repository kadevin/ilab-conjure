# 下载 / Releases

当前正式版本：[v0.9.3](https://github.com/kadevin/ilab-conjure/releases/tag/v0.9.3)

## 版本说明

当前版本：`v0.9.3`。本版改善高分辨率参考图在“最近上传”、本地导入和草稿恢复时的显示性能，修复部分 Windows 设备上 GPT 与 Gemini 模型切换图标破损，并更新存在已知安全问题的运行时组件。建议所有用户升级，尤其是经常使用多张大图或遇到图标异常的用户。

受影响平台：macOS 与 Windows 的标准版和 portable 一键包；WebUI 图片性能改进也适用于桌面和手机浏览器。图标修复主要针对 Windows 的 SVG 类型识别。

必要操作与数据迁移：升级前退出旧实例，升级后重启应用并刷新已打开的页面。无需迁移本地任务或图片；旧“最近上传”图片在首次显示时按需生成小图，不会在升级时一次性处理。Windows 标准 ZIP 仍需手动替换应用文件。

本版详情：

### P1 · 重要

#### 安全与必须操作

- **更新底层异步运行组件。** 升级存在已知安全问题的锁定依赖，降低相关风险；升级无需重新配置。

#### 变更与优化

- **“最近上传”改用小尺寸预览图。** 多张 4K 参考图不再作为列表图片反复加载和解码；选入输入栏后也显示小图。原图仍用于编辑和生成，不降低提交质量。已有图片首次显示时会按需生成预览图，后续复用。
- **本地导入与草稿恢复改用小尺寸预览图。** 连续导入多张高分辨率静态图片时，输入栏逐张生成并复用小图；恢复草稿直接显示已生成的小图，避免再次同时解码多张原图。原始文件继续用于编辑和生成，首次导入时小图可能逐张出现。

### P2 · 常规

#### 兼容性/安装/打包/更新

- **修复 GPT 与 Gemini 模型切换图标破损。** 在部分 Windows 设备将 SVG 错误识别为文本或二进制内容时，应用现在明确以 SVG 图片类型提供图标，避免无法显示。

#### 已知问题

- 大尺寸 GIF 动图仍使用原始动态预览，连续导入时可能出现短暂停顿。

### P3 · 低影响

#### 工程与文档

- 补充最近上传和本地导入的缩略图生成、草稿恢复、静态资源缓存版本、SVG 文件类型和依赖锁定的回归验证。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-0.9.3.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.3/iLab-GPT-CONJURE-macos-arm64-0.9.3.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.3/iLab-GPT-CONJURE-macos-arm64-0.9.3.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-0.9.3.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.3/iLab-GPT-CONJURE-macos-x64-0.9.3.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.3/iLab-GPT-CONJURE-macos-x64-0.9.3.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_0.9.3.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.3/iLab-GPT-CONJURE-windows-x64_0.9.3.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.3/iLab-GPT-CONJURE-windows-x64_0.9.3.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.9.3.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.3/ilab-gpt-conjure_windows_portable_x64_0.9.3.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.3/ilab-gpt-conjure_windows_portable_x64_0.9.3.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.9.3.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.3/ilab-gpt-conjure_macos_portable_arm64_0.9.3.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.3/ilab-gpt-conjure_macos_portable_arm64_0.9.3.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.9.3.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.3/ilab-gpt-conjure_macos_portable_x64_0.9.3.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.3/ilab-gpt-conjure_macos_portable_x64_0.9.3.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.3/latest.json)

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
