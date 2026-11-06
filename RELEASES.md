# 下载 / Releases

当前正式版本：[v1.1.0](https://github.com/kadevin/ilab-conjure/releases/tag/v1.1.0)

## 版本说明

### v1.1.0

本版新增 GPT Image 2.6、SVG／GIF 输出和独立图片标注，修复 macOS 安装包启动以及部分图片下载与历史参数恢复问题。建议 v1.0.0 用户升级，尤其是遇到启动失败的 macOS 用户。适用于 macOS、Windows 标准版与便携版，以及桌面和手机 WebUI。

升级前等待任务结束并退出旧实例，升级后重启应用并刷新页面。现有任务、图片和设置无需手动迁移；已有供应商绑定不会自动升级，使用 2.6 需配置支持相应型号的 Images API 供应商。Codex 通道继续使用 Image 2，Windows 标准 ZIP 仍需手动替换应用文件。

### P0 · 严重

#### 兼容性/安装/打包/更新

- **修复 macOS 安装包无法启动。** 标准版和便携版初始化认证设置时，现在正确加载包内依赖，避免全新环境在依赖检查通过后仍报缺少 `httpx` 并退出。感谢 PR #51 的贡献。

### P1 · 重要

#### 新增

- **支持 GPT Image 2.6 Flare／Sunburst。** 可绑定对应远端型号，并控制复杂度及超高／最高质量；不同型号按自身支持的参数展示控件。
- **生成 SVG 矢量图和 GIF 动画。** SVG 支持按单张请求组成批量输出；GIF 可设置帧数和每帧时长，并查看总时长。预览保留矢量和动画，历史备份与恢复支持新格式。
- **用独立标注层指导图片编辑。** Image 2.5／2.6 的 Images API 编辑可在第一张参考图上绘制透明标注，保留原图并分别发送；标注随任务和备份保存，与蒙版互斥。

#### 修复

- **兼容图片下载服务的格式误标。** 对实际可解码的 PNG、JPEG、WebP 等图片，按解码结果保存正确扩展名，避免供应商生成成功后因下载响应格式标签不准确而失败；仍拒绝无效图片和不安全内容。

### P2 · 常规

#### 变更与优化

- **GIF 设置集中在“额外选项”。** 帧数、每帧时长和总时长沿用压缩率弹层入口，减少参数区占用；高分辨率下按像素预算约束帧数，兼顾桌面、窄屏、深浅主题及键盘操作。
- **Image 2.5 增加超高／最高质量选项。** 旧 Image 2 和 Codex 参数保持原有范围。

#### 修复

- **参数锁恢复完整保留新选项。** 解锁和恢复锁定状态时，不再将复杂度、GIF 帧数和时长重置为默认值。
- **跨版本历史参数不再静默失真。** 参数定义兼容时保留当前型号和供应商；不兼容时先展示历史参数，点击“采用”后切换到原任务型号，保留格式、尺寸及动画设置。
- **超宽图片标注撤销保持原尺寸。** 宽度超过 4096 像素的图片在标注撤销、重做、保存和重新打开后，不再缩小画布坐标范围。
- **修复正式发布前的附件校验。** 待发布 Release 使用准确的发布标识读取附件，避免安装包已经上传却在校验阶段失败。

### P3 · 低影响

#### 工程与文档

- 整理测试入口和重复合同断言，集中前端测试发现与运行，保留行为回归覆盖；补充新格式、标注、图片下载和安装包认证初始化测试。

#### 已知问题

- SVG／GIF 仅支持 Images API 生成；标注编辑需要支持该参数的供应商。未对所有第三方供应商执行真实付费生成验证。
- 本版不提供 Linux 安装包；macOS 安装包仍未进行 Apple Developer ID 签名和公证。详见[依赖安全说明](https://github.com/kadevin/ilab-conjure/blob/v1.1.0/docs/dependency-security.md)。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-1.1.0.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.0/iLab-GPT-CONJURE-macos-arm64-1.1.0.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.0/iLab-GPT-CONJURE-macos-arm64-1.1.0.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-1.1.0.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.0/iLab-GPT-CONJURE-macos-x64-1.1.0.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.0/iLab-GPT-CONJURE-macos-x64-1.1.0.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_1.1.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.0/iLab-GPT-CONJURE-windows-x64_1.1.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.0/iLab-GPT-CONJURE-windows-x64_1.1.0.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_1.1.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.0/ilab-gpt-conjure_windows_portable_x64_1.1.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.0/ilab-gpt-conjure_windows_portable_x64_1.1.0.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_1.1.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.0/ilab-gpt-conjure_macos_portable_arm64_1.1.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.0/ilab-gpt-conjure_macos_portable_arm64_1.1.0.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_1.1.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.0/ilab-gpt-conjure_macos_portable_x64_1.1.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.0/ilab-gpt-conjure_macos_portable_x64_1.1.0.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v1.1.0/latest.json)

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
