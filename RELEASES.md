# 下载 / Releases

当前正式版本：[v0.8.4](https://github.com/kadevin/ilab-conjure/releases/tag/v0.8.4)

## 版本说明

当前版本：`v0.8.4`。这是面向用户配置迁移和 API 凭据安全的功能更新。建议需要迁移或保护 chip、公用图、提示词模板与系统设置，曾因修改供应商 Base URL 丢失已保存 Key，或在点击生成后看到按钮短暂不可用闪烁的用户更新；其他 `v0.8.3` 用户可以按需升级。

受影响平台：macOS 与 Windows 的标准版和 portable 一键包。升级前请退出旧实例；Windows 标准版仍需手动解压替换，portable 可使用现有更新入口，支持更新助手的 macOS 标准版可按界面提示更新。

必要操作与数据迁移：无需迁移或重置数据。已有设置、任务数据库、历史图库、输入图和输出图会保留，本次更新不会自动改写既有用户配置。备份包默认不含 API Key；如明确勾选包含 Key，ZIP 不加密，请妥善保存。`v0.8.3` 及更早版本不能导入新的用户配置备份包。

本版重点：系统设置新增可选择类别的用户配置备份与恢复，支持安全的增量或二次确认替换；API 供应商编辑不再因 Base URL 变更静默清除 Key，并保留后台防重提交而不改变生成按钮外观。

本版详情：

### P1 · 重要

#### 新增

- “系统设置 → 存储与通知”新增“配置备份与恢复”：可单独或组合备份 chip、公用图、提示词模板和系统设置，并在导入前预览包内与当前数据数量。
- 恢复支持“增量”和“替换”两种模式。增量恢复保留现有数据并跳过重复项；替换只作用于明确选择的类别，先展示清除与导入数量，再要求独立勾选和第二次确认。
- 备份可按需包含 API Key，但默认排除且持续提示 ZIP 未加密；Codex / ChatGPT OAuth 登录态、任务历史、输入图与输出图始终不进入用户配置包。已完成的临时包在 24 小时内可重复下载。

#### 修复

- 替换恢复不能再用“备份为空、当前非空”的受保护子类别隐式清空颜色、提示词片段、公用图或模板；恢复写入采用事务快照和回滚，启动时也会恢复被中断的事务，避免失败后留下半恢复状态。
- 备份会核验公用图文件身份与摘要，模板本地缩略图迁移到专用受管素材目录；源文件在打包期间变化、路径越界、伪造图片或摘要不符时安全失败，并返回可操作的原因。

### P2 · 常规

#### 修复

- 新建或实际未保存 Key 的 API 供应商不再允许保存；同一 origin 内修改 Base URL 会继续安全复用隐藏 Key，修改协议、域名或端口时会显示原、新 origin 风险提示，由用户选择返回填写新 Key，或明确保留原 Key 并保存，不再静默清空导致供应商不可用。
- API 设置保存成功后立即从浏览器状态清除明文 Key；复制供应商只允许在相同 origin 复用隐藏 Key，跨 origin 复制继续拒绝。
- 点击生成后仍在后台锁定重复提交，但按钮不再短暂变灰、切换“提交中”文字或闪烁；原有生成快捷键提示保持可见，同一次服务端响应到达前的重复点击只提交一个任务。
- 备份失败状态会显示稳定、可定位的原因；备份就绪后“下载备份”提升为带下载图标的主操作，创建新备份降为次级操作。

#### 兼容性/安装/打包/更新

- 本版不新增运行时依赖或数据库迁移。现有用户配置存储、请求策略、任务数据库和图片数据格式保持兼容；如未使用新备份恢复模板缩略图，回退到 `v0.8.3` 无需转换本地数据。

#### 已知问题

- macOS 标准 DMG 和 portable zip 仍未签名、未 notarize；如果系统拦截启动，请按下方说明使用右键或 Control-click 打开。Windows 标准 ZIP 仍需手动替换程序文件。

### P3 · 低影响

#### 工程与文档

- 同步全部 `14` 种界面的备份恢复安全文案、用户文档、设计合同和缓存版本，并补充备份格式、分块上传、事务恢复、数据锁、图库与模板素材、API 凭据以及生成按钮防重提交的自动验证。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-0.8.4.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.4/iLab-GPT-CONJURE-macos-arm64-0.8.4.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.4/iLab-GPT-CONJURE-macos-arm64-0.8.4.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-0.8.4.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.4/iLab-GPT-CONJURE-macos-x64-0.8.4.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.4/iLab-GPT-CONJURE-macos-x64-0.8.4.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_0.8.4.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.4/iLab-GPT-CONJURE-windows-x64_0.8.4.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.4/iLab-GPT-CONJURE-windows-x64_0.8.4.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.8.4.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.4/ilab-gpt-conjure_windows_portable_x64_0.8.4.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.4/ilab-gpt-conjure_windows_portable_x64_0.8.4.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.8.4.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.4/ilab-gpt-conjure_macos_portable_arm64_0.8.4.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.4/ilab-gpt-conjure_macos_portable_arm64_0.8.4.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.8.4.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.4/ilab-gpt-conjure_macos_portable_x64_0.8.4.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.4/ilab-gpt-conjure_macos_portable_x64_0.8.4.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v0.8.4/latest.json)

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
