<h1 align="center">iLab CONJURE</h1>

<p align="center">
  <sub>多模型 AI 图片生成工作台 · GPT Image / Gemini · 图库、模板、历史库与并发任务</sub>
</p>

<p align="center">
  <a href="https://github.com/kadevin/ilab-conjure/releases"><img alt="release" src="https://img.shields.io/github/v/release/kadevin/ilab-conjure?style=flat-square&logo=github&label=release&color=0EA5E9"></a>
  <a href="https://github.com/kadevin/ilab-conjure/actions/workflows/ci.yml"><img alt="CI status" src="https://github.com/kadevin/ilab-conjure/actions/workflows/ci.yml/badge.svg?branch=main&event=push"></a>
  <a href="https://github.com/kadevin/ilab-conjure/commits/main"><img alt="last commit" src="https://img.shields.io/github/last-commit/kadevin/ilab-conjure?style=flat-square&logo=github&label=last%20commit&color=10B981"></a>
  <a href="https://github.com/kadevin/ilab-conjure/stargazers"><img alt="stars" src="https://img.shields.io/github/stars/kadevin/ilab-conjure?style=flat-square&logo=github&label=stars&color=0284C7"></a>
  <a href="https://github.com/kadevin/ilab-conjure/network/members"><img alt="forks" src="https://img.shields.io/github/forks/kadevin/ilab-conjure?style=flat-square&logo=github&label=forks&color=0369A1"></a>
</p>

<p align="center">
  <img alt="license AGPL-3.0-only" src="https://img.shields.io/badge/license-AGPL--3.0--only-22C55E?style=flat-square">
  <img alt="Python: security-patched release required" src="https://img.shields.io/badge/python-security%20patched-3776AB?style=flat-square&logo=python&logoColor=white">
  <img alt="FastAPI WebUI" src="https://img.shields.io/badge/WebUI-FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white">
  <img alt="CLI" src="https://img.shields.io/badge/CLI-enabled-334155?style=flat-square">
  <img alt="OpenAI-Compatible API" src="https://img.shields.io/badge/OpenAI--Compatible-API-111827?style=flat-square">
  <img alt="Advanced OAuth mode" src="https://img.shields.io/badge/local%20OAuth-advanced%20mode-B45309?style=flat-square">
</p>


<p align="center">
  中文 · <a href="README.en.md">English</a> · <a href="RELEASES.md">下载 / Releases</a>
</p>

<p align="center">
  <img src="assets/UI_cn.webp" alt="iLab CONJURE WebUI 截图" width="960" />
</p>

## 简介

iLab CONJURE 是本地优先的 AI 图片生成工作台，支持 GPT Image、Gemini，以及个人本机 Codex 工作流。通过 WebUI 完成生成、编辑和素材管理，也可用 CLI 自动化处理。

