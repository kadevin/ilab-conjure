# 下载 / Releases

当前正式版本：[v0.9.0](https://github.com/kadevin/ilab-conjure/releases/tag/v0.9.0)

## 版本说明

当前版本：`v0.9.0`。这是一次局域网共享、手机触屏工作流和透明背景生成更新，并修复 macOS 标准版自动更新的严格签名校验问题。建议需要跨设备使用、透明素材输出，或遇到自动更新失败的用户升级。

受影响平台：macOS 与 Windows 的标准版和 portable 一键包；WebUI 改进适用于桌面和手机浏览器。macOS Apple Silicon、Intel 标准 DMG 均包含签名修复。Windows 标准 ZIP 继续手动替换，portable 与支持更新助手的 macOS 标准版沿用现有更新入口。

必要操作与数据迁移：升级前退出旧实例，无需数据库迁移或手动搬迁任务、图库和图片。局域网访问默认关闭，须在“系统设置 → 网络”开启并重启 WebUI 服务；关闭后也要重启才生效。开放后无需登录，可访问该地址的人共用供应商、任务、图库和队列，也可修改设置与删除数据，请仅在可信网络中启用，不要映射到公网。透明背景需要 PNG 或 WebP，开启时 JPEG 会自动切换为 PNG。

本版重点：手机可以通过局域网完成生成、参考图输入、历史浏览和大图操作；GPT Image 支持原生参数与提示词两种透明背景方式；任务首屏不再等待实时连接；修复 macOS 更新失败及多处移动端裁切、重叠和误触问题。

本版详情：

### P1 · 重要

#### 新增

- 增加“允许局域网访问”设置及可复制的访问地址。同一局域网内的手机、平板和电脑可以共同使用同一个工作区；设置区明确区分已保存、待重启和已生效状态，保存开关不会中断正在执行的任务。
- 增加手机触屏工作流：紧凑顶栏提供任务、供应商、新建和更多入口，底部保留生成与参数按钮，完整参数在独立面板中编辑。支持照片／文件选择、返回编辑、双指缩放、放大后平移和左右滑动切图，并适配软键盘与安全区域。
- GPT Image 2、2.5 Flare / Sunburst 增加透明背景开关。API 模型绑定可选择“原生参数”或“提示词兼容”，Codex 使用提示词兼容；所选策略随任务保存，重试继续使用原策略。结果检测实际透明像素，未实现透明时保留图片并给出提示，不自动重试产生额外消耗。

#### 修复

- 修复 macOS 标准版自动更新被严格签名校验阻止的问题（#22）。运行时裁剪会清除失效的 Headers 链接，裁剪后分别重签 Python.framework 和 App；生成 DMG 前验证最终内容，签名或严格校验失败立即停止打包。更新助手继续保留原有严格校验。
- 修复实时连接延迟时首屏任务与队列迟迟不出现的问题。页面主动加载初始状态，后到的旧响应不再覆盖更新的任务、队列或服务重启后的状态。

### P2 · 常规

#### 新增

- 在当前页面切换任务或新建任务后，可以恢复尚未提交的提示词与参考输入草稿；恢复输入时保留当前生成参数。离开仍有编辑内容的页面会触发浏览器提示，图片编辑器放弃未保存修改时也会确认。
- 自定义尺寸不合法时，直接标记对应输入并提供可采用的合法尺寸建议，减少反复试填。

#### 变更与优化

- 批量管理使用带图标的实色按钮，全选本组和全选等待中均可再次点击取消；不必退出批量管理才能清空对应选择。全选请求失败、任务范围切换和未加载任务的选择状态也有一致处理。
- 输出设置中的主模型与联网搜索、透明背景采用紧凑同行布局，开关不再显示容易误解的固定“开启”文字；不使用主模型的通道显示简洁的直连说明，开关切换不再额外抬高参数区。
- 强化分段选项和任务卡的选中对比度，统一焦点、圆角与控件尺寸，提升深浅主题下的辨识度。
- API 供应商的模型绑定支持折叠查看，默认供应商操作明确限定为对应型号。任务失败时区分凭据、额度、输入与临时问题，提供更明确的恢复入口；删除与“保留成功图片并结束”操作说明实际影响。

#### 修复

- 修复供应商设置中的双重滚动条、切换标签时短暂出现的滚动条，以及重复点击当前供应商仍显示自动保存的问题；切换设置标签时保留正在编辑的供应商内容。
- 修复选中任务卡顶部高亮被容器裁切的问题，并调整批量管理区域过多描边和不明确的按钮外观。
- 修复手机预览中图片压住标题、操作区错位与按钮尺寸不一的问题；结果操作完整放在图片下方，长竖图与多图预览按内容布局。
- 修复手机大图浏览缺少明显关闭入口、点击空白无法退出及缩放控件被遮挡的问题；关闭与切图入口在深浅图片上均保持可见，拖动和缩放结束不会误切图或误关闭。
- 修复手机历史页顶部占用过大、标签裁切及缺少返回生成页导航的问题；历史详情使用不透明背景，标题、关闭按钮与操作组清晰分离，消除背景信息叠加。
- 修复手机参考输入区上下间距、GPT／Gemini 与主题切换组件样式，以及参考图缩略图被压扁裁切的问题。参考图和最近上传均可横向浏览，图片与图库／移除操作分开，避免放大的触控按钮相互覆盖。
- 修复局域网 HTTP 环境缺少安全上下文时，复制文字、历史导入和配置恢复受到浏览器能力限制的问题。复制提供可选中文字的回退，导入和恢复保留完整性校验。
- 透明结果使用保留 Alpha 通道的缩略图，正确处理调色板透明图片，避免预览时透明背景变成不透明色块。

#### 兼容性/安装/打包/更新

- 启动器和启动脚本尊重保存的局域网设置；显式传入 `--host` 时仍以启动参数为准。Codex 本机登录态、既有模型绑定、任务历史和存储路径继续兼容。

#### 已知问题

- 提示词兼容方式能否生成真实透明背景取决于模型和供应商通道，不能保证所有中转站都支持。结果会按实际像素提示状态。
- macOS 包尚未使用 Apple Developer ID 签名，也未 notarize；首次打开仍可能需要右键或 Control-click 选择 Open。Windows 标准 ZIP 仍需手动替换程序文件。

### P3 · 低影响

#### 工程与文档

- 补充触屏交互、草稿恢复、批量选择、透明背景、局域网访问、状态同步和 macOS 打包回归验证，更新中英文使用说明、设计合同与安全边界。
- 为不提供 Web Crypto 的局域网 HTTP 浏览器加入 SHA256 兼容实现，并排除 Rust 本地构建目录进入版本控制。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-0.9.0.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.0/iLab-GPT-CONJURE-macos-arm64-0.9.0.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.0/iLab-GPT-CONJURE-macos-arm64-0.9.0.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-0.9.0.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.0/iLab-GPT-CONJURE-macos-x64-0.9.0.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.0/iLab-GPT-CONJURE-macos-x64-0.9.0.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_0.9.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.0/iLab-GPT-CONJURE-windows-x64_0.9.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.0/iLab-GPT-CONJURE-windows-x64_0.9.0.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.9.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.0/ilab-gpt-conjure_windows_portable_x64_0.9.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.0/ilab-gpt-conjure_windows_portable_x64_0.9.0.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.9.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.0/ilab-gpt-conjure_macos_portable_arm64_0.9.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.0/ilab-gpt-conjure_macos_portable_arm64_0.9.0.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.9.0.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.0/ilab-gpt-conjure_macos_portable_x64_0.9.0.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.0/ilab-gpt-conjure_macos_portable_x64_0.9.0.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.0/latest.json)

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
