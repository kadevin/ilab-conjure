# 下载 / Releases

当前正式版本：[v0.5.0](https://github.com/kadevin/ilab-gpt-conjure/releases/tag/v0.5.0)

## 版本说明

当前版本：`v0.5.0`。这个版本提供 Windows x64、macOS Apple Silicon、macOS Intel 三种免安装一键包；下载对应平台的 zip 后解压即可启动本地 WebUI，并可在包内一键更新到后续版本。

本版重点：这一版把 Codex 默认生图通道从 Responses 切到直连 Image 通道，生成走 `codex/images/generations`，编辑走 `codex/images/edits`，用于恢复 2K / 4K 和高质量输出；Responses 通道仍保留为兼容选项。

本版详情：

- Codex Image 直连：新增 Codex 专用 Images 客户端，使用本机 Codex OAuth 登录态请求 `https://chatgpt.com/backend-api/codex/images/generations` 和 `https://chatgpt.com/backend-api/codex/images/edits`；生成和编辑请求都使用 JSON payload，支持 `gpt-image-2`、自定义尺寸、质量、输出格式和参考图。
- Codex 通道切换：右上角 API 设置面板顶部新增“Codex 通道”切换，可在 `Image` 和 `Responses` 之间切换；默认使用 `Image`，设置会持久化，复用历史任务时也会恢复对应通道。
- 高分辨率输出：Codex `Image` 模式用于 2K / 4K 和高质量生成、编辑任务；Codex `Responses` 模式仍保留为兼容通道，但高分辨率任务建议使用默认的 `Image` 模式。
- 队列与历史兼容：新任务会记录 `codex_mode`、`requested_backend` 和实际 `backend`；队列 worker、重试失败槽位、任务复用和请求预览都会按任务记录选择 `codex_images` 或 `codex_responses`，避免历史任务和等待中任务跑错通道。
- 提示词保真规则：Codex `Image` 模式和 API Images 模式使用同一套直接 Images 传输规则；严格保真提示会合并进 prompt，不再把额外 instructions 作为 Responses 字段发送。
- 并发执行：Codex `Image` 模式纳入直接 Images 并发执行路径，多图任务可以像 API Images 一样按槽位并发请求，减少多张图等待时间；Responses 模式继续走原有单请求工具调用流程。
- 联网搜索边界：联网搜索仍只在 Responses 通道生效；使用 Codex 默认 `Image` 模式时，生成重点放在尺寸、质量和编辑参数的稳定传递上。
- 网络层优化：实时事件连接成功后，启动流程不再额外全量刷新 `/api/tasks/recent`；只有 `EventSource` 不可用时才走完整任务列表兜底，减少大历史库启动时的重复网络请求和列表重算。
- 静态资源与前端合同：前端资源版本提升到 `runtime-329`；静态测试锁定 Codex 通道切换、请求预览、表单提交、队列后端选择和实时事件兜底路径，降低后续改动回归风险。
- 一键包与文档：版本提升到 0.5.0，公开 README 和 RELEASES 将同步更新 Codex Image 默认通道、Responses 兼容说明和三平台一键包下载信息；Release 页面继续带完整 `当前版本`、`本版重点`、`本版详情`、三平台一键包和 macOS 未签名说明。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.5.0.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.5.0/ilab-gpt-conjure_windows_portable_x64_0.5.0.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.5.0/ilab-gpt-conjure_windows_portable_x64_0.5.0.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.5.0.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.5.0/ilab-gpt-conjure_macos_portable_arm64_0.5.0.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.5.0/ilab-gpt-conjure_macos_portable_arm64_0.5.0.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.5.0.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.5.0/ilab-gpt-conjure_macos_portable_x64_0.5.0.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.5.0/ilab-gpt-conjure_macos_portable_x64_0.5.0.zip.sha256.txt) |

使用方式：

1. 下载对应平台的 zip。
2. 解压到普通用户目录，不要放在系统保护目录。
3. Windows 双击 `Start WebUI Portable.bat`；macOS 双击
   `Start WebUI Portable.command`。
4. 如果浏览器没有自动打开，访问 `http://127.0.0.1:8787/`。

启动脚本会短暂检测最新 GitHub Release；发现新版本时会在 WebUI 左下角版本入口显示提醒，不会自动更新。
更新已经解压的一键包时，先关闭 WebUI 服务窗口，然后运行 Windows 的
`Update WebUI Portable.bat` 或 macOS 的 `Update WebUI Portable.command`。
更新脚本会下载当前平台对应的最新 GitHub Release 资产，校验 SHA256，保留本地 `data/`，并把被替换文件备份到 `.backup/`。如果不希望启动时检查版本，可在启动前设置
`ILAB_SKIP_VERSION_CHECK=1`。

macOS 包是未签名的 portable zip，不是已签名 `.app` 或 notarized DMG。
启动脚本会尝试在启动前移除当前解压目录内的 quarantine 标记。如果 macOS
仍然拦截启动脚本，可以右键或 Control-click `Start WebUI Portable.command`，
选择 Open，并在系统安全提示中再次确认。也可以对解压目录执行：

```bash
xattr -dr com.apple.quarantine /path/to/ilab-gpt-conjure_macos_portable_arm64
# 或：
xattr -dr com.apple.quarantine /path/to/ilab-gpt-conjure_macos_portable_x64
```

一键包内的 `data/` 目录会保存本地设置、公用图库、输入图、输出图、任务数据库和日志。
不要把这些本地数据、API key 或 OAuth 文件提交到 Git。
