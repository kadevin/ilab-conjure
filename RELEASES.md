# 下载 / Releases

正式版本见 [GitHub 最新正式版](https://github.com/kadevin/ilab-conjure/releases/latest)。下方 v1.2.0 下载链接在该版本发布后生效。

## 版本说明

### v1.2.0

本版为 WebUI 加入实时预览换肤，并开放 GPT Image 2.6 带参考图时的 SVG 和 GIF 输出。建议使用这些功能或遇到上传预览显示异常的 v1.1.1 用户升级。变更适用于 macOS 和 Windows 的标准版及便携版。

升级前等待任务结束并退出旧实例，升级后重新打开应用。现有任务、图片和设置无需迁移。Windows 标准 ZIP 仍需手动替换应用文件。

### P1 · 重要

#### 新增

- **在顶栏实时换肤。** 点击明暗切换旁的颜色圆点，可预览预设皮肤、自定义主色和背景色系。应用后，生成页和历史库会使用保存的配色，滚动条和下拉框也随主题变化。手机端从「更多」进入。
- **GPT Image 2.6 支持带参考图输出 SVG 和 GIF。** 添加参考图后可继续选择两种格式。GIF 的帧数和单帧时长在「额外选项」中设置。实际可用性取决于供应商和账号权限。

### P2 · 常规

#### 新增

- **Responses 主模型新增 GPT‑6.2 Sol 和 Astra。** 从「输出设置 → 主模型」选择，默认主模型仍为 `gpt-6-luna`。

#### 兼容性/安装/打包/更新

- **配置备份可迁移配色。** 常规备份会携带已保存的配色。需要在旧版恢复时，勾选「兼容旧版（不包含配色）」，即可导出旧版能读取的配置包。

#### 修复

- **SVG 结果可以直接复用为参考图。** 从预览或历史库添加时会生成保留尺寸和透明背景的 PNG 副本，原始 SVG 仍可下载。
- **GIF 编辑会提前校验不兼容设置。** 使用 OpenAI 官方端点时最多 16 帧。遇到蒙版、压缩和部分预览等不兼容参数时，会显示具体原因和修正方法。
- **等待上传时显示参考图缩略图。** 提交含本地参考图的任务后，上传尚未完成时即可看到本地预览。感谢 [PR #57](https://github.com/kadevin/ilab-conjure/pull/57) 的贡献。

### P3 · 低影响

#### 修复

- **离线时保留基础应用清单。** 自定义配色清单请求遇到网络故障时，会回退到已缓存的基础清单。

#### 工程与文档

- **发布状态更清楚。** 流水线明确区分仅构建产物和正式发布，发布摘要写入失败时仍保留已确认的发布结果。
- **增加赞助入口。** 中英文 README 和仓库 Funding 配置已添加爱发电链接。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-1.2.0.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.0/iLab-GPT-CONJURE-macos-arm64-1.2.0.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.0/iLab-GPT-CONJURE-macos-arm64-1.2.0.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-1.2.0.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.0/iLab-GPT-CONJURE-macos-x64-1.2.0.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.0/iLab-GPT-CONJURE-macos-x64-1.2.0.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_1.2.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.0/iLab-GPT-CONJURE-windows-x64_1.2.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.0/iLab-GPT-CONJURE-windows-x64_1.2.0.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_1.2.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.0/ilab-gpt-conjure_windows_portable_x64_1.2.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.0/ilab-gpt-conjure_windows_portable_x64_1.2.0.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_1.2.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.0/ilab-gpt-conjure_macos_portable_arm64_1.2.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.0/ilab-gpt-conjure_macos_portable_arm64_1.2.0.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_1.2.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.0/ilab-gpt-conjure_macos_portable_x64_1.2.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.0/ilab-gpt-conjure_macos_portable_x64_1.2.0.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v1.2.0/latest.json)

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
