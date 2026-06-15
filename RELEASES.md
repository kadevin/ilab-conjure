# 下载 / Releases

当前正式版本：[v0.4.0](https://github.com/kadevin/ilab-gpt-conjure/releases/tag/v0.4.0)

## 版本说明

当前版本：`v0.4.0`。这个版本提供 Windows x64、macOS Apple Silicon、macOS Intel 三种免安装一键包；下载对应平台的 zip 后解压即可启动本地 WebUI，并可在包内一键更新到后续版本。

本版重点：这一版把搜索能力作为主线升级：Codex 与 API Responses 模式新增可选联网搜索，生成页和历史库搜索支持任务 ID 与历史任务命中；同时继续收口历史库浏览、提示词复制/展示、短屏布局和一键包发布说明。

本版详情：

- 搜索生成：Codex 和 API Responses 模式新增“联网搜索”选项，请求会按顺序先调用 `web_search` 再调用 `image_generation`，并把搜索到的正式名称、英文片名、人物、日期和地点等事实写入图像提示词，避免只按字面翻译生成。
- 搜索范围：生成页搜索框支持搜索任务 ID，并能从历史任务中命中结果；历史库搜索也支持任务 ID。历史库的“复用任务”改为在生成页查看该任务，便于把提示词、输入图和输出图一起还原到当前工作台。
- 历史库：排序控件从两项下拉改为切换按钮；右键删除、归档和恢复任务时保留当前滚动位置，不再整页刷新回顶部；批量选择、右键菜单和任务卡局部更新逻辑继续收口。
- 历史详情：大图浏览保留左右键切换同一任务多图，并新增上下方向键在前后任务之间切换；多图任务会展示每张图各自的优化提示词，避免 Responses 多图任务只看到一套提示词。
- 提示词工作流：修复右键复制提示词在任务卡省略文本上取值导致的截断问题；修复全选超长提示词后“收藏”浮动按钮溢出；提示词查找、片段 chip 和模板入口在短屏下保持稳定。
- 输出设置与布局：联网搜索开关和主模型控件放在同一组；短屏桌面布局继续压缩但保持图像输入、提示词和输出设置底部对齐，避免按钮错位、面板撑穿和控件居中突兀。
- 一键包与文档：版本提升到 0.4.0，公开 README 和 RELEASES 同步更新搜索功能说明；Release 页面继续带完整 `当前版本`、`本版重点`、`本版详情`、三平台一键包和 macOS 未签名说明。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.4.0.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.4.0/ilab-gpt-conjure_windows_portable_x64_0.4.0.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.4.0/ilab-gpt-conjure_windows_portable_x64_0.4.0.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.4.0.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.4.0/ilab-gpt-conjure_macos_portable_arm64_0.4.0.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.4.0/ilab-gpt-conjure_macos_portable_arm64_0.4.0.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.4.0.zip](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.4.0/ilab-gpt-conjure_macos_portable_x64_0.4.0.zip) | [sha256](https://github.com/kadevin/ilab-gpt-conjure/releases/download/v0.4.0/ilab-gpt-conjure_macos_portable_x64_0.4.0.zip.sha256.txt) |

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
