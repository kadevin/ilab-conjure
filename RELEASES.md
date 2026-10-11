# 下载 / Releases

当前正式版本：[v0.9.7](https://github.com/kadevin/ilab-conjure/releases/tag/v0.9.7)

## 版本说明

当前版本：`v0.9.7`。本版加入统一的 @ 图片引用，并修复参考图在缓存清理、并发提交及异常恢复过程中被误删的问题。建议使用上传参考图、多图任务或历史重试的用户升级。

受影响平台：macOS 与 Windows 的标准版和 portable 一键包，以及桌面和手机 WebUI。

必要操作与数据迁移：升级前退出旧实例，升级后重启应用并刷新已打开的页面。无需手动迁移任务、图片或设置，旧任务继续兼容；此前已丢失的参考图需要重新添加原图。Windows 标准 ZIP 仍需手动替换应用文件。

本版详情：

### P0 · 严重

#### 修复

- **多图提交不再误删本批参考图。** 修复参考图缓存达到上限、已有图片被历史任务引用时，新上传图片在任务登记前被清理，导致生成或编辑报告“Reference asset not found”的问题。整组图片会保留到任务完成登记。
- **异常提交保留待恢复任务的输入。** 修复任务记录已保存但索引写入失败后，后续提交仍可能清理其参考图的问题。写入异常后按磁盘任务记录确认引用；记录无法可靠读取时停止删除，避免扩大输入丢失。

### P1 · 重要

#### 新增

- **@ 同时引用当前参考图与公用图库。** 候选按“当前参考图 → 公用图库”分组，支持按编号、名称搜索，以及方向键、回车和 Esc 操作；输入法确认不会误插入图片引用。
- **提示词中的图片引用随实际输入对应。** 调整顺序、裁剪或替换图片、重复使用同一张图后，引用仍绑定原图片身份，并按服务端去重后的实际编号解析。原文提示词模式同样支持显式图片引用。

### P2 · 常规

#### 变更与优化

- **草稿、历史与备份保留图片引用。** 恢复输入时同步恢复提示词与参考图，缺失图片会明确阻止提交，避免按同名或编号绑定到另一张图；上传图引用保存为模板时转换为占位符。
- **引用与附件操作保持清晰。** 上传图片不会自动插入提示词引用；删除上传图引用保留附件，删除参考栏图片同步移除对应引用。公用图库继续沿用最后一处引用删除后的附件联动行为。

#### 修复

- **异步预检期间保留已选参考图。** 复用最近图片并上传图片或文档时，并发提交和删除不会再清理预检中使用的图片；取消或校验失败后会正确释放临时保护。

### P3 · 低影响

#### 兼容性/安装/打包/更新

- **升级后加载新版引用界面。** 同步生成页、历史页、样式和离线缓存版本，避免继续使用旧版图片引用资源。

#### 工程与文档

- 补充图片引用、缓存边界、并发操作、取消和失败恢复的回归验证，并同步中英文使用说明与设计合同。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-0.9.7.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.7/iLab-GPT-CONJURE-macos-arm64-0.9.7.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.7/iLab-GPT-CONJURE-macos-arm64-0.9.7.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-0.9.7.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.7/iLab-GPT-CONJURE-macos-x64-0.9.7.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.7/iLab-GPT-CONJURE-macos-x64-0.9.7.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_0.9.7.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.7/iLab-GPT-CONJURE-windows-x64_0.9.7.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.7/iLab-GPT-CONJURE-windows-x64_0.9.7.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.9.7.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.7/ilab-gpt-conjure_windows_portable_x64_0.9.7.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.7/ilab-gpt-conjure_windows_portable_x64_0.9.7.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.9.7.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.7/ilab-gpt-conjure_macos_portable_arm64_0.9.7.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.7/ilab-gpt-conjure_macos_portable_arm64_0.9.7.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.9.7.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.7/ilab-gpt-conjure_macos_portable_x64_0.9.7.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.7/ilab-gpt-conjure_macos_portable_x64_0.9.7.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.7/latest.json)

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
