# 下载 / Releases

当前正式版本：[v0.7.0](https://github.com/kadevin/ilab-conjure/releases/tag/v0.7.0)

## 版本说明

当前版本：`v0.7.0`。本版完成一次面向多模型能力的项目升级：原 `iLab GPT CONJURE` 最初围绕 `GPT-Image-2` 构建，现在新增 Gemini 图像模型支持，并将项目与产品显示名统一升级为 `iLab CONJURE`。同时完善模型与供应商切换、历史参数恢复、并发调度和生成页交互。建议所有用户更新。

本版重点：0.7.0 将 GPT Image 与 Gemini 纳入统一生成工作台，支持官方协议与兼容中转站的模型绑定；任务、供应商和参数状态可在生成页、任务列表与历史库之间保持一致，并完成 `iLab CONJURE` 项目升级与 GitHub 仓库更名。

本版详情：

### 升级必读

- `v0.6.1` 及更早的 macOS 标准 App 尚未包含更新助手，需要从 Release 页面手动下载并覆盖安装 `v0.7.0` 一次；完成这次引导升级后，后续版本即可从菜单栏“检查更新”一键安装。`v0.6.2` 用户可直接使用已有的更新助手安装本版。
- Windows 标准 ZIP 仍需下载后手动替换；portable 包继续使用现有的用户确认式自动更新。
- `v0.5.4` 及更早 portable 用户首次升级到 `0.5.5` 或更新版本时，建议手动下载完整标准包或完整 portable 包；旧 updater 只保证升级 WebUI/依赖，不保证安装新的小兔子启动器、标准 `.app` / `.exe` 入口和迁移助手。
- 新用户建议优先下载标准包。标准包把用户数据写入系统应用数据目录；portable 包继续把数据写在同级 `data/`，用于老用户过渡、调试和临时工作流。
- 已有任务、图片和供应商设置会继续保留；新增配置由程序自动兼容处理，无需手动迁移数据。
- macOS 一键更新只会在用户主动确认后执行，不会后台静默下载或安装；用户数据保存在应用包外，不参与程序替换。
- macOS 标准 DMG 和 portable zip 都暂未签名、未 notarize，首次启动可能需要右键或 Control-click 选择 Open。

### 项目升级

- 项目原名 `iLab GPT CONJURE`，最初围绕 `GPT-Image-2` 构建；随着 Gemini 支持加入并为后续更多模型预留统一扩展能力，项目与产品显示名统一升级为 `iLab CONJURE`。
- GitHub 仓库由 `ilab-gpt-conjure` 更名为 `ilab-conjure`。这是同一项目的延续，历史 Release、旧名称搜索结果和既有用户数据仍保持连续。
- 为避免破坏现有安装和自动更新，过渡期安装包文件名、`.app` / `.exe` 名称及用户数据目录继续沿用原项目名称。

### GPT Image 与 Gemini

- 左上角模型家族切换器统一提供 GPT 与 Gemini，具体模型、可用供应商和输出参数会随当前家族联动更新。
- Gemini 图像模型支持文生图、参考图生成与模型对应的比例、安全和输出控制；GPT Image 原有生成与编辑能力保持不变。
- 任务卡、历史记录和结果预览统一显示模型家族、尺寸、供应商与协议摘要，跨家族查看任务时也能保持信息一致。
- 模型切换采用稳定的参数草稿和面板过渡，减少整块输入输出区域切换时的不协调加载与页面跳动。

### 供应商与协议

- 供应商绑定直接选择 OpenAI Images、OpenAI Responses 或 Gemini 协议，无需先进入额外的“OpenAI 兼容”层级。
- Codex Image 与 Codex Responses 作为两个内置供应商选项直接出现在生成页；系统设置不再保留重复的 Codex 通道选项。
- 一个自定义供应商可以绑定多个模型、远端模型名和兼容层，并可添加 Emoji 图标，便于在生成页快速识别。
- 可按绑定追加与界面语言一致的比例提示，兼容忽略尺寸字段的 Responses 通道或中转站，同时不改变其他绑定的请求行为。
- 设置面板和生成页下拉菜单统一使用主题样式，补齐弹层溢出、语言列表显示和滚动条配色。

### 任务、参数与并发修复

- “使用此任务参数”会同步恢复正确的模型家族、具体模型、供应商、比例、质量和审核设置，不再出现参数来自一个模型而可选项仍属于另一个模型的情况。
- 从历史库使用“生成页查看”只会打开任务，不再意外改写当前供应商；主动复用任务参数时才切换相应模型与供应商。
- 修复部分历史任务比例回落为 1:1、比例与分辨率显示重复，以及历史参数被误解析为底层字段名或无关选项的问题。
- 供应商并发上限可由多个任务共同使用，不再只有单个任务一次生成多张时才能占满并发额度。
- 预览区会与固定高度的输入区域上下对齐，不同图片数量和比例之间切换任务时页面结构保持稳定。

### 界面与交互

- 模型家族切换器采用平滑滑动指示，并在窄侧栏自动压缩为图标；新建按钮也会收缩为加号，避免遮挡应用名称。
- API 供应商编辑表单压缩为更紧凑的双行布局，将图标并入供应商名称，并固定保存与取消操作的位置。
- 模型绑定中的兼容层、比例提示、默认供应商和删除操作重新分组，降低输入框与按钮难以区分的问题。
- 任务卡和历史卡统一 GPT / Gemini 图标与摘要层级，Gemini 卡片不再缺少尺寸、供应商或协议信息。
- 输出设置移除普通用户无需理解的兼容迁移提示，只在确实需要用户操作时显示状态说明。

### 安装包与发布工作流

- 继续提供 Windows x64、macOS Apple Silicon、macOS Intel 三种 portable zip，以及 macOS 双架构 DMG 和 Windows 标准 App ZIP。
- Release workflow 同时构建并上传 macOS Apple Silicon DMG、macOS Intel DMG、Windows 标准 App ZIP、Windows x64 portable、macOS Apple Silicon portable、macOS Intel portable、所有 `.sha256.txt` 和 signed `latest.json`。
- `latest.json` 同时服务 portable 自动更新与 macOS 标准 App 一键更新；两类更新都需要用户主动确认，并校验签名和下载文件完整性。
- 包含更新助手的 macOS 标准 App 可在用户确认后校验 DMG、带回滚保护地覆盖并重新启动；Windows 标准 ZIP 继续下载后手动替换。

### 文档与维护

- README 补充 `iLab GPT CONJURE`、`GPT-Image-2` 与 `iLab CONJURE` 的项目延续关系，并明确仓库更名和兼容期文件名策略。
- 同步更新标准包、portable 包、供应商配置和更新器说明，明确首次引导升级、用户确认、回滚保护与数据保留边界。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-0.7.0.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.7.0/iLab-GPT-CONJURE-macos-arm64-0.7.0.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.7.0/iLab-GPT-CONJURE-macos-arm64-0.7.0.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-0.7.0.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.7.0/iLab-GPT-CONJURE-macos-x64-0.7.0.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.7.0/iLab-GPT-CONJURE-macos-x64-0.7.0.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_0.7.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.7.0/iLab-GPT-CONJURE-windows-x64_0.7.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.7.0/iLab-GPT-CONJURE-windows-x64_0.7.0.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.7.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.7.0/ilab-gpt-conjure_windows_portable_x64_0.7.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.7.0/ilab-gpt-conjure_windows_portable_x64_0.7.0.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.7.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.7.0/ilab-gpt-conjure_macos_portable_arm64_0.7.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.7.0/ilab-gpt-conjure_macos_portable_arm64_0.7.0.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.7.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.7.0/ilab-gpt-conjure_macos_portable_x64_0.7.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.7.0/ilab-gpt-conjure_macos_portable_x64_0.7.0.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v0.7.0/latest.json)

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
