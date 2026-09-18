# 下载 / Releases

当前正式版本：[v0.9.2](https://github.com/kadevin/ilab-conjure/releases/tag/v0.9.2)

## 版本说明

当前版本：`v0.9.2`。这是一次安全、可靠性与性能更新，重点保护本地任务和登录数据，修复备份恢复与 macOS portable 更新，并改善大量任务和大图编辑时的响应。建议所有用户升级，尤其是使用局域网共享、历史备份、macOS portable 或大图编辑的用户。

受影响平台：macOS 与 Windows 的标准版和 portable 一键包；WebUI 修复适用于桌面和手机浏览器。portable 更新器修复仅涉及 macOS。

必要操作与数据迁移：升级前退出旧实例，升级后重启服务并刷新已打开的页面。旧版 macOS portable 的更新脚本可能在替换自身运行环境时中断，首次升级到本版建议手动下载完整包，在退出旧实例后保留并迁移原 `data/`；不要先删除旧包或备份。任务索引会自动增加辅助结构并在首次需要时重建全文搜索索引，大型历史库首次启动可能稍慢；索引升级不会改写原始任务、图片和设置。

本版详情：

### P1 · 重要

#### 安全与必须操作

- **加强任务删除的数据边界。** 删除前完整校验任务标识、任务归属及存储路径，防止异常请求影响未选中的任务或其他本地文件。
- **修复粘贴外部富文本时的安全问题。** 提示词编辑器安全提取纯文本，并加强页面脚本限制，避免剪贴板内容触发非预期行为。
- **加强供应商结果图片下载的地址校验。** 对间接图片地址和跳转进行检查，阻止意外访问本机或内网服务；用户明确配置的本地供应商仍支持同源图片下载。
- **收紧局域网共享的访问主机校验。** 使用设置页提供的 LAN 地址、本机名称或明确配置的监听名称访问；任意自定义 DNS 别名可能不再被接受。局域网共享仍仅适用于可信网络。

#### 变更与优化

- **减少异常历史记录造成的反复卡顿。** 已尝试修复但仍缺少信息的记录不再在每次查询时重复读取，并避免多个请求重复执行同一批修复，让后续历史查询保持轻快。
- **降低图片编辑撤销历史的内存占用。** 未发生像素变化的操作共享图像副本，关闭编辑器或淘汰历史时释放资源；在最多 30 个历史状态之外增加内存预算，大图或多图层场景可能保留较少步骤，但至少保留一步撤销。
- **改善大面积填充时的页面响应。** 填充计算移到后台，减少主界面阻塞；保存会等待填充完成，切换工具、撤销或关闭编辑器可取消待处理填充，避免提交半成品。
- **减少大量任务下的队列刷新开销。** 多个实时连接共用未变化的队列快照，耗时读取在后台线程处理，减少对其他请求的阻塞。
- **降低任务耗时显示的刷新成本。** 批量更新卡片计时，减少任务很多时反复查找页面元素造成的 CPU 开销，保留原有显示精度。
- **加快大型历史库的全文搜索索引维护。** 精确定位需要更新的记录，跳过搜索文本未变化的重复写入，降低任务数量增加后的索引更新成本。

#### 修复

- **修复查看、归档或取消任务时覆盖并发生成结果的问题。** 状态更新统一读取最新记录后保存，避免完成数量回退、后续图片暂时不可见，以及删除后被旧操作重新写回。
- **修复历史备份恢复时丢失合法提示词的问题。** 以斜杠、路径或本地地址形式开头的普通文本，以及多行和 Unicode 提示词，恢复后保留原内容。
- **修复登录状态写入失败时可能损坏登录文件的问题。** 刷新登录状态采用原子保存，磁盘或替换失败时保留完整旧文件；若上游已轮换凭据，仍可能需要重新登录。

#### 兼容性/安装/打包/更新

- **修复 macOS portable 更新和回滚中断的问题。** 替换应用及运行环境后，路径检查与回滚继续可用，失败时可恢复旧程序并保留 `data/`。本修复随新包交付，旧包首次升级请按上方手动安装提示操作。

### P2 · 常规

#### 已知问题

- 大型历史库首次索引升级或首次处理一批异常旧记录仍可能短暂停顿；本版主要消除重复工作，不承诺首次维护无等待。
- 超大、多图层图片仍可能占用较多内存。撤销预算按像素副本计算；为保留当前状态和至少一步撤销，必要时允许超出预算。填充前后仍有像素读写开销，低配置设备可能短暂停顿。
- 直接在磁盘手工修改任务 JSON 后，可能需要重建索引；应用内正常操作会更新索引和缓存。

### P3 · 低影响

#### 工程与文档

- 拆分历史页的筛选、分页、选择、详情与渲染职责，保留既有滚动窗口、多选、快捷键、备份和导入能力。
- 拆分任务列表、图片编辑、供应商设置、备份校验、存储扫描与启动器更新校验模块，便于后续维护与定位回归；没有新增运行时依赖。
- 补充安全边界、并发状态、备份文本保留、撤销内存、后台填充和大量任务场景的回归验证，并更新设计、安全和中英文下载说明。

## 推荐下载

| 平台 | 推荐给 | 下载 | SHA256 |
| --- | --- | --- | --- |
| macOS Apple Silicon | 新用户，M1/M2/M3/M4 | [iLab-GPT-CONJURE-macos-arm64-0.9.2.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.2/iLab-GPT-CONJURE-macos-arm64-0.9.2.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.2/iLab-GPT-CONJURE-macos-arm64-0.9.2.dmg.sha256.txt) |
| macOS Intel | 新用户，Intel x64 | [iLab-GPT-CONJURE-macos-x64-0.9.2.dmg](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.2/iLab-GPT-CONJURE-macos-x64-0.9.2.dmg) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.2/iLab-GPT-CONJURE-macos-x64-0.9.2.dmg.sha256.txt) |
| Windows x64 | 新用户，Windows 10/11 x64 | [iLab-GPT-CONJURE-windows-x64_0.9.2.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.2/iLab-GPT-CONJURE-windows-x64_0.9.2.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.2/iLab-GPT-CONJURE-windows-x64_0.9.2.zip.sha256.txt) |