新用户可直接下载[应用包](#应用包下载)；开发者可[从源码安装](#安装)。接入供应商建议使用 API 模式，本工具不适合作为公网多用户服务。

## 功能

- **多模型生成：** 支持文生图、参考图和图像编辑，可配置多个供应商、远端模型名及并发上限。
- **提示词与素材：** 公用图库、最近上传、图片／颜色／片段快捷引用和模板库，配合多图层编辑器复用素材。
- **输出控制：** 调整尺寸、比例、质量、数量和格式；支持模型提供的透明背景、联网搜索及参数锁定。
- **任务与历史：** 并发队列、多图输出、失败重试，以及历史搜索、收藏、标签、批量整理和 ZIP 导出。
- **界面与设置：** 响应式紧凑布局、深浅主题、14 种语言选项，以及代理、存储、通知和配置备份恢复。
- **本地运行：** 提供 macOS、Windows 应用包与 portable 包，支持托盘／菜单栏启动和 CLI。

<details>
<summary>模型与通道说明</summary>

GPT Image 支持 Image 2、2.5 和 2.6 的 Flare／Sunburst；API 供应商可分别绑定远端模型名，现有绑定不会自动升级。Codex 通道保持 Image 2。Gemini 包含 Nano Banana Pro、2.1、2 和 2 Lite，其中 2.1 支持 1K／2K／4K、最多 14 张参考图及 Google 搜索。

Responses 通道可设置主模型，默认 `gpt-6-luna`，候选包含 `gpt-6.1-terra`（取决于供应商支持）；已保存的选择会保留，旧的 `gpt-5.4-mini` 可手动切换。Image 直连不使用主模型。模型列表查询仅辅助填写，不会自动保存或验证生图能力。

GPT Image 的透明背景适用于 PNG／WebP，可按通道使用原生参数或提示词兼容；结果未实现透明时保留图片并提示，不自动重新生成。

</details>

## 认证模式

**API 模式（推荐）：** 在系统设置中填写供应商的 Base URL、API Key、模型名和调用方式。

**Codex / ChatGPT OAuth（高级本机模式）：** 复用本机登录态，选择 Codex Image 或 Codex Responses。此模式调用内部接口，仅供个人本机工作流；并非官方推荐的 API 集成方式，接口及账号用量规则可能变化。

凭据、提示词、图片、任务数据库和日志应留在本地，不要提交到 Git。安全边界见 [SECURITY.md](SECURITY.md)。

## 应用包下载

正式版本与下载入口见 [下载 / Releases](RELEASES.md) 或 [GitHub 最新正式版](https://github.com/kadevin/ilab-conjure/releases/latest)。

| 平台 | 安装与启动 |
| --- | --- |
| macOS | 按芯片选择 arm64 或 x64 DMG，将 App 拖入 Applications 后打开。 |
| Windows | 下载 x64 App ZIP，解压到普通用户目录，运行 `iLab GPT CONJURE.exe`。 |
| Portable | 下载对应平台 ZIP，解压后运行 `Start iLab GPT CONJURE.app` 或 `.exe`。 |

应用包内置 Python、依赖和前端资源，日常使用无需 Node.js。标准版数据保存在 macOS 的 `~/Library/Application Support/iLab GPT CONJURE` 或 Windows 的 `%APPDATA%\iLab GPT CONJURE`；portable 数据保存在同级 `data/`。

**更新：** macOS 标准版和 portable 可从托盘／菜单栏检查更新，确认后校验签名与文件哈希并安装；Windows 标准 ZIP 手动替换。更新前退出旧实例，保留数据目录。安装依赖失败时检查网络或重新下载完整包，无需删除图库、配置或任务记录。

<details>
<summary>旧版迁移与 macOS 打开提示</summary>

项目自 v0.7.0 从 `iLab GPT CONJURE` 更名为 `iLab CONJURE`；部分安装包、程序和数据目录仍沿用旧名。标准版首次启动可在确认后复制相邻 portable 数据，不删除旧目录，也不自动覆盖已有标准版数据。

v0.6.1 及更早的 macOS 标准版需手动安装一次支持更新助手的版本；v0.5.4 及更早 portable 用户建议下载完整包升级。Portable 更新保留 `data/`，被替换文件备份到 `.backup/`；终端调试和手动更新可使用包内 `Start WebUI Portable`、`Update WebUI Portable` 脚本。

macOS 构建使用临时签名（ad-hoc），未使用 Developer ID 签名或经过公证。确认下载来源可信后，可右键 App →“打开”，并在系统提示中确认。Portable 解压目录也可使用：

```bash
xattr -dr com.apple.quarantine /path/to/ilab-gpt-conjure_macos_portable_arm64
# Intel Mac 使用对应的 macos_portable_x64 目录
```

</details>

## 环境要求

以下仅适用于源码安装：Python 安全补丁基线为 **3.11.18、3.12.16、3.13.18、3.14.10、3.15.2** 或对应分支的更新版本；安装依赖需 **pip 26.2.2+**。修改前端时才需要 Node.js，版本见 [`.node-version`](.node-version)。

## 安装

以下命令用于 macOS／Linux 终端；Windows PowerShell 中将 `python3` 换为 `py -3`（未安装 Python Launcher 时用 `python`），将 `.venv/bin/python` 换为 `.venv\Scripts\python.exe`。

```bash
git clone https://github.com/kadevin/ilab-conjure.git
cd ilab-conjure
python3 codex_image/runtime_security.py
python3 -m venv .venv
.venv/bin/python codex_image/runtime_security.py --installer
.venv/bin/python -m pip install --require-hashes -r requirements-webui.txt
```

若 `--installer` 提示 pip 过旧，先执行下方升级，再重新运行安装检查和依赖安装两条命令。启动检查不会修改全局 Python 或 pip；升级依赖不能代替升级解释器。旧环境也需更新锁定依赖，以满足 Pillow、certifi 安全要求。

<details>
<summary>升级项目环境中的旧 pip</summary>

在项目目录执行，Windows PowerShell 按上文替换 Python 路径。命令通过 HTTPS 下载固定 wheel，核对 SHA-256 后仅安装到当前项目虚拟环境；校验或下载失败即停止，不关闭 TLS 校验。

```bash
.venv/bin/python -c "
import hashlib, pathlib, subprocess, sys, tempfile, urllib.request
url = 'https://files.pythonhosted.org/packages/3f/06/3e4420302363fbb71be3c7f35ce042f54bfca330e3e66b3a2e3c4cca579f/pip-26.2.2-py3-none-any.whl'
expected = 'fd7f4dfa8190e014013b9f08f3e973f4e4c26ffd179a204895533a7254813a70'
with tempfile.TemporaryDirectory() as folder:
    wheel = pathlib.Path(folder) / 'pip-26.2.2-py3-none-any.whl'
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != expected:
        sys.exit('SHA256 mismatch; installation stopped')
    wheel.write_bytes(data)
    subprocess.run([sys.executable, str(wheel) + '/pip', 'install', '--no-index', '--no-deps', str(wheel)], check=True)
"
```

</details>

## 启动 WebUI

macOS 双击 `Start WebUI.command`，Windows 双击 `Start WebUI.bat`，然后访问 **http://127.0.0.1:8787/**。也可手动启动：

```bash
.venv/bin/python -m codex_image.webui.server codex_image.webui.app:app --port 8787 --no-access-log
```

**局域网访问：** 在“系统设置 → 网络”开启后重启服务，其他设备使用设置中显示的地址。此功能默认关闭，开关均需重启；保存不会中断当前任务。仅用于可信局域网：访问者无需登录，可共享并修改设置、任务和图库。手动启动时省略 `--host` 才会跟随设置，显式 `--host 127.0.0.1` 保持仅本机访问；HTTP 下部分浏览器功能可能受限。

## WebUI 使用说明

1. 选择模型和供应商，在系统设置中配置 API、网络及其他偏好。
2. 上传、拖入或粘贴参考图，也可从最近上传、公用图库选择。
3. 输入提示词，按需插入快捷引用或模板，调整输出参数后开始生成。
4. 在左侧跟踪任务、右侧查看和下载结果；进入历史库搜索、收藏、打标签或批量导出。

GPT Image 2.6 通过 Images API 提供复杂度、超高／最高质量，以及 SVG 和 GIF 输出。SVG／GIF 仅用于生成；GIF 的帧数（2–64）和每帧时长（20–2000 毫秒）收纳在“额外选项”，同时显示总时长；高分辨率下会按本地解码预算降低可选帧数上限。SVG 批量输出按单张请求执行。Image 2.5／2.6 的 Images API 编辑支持在第一张参考图上保存独立透明标注层；标注与原图分别发送，不能与蒙版同时使用。

紧凑模式中，透明背景和压缩率收纳在“格式”旁的额外选项图标中；JPEG／WebP 的压缩率可调范围为 50%–100%。

停止任务会中断本地请求与等待，但供应商可能继续生成并计费。已生成图片和历史会保留。同标签页进入历史库会暂存输入，返回后恢复；复用历史任务后可通过“恢复草稿”找回原输入。

### 网络与下载

网络出口可选系统、直连或自定义 HTTP(S) 代理；请求超时为 1–30 分钟（默认 10），可重试失败的重试次数为 0–5（默认 2），保存后对后续任务生效。图片下载或 DNS 重试不会重新提交生成；已发出但结果不确定的请求不会自动重放。

若 Clash/Mihomo Fake-IP DNS 导致生成成功但下载失败，可开启“图片下载兼容 Fake-IP DNS”。默认关闭，仅向 Cloudflare 查询受影响图片域名的公网地址，不修改系统或局域网 DNS。

### 存储路径与旧数据

修改存储路径需重启，不会自动搬迁数据。切换后历史为空时，可在“存储与通知 → 查看原默认目录”改回原路径并重启。迁移前先备份、退出应用，再完整复制输入与输出目录（含图库、参考素材和源数据），不要只复制图片或单个数据库，也不要覆盖已有目标数据。

macOS 标准版保留自定义路径；从 portable 迁移时仅调整原 `data/` 内的路径，外部目录不变。原路径配置保存在 `.migration/webui-settings-before-path-rebase.json`，旧数据不删除。

### 用户配置备份与恢复

在“存储与通知 → 配置备份与恢复”选择 chip、公用图、模板或系统设置，导出 ZIP。备份为所选类别的完整快照，创建后 24 小时内可重复下载；放弃或到期后清理服务端临时副本。

备份恢复页面可直接切换其他设置标签；恢复配置后，尚未保存的网络、存储和供应商编辑草稿会保留并提示。

恢复前会校验文件并展示内容：**增量恢复**保留现有内容、跳过重复项，冲突资源另建副本；**替换恢复**仅影响所选类别，展示删除及引用影响并要求再次确认。备份资源组为空而本地非空时拒绝替换，运行或排队任务也可能阻止图库或设置替换。

API Key 默认排除，手动包含后 ZIP **不加密**；OAuth 登录态不备份。模板本地缩略图随包迁移，外部图片保留 URL，缺失素材或无效路径会警告并跳过。恢复存储路径需重启；生成任务与历史图片请使用历史库的“任务备份”。

## 公用图库（公共图库）

将上传图或生成结果保存为可复用参考素材，支持分类、命名、用途备注、替换和拖拽排序。在图库中选择，或输入 `@` 搜索引用。素材保存在本地，删除图库条目可能使旧任务出现缺失引用。

## 三种 chip

| 输入 | 用途 |
| --- | --- |
| `@` | 搜索当前参考图和公用图库，插入图片引用；图库图片会同时加入参考输入。 |
| `#` | 插入十六进制颜色，如 `#FF6600`。 |
| `~` / `～` | 插入已保存的提示词片段，提交时展开为完整内容。 |

使用方向键选择、回车确认、Esc 关闭。选中文字可收藏为片段，之后查看、编辑或展开复用。

图片引用按实际提交顺序解析并去重；普通粘贴的 `@图1` 文本不会自动绑定图片。删除上传图的引用保留图片，删除图库最后一处引用会移除本次图库参考；删除参考图会同步移除引用，可用“恢复输入”找回。缺失引用需重新选择或删除，保存模板时上传图引用转为 `{{图1}}` 占位符。

## 提示词模板

点击“管理模板库”，保存和复用较长提示词，支持分类、收藏、缩略图、导入导出。插入会写入当前提示词，替换会覆盖当前文本，不会隐藏注入。模板默认保存在 `output/webui-prompt-templates.json`。

## CLI

```bash
.venv/bin/python -m codex_image generate --prompt "A clean product photo of a ceramic mug" --out output/mug.png
```

支持参考图、编辑、mask 和 dry-run，完整参数见 `--help`。

## 开发

开发与验证见 [CONTRIBUTING.md](CONTRIBUTING.md)，打包与发布见 [RELEASES.md](RELEASES.md)，安全基线见 [依赖安全说明](docs/dependency-security.md)。修改 TypeScript 或 CSS 后需生成并同步 `codex_image/webui/static/` 中的资源。

## 许可证

采用 [GNU AGPLv3](LICENSE)。修改后通过网络提供服务时，需按协议开放对应源码。许可证仅适用于代码，不授予项目名称、Logo、素材、凭据、用户内容或第三方模型／API 服务的权利。

## 交流与定制开发

欢迎交流 AI 编程与生图工作流，也接受本地工具、企业网站和智能体应用定制。扫码时备注 `iLab CONJURE` 或 `定制开发`。

<p align="center">
  <img src="assets/wechat-qr.jpg" alt="iLab WeChat QR Code" width="240" />
</p>