标准包数据目录：

- macOS：`~/Library/Application Support/iLab GPT CONJURE/`
- Windows：`%APPDATA%\iLab GPT CONJURE\`

包含更新助手的 macOS 标准 App 会校验 signed `latest.json` 与 DMG SHA256，并在用户确认后自动覆盖、失败回滚和重新启动；`v0.6.1` 及更早的 macOS 标准 App 需要先手动安装当前版本一次，Windows 标准 ZIP 仍手动替换。

## 免安装一键包

| 平台 | 适用设备 | 下载 | SHA256 |
| --- | --- | --- | --- |
| Windows x64 | Windows 10/11 x64 | [ilab-gpt-conjure_windows_portable_x64_0.9.2.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.2/ilab-gpt-conjure_windows_portable_x64_0.9.2.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.2/ilab-gpt-conjure_windows_portable_x64_0.9.2.zip.sha256.txt) |
| macOS Apple Silicon | M1/M2/M3/M4 | [ilab-gpt-conjure_macos_portable_arm64_0.9.2.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.2/ilab-gpt-conjure_macos_portable_arm64_0.9.2.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.2/ilab-gpt-conjure_macos_portable_arm64_0.9.2.zip.sha256.txt) |
| macOS Intel | Intel x64 | [ilab-gpt-conjure_macos_portable_x64_0.9.2.zip](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.2/ilab-gpt-conjure_macos_portable_x64_0.9.2.zip) | [sha256](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.2/ilab-gpt-conjure_macos_portable_x64_0.9.2.zip.sha256.txt) |

portable 自动更新 manifest：

- [latest.json](https://github.com/kadevin/ilab-conjure/releases/download/v0.9.2/latest.json)

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
