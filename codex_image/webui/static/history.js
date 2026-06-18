(() => {
  // codex_image/webui/frontend/src/state.ts
  function getLegacyBridge() {
    const bridge = window.__codexImageWebUI;
    if (!bridge) {
      throw new Error("WebUI legacy bridge is not initialized");
    }
    return bridge;
  }

  // codex_image/webui/frontend/src/i18n.ts
  var LOCALE_STORAGE_KEY = "codex-image-locale-preference";
  var LOCALE_CHANGE_EVENT = "codex-image-locale-change";
  var DEFAULT_LOCALE = "zh-CN";
  var LOCALES = ["zh-CN", "en"];
  var DICTIONARIES = {
    "zh-CN": {
      "app.newTask": "\u65B0\u5EFA",
      "app.newTaskAria": "\u65B0\u5EFA\u5BF9\u8BDD",
      "sidebar.searchPlaceholder": "\u641C\u7D22\u63D0\u793A\u8BCD\u6216\u4EFB\u52A1 ID",
      "sidebar.filters": "\u4EFB\u52A1\u7B5B\u9009",
      "sidebar.allRatios": "\u5168\u90E8\u6BD4\u4F8B",
      "sidebar.allOrientations": "\u5168\u90E8\u65B9\u5411",
      "sidebar.allModes": "\u5168\u90E8\u6A21\u5F0F",
      "sidebar.allResolutions": "\u5168\u90E8\u5206\u8FA8\u7387",
      "sidebar.activeTasks": "\u8FDB\u884C\u4E2D\u4EFB\u52A1",
      "sidebar.topAnchors": "\u9876\u90E8\u65F6\u95F4\u5BFC\u822A",
      "sidebar.bottomAnchors": "\u5E95\u90E8\u65F6\u95F4\u5BFC\u822A",
      "sidebar.resize": "\u8C03\u6574\u4FA7\u680F\u5BBD\u5EA6",
      "batch.selected": "\u5DF2\u9009\u62E9 0 \u4E2A",
      "batch.selectedCount": "\u5DF2\u9009\u62E9 {count} \u4E2A",
      "batch.archivedCount": "\u5DF2\u5F52\u6863 {count} \u4E2A\u4F1A\u8BDD",
      "batch.archiveFailed": "\u6279\u91CF\u5F52\u6863\u5931\u8D25",
      "batch.runningCannotDeleteSelected": "\u9009\u4E2D\u7684\u4F1A\u8BDD\u6B63\u5728\u8FD0\u884C\uFF0C\u4E0D\u80FD\u5220\u9664",
      "batch.deleteTitle": "\u5220\u9664 {count} \u4E2A\u4F1A\u8BDD\uFF1F",
      "batch.deleteMessage": "\u4F1A\u540C\u65F6\u5220\u9664\u672C\u5730\u56FE\u7247\u6587\u4EF6\u3002",
      "batch.deleteSkippedDetail": "{count} \u4E2A\u8FD0\u884C\u4E2D\u4EFB\u52A1\u4F1A\u4FDD\u7559",
      "batch.deleteSkippedSuffix": "\uFF0C{count} \u4E2A\u8FD0\u884C\u4E2D\u672A\u5220\u9664",
      "batch.deletedCount": "\u5DF2\u5220\u9664 {count} \u4E2A\u4F1A\u8BDD{skipped}",
      "batch.deleteFailed": "\u6279\u91CF\u5220\u9664\u5931\u8D25",
      "action.archive": "\u5F52\u6863",
      "action.delete": "\u5220\u9664",
      "action.cancel": "\u53D6\u6D88",
      "action.clear": "\u6E05\u7A7A",
      "action.paste": "\u7C98\u8D34",
      "action.find": "\u67E5\u627E",
      "action.replace": "\u66FF\u6362",
      "action.close": "\u5173\u95ED",
      "action.confirm": "\u786E\u8BA4",
      "action.confirmQuestion": "\u786E\u8BA4\u64CD\u4F5C\uFF1F",
      "action.refresh": "\u21BB \u5237\u65B0",
      "action.save": "\u4FDD\u5B58",
      "action.add": "\u6DFB\u52A0",
      "action.new": "\u65B0\u5EFA",
      "action.import": "\u5BFC\u5165",
      "action.export": "\u5BFC\u51FA",
      "queue.empty": "\u6682\u65E0\u6392\u961F",
      "queue.emptyAria": "\u961F\u5217\u72B6\u6001\uFF1A\u6682\u65E0\u6392\u961F",
      "queue.jumpTitle": "\u8DF3\u8F6C\u5230\u8FDB\u884C\u4E2D\u4EFB\u52A1",
      "queue.emptyTitle": "\u6682\u65E0\u6392\u961F\u4EFB\u52A1",
      "queue.channel": "\u901A\u9053 {count}",
      "queue.availableChannels": "\u53EF\u7528\u901A\u9053 {usable}/{total}",
      "queue.dispatching": "\u8C03\u5EA6\u4E2D \xB7 \u7B49\u5F85 {waiting}",
      "queue.runningWaiting": "\u8FD0\u884C {running} \xB7 \u7B49\u5F85 {waiting}",
      "queue.statusLabel": "\u961F\u5217\u72B6\u6001\uFF1A{text} \xB7 {channelText}\u3002\u70B9\u51FB\u8DF3\u8F6C\u5230\u8FDB\u884C\u4E2D\u4EFB\u52A1",
      "queue.runningActions": "\u8FD0\u884C\u4EFB\u52A1\u961F\u5217\u64CD\u4F5C",
      "queue.waitingActions": "\u7B49\u5F85\u4EFB\u52A1\u961F\u5217\u64CD\u4F5C",
      "queue.cancelRunning": "\u53D6\u6D88",
      "queue.cancelRunningTitle": "\u53D6\u6D88\u8FD0\u884C\u4EFB\u52A1",
      "queue.dragWaiting": "\u62D6\u52A8\u8C03\u6574\u7B49\u5F85\u987A\u5E8F",
      "queue.dragSort": "\u62D6\u52A8\u6392\u5E8F",
      "queue.moveUp": "\u4E0A",
      "queue.moveUpTitle": "\u4E0A\u79FB\u7B49\u5F85\u4EFB\u52A1",
      "queue.moveDown": "\u4E0B",
      "queue.moveDownTitle": "\u4E0B\u79FB\u7B49\u5F85\u4EFB\u52A1",
      "queue.promote": "\u9876",
      "queue.promoteTitle": "\u7F6E\u9876\u7B49\u5F85\u4EFB\u52A1",
      "queue.promoteFailed": "\u7F6E\u9876\u5931\u8D25",
      "queue.deleteWaitingShort": "\u5220",
      "queue.deleteWaitingTitle": "\u5220\u9664\u7B49\u5F85\u4EFB\u52A1",
      "queue.deleteWaitingTitleConfirm": "\u5220\u9664\u7B49\u5F85\u4EFB\u52A1\uFF1F",
      "queue.deleteWaitingMessage": "\u4F1A\u4ECE\u961F\u5217\u548C\u5386\u53F2\u5217\u8868\u4E2D\u79FB\u9664\u3002",
      "queue.deleteQueuedFailed": "\u5220\u9664\u961F\u5217\u4EFB\u52A1\u5931\u8D25",
      "queue.queuedDeleted": "\u961F\u5217\u4EFB\u52A1\u5DF2\u5220\u9664",
      "queue.cancelRunningConfirm": "\u53D6\u6D88\u4EFB\u52A1",
      "queue.cancelRunningTitleConfirm": "\u53D6\u6D88\u8FD0\u884C\u4EFB\u52A1\uFF1F",
      "queue.cancelRunningMessage": "\u5F53\u524D\u4EFB\u52A1\u4F1A\u505C\u6B62\uFF0C\u5386\u53F2\u8BB0\u5F55\u4F1A\u4FDD\u7559\u3002",
      "queue.cancelRunningFailed": "\u53D6\u6D88\u4EFB\u52A1\u5931\u8D25",
      "queue.runningCancelled": "\u4EFB\u52A1\u5DF2\u53D6\u6D88",
      "queue.reorderFailed": "\u961F\u5217\u6392\u5E8F\u5931\u8D25",
      "queue.realtimeUpdateFailed": "\u5B9E\u65F6\u72B6\u6001\u66F4\u65B0\u5931\u8D25",
      "queue.realtimeDisconnected": "\u5B9E\u65F6\u72B6\u6001\u8FDE\u63A5\u5DF2\u65AD\u5F00\uFF0C\u5237\u65B0\u9875\u9762\u53EF\u6062\u590D",
      "queue.readFailed": "\u961F\u5217\u8BFB\u53D6\u5931\u8D25",
      "status.waiting": "\u7B49\u5F85\u4EFB\u52A1",
      "status.shownActiveTasks": "\u5DF2\u663E\u793A\u8FDB\u884C\u4E2D\u4EFB\u52A1",
      "status.jsonCopied": "JSON \u5DF2\u590D\u5236",
      "taskStatus.submitting": "\u63D0\u4EA4\u4E2D",
      "taskStatus.running": "\u751F\u6210\u4E2D",
      "taskStatus.runningWithElapsed": "\u751F\u6210\u4E2D \xB7 {elapsed}",
      "taskStatus.completed": "\u5DF2\u5B8C\u6210",
      "taskStatus.partialFailed": "\u90E8\u5206\u5931\u8D25",
      "taskStatus.failed": "\u5931\u8D25",
      "taskStatus.queued": "\u6392\u961F\u4E2D",
      "taskStatus.unknown": "\u672A\u77E5\u72B6\u6001",
      "taskStatus.task": "\u4EFB\u52A1",
      "taskStatus.connectionInterrupted": "\u8FDE\u63A5\u4E2D\u65AD",
      "taskStatus.lastFailed": "\u4E0A\u6B21\u5931\u8D25",
      "taskStatus.waitingRetry": "{reason}\uFF0C\u7B49\u5F85\u91CD\u8BD5\uFF08\u7B2C {attempt}/{max} \u6B21\u5C1D\u8BD5\uFF09",
      "taskStatus.retrying": "{reason}\uFF0C\u91CD\u8BD5\u4E2D\uFF08\u7B2C {attempt}/{max} \u6B21\u5C1D\u8BD5\uFF09",
      "taskStatus.nonRetryableAttempt": "\u7B2C {attempt}/{max} \u6B21\uFF0C\u4E0D\u53EF\u91CD\u8BD5",
      "taskStatus.manualRetryAvailable": "\u5DF2\u505C\u6B62\uFF0C\u53EF\u624B\u52A8\u91CD\u8BD5\u5931\u8D25\u56FE\u7247",
      "taskStatus.runtime": "\u8017\u65F6 {duration}",
      "taskStatus.runtimeCompleted": "\u8017\u65F6 {duration} \xB7 \u5B8C\u6210 {time}",
      "taskStatus.completedAt": "\u5B8C\u6210 {time}",
      "taskCard.count": "{count} \u5F20",
      "taskCard.successCount": "\u6210\u529F {count}",
      "taskCard.failedCount": "\u5931\u8D25 {count}",
      "taskCard.runningCount": "\u751F\u6210\u4E2D {count}",
      "taskCard.waitingCount": "\u7B49\u5F85 {count}",
      "taskCard.textToImageThumb": "\u6587\u751F\u56FE\u4EFB\u52A1\u7F29\u7565\u56FE",
      "taskCard.imageToImageThumb": "\u56FE\u751F\u56FE\u4EFB\u52A1\u7F29\u7565\u56FE",
      "taskCard.failedThumb": "\u4EFB\u52A1\u5931\u8D25",
      "taskCard.textBadge": "\u6587",
      "taskMode.edit": "\u7F16\u8F91",
      "taskMode.generate": "\u751F\u6210",
      "document.generatingQueue": "\u751F\u6210\u4E2D \xB7 \u961F\u5217 {total}",
      "document.queuedWaiting": "\u6392\u961F\u4E2D \xB7 \u7B49\u5F85 {count}",
      "runFeedback.editing": "\u7F16\u8F91\u4E2D",
      "runFeedback.generating": "\u751F\u6210\u4E2D",
      "runFeedback.status": "{action}\uFF0C\u8BA1\u65F6 {elapsed}",
      "footer.archive": "\u4F1A\u8BDD\u5F52\u6863",
      "footer.archiveCount": "\u4F1A\u8BDD\u5F52\u6863 {count}",
      "footer.historyLibrary": "\u5386\u53F2\u5E93",
      "historyLibrary.openFull": "\u6253\u5F00\u5B8C\u6574\u5386\u53F2\u5E93",
      "history.documentTitle": "\u5386\u53F2\u5E93 - iLab GPT CONJURE",
      "history.back": "\u8FD4\u56DE\u751F\u6210\u9875",
      "history.title": "\u5386\u53F2\u5E93",
      "history.loading": "\u8F7D\u5165\u4E2D",
      "history.total": "{total} \u4E2A\u4EFB\u52A1 \xB7 {archived} \u5DF2\u5F52\u6863",
      "history.search": "\u641C\u7D22",
      "history.searchPlaceholder": "\u641C\u7D22\u63D0\u793A\u8BCD\u6216\u4EFB\u52A1 ID",
      "history.clear": "\u6E05\u7A7A",
      "history.month": "\u6708\u4EFD",
      "history.status": "\u72B6\u6001",
      "history.promptMode": "\u63D0\u793A\u8BCD\u6A21\u5F0F",
      "history.size": "\u5C3A\u5BF8",
      "history.quality": "\u8D28\u91CF",
      "history.ratio": "\u6BD4\u4F8B",
      "history.orientation": "\u65B9\u5411",
      "history.backend": "\u540E\u7AEF",
      "history.provider": "\u4F9B\u5E94\u5546",
      "history.archived": "\u5F52\u6863",
      "history.all": "\u5168\u90E8",
      "history.allMonths": "\u5168\u90E8\u6708\u4EFD",
      "history.allStatuses": "\u5168\u90E8\u72B6\u6001",
      "history.allPromptModes": "\u5168\u90E8\u6A21\u5F0F",
      "history.allSizes": "\u5168\u90E8\u5C3A\u5BF8",
      "history.allQualities": "\u5168\u90E8\u8D28\u91CF",
      "history.allRatios": "\u5168\u90E8\u6BD4\u4F8B",
      "history.ratioOther": "\u5176\u4ED6",
      "history.allOrientations": "\u5168\u90E8\u65B9\u5411",
      "history.allBackends": "\u5168\u90E8\u540E\u7AEF",
      "history.allProviders": "\u5168\u90E8\u4F9B\u5E94\u5546",
      "history.unarchived": "\u672A\u5F52\u6863",
      "history.archivedOnly": "\u5DF2\u5F52\u6863",
      "history.tasksAria": "\u5386\u53F2\u4EFB\u52A1",
      "history.taskListTitle": "\u5386\u53F2\u4EFB\u52A1",
      "history.browseNewest": "\u6309\u65F6\u95F4\u5012\u5E8F\u6D4F\u89C8",
      "history.view": "\u89C6\u56FE",
      "history.grid": "\u7F51\u683C",
      "history.list": "\u5217\u8868",
      "history.sort": "\u6392\u5E8F",
      "history.newest": "\u6700\u65B0\u4F18\u5148",
      "history.oldest": "\u6700\u65E9\u4F18\u5148",
      "history.refresh": "\u5237\u65B0",
      "history.selectedCount": "\u5DF2\u9009\u62E9 {count} \u4E2A\u4EFB\u52A1",
      "history.confirmDelete": "\u786E\u8BA4\u5220\u9664",
      "history.detail": "\u4EFB\u52A1\u8BE6\u60C5",
      "history.detailTitle": "\u5386\u53F2\u4EFB\u52A1",
      "history.closeDetail": "\u5173\u95ED\u4EFB\u52A1\u8BE6\u60C5",
      "history.resizeFilters": "\u8C03\u6574\u7B5B\u9009\u680F\u5BBD\u5EA6",
      "history.resizeDetail": "\u8C03\u6574\u8BE6\u60C5\u680F\u5BBD\u5EA6",
      "history.detailEmpty": "\u9009\u62E9\u4E00\u4E2A\u5386\u53F2\u4EFB\u52A1\u67E5\u770B\u8BE6\u60C5",
      "history.loadingDetail": "\u8F7D\u5165\u8BE6\u60C5...",
      "history.loadMore": "\u7EE7\u7EED\u8F7D\u5165",
      "history.loadingMore": "\u8F7D\u5165\u4E2D...",
      "history.noMore": "\u6CA1\u6709\u66F4\u591A\u4EFB\u52A1",
      "history.loadFailed": "\u8F7D\u5165\u5931\u8D25\uFF0C\u5237\u65B0\u6216\u7EE7\u7EED\u6EDA\u52A8\u91CD\u8BD5",
      "history.summaryFailed": "\u6458\u8981\u8F7D\u5165\u5931\u8D25",
      "history.tasksFailed": "\u5386\u53F2\u4EFB\u52A1\u8F7D\u5165\u5931\u8D25",
      "history.detailFailed": "\u8BE6\u60C5\u8F7D\u5165\u5931\u8D25",
      "history.noMatches": "\u6682\u65E0\u5339\u914D\u4EFB\u52A1",
      "history.loadedCount": "{count} \u6761\u5DF2\u8F7D\u5165",
      "history.windowNotice": "\u5217\u8868\u7A97\u53E3\u5DF2\u9650\u5236\u4E3A {count} \u6761\uFF1B\u4E0A\u4E0B\u6EDA\u52A8\u4F1A\u6309\u9700\u6062\u590D\u76F8\u90BB\u4EFB\u52A1",
      "history.selectTask": "\u9009\u62E9\u4EFB\u52A1",
      "history.viewing": "\u67E5\u770B\u4E2D",
      "history.noPreview": "\u6682\u65E0\u53EF\u9884\u89C8\u56FE\u7247",
      "history.downloadAll": "\u6253\u5305\u4E0B\u8F7D",
      "history.downloadSelected": "\u4E0B\u8F7D\u7CBE\u9009",
      "history.deleteUnselected": "\u5220\u9664\u672A\u7CBE\u9009",
      "history.confirmDeleteUnselected": "\u786E\u8BA4\u5220\u9664\u672A\u7CBE\u9009",
      "history.selected": "\u5DF2\u7CBE\u9009",
      "history.select": "\u7CBE\u9009",
      "history.downloadIndex": "\u4E0B\u8F7D {index}",
      "history.addReference": "\u52A0\u5165\u53C2\u8003\u56FE",
      "history.outputActions": "\u7ED3\u679C\u56FE\u64CD\u4F5C",
      "history.inputReferences": "\u8F93\u5165\u53C2\u8003\u56FE",
      "history.inputReferenceIndex": "\u8F93\u5165\u53C2\u8003\u56FE {index}",
      "history.copyPrompt": "\u590D\u5236\u63D0\u793A\u8BCD",
      "history.copyPrompts": "\u590D\u5236\u63D0\u793A\u8BCD",
      "history.copyPromptShort": "\u590D\u5236",
      "history.copyPromptPanel": "\u590D\u5236{title}",
      "history.copyOutputPromptPanel": "\u590D\u5236\u56FE {index} \u4F18\u5316\u63D0\u793A\u8BCD",
      "history.copyTaskIds": "\u590D\u5236\u4EFB\u52A1 ID",
      "history.reuseTask": "\u751F\u6210\u9875\u67E5\u770B",
      "history.downloadTask": "\u4E0B\u8F7D",
      "history.downloadSelectedTasks": "\u6279\u91CF\u4E0B\u8F7D",
      "history.contextMenuLabel": "\u5386\u53F2\u4EFB\u52A1\u53F3\u952E\u83DC\u5355",
      "history.promptCopied": "\u63D0\u793A\u8BCD\u5DF2\u590D\u5236",
      "history.promptsCopied": "\u5DF2\u590D\u5236 {count} \u4E2A\u4EFB\u52A1\u7684\u63D0\u793A\u8BCD",
      "history.taskIdsCopied": "\u5DF2\u590D\u5236 {count} \u4E2A\u4EFB\u52A1 ID",
      "history.promptCopiedShort": "\u5DF2\u590D\u5236",
      "history.promptCopyFailed": "\u590D\u5236\u63D0\u793A\u8BCD\u5931\u8D25",
      "history.promptCopyFailedShort": "\u5931\u8D25",
      "history.noPrompt": "\u8FD9\u4E2A\u4EFB\u52A1\u6CA1\u6709\u53EF\u590D\u5236\u7684\u63D0\u793A\u8BCD",
      "history.noPromptShort": "\u65E0\u5185\u5BB9",
      "history.downloadStarted": "\u5DF2\u5F00\u59CB\u4E0B\u8F7D",
      "history.batchDownloadStarted": "\u5DF2\u5F00\u59CB\u4E0B\u8F7D {count} \u4E2A\u4EFB\u52A1",
      "history.noDownloadableOutputs": "\u6CA1\u6709\u53EF\u4E0B\u8F7D\u56FE\u7247",
      "history.confirmDeleteSelected": "\u786E\u8BA4\u5220\u9664\u5DF2\u9009",
      "history.openPreview": "\u653E\u5927\u9884\u89C8",
      "history.closePreview": "\u5173\u95ED\u9884\u89C8",
      "history.untitled": "Untitled",
      "history.promptCompare": "\u63D0\u793A\u8BCD\u5BF9\u6BD4",
      "history.promptOriginal": "\u539F\u59CB\u63D0\u793A\u8BCD",
      "history.promptSubmitted": "\u4F18\u5316\u63D0\u793A\u8BCD",
      "history.promptRevised": "\u4F18\u5316\u7ED3\u679C",
      "history.outputRevisedPromptTitle": "\u56FE {index} \u4F18\u5316\u63D0\u793A\u8BCD",
      "history.outputRevisedPromptNotice": "\u6BCF\u5F20\u56FE\u7684\u4F18\u5316\u63D0\u793A\u8BCD\u4E0D\u540C\uFF0C\u89C1\u5BF9\u5E94\u56FE\u7247\u4E0B\u65B9\u3002",
      "history.promptEmpty": "\u6682\u65E0\u5185\u5BB9",
      "history.promptMode.strict": "\u4FDD\u771F",
      "history.promptMode.original": "\u539F\u59CB",
      "history.promptMode.off": "\u521B\u610F",
      "history.quality.high": "\u9AD8",
      "history.quality.medium": "\u4E2D",
      "history.quality.low": "\u4F4E",
      "history.quality.auto": "\u81EA\u52A8",
      "footer.batch": "\u6279\u91CF\u7BA1\u7406",
      "footer.storage": "\u5B58\u50A8\u8BBE\u7F6E",
      "footer.apiStatus": "API \u72B6\u6001: \u6B63\u5E38",
      "footer.version": "\u7248\u672C {version}",
      "footer.versionInfo": "\u7248\u672C\u4FE1\u606F",
      "footer.versionLoading": "\u7248\u672C ...",
      "footer.updateBadge": "\u6709\u65B0\u7248\u672C",
      "footer.updateAvailable": "\u6709\u65B0\u7248\u672C {version}",
      "version.title": "\u7248\u672C\u4E0E\u66F4\u65B0",
      "version.loading": "\u6B63\u5728\u8BFB\u53D6\u7248\u672C\u72B6\u6001",
      "version.current": "\u5F53\u524D\u7248\u672C",
      "version.latest": "\u6700\u65B0\u7248\u672C",
      "version.source": "\u8FD0\u884C\u65B9\u5F0F",
      "version.sourcePortable": "\u4E00\u952E\u5305",
      "version.sourceSource": "\u6E90\u7801\u8FD0\u884C",
      "version.upToDate": "\u5F53\u524D\u5DF2\u7ECF\u662F\u6700\u65B0\u7248",
      "version.updateAvailable": "\u53D1\u73B0\u65B0\u7248\u672C {version}\u3002\u5173\u95ED WebUI \u670D\u52A1\u7A97\u53E3\u540E\u8FD0\u884C\u66F4\u65B0\u5668\u5373\u53EF\u5347\u7EA7\u3002",
      "version.noUpdater": "\u5F53\u524D\u4E0D\u662F\u4E00\u952E\u5305\u8FD0\u884C\uFF0C\u4E0D\u80FD\u81EA\u52A8\u542F\u52A8\u66F4\u65B0\u5668\u3002",
      "version.openUpdater": "\u542F\u52A8\u66F4\u65B0\u5668",
      "version.release": "\u67E5\u770B\u53D1\u5E03\u9875",
      "version.updaterStarted": "\u66F4\u65B0\u5668\u5DF2\u542F\u52A8\u3002\u8BF7\u5173\u95ED\u5F53\u524D WebUI \u670D\u52A1\u7A97\u53E3\uFF0C\u518D\u6309\u66F4\u65B0\u5668\u63D0\u793A\u64CD\u4F5C\u3002",
      "version.updaterFailed": "\u542F\u52A8\u66F4\u65B0\u5668\u5931\u8D25\uFF0C\u8BF7\u624B\u52A8\u8FD0\u884C\u5305\u5185\u66F4\u65B0\u811A\u672C\u3002",
      "notifications.title": "\u4EFB\u52A1\u901A\u77E5",
      "notifications.unread": "\u4EFB\u52A1\u901A\u77E5\uFF0C{count} \u6761\u672A\u8BFB",
      "notifications.unreadSummary": "{count} \u672A\u8BFB",
      "notifications.empty": "\u6682\u65E0\u4EFB\u52A1\u901A\u77E5",
      "notifications.taskFailed": "\u4EFB\u52A1\u5931\u8D25",
      "notifications.taskPartial": "\u4EFB\u52A1\u90E8\u5206\u5B8C\u6210",
      "notifications.taskCompleted": "\u4EFB\u52A1\u5DF2\u5B8C\u6210",
      "notifications.generationFailed": "\u751F\u6210\u5931\u8D25",
      "notifications.successCount": "{count} \u5F20\u6210\u529F",
      "notifications.resultAvailable": "\u6709\u7ED3\u679C\u53EF\u67E5\u770B",
      "notifications.failedCount": "{count} \u5F20\u5931\u8D25",
      "notifications.systemUnsupported": "\u5F53\u524D\u6D4F\u89C8\u5668\u4E0D\u652F\u6301\u7CFB\u7EDF\u901A\u77E5",
      "notifications.systemBlocked": "\u7CFB\u7EDF\u901A\u77E5\u5DF2\u88AB\u6D4F\u89C8\u5668\u963B\u6B62\uFF0C\u9700\u8981\u5728\u6D4F\u89C8\u5668\u8BBE\u7F6E\u91CC\u5F00\u542F",
      "notifications.systemDenied": "\u7CFB\u7EDF\u901A\u77E5\u672A\u5F00\u542F",
      "notifications.systemEnabled": "\u7CFB\u7EDF\u901A\u77E5\u5DF2\u5F00\u542F",
      "notifications.taskMissing": "\u4EFB\u52A1\u4E0D\u5B58\u5728\u6216\u5DF2\u5220\u9664",
      "theme.label": "\u4E3B\u9898\u6A21\u5F0F",
      "theme.system": "\u8DDF\u968F",
      "theme.light": "\u6D45\u8272",
      "theme.dark": "\u6DF1\u8272",
      "language.label": "\u8BED\u8A00 / Language",
      "language.zh": "\u4E2D",
      "language.en": "EN",
      "auth.label": "\u6388\u6743\u6765\u6E90",
      "auth.checking": "\u6388\u6743\u68C0\u67E5\u4E2D",
      "auth.missingCodexSession": "\u6CA1\u6709\u68C0\u6D4B\u5230 Codex \u767B\u5F55\u6001",
      "auth.switchFailed": "\u6388\u6743\u6765\u6E90\u5207\u6362\u5931\u8D25",
      "auth.sourceUnavailable": "{source} \u4E0D\u53EF\u7528",
      "auth.notActive": "\u672A\u751F\u6548",
      "api.settings": "API \u8BBE\u7F6E",
      "api.provider": "API \u4F9B\u5E94\u5546",
      "imageInput.title": "\u56FE\u50CF\u8F93\u5165",
      "imageInput.uploadAria": "\u70B9\u51FB\u3001\u62D6\u5165\u6216\u7C98\u8D34\u56FE\u7247",
      "imageInput.uploadFull": "\u70B9\u51FB\u3001\u62D6\u5165\u6216\u7C98\u8D34\u56FE\u7247",
      "imageInput.uploadCompact": "\u6DFB\u52A0\u56FE\u7247",
      "imageInput.uploadSubtitle": "\u652F\u6301\u591A\u5F20\u53C2\u8003\u56FE",
      "imageInput.recent": "\u6700\u8FD1\u4E0A\u4F20",
      "imageInput.recentBadge": "\u6700\u8FD1",
      "imageInput.uploadBadge": "\u4E0A\u4F20",
      "imageInput.addToGallery": "\u52A0\u5165\u56FE\u5E93",
      "imageInput.addToGalleryShort": "\u56FE\u5E93",
      "imageInput.removeImage": "\u79FB\u9664\u56FE\u7247",
      "imageInput.editedBadge": "\u5DF2\u7F16\u8F91",
      "imageInput.editImage": "\u7F16\u8F91{name}",
      "imageInput.deletedRecent": "\u6700\u8FD1\u4E0A\u4F20\u5DF2\u5220\u9664",
      "imageInput.deletedGallery": "\u56FE\u5E93\u56FE\u7247\u5DF2\u5220\u9664",
      "recentAssets.defaultName": "\u6700\u8FD1\u4E0A\u4F20",
      "recentAssets.use": "\u4F7F\u7528{name}",
      "recentAssets.delete": "\u5220\u9664{name}",
      "recentAssets.deleteTitle": "\u5220\u9664\u6700\u8FD1\u4E0A\u4F20\uFF1F",
      "recentAssets.deleteMessage": "\u4F1A\u4ECE\u300C\u6700\u8FD1\u4E0A\u4F20\u300D\u4E2D\u5220\u9664\u8FD9\u5F20\u56FE\u7247\u3002\u5982\u679C\u5B83\u5DF2\u88AB\u6DFB\u52A0\u5230\u5F53\u524D\u56FE\u50CF\u8F93\u5165\uFF0C\u4F1A\u4ECE\u5F53\u524D\u8F93\u5165\u4E2D\u79FB\u9664\uFF1B\u5386\u53F2\u4EFB\u52A1\u91CC\u5F15\u7528\u8FD9\u5F20\u6700\u8FD1\u4E0A\u4F20\u56FE\u7684\u8F93\u5165\u9884\u89C8\u4E5F\u4F1A\u5931\u6548\u3002\u4E0D\u4F1A\u5F71\u54CD\u516C\u7528\u56FE\u5E93\u3002",
      "recentAssets.loadFailed": "\u6700\u8FD1\u4E0A\u4F20\u8BFB\u53D6\u5931\u8D25",
      "recentAssets.deleteFailed": "\u6700\u8FD1\u4E0A\u4F20\u5220\u9664\u5931\u8D25",
      "recentAssets.deleted": "\u6700\u8FD1\u4E0A\u4F20\u5DF2\u5220\u9664",
      "inputSource.uploadFallback": "\u4E0A\u4F20\u56FE\u7247",
      "inputSource.galleryFallback": "\u56FE\u5E93\u56FE\u7247",
      "inputSource.focusPasteFallback": "{prefix}\uFF0C\u56FE\u7247\u8F93\u5165\u533A\u5DF2\u805A\u7126\uFF0C\u8BF7\u6309 {shortcut} \u7C98\u8D34\u56FE\u7247",
      "inputSource.pastedCount": "\u5DF2\u7C98\u8D34 {count} \u5F20\u526A\u8D34\u677F\u56FE\u7247",
      "inputSource.droppedCount": "\u5DF2\u6DFB\u52A0 {count} \u5F20\u62D6\u5165\u56FE\u7247",
      "inputSource.dropImagesOnly": "\u53EA\u80FD\u62D6\u5165\u56FE\u7247\u6587\u4EF6",
      "inputSource.clipboardUnsupported": "\u5F53\u524D\u6D4F\u89C8\u5668\u4E0D\u652F\u6301\u76F4\u63A5\u8BFB\u53D6\u526A\u8D34\u677F",
      "inputSource.clipboardEmpty": "\u6CA1\u6709\u8BFB\u5230\u526A\u8D34\u677F\u56FE\u7247",
      "inputSource.clipboardDenied": "\u6D4F\u89C8\u5668\u62D2\u7EDD\u76F4\u63A5\u8BFB\u53D6\u526A\u8D34\u677F",
      "inputSource.clipboardReadFailed": "\u65E0\u6CD5\u8BFB\u53D6\u526A\u8D34\u677F",
      "status.missingGalleryReference": "\u6709\u56FE\u5E93\u53C2\u8003\u56FE\u5DF2\u5220\u9664\uFF0C\u8BF7\u79FB\u9664\u540E\u518D\u751F\u6210",
      "status.missingRecentReference": "\u6709\u6700\u8FD1\u4E0A\u4F20\u53C2\u8003\u56FE\u5DF2\u5220\u9664\uFF0C\u8BF7\u79FB\u9664\u540E\u518D\u751F\u6210",
      "status.emptyPrompt": "\u8BF7\u8F93\u5165\u63D0\u793A\u8BCD",
      "status.editNeedsImage": "\u7F16\u8F91\u6A21\u5F0F\u81F3\u5C11\u9700\u8981 1 \u5F20\u56FE\u7247",
      "status.loadedTask": "\u5DF2\u8F7D\u5165\u4EFB\u52A1 {taskId}",
      "status.reusedTask": "\u5DF2\u5728\u751F\u6210\u9875\u6253\u5F00\u4EFB\u52A1 {taskId}",
      "status.loadingHistoryInputs": "\u6B63\u5728\u8F7D\u5165\u5386\u53F2\u8F93\u5165\u56FE...",
      "status.historyInputLoadFailed": "\u65E0\u6CD5\u8F7D\u5165\u5386\u53F2\u8F93\u5165\u56FE: {url}",
      "referenceCollector.alreadyStaged": "\u5DF2\u5728\u5F85\u52A0\u5165\u53C2\u8003\u56FE",
      "referenceCollector.staged": "\u5DF2\u6682\u5B58 {count} \u5F20\u53C2\u8003\u56FE",
      "referenceCollector.title": "\u5F85\u52A0\u5165\u53C2\u8003\u56FE \xB7 {count} \u5F20",
      "referenceCollector.addAll": "\u5168\u90E8\u52A0\u5165\u53C2\u8003\u56FE",
      "referenceCollector.itemFallback": "\u5F85\u52A0\u5165\u53C2\u8003\u56FE",
      "referenceCollector.remove": "\u79FB\u9664\u5F85\u52A0\u5165\u53C2\u8003\u56FE",
      "referenceCollector.cleared": "\u5F85\u52A0\u5165\u53C2\u8003\u56FE\u5DF2\u6E05\u7A7A",
      "referenceCollector.added": "\u5DF2\u52A0\u5165 {count} \u5F20\u53C2\u8003\u56FE",
      "referenceCollector.addFailed": "\u5F85\u52A0\u5165\u53C2\u8003\u56FE\u52A0\u5165\u5931\u8D25",
      "referenceCollector.readFailed": "\u56FE\u7247\u8BFB\u53D6\u5931\u8D25\uFF1A{status}",
      "gallery.quick": "\u5FEB\u901F\u9009\u62E9\u516C\u7528\u56FE\u5E93",
      "gallery.current": "\u5F53\u524D\u5206\u7C7B\u56FE\u5E93",
      "gallery.categories": "\u56FE\u5E93\u5206\u7C7B",
      "gallery.categoryPortrait": "\u4EBA\u50CF",
      "gallery.categoryCharacter": "\u89D2\u8272",
      "gallery.categoryProduct": "\u4EA7\u54C1",
      "gallery.categoryPortraitRole": "\u4EBA\u50CF\u53C2\u8003",
      "gallery.categoryCharacterRole": "\u89D2\u8272\u53C2\u8003",
      "gallery.categoryProductRole": "\u4EA7\u54C1\u53C2\u8003",
      "gallery.referenceRole": "\u53C2\u8003\u56FE",
      "gallery.manage": "\u7BA1\u7406\u516C\u7528\u5E93",
      "gallery.loadFailed": "\u56FE\u5E93\u8BFB\u53D6\u5931\u8D25",
      "gallery.imageOrderUpdateFailed": "\u66F4\u65B0\u56FE\u7247\u987A\u5E8F\u5931\u8D25",
      "gallery.imageOrderUpdated": "\u56FE\u7247\u987A\u5E8F\u5DF2\u66F4\u65B0",
      "gallery.categoryName": "\u5206\u7C7B\u540D\u79F0",
      "gallery.categoryPromptRole": "\u63D0\u793A\u8BCD\u7528\u9014",
      "gallery.categorySave": "\u4FDD\u5B58",
      "gallery.categoryDelete": "\u5220\u9664",
      "gallery.categoryLoadFailed": "\u5206\u7C7B\u8BFB\u53D6\u5931\u8D25",
      "gallery.categoryNameRequired": "\u8BF7\u8F93\u5165\u5206\u7C7B\u540D\u79F0",
      "gallery.categoryCreateFailed": "\u65B0\u589E\u5206\u7C7B\u5931\u8D25",
      "gallery.categoryCreated": "\u5206\u7C7B\u5DF2\u65B0\u589E",
      "gallery.categorySaveFailed": "\u4FDD\u5B58\u5206\u7C7B\u5931\u8D25",
      "gallery.categorySaved": "\u5206\u7C7B\u5DF2\u4FDD\u5B58",
      "gallery.categoryDeleteTitle": "\u5220\u9664\u56FE\u5E93\u5206\u7C7B\uFF1F",
      "gallery.categoryDeleteMessage": "\u5206\u7C7B\u4E0B\u7684\u56FE\u7247\u4F1A\u79FB\u52A8\u5230\u5176\u4ED6\u5206\u7C7B\uFF0C\u56FE\u5E93\u56FE\u7247\u4E0D\u4F1A\u88AB\u5220\u9664\u3002",
      "gallery.categoryDeleteConfirm": "\u5220\u9664\u5206\u7C7B",
      "gallery.categoryDeleteFailed": "\u5220\u9664\u5206\u7C7B\u5931\u8D25",
      "gallery.categoryDeletedMigrated": "\u5206\u7C7B\u300C{name}\u300D\u5DF2\u5220\u9664\uFF0C\u56FE\u7247\u5DF2\u8FC1\u79FB",
      "gallery.categoryOrderUpdateFailed": "\u66F4\u65B0\u5206\u7C7B\u987A\u5E8F\u5931\u8D25",
      "gallery.categoryOrderUpdated": "\u5206\u7C7B\u987A\u5E8F\u5DF2\u66F4\u65B0",
      "gallery.categoryFallback": "\u56FE\u5E93\u5206\u7C7B",
      "gallery.imageFallback": "\u56FE\u5E93\u56FE\u7247",
      "gallery.imageLoadFailed": "\u65E0\u6CD5\u8F7D\u5165\u8FD9\u5F20\u56FE\u7247",
      "gallery.editImageLoadFailed": "\u65E0\u6CD5\u8F7D\u5165\u8FD9\u5F20\u56FE\u7247\u8FDB\u884C\u7F16\u8F91",
      "gallery.cannotAddImage": "\u8FD9\u5F20\u56FE\u7247\u65E0\u6CD5\u52A0\u5165\u56FE\u5E93",
      "gallery.nameRequired": "\u8BF7\u8F93\u5165\u56FE\u5E93\u540D\u79F0",
      "gallery.saveFailed": "\u4FDD\u5B58\u56FE\u5E93\u5931\u8D25",
      "gallery.savedAsReference": "\u5DF2\u6DFB\u52A0\u5230\u56FE\u5E93\uFF0C\u5E76\u5207\u6362\u4E3A\u56FE\u5E93\u5F15\u7528",
      "gallery.renameImage": "\u91CD\u547D\u540D\u56FE\u5E93\u56FE\u7247",
      "gallery.moveToCategory": "\u79FB\u52A8\u5230\u5206\u7C7B",
      "gallery.categoryRequired": "\u8BF7\u9009\u62E9\u56FE\u5E93\u5206\u7C7B",
      "gallery.promptNoteTitle": "\u56FE\u5E93\u5F15\u7528\u5907\u6CE8",
      "gallery.updateFailed": "\u66F4\u65B0\u56FE\u5E93\u5931\u8D25",
      "gallery.selectImageFile": "\u8BF7\u9009\u62E9\u56FE\u7247\u6587\u4EF6",
      "gallery.replaceImageFailed": "\u66FF\u6362\u56FE\u5E93\u56FE\u7247\u5931\u8D25",
      "gallery.replacedImage": "\u5DF2\u66FF\u6362\u300C{name}\u300D\u7684\u539F\u56FE",
      "gallery.deleteImageTitle": "\u5220\u9664\u56FE\u5E93\u56FE\u7247\uFF1F",
      "gallery.deleteImageMessage": "\u5386\u53F2\u4EFB\u52A1\u91CC\u7684\u5F15\u7528\u4F1A\u663E\u793A\u4E3A\u5DF2\u5220\u9664\u3002",
      "gallery.deleteFailed": "\u5220\u9664\u56FE\u5E93\u5931\u8D25",
      "gallery.deletedSuffix": "\uFF08\u5DF2\u5220\u9664\uFF09",
      "gallery.editImageLabel": "\u7F16\u8F91\u56FE\u5E93\u56FE\u7247",
      "gallery.fieldCategory": "\u5206\u7C7B",
      "gallery.fieldPromptNote": "\u5F15\u7528\u5907\u6CE8",
      "gallery.fieldName": "\u540D\u79F0",
      "quickGallery.empty": "\u6682\u65E0{category}\u56FE\u7247",
      "promptGallery.remove": "\u79FB\u9664 @{name}",
      "prompt.title": "\u63D0\u793A\u8BCD",
      "prompt.editorLabel": "\u63D0\u793A\u8BCD",
      "prompt.placeholder": "\u63CF\u8FF0\u4F60\u8981\u751F\u6210\u6216\u7F16\u8F91\u7684\u56FE\u7247\uFF0C\u8F93\u5165 @ \u53EF\u8C03\u7528\u56FE\u5E93\u53C2\u8003\u56FE\uFF0C\u8F93\u5165 # \u53EF\u63D2\u5165\u989C\u8272\u7801\uFF0C\u8F93\u5165 ~ \u6216 \uFF5E \u53EF\u8C03\u7528\u63D0\u793A\u8BCD\u7247\u6BB5",
      "prompt.run": "\u5F00\u59CB\u751F\u6210",
      "prompt.runEdit": "\u5F00\u59CB\u7F16\u8F91",
      "prompt.runTitle": "\u5F00\u59CB\u751F\u6210\uFF08Cmd+Enter\uFF09",
      "prompt.runEditTitle": "\u5F00\u59CB\u7F16\u8F91\uFF08Cmd+Enter\uFF09",
      "prompt.findPanel": "\u67E5\u627E\u66FF\u6362\u63D0\u793A\u8BCD",
      "prompt.findText": "\u67E5\u627E\u6587\u672C",
      "prompt.replaceWith": "\u66FF\u6362\u4E3A",
      "prompt.findActions": "\u67E5\u627E\u66FF\u6362\u64CD\u4F5C",
      "prompt.countZero": "0 \u5904",
      "prompt.matchCount": "{count} \u5904",
      "prompt.foundCount": "\u627E\u5230 {count} \u5904",
      "prompt.noMatch": "\u672A\u627E\u5230\u5339\u914D\u6587\u672C",
      "prompt.replacedCount": "\u5DF2\u66FF\u6362 {count} \u5904",
      "prompt.closeFind": "\u5173\u95ED\u67E5\u627E\u66FF\u6362",
      "prompt.recentTemplates": "\u6700\u8FD1\u4F7F\u7528\u6A21\u677F",
      "prompt.manageTemplates": "\u7BA1\u7406\u6A21\u677F\u5E93",
      "promptModel.galleryHeader": "\u53C2\u8003\u56FE\u8BF4\u660E\uFF1A",
      "promptModel.galleryInstruction": "- \u53C2\u8003\u56FE {number}\uFF1A\u56FE\u5E93\u300C{name}\u300D\uFF0C\u7528\u9014\uFF1A{role}\u3002\u63D0\u793A\u8BCD\u4E2D\u7684 @{name} \u6307\u8FD9\u5F20\u56FE\u3002{note}",
      "outputSettings.title": "\u8F93\u51FA\u8BBE\u7F6E",
      "output.mainModel": "\u4E3B\u6A21\u578B",
      "output.selectMainModel": "\u9009\u62E9\u4E3B\u6A21\u578B",
      "output.mainModelCustomForInput": "\u6309\u5F53\u524D\u8F93\u5165\u4F7F\u7528\u81EA\u5B9A\u4E49\u6A21\u578B",
      "output.apiDirect": "API \u76F4\u8FDE",
      "output.apiToolModel": "\u4F7F\u7528 API \u56FE\u50CF\u5DE5\u5177\u6A21\u578B",
      "output.mainModelUnused": "\u4E3B\u6A21\u578B\u4E0D\u53C2\u4E0E\u672C\u6B21\u8BF7\u6C42",
      "output.webSearch": "\u8054\u7F51\u641C\u7D22",
      "output.webSearchToggle": "\u5F00\u542F",
      "output.webSearchTitle": "\u5148\u8054\u7F51\u641C\u7D22\uFF0C\u518D\u7528\u4E8E\u672C\u6B21\u751F\u6210\uFF1B\u4EC5 Codex \u548C API Responses \u652F\u6301",
      "output.promptMode": "\u63D0\u793A\u8BCD\u6A21\u5F0F",
      "output.modeOriginal": "\u539F\u59CB\u6A21\u5F0F",
      "output.modeStrict": "\u4FDD\u771F\u6A21\u5F0F",
      "output.modeCreative": "\u521B\u610F\u6A21\u5F0F",
      "output.sizeMode": "\u5C3A\u5BF8\u6A21\u5F0F",
      "output.sizePreset": "\u9884\u8BBE\u5C3A\u5BF8",
      "output.sizeCustom": "\u81EA\u5B9A\u4E49\u5C3A\u5BF8",
      "output.orientation": "\u65B9\u5411",
      "output.square": "\u65B9\u5F62",
      "output.portrait": "\u7AD6\u56FE",
      "output.landscape": "\u6A2A\u56FE",
      "output.resolution": "\u5206\u8FA8\u7387",
      "output.pixelSize": "\u50CF\u7D20\u5C3A\u5BF8",
      "output.width": "\u5BBD\u5EA6",
      "output.height": "\u9AD8\u5EA6",
      "output.swapSize": "\u4EA4\u6362\u5BBD\u9AD8",
      "output.customSizeHint": "\u5355\u4F4D px \xB7 16-3840 \xB7 16\u500D\u6570 \xB7 \u22643:1",
      "output.imageSizeUnavailable": "\u56FE\u7247\u5C3A\u5BF8\u4E0D\u53EF\u7528",
      "output.imageLoadFailed": "\u56FE\u7247\u52A0\u8F7D\u5931\u8D25",
      "output.customSizeRequired": "\u8BF7\u8F93\u5165\u5BBD\u5EA6\u548C\u9AD8\u5EA6",
      "output.customSizeBounds": "\u5BBD\u9AD8\u9700\u5728 16-3840 px \u4E4B\u95F4",
      "output.customSizeMultiple": "\u5BBD\u9AD8\u9700\u4E3A 16 \u7684\u500D\u6570",
      "output.customSizeRatio": "\u957F\u77ED\u8FB9\u6BD4\u4F8B\u4E0D\u80FD\u8D85\u8FC7 3:1",
      "output.customSizePixels": "\u603B\u50CF\u7D20\u9700\u5728 655,360-8,294,400 \u4E4B\u95F4",
      "output.ratioLock": "\u6BD4\u4F8B\u9501\u5B9A\uFF08\u53EF\u9009\uFF09",
      "output.customRatio": "\u81EA\u5B9A\u4E49\u5BBD\u9AD8\u6BD4",
      "output.ratioWidth": "\u5BBD",
      "output.ratioHeight": "\u9AD8",
      "output.firstImageRatio": "\u83B7\u53D6\u7B2C\u4E00\u5F20\u53C2\u8003\u56FE\u5BBD\u9AD8\u6BD4",
      "output.useFirstImage": "\u53D6\u9996\u56FE",
      "output.ratioHint": "\u7559\u7A7A\u5219\u81EA\u7531\u5BBD\u9AD8 \xB7 \u586B\u6EE1\u540E\u540C\u6B65",
      "output.ratio": "\u6BD4\u4F8B",
      "output.quality": "\u8D28\u91CF",
      "output.qualityAuto": "\u81EA\u52A8",
      "output.qualityLow": "\u4F4E",
      "output.qualityMedium": "\u4E2D",
      "output.qualityHigh": "\u9AD8",
      "output.quantity": "\u6570\u91CF",
      "output.pixelPreview": "\u8F93\u51FA\u50CF\u7D20: 1024 x 1024 px",
      "output.pixelPreviewValue": "\u8F93\u51FA\u50CF\u7D20: {value}",
      "output.pixelPreviewAuto": "\u8F93\u51FA\u50CF\u7D20: auto\uFF08OpenAI \u81EA\u52A8\u9009\u62E9\uFF09",
      "output.format": "\u8F93\u51FA\u683C\u5F0F",
      "output.compression": "\u538B\u7F29\u7387",
      "output.moderation": "\u5BA1\u6838",
      "preview.title": "\u9884\u89C8\u7ED3\u679C",
      "preview.selectedZero": "\u5DF2\u9009 0",
      "preview.selectedCount": "\u5DF2\u9009 {selected}/{total}",
      "preview.downloadSelected": "\u53EA\u4E0B\u8F7D\u7CBE\u9009",
      "preview.deleteUnselected": "\u5220\u9664\u672A\u7CBE\u9009",
      "preview.downloadAll": "\u6253\u5305\u4E0B\u8F7D",
      "preview.empty": "\u6682\u65E0\u56FE\u7247",
      "preview.taskFailed": "\u4EFB\u52A1\u5931\u8D25",
      "preview.partialFailed": "\u90E8\u5206\u56FE\u7247\u751F\u6210\u5931\u8D25",
      "preview.failedOutput": "\u7B2C {index} \u5F20\u5931\u8D25",
      "preview.progressLine": "\u5DF2\u5B8C\u6210 {generated} / {total} \xB7 \u8BA1\u65F6 {elapsed}",
      "preview.failureLine": "\u5DF2\u5B8C\u6210 {generated} / {total} \xB7 \u5931\u8D25 {failed}",
      "preview.elapsedLine": "\u8BA1\u65F6 {elapsed}",
      "preview.lastError": "\u4E0A\u6B21\u9519\u8BEF\uFF1A{error}",
      "preview.continueGenerating": "\u7EE7\u7EED\u751F\u6210\u4E2D",
      "preview.waitingContinue": "\u7B49\u5F85\u7EE7\u7EED\u751F\u6210",
      "preview.retryFailed": "\u4EC5\u91CD\u8BD5\u5931\u8D25\u56FE\u7247",
      "preview.acceptSuccesses": "\u63A5\u53D7\u5DF2\u6210\u529F\u7ED3\u679C",
      "preview.generateMode": "\u751F\u6210",
      "preview.editMode": "\u7F16\u8F91",
      "preview.runningTitle": "{mode}\u4EFB\u52A1\u8FD0\u884C\u4E2D",
      "preview.submittingTitle": "\u63D0\u4EA4\u4EFB\u52A1\u4E2D",
      "preview.queuedTitle": "\u4EFB\u52A1\u6392\u961F\u4E2D",
      "preview.submittingDetail": "\u6B63\u5728\u4FDD\u5B58\u8F93\u5165\u5E76\u5199\u5165\u961F\u5217\uFF0C\u5B8C\u6210\u540E\u4F1A\u81EA\u52A8\u8FDB\u5165\u751F\u6210\u6D41\u7A0B\u3002",
      "preview.queuedDetail": "\u4EFB\u52A1\u5DF2\u8FDB\u5165\u961F\u5217\uFF0C\u7B49\u5F85\u53EF\u7528\u901A\u9053\u63A5\u624B\u3002",
      "preview.featured": "\u7CBE\u9009",
      "preview.addFeatured": "\u52A0\u5165\u7CBE\u9009",
      "preview.selectedFeatured": "\u5DF2\u7CBE\u9009",
      "preview.removeFeatured": "\u53D6\u6D88\u7CBE\u9009",
      "preview.selectionAdded": "\u5DF2\u52A0\u5165\u7CBE\u9009",
      "preview.selectionRemoved": "\u5DF2\u53D6\u6D88\u7CBE\u9009",
      "preview.selectionUpdateFailed": "\u7CBE\u9009\u72B6\u6001\u66F4\u65B0\u5931\u8D25",
      "preview.noUnselectedOutputs": "\u6CA1\u6709\u53EF\u5220\u9664\u7684\u672A\u7CBE\u9009\u56FE\u7247",
      "preview.deleteUnselectedTitle": "\u5220\u9664\u672A\u7CBE\u9009\u56FE\u7247\uFF1F",
      "preview.deleteUnselectedMessage": "\u4F1A\u5220\u9664\u5F53\u524D\u4EFB\u52A1\u91CC\u672A\u7CBE\u9009\u7684\u672C\u5730\u56FE\u7247\u6587\u4EF6\u3002",
      "preview.deleteUnselectedDetail": "\u4FDD\u7559 {selected} \u5F20\uFF0C\u5220\u9664 {deleted} \u5F20",
      "preview.deleteUnselectedFailed": "\u5220\u9664\u672A\u7CBE\u9009\u5931\u8D25",
      "preview.deleteUnselectedDone": "\u672A\u7CBE\u9009\u56FE\u7247\u5DF2\u5220\u9664",
      "preview.addReference": "\u52A0\u5165\u53C2\u8003\u56FE",
      "preview.stage": "\u6682\u5B58",
      "preview.stageReference": "\u6682\u5B58\u5230\u5F85\u52A0\u5165\u53C2\u8003\u56FE",
      "preview.prompt": "\u63D0\u793A\u8BCD",
      "preview.download": "\u4E0B\u8F7D",
      "preview.downloadImage": "\u4E0B\u8F7D\u8BE5\u56FE\u7247",
      "lightbox.label": "\u56FE\u7247\u9884\u89C8",
      "lightbox.close": "\u5173\u95ED\u9884\u89C8",
      "lightbox.previous": "\u4E0A\u4E00\u5F20",
      "lightbox.next": "\u4E0B\u4E00\u5F20",
      "promptPopover.title": "\u63D0\u793A\u8BCD\u5BF9\u6BD4",
      "promptPopover.summary": "\u539F\u59CB {original} \xB7 \u4F18\u5316 {optimized}",
      "promptPopover.original": "\u539F\u59CB\u63D0\u793A\u8BCD",
      "promptPopover.optimized": "\u4F18\u5316\u540E\u63D0\u793A\u8BCD",
      "promptPopover.charCount": "{count} \u5B57",
      "promptPopover.empty": "\u65E0",
      "promptPopover.notReturned": "\u672A\u8FD4\u56DE",
      "promptPopover.noOptimized": "\u672A\u8FD4\u56DE\u4F18\u5316\u63D0\u793A\u8BCD",
      "promptPopover.submitted": "\u67E5\u770B\u5B9E\u9645\u63D0\u4EA4\u63D0\u793A\u8BCD",
      "promptPopover.close": "\u5173\u95ED\u63D0\u793A\u8BCD",
      "promptPopover.copyOptimized": "\u590D\u5236\u4F18\u5316\u540E\u63D0\u793A\u8BCD",
      "promptPopover.copied": "\u5DF2\u590D\u5236",
      "taskContext.menuLabel": "\u4EFB\u52A1\u53F3\u952E\u83DC\u5355",
      "taskContext.view": "\u67E5\u770B\u4EFB\u52A1",
      "taskContext.copyId": "\u590D\u5236\u4EFB\u52A1 ID",
      "taskContext.copyPrompt": "\u590D\u5236\u63D0\u793A\u8BCD",
      "taskContext.revealOutput": "\u6253\u5F00\u8F93\u51FA\u76EE\u5F55",
      "taskContext.archive": "\u5F52\u6863\u4EFB\u52A1",
      "taskContext.delete": "\u5220\u9664\u4EFB\u52A1",
      "taskContext.idCopied": "\u4EFB\u52A1 ID \u5DF2\u590D\u5236",
      "taskContext.promptCopied": "\u63D0\u793A\u8BCD\u5DF2\u590D\u5236",
      "taskContext.noPrompt": "\u8FD9\u4E2A\u4EFB\u52A1\u6CA1\u6709\u53EF\u590D\u5236\u7684\u63D0\u793A\u8BCD",
      "taskContext.revealFailed": "\u6253\u5F00\u8F93\u51FA\u76EE\u5F55\u5931\u8D25",
      "taskContext.revealOpened": "\u5DF2\u6253\u5F00\u8F93\u51FA\u76EE\u5F55",
      "taskContext.actionFailed": "\u4EFB\u52A1\u64CD\u4F5C\u5931\u8D25",
      "taskActions.group": "\u4EFB\u52A1\u64CD\u4F5C",
      "taskActions.deleteTitle": "\u5220\u9664\u4EFB\u52A1\uFF1F",
      "taskActions.deleteMessage": "\u4F1A\u540C\u65F6\u5220\u9664\u672C\u5730\u56FE\u7247\u6587\u4EF6\u3002",
      "taskActions.runningCannotDelete": "\u8FD0\u884C\u4E2D\u7684\u4EFB\u52A1\u4E0D\u80FD\u5220\u9664",
      "taskActions.updated": "\u4EFB\u52A1\u72B6\u6001\u5DF2\u66F4\u65B0",
      "taskActions.archived": "\u4F1A\u8BDD\u5DF2\u5F52\u6863",
      "taskActions.archiveFailed": "\u5F52\u6863\u5931\u8D25",
      "taskActions.deleted": "\u4EFB\u52A1\u5DF2\u5220\u9664",
      "taskActions.deleteFailed": "\u5220\u9664\u5931\u8D25",
      "taskActions.noRetryableFailedImages": "\u8FD9\u4E2A\u4EFB\u52A1\u6CA1\u6709\u53EF\u91CD\u8BD5\u7684\u5931\u8D25\u56FE\u7247",
      "taskActions.retryFailedOutputsFailed": "\u91CD\u8BD5\u5931\u8D25\u56FE\u7247\u5931\u8D25",
      "taskActions.requeuedFailedImages": "\u5DF2\u91CD\u65B0\u5165\u961F\u5931\u8D25\u56FE\u7247",
      "taskActions.noAcceptableSuccessImages": "\u8FD9\u4E2A\u4EFB\u52A1\u6CA1\u6709\u53EF\u63A5\u53D7\u7684\u6210\u529F\u56FE\u7247",
      "taskActions.acceptSuccessesFailed": "\u63A5\u53D7\u6210\u529F\u7ED3\u679C\u5931\u8D25",
      "taskActions.acceptedSuccesses": "\u5DF2\u63A5\u53D7\u6210\u529F\u7ED3\u679C",
      "taskActions.viewedUpdateFailed": "\u5DF2\u8BFB\u72B6\u6001\u66F4\u65B0\u5931\u8D25",
      "taskActions.failedFallback": "\u4EFB\u52A1\u5931\u8D25",
      "taskList.empty": "\u6682\u65E0\u5386\u53F2\u4EFB\u52A1",
      "taskList.selectSession": "\u9009\u62E9\u4F1A\u8BDD",
      "taskList.unreadUpdate": "\u672A\u8BFB\u66F4\u65B0",
      "taskList.viewing": "\u67E5\u770B\u4E2D",
      "taskDerived.usageLimited": "\u7528\u91CF\u53D7\u9650",
      "taskSubmit.requestFailed": "\u8BF7\u6C42\u5931\u8D25",
      "taskSubmit.queued": "\u4EFB\u52A1\u5DF2\u52A0\u5165\u961F\u5217",
      "taskSubmit.timeout": "\u63D0\u4EA4\u4EFB\u52A1\u8D85\u65F6\uFF0C\u540E\u7AEF\u6CA1\u6709\u53CA\u65F6\u8FD4\u56DE\u3002\u8BF7\u5237\u65B0\u961F\u5217\u540E\u786E\u8BA4\u662F\u5426\u5DF2\u5165\u961F\uFF0C\u518D\u51B3\u5B9A\u662F\u5426\u91CD\u8BD5\u3002",
      "taskSubmit.failed": "\u4EFB\u52A1\u63D0\u4EA4\u5931\u8D25",
      "templates.title": "\u63D0\u793A\u8BCD\u6A21\u677F",
      "templates.summary": "\u672C\u5730\u6A21\u677F\u5E93",
      "templates.availableCount": "{count} \u4E2A\u53EF\u7528\u6A21\u677F",
      "templates.noMatch": "\u6682\u65E0\u5339\u914D\u6A21\u677F",
      "templates.empty": "\u6682\u65E0\u6A21\u677F",
      "templates.favoriteBadge": "\u5DF2\u6536\u85CF",
      "templates.usageCount": "{count} \u6B21",
      "templates.back": "\u8FD4\u56DE",
      "templates.edit": "\u7F16\u8F91",
      "templates.copy": "\u590D\u5236",
      "templates.insert": "\u63D2\u5165",
      "templates.formTitle": "\u6807\u9898",
      "templates.formShortTitle": "\u77ED\u6807\u9898",
      "templates.formCategory": "\u5206\u7C7B",
      "templates.formTags": "\u6807\u7B7E",
      "templates.formThumbnail": "\u7F29\u7565\u56FE",
      "templates.formContent": "\u5185\u5BB9",
      "templates.formNotes": "\u5907\u6CE8",
      "templates.formFavorite": "\u6536\u85CF",
      "templates.thumbnailClear": "\u6E05\u9664",
      "templates.thumbnailNone": "\u672A\u9009\u62E9",
      "templates.thumbnailEmpty": "\u6682\u65E0\u5386\u53F2\u7F29\u7565\u56FE",
      "templates.newCategory": "\u65B0\u5206\u7C7B",
      "templates.search": "\u641C\u7D22\u6A21\u677F\u3001\u6807\u7B7E\u3001\u5185\u5BB9",
      "templates.filter": "\u6A21\u677F\u7B5B\u9009",
      "templates.all": "\u5168\u90E8",
      "templates.categoryCommon": "\u5E38\u7528",
      "templates.categoryPortrait": "\u4EBA\u50CF",
      "templates.categoryProduct": "\u4EA7\u54C1",
      "templates.categoryRepair": "\u4FEE\u590D",
      "templates.categoryPoster": "\u6D77\u62A5",
      "templates.categoryEcommerce": "\u7535\u5546",
      "templates.favorite": "\u6536\u85CF",
      "templates.recent": "\u6700\u8FD1",
      "templates.category": "\u5206\u7C7B",
      "templates.loadFailed": "\u63D0\u793A\u8BCD\u6A21\u677F\u8BFB\u53D6\u5931\u8D25",
      "templates.useStateUpdateFailed": "\u63D0\u793A\u8BCD\u6A21\u677F\u4F7F\u7528\u72B6\u6001\u66F4\u65B0\u5931\u8D25",
      "templates.copied": "\u63D0\u793A\u8BCD\u6A21\u677F\u5DF2\u590D\u5236",
      "templates.copyFailed": "\u63D0\u793A\u8BCD\u6A21\u677F\u590D\u5236\u5931\u8D25",
      "templates.history": "\u5386\u53F2\u8BB0\u5F55",
      "templates.saveFailed": "\u63D0\u793A\u8BCD\u6A21\u677F\u4FDD\u5B58\u5931\u8D25",
      "templates.saved": "\u63D0\u793A\u8BCD\u6A21\u677F\u5DF2\u4FDD\u5B58",
      "templates.deleteFailed": "\u63D0\u793A\u8BCD\u6A21\u677F\u5220\u9664\u5931\u8D25",
      "templates.deleted": "\u63D0\u793A\u8BCD\u6A21\u677F\u5DF2\u5220\u9664",
      "templates.categoryAddFailed": "\u6A21\u677F\u5206\u7C7B\u6DFB\u52A0\u5931\u8D25",
      "templates.categoryAdded": "\u6A21\u677F\u5206\u7C7B\u5DF2\u6DFB\u52A0",
      "templates.categorySaveFailed": "\u6A21\u677F\u5206\u7C7B\u4FDD\u5B58\u5931\u8D25",
      "templates.categorySaved": "\u6A21\u677F\u5206\u7C7B\u5DF2\u4FDD\u5B58",
      "templates.categoryDeleteFailed": "\u6A21\u677F\u5206\u7C7B\u5220\u9664\u5931\u8D25",
      "templates.categoryDeleted": "\u6A21\u677F\u5206\u7C7B\u5DF2\u5220\u9664",
      "templates.importFailed": "\u6A21\u677F\u5305\u5BFC\u5165\u5931\u8D25",
      "templates.importedCount": "\u5DF2\u5BFC\u5165 {count} \u4E2A\u6A21\u677F",
      "templates.exportFailed": "\u6A21\u677F\u5305\u5BFC\u51FA\u5931\u8D25",
      "templates.exported": "\u6A21\u677F\u5305\u5DF2\u5BFC\u51FA",
      "snippets.suggestLabel": "\u63D0\u793A\u8BCD\u7247\u6BB5\u9009\u62E9\u5668",
      "snippets.saveSelection": "\u6536\u85CF",
      "snippets.saveSelectionLabel": "\u6536\u85CF\u9009\u4E2D\u7684\u63D0\u793A\u8BCD\u7247\u6BB5",
      "snippets.popoverLabel": "\u63D0\u793A\u8BCD\u7247\u6BB5",
      "snippets.defaultCategory": "\u5E38\u7528",
      "snippets.loadFailed": "\u63D0\u793A\u8BCD\u7247\u6BB5\u8BFB\u53D6\u5931\u8D25",
      "snippets.remove": "\u79FB\u9664 ~{tag}",
      "snippets.expand": "\u5C55\u5F00",
      "snippets.edit": "\u7F16\u8F91",
      "snippets.close": "\u5173\u95ED",
      "snippets.editTitle": "\u7F16\u8F91\u7247\u6BB5",
      "snippets.saveTitle": "\u6536\u85CF\u7247\u6BB5",
      "snippets.shortTag": "\u77ED\u6807\u7B7E",
      "snippets.title": "\u6807\u9898",
      "snippets.category": "\u5206\u7C7B",
      "snippets.content": "\u5185\u5BB9",
      "snippets.titlePlaceholder": "\u9ED8\u8BA4\u4F7F\u7528\u77ED\u6807\u7B7E",
      "snippets.cancel": "\u53D6\u6D88",
      "snippets.save": "\u4FDD\u5B58",
      "snippets.saveFailed": "\u63D0\u793A\u8BCD\u7247\u6BB5\u4FDD\u5B58\u5931\u8D25",
      "snippets.saved": "\u63D0\u793A\u8BCD\u7247\u6BB5\u5DF2\u4FDD\u5B58",
      "snippets.defaultTag": "\u5E38\u7528\u7247\u6BB5",
      "colors.white": "\u767D\u8272",
      "colors.black": "\u9ED1\u8272",
      "colors.warmBeige": "\u6696\u7C73\u8272",
      "colors.lightGreen": "\u6D45\u7EFF",
      "colors.brandGreen": "\u54C1\u724C\u7EFF",
      "colors.peachOrange": "\u6843\u6A59",
      "colors.lightBlue": "\u6D45\u84DD",
      "colors.lightPink": "\u6D45\u7C89",
      "colors.loadFailed": "\u989C\u8272\u914D\u7F6E\u8BFB\u53D6\u5931\u8D25",
      "colors.saveFailed": "\u989C\u8272\u914D\u7F6E\u4FDD\u5B58\u5931\u8D25",
      "colors.importFailed": "\u989C\u8272\u914D\u7F6E\u5BFC\u5165\u5931\u8D25",
      "colors.importedCount": "\u5DF2\u5BFC\u5165 {count} \u4E2A\u989C\u8272",
      "colors.recentSaveFailed": "\u6700\u8FD1\u989C\u8272\u4FDD\u5B58\u5931\u8D25",
      "colors.favoriteSaveFailed": "\u5E38\u7528\u989C\u8272\u4FDD\u5B58\u5931\u8D25",
      "colors.favoriteDeleteFailed": "\u5E38\u7528\u989C\u8272\u5220\u9664\u5931\u8D25",
      "colors.update": "\u66F4\u65B0",
      "colors.insert": "\u63D2\u5165",
      "colors.pick": "\u9009\u62E9\u989C\u8272",
      "colors.pickShort": "\u53D6\u8272",
      "colors.hexValue": "\u989C\u8272\u503C",
      "colors.pendingUpdate": "\u989C\u8272\u5DF2\u4FEE\u6539\uFF0C\u70B9\u51FB\u66F4\u65B0\u751F\u6548",
      "colors.save": "\u4FDD\u5B58",
      "colors.exportPs": "\u5BFC\u51FA",
      "colors.importPs": "\u5BFC\u5165",
      "colors.done": "\u5B8C\u6210",
      "colors.manage": "\u7BA1\u7406",
      "colors.favorites": "\u5E38\u7528\u989C\u8272",
      "colors.recent": "\u6700\u8FD1\u989C\u8272",
      "colors.recentLabel": "\u6700\u8FD1",
      "colors.deleteFavorite": "\u5220\u9664\u5E38\u7528\u8272 {name}",
      "colors.modify": "\u4FEE\u6539\u989C\u8272",
      "colors.modifyValue": "\u4FEE\u6539\u989C\u8272 {value}",
      "colors.removeValue": "\u79FB\u9664\u989C\u8272 {value}",
      "taskGroup.today": "\u4ECA\u5929",
      "taskGroup.yesterday": "\u6628\u5929",
      "taskGroup.last7": "\u6700\u8FD1 7 \u5929",
      "taskGroup.older": "\u66F4\u65E9",
      "taskGroup.searchResults": "\u641C\u7D22\u7ED3\u679C",
      "taskGroup.active": "\u8FDB\u884C\u4E2D",
      "taskGroup.running": "\u8FD0\u884C\u4E2D",
      "taskGroup.waiting": "\u7B49\u5F85\u4E2D",
      "taskGroup.dispatchPending": "\u6B63\u5728\u5206\u914D\u53EF\u7528\u901A\u9053...",
      "taskGroup.expand": "\u5C55\u5F00 {label}",
      "taskGroup.collapse": "\u6536\u8D77 {label}",
      "taskGroup.buttonLabel": "{label}\uFF0C{count} \u4E2A\u4EFB\u52A1",
      "archive.title": "\u4F1A\u8BDD\u5F52\u6863",
      "archive.empty": "\u6682\u65E0\u5F52\u6863\u4F1A\u8BDD",
      "archive.count": "{count} \u4E2A\u5F52\u6863\u4F1A\u8BDD",
      "archive.restore": "\u6062\u590D",
      "archive.archiveFailed": "\u5F52\u6863\u5931\u8D25",
      "archive.restoreFailed": "\u6062\u590D\u5931\u8D25",
      "archive.restored": "\u4F1A\u8BDD\u5DF2\u6062\u590D",
      "archive.archiving": "\u6B63\u5728\u5F52\u6863...",
      "archive.restoring": "\u6B63\u5728\u6062\u590D...",
      "archive.deleting": "\u6B63\u5728\u5220\u9664...",
      "archive.restoredCount": "\u5DF2\u6062\u590D {count} \u4E2A\u4EFB\u52A1",
      "settings.title": "\u5B58\u50A8\u8BBE\u7F6E",
      "settings.status": "\u4FDD\u5B58\u540E\u91CD\u542F WebUI \u751F\u6548",
      "settings.inputRoot": "\u8F93\u5165\u76EE\u5F55",
      "settings.outputRoot": "\u8F93\u51FA\u76EE\u5F55",
      "settings.galleryRoot": "\u516C\u7528\u56FE\u5E93\u76EE\u5F55",
      "settings.sourceDataRoot": "\u6E90\u6570\u636E\u76EE\u5F55",
      "settings.notificationsCopy": "\u4EFB\u52A1\u5B8C\u6210\u6216\u5931\u8D25\u65F6\u63D0\u9192\uFF0C\u7CFB\u7EDF\u901A\u77E5\u9700\u624B\u52A8\u5F00\u542F\u3002",
      "settings.inAppNotification": "\u7AD9\u5185\u901A\u77E5",
      "settings.systemNotification": "\u7CFB\u7EDF\u901A\u77E5",
      "settings.save": "\u4FDD\u5B58\u8BBE\u7F6E",
      "settings.loadFailed": "\u8BBE\u7F6E\u8BFB\u53D6\u5931\u8D25",
      "settings.saveFailed": "\u8BBE\u7F6E\u4FDD\u5B58\u5931\u8D25",
      "settings.savedRestart": "\u5DF2\u4FDD\u5B58\uFF0C\u91CD\u542F WebUI \u540E\u751F\u6548",
      "settings.saved": "\u5DF2\u4FDD\u5B58",
      "settings.savedRestartStatus": "\u8BBE\u7F6E\u5DF2\u4FDD\u5B58\uFF0C\u91CD\u542F WebUI \u540E\u751F\u6548",
      "apiSettings.title": "API \u8BBE\u7F6E",
      "apiSettings.status": "\u4FDD\u5B58\u540E\u7ACB\u5373\u7528\u4E8E Codex \u548C API \u6A21\u5F0F",
      "apiSettings.codexMode": "Codex \u901A\u9053",
      "apiSettings.codexImages": "Image",
      "apiSettings.codexResponses": "Responses",
      "apiSettings.provider": "\u4F9B\u5E94\u5546",
      "apiSettings.providerName": "\u4F9B\u5E94\u5546\u540D\u79F0",
      "apiSettings.mode": "\u8C03\u7528\u65B9\u5F0F",
      "apiSettings.images": "\u76F4\u8FDE Image API",
      "apiSettings.responses": "Responses API",
      "apiSettings.modeImagesShort": "\u76F4\u8FDE",
      "apiSettings.imageModel": "\u56FE\u50CF\u5DE5\u5177\u6A21\u578B",
      "apiSettings.concurrency": "Provider \u603B\u5E76\u53D1\u4E0A\u9650",
      "apiSettings.save": "\u4FDD\u5B58 API \u8BBE\u7F6E",
      "apiSettings.loadFailed": "API \u8BBE\u7F6E\u8BFB\u53D6\u5931\u8D25",
      "apiSettings.savedKeyPlaceholder": "\u540E\u7AEF\u5DF2\u4FDD\u5B58 API Key\uFF0C\u8F93\u5165\u65B0 key \u53EF\u8986\u76D6",
      "apiSettings.newProvider": "\u65B0\u4F9B\u5E94\u5546",
      "apiSettings.saving": "\u4FDD\u5B58\u4E2D...",
      "apiSettings.savingStatus": "\u6B63\u5728\u4FDD\u5B58 API \u8BBE\u7F6E...",
      "apiSettings.saveFailed": "API \u8BBE\u7F6E\u4FDD\u5B58\u5931\u8D25",
      "apiSettings.savedSummary": "\u5DF2\u4FDD\u5B58 \xB7 Codex {codex} \xB7 API {provider} \xB7 {mode} \xB7 {model} \xB7 \u5E76\u53D1 {concurrency}",
      "apiSettings.savedShort": "\u5DF2\u4FDD\u5B58",
      "apiSettings.savedStatus": "API \u8BBE\u7F6E\u5DF2\u4FDD\u5B58",
      "apiSettings.saveFailedShort": "\u4FDD\u5B58\u5931\u8D25",
      "imageEditor.title": "\u7F16\u8F91\u8F93\u5165\u56FE\u7247",
      "imageEditor.promptHint": "\u56FE\u4E2D\u7684\u624B\u7ED8\u7BAD\u5934\u548C\u6807\u8BB0\u4EC5\u7528\u4E8E\u6307\u793A\u7F16\u8F91\u8981\u6C42\uFF0C\u4E0D\u8981\u4FDD\u7559\u5728\u6700\u7EC8\u753B\u9762\u4E2D\u3002",
      "imageEditor.inputFallback": "\u8F93\u5165\u56FE\u7247",
      "imageEditor.openFailed": "\u65E0\u6CD5\u6253\u5F00\u8FD9\u5F20\u56FE\u7247\u8FDB\u884C\u7F16\u8F91",
      "imageEditor.loadForEditFailed": "\u65E0\u6CD5\u8F7D\u5165\u8FD9\u5F20\u56FE\u7247\u8FDB\u884C\u7F16\u8F91",
      "imageEditor.canvasCreateFailed": "\u65E0\u6CD5\u521B\u5EFA\u56FE\u7247\u7F16\u8F91\u753B\u5E03",
      "imageEditor.closedRegionRequired": "\u8BF7\u5148\u7528\u753B\u7B14\u5708\u51FA\u5C01\u95ED\u533A\u57DF",
      "imageEditor.saveFailed": "\u56FE\u7247\u7F16\u8F91\u4FDD\u5B58\u5931\u8D25",
      "imageEditor.saved": "\u5DF2\u4FDD\u5B58\u7F16\u8F91\u540E\u7684\u8F93\u5165\u56FE",
      "imageEditor.uneditable": "\u8FD9\u5F20\u56FE\u7247\u65E0\u6CD5\u7F16\u8F91",
      "imageEditor.resetDone": "\u5DF2\u91CD\u7F6E\u5230\u539F\u56FE",
      "imageEditor.resetFailed": "\u65E0\u6CD5\u91CD\u7F6E\u539F\u56FE",
      "imageEditor.subtitle": "\u88C1\u526A\u3001\u6D82\u9E26\u3001\u6CB9\u6F06\u6876\u586B\u5145\u6216\u6DFB\u52A0\u7BAD\u5934\u540E\u4FDD\u5B58\u4E3A\u65B0\u7684\u8F93\u5165\u56FE",
      "imageEditor.toolbar": "\u56FE\u7247\u7F16\u8F91\u5DE5\u5177\u680F",
      "imageEditor.tools": "\u5DE5\u5177",
      "imageEditor.brush": "\u753B\u7B14",
      "imageEditor.arrow": "\u7BAD\u5934",
      "imageEditor.crop": "\u88C1\u526A",
      "imageEditor.fill": "\u6CB9\u6F06\u6876",
      "imageEditor.fillLabel": "\u6CB9\u6F06\u6876\u586B\u5145",
      "imageEditor.colors": "\u989C\u8272",
      "imageEditor.red": "\u7EA2\u8272",
      "imageEditor.blue": "\u84DD\u8272",
      "imageEditor.green": "\u7EFF\u8272",
      "imageEditor.yellow": "\u9EC4\u8272",
      "imageEditor.white": "\u767D\u8272",
      "imageEditor.black": "\u9ED1\u8272",
      "imageEditor.customColor": "\u81EA\u5B9A\u4E49\u989C\u8272",
      "imageEditor.stroke": "\u7C97\u7EC6",
      "imageEditor.history": "\u5386\u53F2",
      "imageEditor.undo": "\u64A4\u9500",
      "imageEditor.redo": "\u91CD\u505A",
      "imageEditor.reset": "\u91CD\u7F6E\u539F\u56FE",
      "imageEditor.canvas": "\u56FE\u7247\u7F16\u8F91\u753B\u5E03",
      "gallery.title": "\u516C\u7528\u56FE\u5E93",
      "gallery.subtitle": "\u9009\u62E9\u53C2\u8003\u56FE\u52A0\u5165\u5F53\u524D\u4EFB\u52A1",
      "gallery.manageCategories": "\u7BA1\u7406\u5206\u7C7B",
      "gallery.categoryManager": "\u7BA1\u7406\u56FE\u5E93\u5206\u7C7B",
      "gallery.categoryManagement": "\u5206\u7C7B\u7BA1\u7406",
      "gallery.categoryCopy": "\u5206\u7C7B\u4F1A\u4FDD\u5B58\u5230\u56FE\u5E93\uFF1B\u63D0\u793A\u8BCD\u7528\u9014\u7528\u4E8E\u751F\u6210\u53C2\u8003\u56FE\u8BF4\u660E",
      "gallery.newCategoryName": "\u65B0\u5206\u7C7B\u540D\u79F0",
      "gallery.newCategoryRole": "\u63D0\u793A\u8BCD\u7528\u9014\uFF0C\u4F8B\u5982\uFF1A\u98CE\u683C\u53C2\u8003",
      "gallery.addCategory": "\u65B0\u589E\u5206\u7C7B",
      "gallery.drawerSubtitle": "\u5F53\u524D\u5206\u7C7B\uFF1A{category}\uFF0C\u70B9\u51FB\u201C\u4F7F\u7528\u201D\u52A0\u5165\u56FE\u50CF\u8F93\u5165",
      "gallery.emptyCategory": "\u8FD9\u4E2A\u5206\u7C7B\u8FD8\u6CA1\u6709\u56FE\u7247",
      "gallery.dragSort": "\u62D6\u62FD\u6392\u5E8F",
      "gallery.dragSortImage": "\u62D6\u62FD\u6392\u5E8F\u56FE\u7247 {name}",
      "gallery.dragSortCategory": "\u62D6\u62FD\u6392\u5E8F\u5206\u7C7B {name}",
      "gallery.use": "\u4F7F\u7528",
      "gallery.replace": "\u66FF\u6362",
      "gallery.rename": "\u91CD\u547D\u540D",
      "gallery.moveCategory": "\u5206\u7C7B",
      "gallery.note": "\u5907\u6CE8",
      "gallery.delete": "\u5220\u9664",
      "gallery.uncategorized": "\u672A\u5206\u7C7B",
      "addGallery.title": "\u6DFB\u52A0\u5230\u56FE\u5E93",
      "addGallery.copy": "\u540D\u79F0\u5168\u5C40\u552F\u4E00\uFF0C\u540E\u7EED\u53EF\u7528 @\u540D\u79F0 \u8C03\u53D6",
      "addGallery.name": "\u540D\u79F0",
      "addGallery.namePlaceholder": "\u4F8B\u5982\uFF1A\u5C0F\u7F8E",
      "addGallery.category": "\u5206\u7C7B",
      "addGallery.note": "\u5F15\u7528\u5907\u6CE8",
      "addGallery.notePlaceholder": "\u4F8B\u5982\uFF1A\u53EA\u53C2\u8003\u8138\u578B\u548C\u53D1\u578B\uFF0C\u4E0D\u53C2\u8003\u8863\u670D\u548C\u80CC\u666F",
      "addGallery.save": "\u4FDD\u5B58\u5230\u56FE\u5E93",
      "close.promptTemplates": "\u5173\u95ED\u63D0\u793A\u8BCD\u6A21\u677F\u9762\u677F",
      "close.archive": "\u5173\u95ED\u4F1A\u8BDD\u5F52\u6863\u9762\u677F",
      "close.settings": "\u5173\u95ED\u5B58\u50A8\u8BBE\u7F6E\u9762\u677F",
      "close.apiSettings": "\u5173\u95ED API \u8BBE\u7F6E\u9762\u677F",
      "close.imageEditor": "\u5173\u95ED\u7F16\u8F91\u8F93\u5165\u56FE\u7247\u9762\u677F",
      "close.gallery": "\u5173\u95ED\u516C\u7528\u56FE\u5E93\u9762\u677F",
      "close.addGallery": "\u5173\u95ED\u6DFB\u52A0\u5230\u56FE\u5E93\u9762\u677F",
      "close.version": "\u5173\u95ED\u7248\u672C\u66F4\u65B0\u9762\u677F"
    },
    en: {
      "app.newTask": "New",
      "app.newTaskAria": "New chat",
      "sidebar.searchPlaceholder": "Search prompts or task ID",
      "sidebar.filters": "Task filters",
      "sidebar.allRatios": "All ratios",
      "sidebar.allOrientations": "All orientations",
      "sidebar.allModes": "All modes",
      "sidebar.allResolutions": "All resolutions",
      "sidebar.activeTasks": "Active tasks",
      "sidebar.topAnchors": "Top time navigation",
      "sidebar.bottomAnchors": "Bottom time navigation",
      "sidebar.resize": "Resize sidebar",
      "batch.selected": "0 selected",
      "batch.selectedCount": "{count} selected",
      "batch.archivedCount": "Archived {count} chats",
      "batch.archiveFailed": "Batch archive failed",
      "batch.runningCannotDeleteSelected": "Selected chats are running and cannot be deleted",
      "batch.deleteTitle": "Delete {count} chats?",
      "batch.deleteMessage": "This will also delete local image files.",
      "batch.deleteSkippedDetail": "{count} running tasks will be kept",
      "batch.deleteSkippedSuffix": ", {count} running tasks not deleted",
      "batch.deletedCount": "Deleted {count} chats{skipped}",
      "batch.deleteFailed": "Batch delete failed",
      "action.archive": "Archive",
      "action.delete": "Delete",
      "action.cancel": "Cancel",
      "action.clear": "Clear",
      "action.paste": "Paste",
      "action.find": "Find",
      "action.replace": "Replace",
      "action.close": "Close",
      "action.confirm": "Confirm",
      "action.confirmQuestion": "Confirm action?",
      "action.refresh": "Refresh",
      "action.save": "Save",
      "action.add": "Add",
      "action.new": "New",
      "action.import": "Import",
      "action.export": "Export",
      "queue.empty": "No queue",
      "queue.emptyAria": "Queue status: no queued tasks",
      "queue.jumpTitle": "Jump to active tasks",
      "queue.emptyTitle": "No queued tasks",
      "queue.channel": "Channels {count}",
      "queue.availableChannels": "Available channels {usable}/{total}",
      "queue.dispatching": "Scheduling \xB7 waiting {waiting}",
      "queue.runningWaiting": "Running {running} \xB7 waiting {waiting}",
      "queue.statusLabel": "Queue status: {text} \xB7 {channelText}. Click to jump to active tasks",
      "queue.runningActions": "Running task queue actions",
      "queue.waitingActions": "Waiting task queue actions",
      "queue.cancelRunning": "Cancel",
      "queue.cancelRunningTitle": "Cancel running task",
      "queue.dragWaiting": "Drag to reorder waiting task",
      "queue.dragSort": "Drag to sort",
      "queue.moveUp": "Up",
      "queue.moveUpTitle": "Move waiting task up",
      "queue.moveDown": "Down",
      "queue.moveDownTitle": "Move waiting task down",
      "queue.promote": "Top",
      "queue.promoteTitle": "Move waiting task to top",
      "queue.promoteFailed": "Move to top failed",
      "queue.deleteWaitingShort": "Del",
      "queue.deleteWaitingTitle": "Delete waiting task",
      "queue.deleteWaitingTitleConfirm": "Delete waiting task?",
      "queue.deleteWaitingMessage": "This removes it from the queue and history list.",
      "queue.deleteQueuedFailed": "Failed to delete queued task",
      "queue.queuedDeleted": "Queued task deleted",
      "queue.cancelRunningConfirm": "Cancel task",
      "queue.cancelRunningTitleConfirm": "Cancel running task?",
      "queue.cancelRunningMessage": "The current task will stop. History will be kept.",
      "queue.cancelRunningFailed": "Failed to cancel task",
      "queue.runningCancelled": "Task cancelled",
      "queue.reorderFailed": "Failed to reorder queue",
      "queue.realtimeUpdateFailed": "Failed to update live status",
      "queue.realtimeDisconnected": "Live status connection was lost. Refresh the page to recover.",
      "queue.readFailed": "Failed to load queue",
      "status.waiting": "Waiting",
      "status.shownActiveTasks": "Showing active tasks",
      "status.jsonCopied": "JSON copied",
      "taskStatus.submitting": "Submitting",
      "taskStatus.running": "Generating",
      "taskStatus.runningWithElapsed": "Generating \xB7 {elapsed}",
      "taskStatus.completed": "Completed",
      "taskStatus.partialFailed": "Partially failed",
      "taskStatus.failed": "Failed",
      "taskStatus.queued": "Queued",
      "taskStatus.unknown": "Unknown status",
      "taskStatus.task": "Task",
      "taskStatus.connectionInterrupted": "Connection interrupted",
      "taskStatus.lastFailed": "Last failed",
      "taskStatus.waitingRetry": "{reason}, waiting to retry (attempt {attempt}/{max})",
      "taskStatus.retrying": "{reason}, retrying (attempt {attempt}/{max})",
      "taskStatus.nonRetryableAttempt": "Attempt {attempt}/{max}, not retryable",
      "taskStatus.manualRetryAvailable": "Stopped; failed images can be retried manually",
      "taskStatus.runtime": "Duration {duration}",
      "taskStatus.runtimeCompleted": "Duration {duration} \xB7 completed {time}",
      "taskStatus.completedAt": "Completed {time}",
      "taskCard.count": "{count} images",
      "taskCard.successCount": "succeeded {count}",
      "taskCard.failedCount": "failed {count}",
      "taskCard.runningCount": "generating {count}",
      "taskCard.waitingCount": "waiting {count}",
      "taskCard.textToImageThumb": "Text-to-image task thumbnail",
      "taskCard.imageToImageThumb": "Image-to-image task thumbnail",
      "taskCard.failedThumb": "Task failed",
      "taskCard.textBadge": "T",
      "taskMode.edit": "Edit",
      "taskMode.generate": "Generate",
      "document.generatingQueue": "Generating \xB7 queue {total}",
      "document.queuedWaiting": "Queued \xB7 waiting {count}",
      "runFeedback.editing": "Editing",
      "runFeedback.generating": "Generating",
      "runFeedback.status": "{action}, elapsed {elapsed}",
      "footer.archive": "Archive",
      "footer.archiveCount": "Archive {count}",
      "footer.historyLibrary": "History",
      "historyLibrary.openFull": "Open full history library",
      "history.documentTitle": "History - iLab GPT CONJURE",
      "history.back": "Back to generator",
      "history.title": "History",
      "history.loading": "Loading",
      "history.total": "{total} tasks \xB7 {archived} archived",
      "history.search": "Search",
      "history.searchPlaceholder": "Search prompts or task ID",
      "history.clear": "Clear",
      "history.month": "Month",
      "history.status": "Status",
      "history.promptMode": "Prompt mode",
      "history.size": "Size",
      "history.quality": "Quality",
      "history.ratio": "Ratio",
      "history.orientation": "Orientation",
      "history.backend": "Backend",
      "history.provider": "Provider",
      "history.archived": "Archived",
      "history.all": "All",
      "history.allMonths": "All months",
      "history.allStatuses": "All statuses",
      "history.allPromptModes": "All modes",
      "history.allSizes": "All sizes",
      "history.allQualities": "All qualities",
      "history.allRatios": "All ratios",
      "history.ratioOther": "Other",
      "history.allOrientations": "All orientations",
      "history.allBackends": "All backends",
      "history.allProviders": "All providers",
      "history.unarchived": "Unarchived",
      "history.archivedOnly": "Archived",
      "history.tasksAria": "Historical tasks",
      "history.taskListTitle": "Historical tasks",
      "history.browseNewest": "Browse newest first",
      "history.view": "View",
      "history.grid": "Grid",
      "history.list": "List",
      "history.sort": "Sort",
      "history.newest": "Newest first",
      "history.oldest": "Oldest first",
      "history.refresh": "Refresh",
      "history.selectedCount": "{count} tasks selected",
      "history.confirmDelete": "Confirm delete",
      "history.detail": "Task detail",
      "history.detailTitle": "History task",
      "history.closeDetail": "Close task detail",
      "history.resizeFilters": "Resize filter sidebar",
      "history.resizeDetail": "Resize detail pane",
      "history.detailEmpty": "Select a historical task to view details",
      "history.loadingDetail": "Loading detail...",
      "history.loadMore": "Load more",
      "history.loadingMore": "Loading...",
      "history.noMore": "No more tasks",
      "history.loadFailed": "Load failed. Refresh or keep scrolling to retry",
      "history.summaryFailed": "Failed to load summary",
      "history.tasksFailed": "Failed to load tasks",
      "history.detailFailed": "Failed to load detail",
      "history.noMatches": "No matching tasks",
      "history.loadedCount": "{count} loaded",
      "history.windowNotice": "The mounted list is limited to {count} tasks; scroll up or down to restore adjacent tasks on demand.",
      "history.selectTask": "Select task",
      "history.viewing": "Viewing",
      "history.noPreview": "No preview images",
      "history.downloadAll": "Download ZIP",
      "history.downloadSelected": "Download selected",
      "history.deleteUnselected": "Delete unselected",
      "history.confirmDeleteUnselected": "Confirm delete unselected",
      "history.selected": "Selected",
      "history.select": "Select",
      "history.downloadIndex": "Download {index}",
      "history.addReference": "Add reference",
      "history.outputActions": "Result image actions",
      "history.inputReferences": "Input references",
      "history.inputReferenceIndex": "Input reference {index}",
      "history.copyPrompt": "Copy prompt",
      "history.copyPrompts": "Copy prompts",
      "history.copyPromptShort": "Copy",
      "history.copyPromptPanel": "Copy {title}",
      "history.copyOutputPromptPanel": "Copy image {index} revised prompt",
      "history.copyTaskIds": "Copy task IDs",
      "history.reuseTask": "View in generator",
      "history.downloadTask": "Download",
      "history.downloadSelectedTasks": "Batch download",
      "history.contextMenuLabel": "History task context menu",
      "history.promptCopied": "Prompt copied",
      "history.promptsCopied": "Copied prompts from {count} tasks",
      "history.taskIdsCopied": "Copied {count} task IDs",
      "history.promptCopiedShort": "Copied",
      "history.promptCopyFailed": "Failed to copy prompt",
      "history.promptCopyFailedShort": "Failed",
      "history.noPrompt": "This task has no prompt to copy",
      "history.noPromptShort": "Empty",
      "history.downloadStarted": "Download started",
      "history.batchDownloadStarted": "Started downloads for {count} tasks",
      "history.noDownloadableOutputs": "No downloadable images",
      "history.confirmDeleteSelected": "Confirm selected delete",
      "history.openPreview": "Open preview",
      "history.closePreview": "Close preview",
      "history.untitled": "Untitled",
      "history.promptCompare": "Prompt comparison",
      "history.promptOriginal": "Original prompt",
      "history.promptSubmitted": "Optimized prompt",
      "history.promptRevised": "Revised result",
      "history.outputRevisedPromptTitle": "Image {index} revised prompt",
      "history.outputRevisedPromptNotice": "Each image has its own revised prompt below the image.",
      "history.promptEmpty": "No content",
      "history.promptMode.strict": "Strict",
      "history.promptMode.original": "Original",
      "history.promptMode.off": "Creative",
      "history.quality.high": "High",
      "history.quality.medium": "Medium",
      "history.quality.low": "Low",
      "history.quality.auto": "Auto",
      "footer.batch": "Batch",
      "footer.storage": "Storage",
      "footer.apiStatus": "API status: OK",
      "footer.version": "Version {version}",
      "footer.versionInfo": "Version info",
      "footer.versionLoading": "Version ...",
      "footer.updateBadge": "New version available",
      "footer.updateAvailable": "New version {version}",
      "version.title": "Version & Update",
      "version.loading": "Reading version status",
      "version.current": "Current version",
      "version.latest": "Latest version",
      "version.source": "Runtime",
      "version.sourcePortable": "Portable package",
      "version.sourceSource": "Source checkout",
      "version.upToDate": "You are already on the latest version",
      "version.updateAvailable": "Version {version} is available. Close the WebUI server window, then run the updater to upgrade.",
      "version.noUpdater": "This runtime is not a portable package, so the updater cannot be started automatically.",
      "version.openUpdater": "Start updater",
      "version.release": "View release",
      "version.updaterStarted": "Updater started. Close the current WebUI server window, then follow the updater prompts.",
      "version.updaterFailed": "Could not start the updater. Run the updater script from the package manually.",
      "notifications.title": "Notifications",
      "notifications.unread": "Notifications, {count} unread",
      "notifications.unreadSummary": "{count} unread",
      "notifications.empty": "No task notifications",
      "notifications.taskFailed": "Task failed",
      "notifications.taskPartial": "Task partially completed",
      "notifications.taskCompleted": "Task completed",
      "notifications.generationFailed": "Generation failed",
      "notifications.successCount": "{count} succeeded",
      "notifications.resultAvailable": "Results available",
      "notifications.failedCount": "{count} failed",
      "notifications.systemUnsupported": "This browser does not support system notifications",
      "notifications.systemBlocked": "System notifications are blocked by the browser. Enable them in browser settings.",
      "notifications.systemDenied": "System notifications are not enabled",
      "notifications.systemEnabled": "System notifications enabled",
      "notifications.taskMissing": "Task does not exist or was deleted",
      "theme.label": "Theme",
      "theme.system": "Auto",
      "theme.light": "Light",
      "theme.dark": "Dark",
      "language.label": "Language",
      "language.zh": "\u4E2D",
      "language.en": "EN",
      "auth.label": "Auth source",
      "auth.checking": "Checking auth",
      "auth.missingCodexSession": "No Codex session detected",
      "auth.switchFailed": "Failed to switch auth source",
      "auth.sourceUnavailable": "{source} unavailable",
      "auth.notActive": "Not active",
      "api.settings": "API Settings",
      "api.provider": "API provider",
      "imageInput.title": "Images",
      "imageInput.uploadAria": "Click, drop, or paste images",
      "imageInput.uploadFull": "Click, drop, or paste images",
      "imageInput.uploadCompact": "Add image",
      "imageInput.uploadSubtitle": "Multiple reference images supported",
      "imageInput.recent": "Recent uploads",
      "imageInput.recentBadge": "Recent",
      "imageInput.uploadBadge": "Upload",
      "imageInput.addToGallery": "Add to gallery",
      "imageInput.addToGalleryShort": "Gallery",
      "imageInput.removeImage": "Remove image",
      "imageInput.editedBadge": "Edited",
      "imageInput.editImage": "Edit {name}",
      "imageInput.deletedRecent": "Recent upload deleted",
      "imageInput.deletedGallery": "Gallery image deleted",
      "recentAssets.defaultName": "Recent upload",
      "recentAssets.use": "Use {name}",
      "recentAssets.delete": "Delete {name}",
      "recentAssets.deleteTitle": "Delete recent upload?",
      "recentAssets.deleteMessage": "This will remove the image from Recent uploads. If it is currently selected as an image input, it will be removed from the current input. Historical tasks that reference this recent upload will lose that input preview. The public gallery is not affected.",
      "recentAssets.loadFailed": "Failed to load recent uploads",
      "recentAssets.deleteFailed": "Failed to delete recent upload",
      "recentAssets.deleted": "Recent upload deleted",
      "inputSource.uploadFallback": "Uploaded image",
      "inputSource.galleryFallback": "Gallery image",
      "inputSource.focusPasteFallback": "{prefix}. Image input is focused; press {shortcut} to paste images.",
      "inputSource.pastedCount": "Pasted {count} clipboard images",
      "inputSource.droppedCount": "Added {count} dropped images",
      "inputSource.dropImagesOnly": "Drop image files only",
      "inputSource.clipboardUnsupported": "This browser cannot read the clipboard directly",
      "inputSource.clipboardEmpty": "No clipboard images found",
      "inputSource.clipboardDenied": "The browser blocked direct clipboard access",
      "inputSource.clipboardReadFailed": "Failed to read the clipboard",
      "status.missingGalleryReference": "A gallery reference image has been deleted. Remove it before generating.",
      "status.missingRecentReference": "A recent upload reference image has been deleted. Remove it before generating.",
      "status.emptyPrompt": "Enter a prompt",
      "status.editNeedsImage": "Edit mode requires at least one image",
      "status.loadedTask": "Loaded task {taskId}",
      "status.reusedTask": "Opened task {taskId} in generator",
      "status.loadingHistoryInputs": "Loading historical input images...",
      "status.historyInputLoadFailed": "Failed to load historical input image: {url}",
      "referenceCollector.alreadyStaged": "Already staged as a reference",
      "referenceCollector.staged": "Staged {count} reference images",
      "referenceCollector.title": "Pending references \xB7 {count}",
      "referenceCollector.addAll": "Add all references",
      "referenceCollector.itemFallback": "Pending reference",
      "referenceCollector.remove": "Remove pending reference",
      "referenceCollector.cleared": "Pending references cleared",
      "referenceCollector.added": "Added {count} reference images",
      "referenceCollector.addFailed": "Failed to add pending references",
      "referenceCollector.readFailed": "Failed to read image: {status}",
      "gallery.quick": "Quick gallery",
      "gallery.current": "Current category gallery",
      "gallery.categories": "Gallery categories",
      "gallery.categoryPortrait": "Portrait",
      "gallery.categoryCharacter": "Character",
      "gallery.categoryProduct": "Product",
      "gallery.categoryPortraitRole": "Portrait reference",
      "gallery.categoryCharacterRole": "Character reference",
      "gallery.categoryProductRole": "Product reference",
      "gallery.referenceRole": "Reference image",
      "gallery.manage": "Manage gallery",
      "gallery.loadFailed": "Failed to load gallery",
      "gallery.imageOrderUpdateFailed": "Failed to update image order",
      "gallery.imageOrderUpdated": "Image order updated",
      "gallery.categoryName": "Category name",
      "gallery.categoryPromptRole": "Prompt role",
      "gallery.categorySave": "Save",
      "gallery.categoryDelete": "Delete",
      "gallery.categoryLoadFailed": "Failed to load categories",
      "gallery.categoryNameRequired": "Enter a category name",
      "gallery.categoryCreateFailed": "Failed to add category",
      "gallery.categoryCreated": "Category added",
      "gallery.categorySaveFailed": "Failed to save category",
      "gallery.categorySaved": "Category saved",
      "gallery.categoryDeleteTitle": "Delete gallery category?",
      "gallery.categoryDeleteMessage": "Images in this category will move to another category. Gallery images will not be deleted.",
      "gallery.categoryDeleteConfirm": "Delete category",
      "gallery.categoryDeleteFailed": "Failed to delete category",
      "gallery.categoryDeletedMigrated": 'Category "{name}" deleted and images migrated',
      "gallery.categoryOrderUpdateFailed": "Failed to update category order",
      "gallery.categoryOrderUpdated": "Category order updated",
      "gallery.categoryFallback": "Gallery category",
      "gallery.imageFallback": "Gallery image",
      "gallery.imageLoadFailed": "Failed to load this image",
      "gallery.editImageLoadFailed": "Failed to load this image for editing",
      "gallery.cannotAddImage": "This image cannot be added to the gallery",
      "gallery.nameRequired": "Enter a gallery name",
      "gallery.saveFailed": "Failed to save gallery image",
      "gallery.savedAsReference": "Added to gallery and switched to gallery reference",
      "gallery.renameImage": "Rename gallery image",
      "gallery.moveToCategory": "Move to category",
      "gallery.categoryRequired": "Choose a gallery category",
      "gallery.promptNoteTitle": "Gallery reference note",
      "gallery.updateFailed": "Failed to update gallery",
      "gallery.selectImageFile": "Choose an image file",
      "gallery.replaceImageFailed": "Failed to replace gallery image",
      "gallery.replacedImage": 'Replaced the source image for "{name}"',
      "gallery.deleteImageTitle": "Delete gallery image?",
      "gallery.deleteImageMessage": "Historical task references will show as deleted.",
      "gallery.deleteFailed": "Failed to delete gallery image",
      "gallery.deletedSuffix": " (deleted)",
      "gallery.editImageLabel": "Edit gallery image",
      "gallery.fieldCategory": "Category",
      "gallery.fieldPromptNote": "Reference note",
      "gallery.fieldName": "Name",
      "quickGallery.empty": "No {category} images",
      "promptGallery.remove": "Remove @{name}",
      "prompt.title": "Prompt",
      "prompt.editorLabel": "Prompt",
      "prompt.placeholder": "Describe the image you want to generate or edit. Type @ for gallery references, # for color codes, and ~ for prompt snippets.",
      "prompt.run": "Generate",
      "prompt.runEdit": "Start editing",
      "prompt.runTitle": "Generate (Cmd+Enter)",
      "prompt.runEditTitle": "Start editing (Cmd+Enter)",
      "prompt.findPanel": "Find and replace prompt",
      "prompt.findText": "Find text",
      "prompt.replaceWith": "Replace with",
      "prompt.findActions": "Find and replace actions",
      "prompt.countZero": "0 matches",
      "prompt.matchCount": "{count} matches",
      "prompt.foundCount": "Found {count} matches",
      "prompt.noMatch": "No matching text",
      "prompt.replacedCount": "Replaced {count} matches",
      "prompt.closeFind": "Close find and replace",
      "prompt.recentTemplates": "Recent templates",
      "prompt.manageTemplates": "Manage templates",
      "promptModel.galleryHeader": "Reference image notes:",
      "promptModel.galleryInstruction": '- Reference image {number}: gallery "{name}", role: {role}. @{name} in the prompt refers to this image.{note}',
      "outputSettings.title": "Output",
      "output.mainModel": "Main model",
      "output.selectMainModel": "Select main model",
      "output.mainModelCustomForInput": "Use a custom model for the current input",
      "output.apiDirect": "API Direct",
      "output.apiToolModel": "Using API image model",
      "output.mainModelUnused": "Main model is not used for this request",
      "output.webSearch": "Web search",
      "output.webSearchToggle": "On",
      "output.webSearchTitle": "Search the web first, then use it for this generation; Codex and API Responses only",
      "output.promptMode": "Prompt mode",
      "output.modeOriginal": "Original",
      "output.modeStrict": "Faithful",
      "output.modeCreative": "Creative",
      "output.sizeMode": "Size mode",
      "output.sizePreset": "Preset",
      "output.sizeCustom": "Custom",
      "output.orientation": "Orientation",
      "output.square": "Square",
      "output.portrait": "Portrait",
      "output.landscape": "Landscape",
      "output.resolution": "Resolution",
      "output.pixelSize": "Pixel size",
      "output.width": "Width",
      "output.height": "Height",
      "output.swapSize": "Swap width and height",
      "output.customSizeHint": "Unit px \xB7 16-3840 \xB7 multiple of 16 \xB7 \u22643:1",
      "output.imageSizeUnavailable": "Image size unavailable",
      "output.imageLoadFailed": "Image failed to load",
      "output.customSizeRequired": "Enter width and height",
      "output.customSizeBounds": "Width and height must be 16-3840 px",
      "output.customSizeMultiple": "Width and height must be multiples of 16",
      "output.customSizeRatio": "Long-to-short side ratio cannot exceed 3:1",
      "output.customSizePixels": "Total pixels must be 655,360-8,294,400",
      "output.ratioLock": "Ratio lock (optional)",
      "output.customRatio": "Custom aspect ratio",
      "output.ratioWidth": "W",
      "output.ratioHeight": "H",
      "output.firstImageRatio": "Use the first reference image aspect ratio",
      "output.useFirstImage": "From image",
      "output.ratioHint": "Leave blank for free size \xB7 Fill both to sync",
      "output.ratio": "Ratio",
      "output.quality": "Quality",
      "output.qualityAuto": "Auto",
      "output.qualityLow": "Low",
      "output.qualityMedium": "Medium",
      "output.qualityHigh": "High",
      "output.quantity": "Count",
      "output.pixelPreview": "Output pixels: 1024 x 1024 px",
      "output.pixelPreviewValue": "Output pixels: {value}",
      "output.pixelPreviewAuto": "Output pixels: auto (OpenAI chooses automatically)",
      "output.format": "Format",
      "output.compression": "Compression",
      "output.moderation": "Moderation",
      "preview.title": "Preview",
      "preview.selectedZero": "0 selected",
      "preview.selectedCount": "Selected {selected}/{total}",
      "preview.downloadSelected": "Download selected",
      "preview.deleteUnselected": "Delete unselected",
      "preview.downloadAll": "Download ZIP",
      "preview.empty": "No images yet",
      "preview.taskFailed": "Task failed",
      "preview.partialFailed": "Some images failed",
      "preview.failedOutput": "Image {index} failed",
      "preview.progressLine": "Completed {generated} / {total} \xB7 elapsed {elapsed}",
      "preview.failureLine": "Completed {generated} / {total} \xB7 failed {failed}",
      "preview.elapsedLine": "Elapsed {elapsed}",
      "preview.lastError": "Last error: {error}",
      "preview.continueGenerating": "Continuing generation",
      "preview.waitingContinue": "Waiting to continue",
      "preview.retryFailed": "Retry failed images",
      "preview.acceptSuccesses": "Accept successful results",
      "preview.generateMode": "Generation",
      "preview.editMode": "Edit",
      "preview.runningTitle": "{mode} running",
      "preview.submittingTitle": "Submitting task",
      "preview.queuedTitle": "Task queued",
      "preview.submittingDetail": "Saving inputs and adding the task to the queue. Generation will start automatically.",
      "preview.queuedDetail": "The task is in the queue and waiting for an available channel.",
      "preview.featured": "Selected",
      "preview.addFeatured": "Select result",
      "preview.selectedFeatured": "Selected",
      "preview.removeFeatured": "Deselect result",
      "preview.selectionAdded": "Result selected",
      "preview.selectionRemoved": "Result deselected",
      "preview.selectionUpdateFailed": "Failed to update selection",
      "preview.noUnselectedOutputs": "No unselected images to delete",
      "preview.deleteUnselectedTitle": "Delete unselected images?",
      "preview.deleteUnselectedMessage": "This will delete local image files for unselected results in this task.",
      "preview.deleteUnselectedDetail": "Keep {selected}, delete {deleted}",
      "preview.deleteUnselectedFailed": "Failed to delete unselected images",
      "preview.deleteUnselectedDone": "Unselected images deleted",
      "preview.addReference": "Add reference",
      "preview.stage": "Stage",
      "preview.stageReference": "Stage as pending reference",
      "preview.prompt": "Prompt",
      "preview.download": "Download",
      "preview.downloadImage": "Download this image",
      "lightbox.label": "Image preview",
      "lightbox.close": "Close preview",
      "lightbox.previous": "Previous image",
      "lightbox.next": "Next image",
      "promptPopover.title": "Prompt Comparison",
      "promptPopover.summary": "Original {original} \xB7 optimized {optimized}",
      "promptPopover.original": "Original prompt",
      "promptPopover.optimized": "Optimized prompt",
      "promptPopover.charCount": "{count} chars",
      "promptPopover.empty": "None",
      "promptPopover.notReturned": "Not returned",
      "promptPopover.noOptimized": "No optimized prompt returned",
      "promptPopover.submitted": "View submitted prompt",
      "promptPopover.close": "Close prompt comparison",
      "promptPopover.copyOptimized": "Copy optimized prompt",
      "promptPopover.copied": "Copied",
      "taskContext.menuLabel": "Task context menu",
      "taskContext.view": "View task",
      "taskContext.copyId": "Copy task ID",
      "taskContext.copyPrompt": "Copy prompt",
      "taskContext.revealOutput": "Open output folder",
      "taskContext.archive": "Archive task",
      "taskContext.delete": "Delete task",
      "taskContext.idCopied": "Task ID copied",
      "taskContext.promptCopied": "Prompt copied",
      "taskContext.noPrompt": "This task has no prompt to copy",
      "taskContext.revealFailed": "Failed to open output folder",
      "taskContext.revealOpened": "Output folder opened",
      "taskContext.actionFailed": "Task action failed",
      "taskActions.group": "Task actions",
      "taskActions.deleteTitle": "Delete task?",
      "taskActions.deleteMessage": "This will also delete local image files.",
      "taskActions.runningCannotDelete": "Running tasks cannot be deleted",
      "taskActions.updated": "Task status updated",
      "taskActions.archived": "Chat archived",
      "taskActions.archiveFailed": "Archive failed",
      "taskActions.deleted": "Task deleted",
      "taskActions.deleteFailed": "Delete failed",
      "taskActions.noRetryableFailedImages": "This task has no failed images to retry",
      "taskActions.retryFailedOutputsFailed": "Failed to retry failed images",
      "taskActions.requeuedFailedImages": "Failed images requeued",
      "taskActions.noAcceptableSuccessImages": "This task has no successful images to accept",
      "taskActions.acceptSuccessesFailed": "Failed to accept successful results",
      "taskActions.acceptedSuccesses": "Successful results accepted",
      "taskActions.viewedUpdateFailed": "Failed to update read state",
      "taskActions.failedFallback": "Task failed",
      "taskList.empty": "No history yet",
      "taskList.selectSession": "Select chat",
      "taskList.unreadUpdate": "Unread update",
      "taskList.viewing": "Viewing",
      "taskDerived.usageLimited": "Usage limited",
      "taskSubmit.requestFailed": "Request failed",
      "taskSubmit.queued": "Task added to queue",
      "taskSubmit.timeout": "Submitting the task timed out before the backend responded. Refresh the queue to confirm whether it was added, then decide whether to retry.",
      "taskSubmit.failed": "Task submission failed",
      "templates.title": "Prompt Templates",
      "templates.summary": "Local template library",
      "templates.availableCount": "{count} available templates",
      "templates.noMatch": "No matching templates",
      "templates.empty": "No templates",
      "templates.favoriteBadge": "Favorite",
      "templates.usageCount": "{count} uses",
      "templates.back": "Back",
      "templates.edit": "Edit",
      "templates.copy": "Copy",
      "templates.insert": "Insert",
      "templates.formTitle": "Title",
      "templates.formShortTitle": "Short title",
      "templates.formCategory": "Category",
      "templates.formTags": "Tags",
      "templates.formThumbnail": "Thumbnail",
      "templates.formContent": "Content",
      "templates.formNotes": "Notes",
      "templates.formFavorite": "Favorite",
      "templates.thumbnailClear": "Clear",
      "templates.thumbnailNone": "None selected",
      "templates.thumbnailEmpty": "No history thumbnails",
      "templates.newCategory": "New category",
      "templates.search": "Search templates, tags, or content",
      "templates.filter": "Template filters",
      "templates.all": "All",
      "templates.categoryCommon": "Common",
      "templates.categoryPortrait": "Portrait",
      "templates.categoryProduct": "Product",
      "templates.categoryRepair": "Repair",
      "templates.categoryPoster": "Poster",
      "templates.categoryEcommerce": "E-commerce",
      "templates.favorite": "Favorites",
      "templates.recent": "Recent",
      "templates.category": "Categories",
      "templates.loadFailed": "Failed to load prompt templates",
      "templates.useStateUpdateFailed": "Failed to update prompt template usage state",
      "templates.copied": "Prompt template copied",
      "templates.copyFailed": "Failed to copy prompt template",
      "templates.history": "History",
      "templates.saveFailed": "Failed to save prompt template",
      "templates.saved": "Prompt template saved",
      "templates.deleteFailed": "Failed to delete prompt template",
      "templates.deleted": "Prompt template deleted",
      "templates.categoryAddFailed": "Failed to add template category",
      "templates.categoryAdded": "Template category added",
      "templates.categorySaveFailed": "Failed to save template category",
      "templates.categorySaved": "Template category saved",
      "templates.categoryDeleteFailed": "Failed to delete template category",
      "templates.categoryDeleted": "Template category deleted",
      "templates.importFailed": "Failed to import template pack",
      "templates.importedCount": "Imported {count} templates",
      "templates.exportFailed": "Failed to export template pack",
      "templates.exported": "Template pack exported",
      "snippets.suggestLabel": "Prompt snippet picker",
      "snippets.saveSelection": "Save",
      "snippets.saveSelectionLabel": "Save selected text as a prompt snippet",
      "snippets.popoverLabel": "Prompt snippet",
      "snippets.defaultCategory": "Common",
      "snippets.loadFailed": "Failed to load prompt snippets",
      "snippets.remove": "Remove ~{tag}",
      "snippets.expand": "Expand",
      "snippets.edit": "Edit",
      "snippets.close": "Close",
      "snippets.editTitle": "Edit snippet",
      "snippets.saveTitle": "Save snippet",
      "snippets.shortTag": "Short tag",
      "snippets.title": "Title",
      "snippets.category": "Category",
      "snippets.content": "Content",
      "snippets.titlePlaceholder": "Uses short tag by default",
      "snippets.cancel": "Cancel",
      "snippets.save": "Save",
      "snippets.saveFailed": "Failed to save prompt snippet",
      "snippets.saved": "Prompt snippet saved",
      "snippets.defaultTag": "Common snippet",
      "colors.white": "White",
      "colors.black": "Black",
      "colors.warmBeige": "Warm beige",
      "colors.lightGreen": "Light green",
      "colors.brandGreen": "Brand green",
      "colors.peachOrange": "Peach orange",
      "colors.lightBlue": "Light blue",
      "colors.lightPink": "Light pink",
      "colors.loadFailed": "Failed to load color settings",
      "colors.saveFailed": "Failed to save color settings",
      "colors.importFailed": "Failed to import color settings",
      "colors.importedCount": "Imported {count} colors",
      "colors.recentSaveFailed": "Failed to save recent colors",
      "colors.favoriteSaveFailed": "Failed to save favorite color",
      "colors.favoriteDeleteFailed": "Failed to delete favorite color",
      "colors.update": "Update",
      "colors.insert": "Insert",
      "colors.pick": "Choose color",
      "colors.pickShort": "Pick",
      "colors.hexValue": "Color value",
      "colors.pendingUpdate": "Color changed. Click Update to apply.",
      "colors.save": "Save",
      "colors.exportPs": "Export",
      "colors.importPs": "Import",
      "colors.done": "Done",
      "colors.manage": "Manage",
      "colors.favorites": "Favorite colors",
      "colors.recent": "Recent colors",
      "colors.recentLabel": "Recent",
      "colors.deleteFavorite": "Delete favorite color {name}",
      "colors.modify": "Edit color",
      "colors.modifyValue": "Edit color {value}",
      "colors.removeValue": "Remove color {value}",
      "taskGroup.today": "Today",
      "taskGroup.yesterday": "Yesterday",
      "taskGroup.last7": "Last 7 days",
      "taskGroup.older": "Older",
      "taskGroup.searchResults": "Search results",
      "taskGroup.active": "Active",
      "taskGroup.running": "Running",
      "taskGroup.waiting": "Waiting",
      "taskGroup.dispatchPending": "Assigning an available channel...",
      "taskGroup.expand": "Expand {label}",
      "taskGroup.collapse": "Collapse {label}",
      "taskGroup.buttonLabel": "{label}, {count} tasks",
      "archive.title": "Archive",
      "archive.empty": "No archived chats",
      "archive.count": "{count} archived chats",
      "archive.restore": "Restore",
      "archive.archiveFailed": "Archive failed",
      "archive.restoreFailed": "Restore failed",
      "archive.restored": "Chat restored",
      "archive.archiving": "Archiving...",
      "archive.restoring": "Restoring...",
      "archive.deleting": "Deleting...",
      "archive.restoredCount": "Restored {count} tasks",
      "settings.title": "Storage",
      "settings.status": "Restart WebUI after saving",
      "settings.inputRoot": "Input folder",
      "settings.outputRoot": "Output folder",
      "settings.galleryRoot": "Gallery folder",
      "settings.sourceDataRoot": "Source data folder",
      "settings.notificationsCopy": "Notify when tasks complete or fail. System notifications must be enabled manually.",
      "settings.inAppNotification": "In-app notifications",
      "settings.systemNotification": "System notifications",
      "settings.save": "Save settings",
      "settings.loadFailed": "Failed to load settings",
      "settings.saveFailed": "Failed to save settings",
      "settings.savedRestart": "Saved. Restart WebUI to apply.",
      "settings.saved": "Saved",
      "settings.savedRestartStatus": "Settings saved. Restart WebUI to apply.",
      "apiSettings.title": "API Settings",
      "apiSettings.status": "Saved settings apply immediately in Codex and API mode",
      "apiSettings.codexMode": "Codex channel",
      "apiSettings.codexImages": "Image",
      "apiSettings.codexResponses": "Responses",
      "apiSettings.provider": "Provider",
      "apiSettings.providerName": "Provider name",
      "apiSettings.mode": "Request mode",
      "apiSettings.images": "Direct Image API",
      "apiSettings.responses": "Responses API",
      "apiSettings.modeImagesShort": "Direct",
      "apiSettings.imageModel": "Image model",
      "apiSettings.concurrency": "Provider concurrency limit",
      "apiSettings.save": "Save API settings",
      "apiSettings.loadFailed": "Failed to load API settings",
      "apiSettings.savedKeyPlaceholder": "API key is saved on the backend. Enter a new key to replace it.",
      "apiSettings.newProvider": "New provider",
      "apiSettings.saving": "Saving...",
      "apiSettings.savingStatus": "Saving API settings...",
      "apiSettings.saveFailed": "Failed to save API settings",
      "apiSettings.savedSummary": "Saved \xB7 Codex {codex} \xB7 API {provider} \xB7 {mode} \xB7 {model} \xB7 concurrency {concurrency}",
      "apiSettings.savedShort": "Saved",
      "apiSettings.savedStatus": "API settings saved",
      "apiSettings.saveFailedShort": "Save failed",
      "imageEditor.title": "Edit Input Image",
      "imageEditor.promptHint": "Hand-drawn arrows and marks in the image are only instructions. Do not keep them in the final image.",
      "imageEditor.inputFallback": "Input image",
      "imageEditor.openFailed": "Failed to open this image for editing",
      "imageEditor.loadForEditFailed": "Failed to load this image for editing",
      "imageEditor.canvasCreateFailed": "Failed to create the image editing canvas",
      "imageEditor.closedRegionRequired": "Use the brush to draw a closed region first",
      "imageEditor.saveFailed": "Failed to save image edit",
      "imageEditor.saved": "Edited input image saved",
      "imageEditor.uneditable": "This image cannot be edited",
      "imageEditor.resetDone": "Reset to original image",
      "imageEditor.resetFailed": "Failed to reset the original image",
      "imageEditor.subtitle": "Crop, draw, fill, or add arrows, then save as a new input image",
      "imageEditor.toolbar": "Image editor toolbar",
      "imageEditor.tools": "Tools",
      "imageEditor.brush": "Brush",
      "imageEditor.arrow": "Arrow",
      "imageEditor.crop": "Crop",
      "imageEditor.fill": "Fill",
      "imageEditor.fillLabel": "Paint bucket fill",
      "imageEditor.colors": "Colors",
      "imageEditor.red": "Red",
      "imageEditor.blue": "Blue",
      "imageEditor.green": "Green",
      "imageEditor.yellow": "Yellow",
      "imageEditor.white": "White",
      "imageEditor.black": "Black",
      "imageEditor.customColor": "Custom color",
      "imageEditor.stroke": "Stroke",
      "imageEditor.history": "History",
      "imageEditor.undo": "Undo",
      "imageEditor.redo": "Redo",
      "imageEditor.reset": "Reset image",
      "imageEditor.canvas": "Image editing canvas",
      "gallery.title": "Gallery",
      "gallery.subtitle": "Choose reference images for the current task",
      "gallery.manageCategories": "Manage categories",
      "gallery.categoryManager": "Manage gallery categories",
      "gallery.categoryManagement": "Category management",
      "gallery.categoryCopy": "Categories are saved to the gallery; prompt roles describe how references are used.",
      "gallery.newCategoryName": "New category name",
      "gallery.newCategoryRole": "Prompt role, e.g. style reference",
      "gallery.addCategory": "Add category",
      "gallery.drawerSubtitle": 'Current category: {category}. Click "Use" to add it to image input.',
      "gallery.emptyCategory": "No images in this category yet",
      "gallery.dragSort": "Drag to sort",
      "gallery.dragSortImage": "Drag-sort image {name}",
      "gallery.dragSortCategory": "Drag-sort category {name}",
      "gallery.use": "Use",
      "gallery.replace": "Replace",
      "gallery.rename": "Rename",
      "gallery.moveCategory": "Category",
      "gallery.note": "Note",
      "gallery.delete": "Delete",
      "gallery.uncategorized": "Uncategorized",
      "addGallery.title": "Add to Gallery",
      "addGallery.copy": "Names are globally unique and can be referenced with @name later",
      "addGallery.name": "Name",
      "addGallery.namePlaceholder": "Example: Mia",
      "addGallery.category": "Category",
      "addGallery.note": "Reference note",
      "addGallery.notePlaceholder": "Example: reference face and hair only, not clothing or background",
      "addGallery.save": "Save to gallery",
      "close.promptTemplates": "Close prompt templates panel",
      "close.archive": "Close archive panel",
      "close.settings": "Close storage settings panel",
      "close.apiSettings": "Close API settings panel",
      "close.imageEditor": "Close image editor panel",
      "close.gallery": "Close gallery panel",
      "close.addGallery": "Close add to gallery panel",
      "close.version": "Close version update panel"
    }
  };
  var currentLocale = DEFAULT_LOCALE;
  function canUseLocale(value) {
    return LOCALES.includes(value);
  }
  function normalizeLocale(value) {
    return canUseLocale(value) ? value : DEFAULT_LOCALE;
  }
  function translate(key, locale = currentLocale) {
    return DICTIONARIES[locale]?.[key] ?? DICTIONARIES[DEFAULT_LOCALE][key] ?? key;
  }
  function formatTranslation(key, values = {}, locale = currentLocale) {
    return translate(key, locale).replace(/\{(\w+)\}/g, (match, name) => {
      const value = values[name];
      return value === void 0 ? match : String(value);
    });
  }
  function translationPairs(value) {
    const pairs = [];
    (value || "").split(";").map((item) => item.trim()).filter(Boolean).forEach((pair) => {
      const [attribute, key] = pair.split(":").map((item) => item.trim());
      if (attribute && key) pairs.push([attribute, key]);
    });
    return pairs;
  }
  function languageSwitcherElement() {
    try {
      return getLegacyBridge().els.languageSwitcher || null;
    } catch {
      return null;
    }
  }
  function updateLanguageSwitcher() {
    const switcher = languageSwitcherElement();
    switcher?.querySelectorAll("[data-language-option]").forEach((button) => {
      const active = normalizeLocale(button.dataset.languageOption) === currentLocale;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }
  function applyLocaleToDocument() {
    document.documentElement.lang = currentLocale;
    document.documentElement.dataset.locale = currentLocale;
    document.querySelectorAll("[data-i18n]").forEach((element) => {
      element.textContent = translate(element.dataset.i18n || "");
    });
    document.querySelectorAll("[data-i18n-attr]").forEach((element) => {
      translationPairs(element.dataset.i18nAttr).forEach(([attribute, key]) => {
        element.setAttribute(attribute, translate(key));
      });
    });
    updateLanguageSwitcher();
  }
  function setLocale(locale, options = {}) {
    currentLocale = normalizeLocale(locale);
    if (options.persist !== false) {
      try {
        localStorage.setItem(LOCALE_STORAGE_KEY, currentLocale);
      } catch {
      }
    }
    applyLocaleToDocument();
    document.dispatchEvent(new CustomEvent(LOCALE_CHANGE_EVENT, { detail: { locale: currentLocale } }));
  }
  function restoreLocalePreference() {
    let saved = DEFAULT_LOCALE;
    try {
      saved = localStorage.getItem(LOCALE_STORAGE_KEY) || DEFAULT_LOCALE;
    } catch {
      saved = DEFAULT_LOCALE;
    }
    setLocale(normalizeLocale(saved), { persist: false });
  }

  // codex_image/webui/frontend/src/webui-utils.ts
  function escapeHtml(value) {
    return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }

  // codex_image/webui/frontend/src/history-detail-media.ts
  function positiveInt(value) {
    const parsed = Number.parseInt(String(value ?? ""), 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }
  function parseSizeParts(value) {
    const match = String(value || "").trim().toLowerCase().match(/^(\d+)\s*x\s*(\d+)$/);
    if (!match) return null;
    const width = positiveInt(match[1]);
    const height = positiveInt(match[2]);
    return width && height ? [width, height] : null;
  }
  function outputSizeForTask(task, index, output = {}) {
    return parseSizeParts(output?.size || output?.output_size) || parseSizeParts(Array.isArray(task?.output_sizes) ? task.output_sizes[index] : "") || parseSizeParts(task?.output_size) || parseSizeParts(task?.params?.size);
  }
  function outputOrientation(record) {
    if (!record.width || !record.height) return "unknown";
    if (record.width > record.height) return "landscape";
    if (record.height > record.width) return "portrait";
    return "square";
  }
  function taskSelectedOutputIndexes(task) {
    const indexes = /* @__PURE__ */ new Set();
    if (Array.isArray(task?.selected_output_indexes)) {
      task.selected_output_indexes.forEach((value) => {
        const index = positiveInt(value);
        if (index !== null) indexes.add(index);
      });
    }
    return indexes;
  }
  function taskOutputRecords(task) {
    const selectedIndexes = taskSelectedOutputIndexes(task);
    const records = [];
    const outputs = Array.isArray(task?.outputs) ? task.outputs : [];
    outputs.forEach((output, fallbackIndex) => {
      if (!output || output.deleted || output.status === "deleted") return;
      const url = String(output.url || output.output_url || "");
      if (!url || output.status === "failed") return;
      const outputIndex = positiveInt(output.index) || fallbackIndex + 1;
      const size = outputSizeForTask(task, fallbackIndex, output);
      records.push({
        url,
        index: outputIndex,
        selected: selectedIndexes.has(outputIndex),
        revisedPrompt: String(output.revised_prompt || ""),
        width: size?.[0] || null,
        height: size?.[1] || null
      });
    });
    if (records.length) return records;
    const urls = Array.isArray(task?.output_urls) ? task.output_urls : task?.output_url ? [task.output_url] : [];
    return urls.filter(Boolean).map((url, index) => {
      const outputIndex = index + 1;
      const size = outputSizeForTask(task, index);
      return {
        url: String(url),
        index: outputIndex,
        selected: selectedIndexes.has(outputIndex),
        revisedPrompt: String(task?.revised_prompts?.[index] || task?.revised_prompt || ""),
        width: size?.[0] || null,
        height: size?.[1] || null
      };
    });
  }
  function historyDetailImagesLayoutClass(records) {
    if (records.length <= 1) return "";
    const orientations = records.map(outputOrientation);
    const known = orientations.filter((orientation2) => orientation2 !== "unknown");
    const allKnown = known.length === records.length;
    const orientation = allKnown && known.every((value) => value === "portrait") ? "portrait" : allKnown && known.every((value) => value === "landscape") ? "landscape" : allKnown && known.every((value) => value === "square") ? "square" : "mixed";
    const stack = records.length === 2 && (orientation === "landscape" || orientation === "square");
    return ` history-detail-images-multi history-detail-images-count-${Math.min(records.length, 4)} history-detail-images-${orientation}${stack ? " history-detail-images-stack" : ""}`;
  }
  function inputRecordLabel(source, fallbackIndex) {
    return String(source?.name || source?.filename || source?.category_name || source?.category || formatTranslation("history.inputReferenceIndex", { index: fallbackIndex }));
  }
  function taskInputRecords(task) {
    const records = [];
    const seen = /* @__PURE__ */ new Set();
    const addRecord = (url, thumbnailUrl, label) => {
      const fullUrl = String(url || thumbnailUrl || "");
      const thumb = String(thumbnailUrl || url || "");
      if (!fullUrl || seen.has(fullUrl)) return;
      seen.add(fullUrl);
      records.push({
        url: fullUrl,
        thumbnailUrl: thumb,
        label: String(label || formatTranslation("history.inputReferenceIndex", { index: records.length + 1 }))
      });
    };
    if (Array.isArray(task?.input_sources)) {
      task.input_sources.forEach((source, index) => {
        if (!source || source.missing) return;
        addRecord(source.image_url || source.url, source.thumbnail_url || source.image_url || source.url, inputRecordLabel(source, index + 1));
      });
    }
    if (!records.length) {
      const inputUrls = Array.isArray(task?.input_urls) ? task.input_urls : [];
      const inputThumbnailUrls = Array.isArray(task?.input_thumbnail_urls) ? task.input_thumbnail_urls : [];
      inputUrls.forEach((url, index) => {
        addRecord(url, inputThumbnailUrls[index] || url, formatTranslation("history.inputReferenceIndex", { index: index + 1 }));
      });
    }
    return records;
  }
  function outputRevisedPromptHtml(taskId, record, index) {
    const revisedPrompt = String(record.revisedPrompt || "").trim();
    if (!revisedPrompt) return "";
    const displayIndex = index + 1;
    const title = formatTranslation("history.outputRevisedPromptTitle", { index: displayIndex });
    return `
    <div class="history-detail-output-prompt">
      <div class="history-detail-output-prompt-header">
        <span>${escapeHtml(title)}</span>
        <button
          class="ghost-button text-sm history-prompt-copy"
          type="button"
          data-history-copy-output-prompt-task-id="${escapeHtml(taskId)}"
          data-history-copy-output-prompt-index="${record.index}"
          aria-label="${escapeHtml(formatTranslation("history.copyOutputPromptPanel", { index: displayIndex }))}"
        >${escapeHtml(translate("history.copyPromptShort"))}</button>
      </div>
      <div class="history-detail-output-prompt-text">${escapeHtml(revisedPrompt)}</div>
    </div>
  `;
  }
  function historyDetailImageHtml(taskId, record, index, selectedCount, totalCount) {
    const selectedClass = record.selected ? " selected" : "";
    const selectedText = record.selected ? translate("history.selected") : translate("history.select");
    const outputBadge = totalCount > 1 ? `<span class="history-detail-output-index">${index + 1} / ${totalCount}</span>` : "";
    const revisedPrompt = outputRevisedPromptHtml(taskId, record, index);
    return `
    <article class="history-detail-image history-detail-output-card${selectedClass}">
      <button
        class="history-detail-image-preview history-detail-output-preview"
        type="button"
        data-history-lightbox-url="${escapeHtml(record.url)}"
        data-history-lightbox-index="${index}"
        aria-label="${escapeHtml(translate("history.openPreview"))}"
      >
        ${outputBadge}
        <img src="${escapeHtml(record.url)}" alt="" loading="lazy" decoding="async">
      </button>
      <div class="history-detail-image-actions" aria-label="${escapeHtml(translate("history.outputActions"))}">
        <button
          class="history-detail-overlay-button"
          type="button"
          aria-pressed="${record.selected ? "true" : "false"}"
          data-history-output-selected-task-id="${escapeHtml(taskId)}"
          data-history-output-selected-index="${record.index}"
        >${selectedText}</button>
        <a class="history-detail-overlay-button" href="${escapeHtml(record.url)}" download>${escapeHtml(formatTranslation("history.downloadIndex", { index: index + 1 }))}</a>
        <button class="history-detail-overlay-button primary" type="button" data-history-reference-handoff-url="${escapeHtml(record.url)}">${escapeHtml(translate("history.addReference"))}</button>
        ${selectedCount === 1 && record.selected ? `<a class="history-detail-overlay-button" href="${escapeHtml(record.url)}" download>${escapeHtml(translate("history.downloadSelected"))}</a>` : ""}
      </div>
      ${revisedPrompt}
    </article>
  `;
  }
  function historyDetailImagesHtml(taskId, records, selectedCount) {
    return records.map((record, index) => historyDetailImageHtml(taskId, record, index, selectedCount, records.length)).join("");
  }
  function historyInputReferencesHtml(task) {
    const records = taskInputRecords(task);
    if (!records.length) return "";
    const thumbs = records.map((record, index) => `
    <button
      class="history-detail-input-thumb"
      type="button"
      title="${escapeHtml(record.label)}"
      data-history-input-lightbox-index="${index}"
      aria-label="${escapeHtml(formatTranslation("history.inputReferenceIndex", { index: index + 1 }))}"
    >
      <img src="${escapeHtml(record.thumbnailUrl)}" alt="" loading="lazy" decoding="async">
    </button>
  `).join("");
    return `
    <section class="history-detail-inputs" aria-label="${escapeHtml(translate("history.inputReferences"))}">
      <div class="history-detail-inputs-header">
        <h3>${escapeHtml(translate("history.inputReferences"))}</h3>
        <span>${records.length}</span>
      </div>
      <div class="history-detail-inputs-list">${thumbs}</div>
    </section>
  `;
  }
  function historyLightboxUrlsFromTask(task) {
    return taskOutputRecords(task).map((record) => record.url).filter(Boolean);
  }
  function historyInputLightboxUrlsFromTask(task) {
    return taskInputRecords(task).map((record) => record.url).filter(Boolean);
  }

  // codex_image/webui/frontend/src/history-window.ts
  function historyTaskCards(root) {
    return [...root.querySelectorAll(".history-task-card[data-history-task-card-id]")];
  }
  function encodeHistoryCursor(createdAt, taskId) {
    const raw = JSON.stringify({ created_at: createdAt, task_id: taskId });
    const bytes = new TextEncoder().encode(raw);
    let binary = "";
    bytes.forEach((byte) => {
      binary += String.fromCharCode(byte);
    });
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  }
  function historyWindowEdgeCursor(root, edge) {
    const cards = historyTaskCards(root);
    const card = edge === "top" ? cards[0] : cards[cards.length - 1];
    if (!card) return "";
    const taskId = String(card.dataset.historyTaskCardId || "");
    const createdAt = String(card.dataset.historyCreatedAt || "");
    return taskId && createdAt ? encodeHistoryCursor(createdAt, taskId) : "";
  }
  function captureHistoryScrollAnchor(root) {
    const rootTop = root.getBoundingClientRect().top;
    for (const card of historyTaskCards(root)) {
      const rect = card.getBoundingClientRect();
      if (rect.bottom < rootTop) continue;
      const taskId = String(card.dataset.historyTaskCardId || "");
      if (!taskId) continue;
      return { taskId, offset: rect.top - rootTop };
    }
    return null;
  }
  function restoreHistoryScrollAnchor(root, anchor) {
    if (!anchor) return;
    const card = historyTaskCards(root).find((item) => String(item.dataset.historyTaskCardId || "") === anchor.taskId);
    if (!card) return;
    const rootTop = root.getBoundingClientRect().top;
    const nextOffset = card.getBoundingClientRect().top - rootTop;
    root.scrollTop += nextOffset - anchor.offset;
  }

  // codex_image/webui/frontend/src/history-lightbox.ts
  var historyLightboxEl = null;
  var historyLightboxState = {
    urls: [],
    index: 0,
    taskId: "",
    onTaskNavigate: null,
    scale: 1,
    pointX: 0,
    pointY: 0,
    panning: false,
    startX: 0,
    startY: 0
  };
  function normalizedHistoryLightboxIndex(index, count) {
    if (!count) return 0;
    return (index % count + count) % count;
  }
  function historyLightboxImage() {
    return historyLightboxEl?.querySelector("[data-history-lightbox-image]") || null;
  }
  function isHistoryLightboxActive() {
    return Boolean(historyLightboxEl && !historyLightboxEl.hidden);
  }
  function stopHistoryLightboxPanning() {
    historyLightboxState.panning = false;
  }
  function setHistoryLightboxTransform() {
    const image = historyLightboxImage();
    if (!image) return;
    image.style.transform = `translate(${historyLightboxState.pointX}px, ${historyLightboxState.pointY}px) scale(${historyLightboxState.scale})`;
  }
  function resetHistoryLightboxTransform() {
    historyLightboxState.scale = 1;
    historyLightboxState.pointX = 0;
    historyLightboxState.pointY = 0;
    stopHistoryLightboxPanning();
    setHistoryLightboxTransform();
  }
  function updateHistoryLightboxControls() {
    if (!historyLightboxEl) return;
    const hasMultipleImages = historyLightboxState.urls.length > 1;
    const prevButton = historyLightboxEl.querySelector("[data-history-lightbox-prev]");
    const nextButton = historyLightboxEl.querySelector("[data-history-lightbox-next]");
    const counter = historyLightboxEl.querySelector("[data-history-lightbox-counter]");
    [prevButton, nextButton, counter].forEach((element) => {
      element?.classList.toggle("hidden", !hasMultipleImages);
    });
    if (counter) {
      counter.textContent = hasMultipleImages ? `${historyLightboxState.index + 1} / ${historyLightboxState.urls.length}` : "";
    }
  }
  function showHistoryLightboxImage(index) {
    if (!historyLightboxEl || !historyLightboxState.urls.length) return;
    const image = historyLightboxImage();
    if (!image) return;
    historyLightboxState.index = normalizedHistoryLightboxIndex(index, historyLightboxState.urls.length);
    image.src = historyLightboxState.urls[historyLightboxState.index] || "";
    resetHistoryLightboxTransform();
    updateHistoryLightboxControls();
  }
  function showPreviousHistoryLightboxImage() {
    if (!isHistoryLightboxActive() || historyLightboxState.urls.length < 2) return;
    showHistoryLightboxImage(historyLightboxState.index - 1);
  }
  function showNextHistoryLightboxImage() {
    if (!isHistoryLightboxActive() || historyLightboxState.urls.length < 2) return;
    showHistoryLightboxImage(historyLightboxState.index + 1);
  }
  function navigateHistoryLightboxTask(direction) {
    if (!isHistoryLightboxActive() || !historyLightboxState.onTaskNavigate) return;
    void historyLightboxState.onTaskNavigate(direction, {
      taskId: historyLightboxState.taskId,
      imageIndex: historyLightboxState.index
    });
  }
  function showPreviousHistoryTask() {
    navigateHistoryLightboxTask("previous");
  }
  function showNextHistoryTask() {
    navigateHistoryLightboxTask("next");
  }
  function ensureHistoryLightbox() {
    if (historyLightboxEl) return historyLightboxEl;
    historyLightboxEl = document.createElement("div");
    historyLightboxEl.className = "history-lightbox";
    historyLightboxEl.hidden = true;
    historyLightboxEl.setAttribute("role", "dialog");
    historyLightboxEl.setAttribute("aria-modal", "true");
    historyLightboxEl.setAttribute("aria-label", translate("lightbox.label"));
    historyLightboxEl.innerHTML = `
    <button class="history-lightbox-close" type="button" data-history-lightbox-close aria-label="${escapeHtml(translate("lightbox.close"))}">
      <svg class="drawer-close-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M6 6l12 12M18 6L6 18"></path>
      </svg>
    </button>
    <button class="history-lightbox-nav history-lightbox-prev" type="button" data-history-lightbox-prev aria-label="${escapeHtml(translate("lightbox.previous"))}">&lsaquo;</button>
    <img alt="" draggable="false" data-history-lightbox-image>
    <button class="history-lightbox-nav history-lightbox-next" type="button" data-history-lightbox-next aria-label="${escapeHtml(translate("lightbox.next"))}">&rsaquo;</button>
    <div class="history-lightbox-counter" data-history-lightbox-counter aria-live="polite"></div>
  `;
    document.body.append(historyLightboxEl);
    historyLightboxEl.querySelector("[data-history-lightbox-close]")?.addEventListener("click", closeHistoryLightbox);
    historyLightboxEl.querySelector("[data-history-lightbox-prev]")?.addEventListener("click", showPreviousHistoryLightboxImage);
    historyLightboxEl.querySelector("[data-history-lightbox-next]")?.addEventListener("click", showNextHistoryLightboxImage);
    historyLightboxEl.addEventListener("wheel", (event) => {
      if (!isHistoryLightboxActive()) return;
      event.preventDefault();
      const delta = event.deltaY * -5e-3;
      historyLightboxState.scale = Math.min(Math.max(0.5, historyLightboxState.scale + delta), 5);
      setHistoryLightboxTransform();
    }, { passive: false });
    historyLightboxEl.addEventListener("click", (event) => {
      if (event.target === historyLightboxEl) closeHistoryLightbox();
    });
    const image = historyLightboxImage();
    image?.addEventListener("mousedown", (event) => {
      if (event.button !== 0) {
        stopHistoryLightboxPanning();
        return;
      }
      event.preventDefault();
      historyLightboxState.panning = true;
      historyLightboxState.startX = event.clientX - historyLightboxState.pointX;
      historyLightboxState.startY = event.clientY - historyLightboxState.pointY;
    });
    image?.addEventListener("contextmenu", stopHistoryLightboxPanning);
    window.addEventListener("mousemove", (event) => {
      if (!historyLightboxState.panning) return;
      if (event.buttons !== void 0 && (event.buttons & 1) !== 1) {
        stopHistoryLightboxPanning();
        return;
      }
      historyLightboxState.pointX = event.clientX - historyLightboxState.startX;
      historyLightboxState.pointY = event.clientY - historyLightboxState.startY;
      setHistoryLightboxTransform();
    });
    window.addEventListener("mouseup", stopHistoryLightboxPanning);
    window.addEventListener("blur", stopHistoryLightboxPanning);
    window.addEventListener("keydown", (event) => {
      if (!isHistoryLightboxActive()) return;
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        showPreviousHistoryLightboxImage();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        showNextHistoryLightboxImage();
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        showPreviousHistoryTask();
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        showNextHistoryTask();
      } else if (event.key === "PageUp") {
        event.preventDefault();
        showPreviousHistoryTask();
      } else if (event.key === "PageDown") {
        event.preventDefault();
        showNextHistoryTask();
      }
    });
    return historyLightboxEl;
  }
  function openHistoryLightbox(urls, index = 0, options = {}) {
    const nextUrls = Array.isArray(urls) ? urls.filter(Boolean) : [];
    if (!nextUrls.length) return;
    const lightbox = ensureHistoryLightbox();
    historyLightboxState.urls = nextUrls;
    historyLightboxState.index = normalizedHistoryLightboxIndex(index, nextUrls.length);
    historyLightboxState.taskId = String(options.taskId || "");
    historyLightboxState.onTaskNavigate = options.onTaskNavigate || null;
    showHistoryLightboxImage(historyLightboxState.index);
    lightbox.hidden = false;
    document.body.classList.add("history-lightbox-open");
    updateHistoryLightboxControls();
  }
  function closeHistoryLightbox() {
    if (!historyLightboxEl || historyLightboxEl.hidden) return;
    historyLightboxEl.hidden = true;
    const image = historyLightboxImage();
    if (image) image.removeAttribute("src");
    stopHistoryLightboxPanning();
    historyLightboxState.urls = [];
    historyLightboxState.index = 0;
    historyLightboxState.taskId = "";
    historyLightboxState.onTaskNavigate = null;
    resetHistoryLightboxTransform();
    document.body.classList.remove("history-lightbox-open");
  }
  function isHistoryLightboxOpen() {
    return isHistoryLightboxActive();
  }

  // codex_image/webui/frontend/src/segmented-indicator.ts
  var HOST_SELECTORS = [".radio-group:not(.ratio-group)", "#authSourceGroup", "#languageSwitcher", ".history-view-toggle", ".history-sort-toggle"];
  var HOST_SELECTOR = HOST_SELECTORS.join(", ");
  var BUTTON_SELECTOR = ".radio-btn, .auth-source-button, .language-option, .history-view-button, .history-sort-button";
  var INDICATOR_CLASS = "segmented-indicator";
  var HOST_CLASS = "segmented-indicator-host";
  var initializedHosts = /* @__PURE__ */ new WeakSet();
  var scheduledFrames = /* @__PURE__ */ new WeakMap();
  var segmentedIndicatorsInitialized = false;
  var resizeObserver = null;
  function activeSegment(host) {
    return host.querySelector(".radio-btn.active, .auth-source-button.active, .language-option.active, .history-view-button.active, .history-sort-button.active");
  }
  function ensureIndicator(host) {
    const existing = Array.from(host.children).find((child) => child.classList.contains(INDICATOR_CLASS));
    if (existing instanceof HTMLElement) return existing;
    const indicator = document.createElement("span");
    indicator.className = INDICATOR_CLASS;
    indicator.setAttribute("aria-hidden", "true");
    host.insertBefore(indicator, host.firstElementChild);
    return indicator;
  }
  function updateIndicator(host) {
    scheduledFrames.delete(host);
    if (!host.isConnected) return;
    const indicator = ensureIndicator(host);
    const active = activeSegment(host);
    if (!active) {
      indicator.style.setProperty("--segmented-indicator-opacity", "0");
      return;
    }
    const hostRect = host.getBoundingClientRect();
    const activeRect = active.getBoundingClientRect();
    const hostStyle = window.getComputedStyle(host);
    const borderLeft = Number.parseFloat(hostStyle.borderLeftWidth) || 0;
    const borderTop = Number.parseFloat(hostStyle.borderTopWidth) || 0;
    indicator.style.setProperty("--segmented-indicator-x", `${activeRect.left - hostRect.left - borderLeft}px`);
    indicator.style.setProperty("--segmented-indicator-y", `${activeRect.top - hostRect.top - borderTop}px`);
    indicator.style.setProperty("--segmented-indicator-width", `${activeRect.width}px`);
    indicator.style.setProperty("--segmented-indicator-height", `${activeRect.height}px`);
    indicator.style.setProperty("--segmented-indicator-opacity", "1");
  }
  function scheduleIndicatorUpdate(host) {
    if (scheduledFrames.has(host)) return;
    scheduledFrames.set(host, window.requestAnimationFrame(() => updateIndicator(host)));
  }
  function watchButtonClassChanges(host) {
    const observer = new MutationObserver(() => scheduleIndicatorUpdate(host));
    host.querySelectorAll(BUTTON_SELECTOR).forEach((button) => {
      observer.observe(button, { attributes: true, attributeFilter: ["class"] });
    });
  }
  function initHost(host) {
    if (initializedHosts.has(host)) return;
    initializedHosts.add(host);
    host.classList.add(HOST_CLASS);
    ensureIndicator(host);
    host.addEventListener("click", () => scheduleIndicatorUpdate(host));
    watchButtonClassChanges(host);
    if ("ResizeObserver" in window) {
      resizeObserver || (resizeObserver = new ResizeObserver((entries) => {
        entries.forEach((entry) => scheduleIndicatorUpdate(entry.target));
      }));
      resizeObserver.observe(host);
    }
    scheduleIndicatorUpdate(host);
  }
  function updateAllIndicators() {
    document.querySelectorAll(HOST_SELECTOR).forEach(scheduleIndicatorUpdate);
  }
  function initSegmentedIndicatorFeature() {
    if (segmentedIndicatorsInitialized) return;
    segmentedIndicatorsInitialized = true;
    document.querySelectorAll(HOST_SELECTOR).forEach(initHost);
    window.addEventListener("resize", updateAllIndicators, { passive: true });
    document.fonts?.ready?.then(updateAllIndicators).catch(() => {
    });
  }

  // codex_image/webui/frontend/src/history.ts
  var HISTORY_FILTER_KEYS = ["month", "prompt_mode", "quality", "ratio", "orientation", "backend", "provider", "archived"];
  var HISTORY_RATIO_OTHER_VALUE = "__other__";
  var HISTORY_PAGE_LIMIT = 50;
  var MAX_MOUNTED_TASK_CARDS = 300;
  var HISTORY_REFERENCE_HANDOFF_KEY = "codex-image-history-reference-handoff";
  var HISTORY_TASK_REUSE_HANDOFF_KEY = "codex-image-history-task-reuse-handoff";
  var HISTORY_THEME_STORAGE_KEY = "codex-image-theme-preference";
  var HISTORY_THUMBNAIL_CACHE_VERSION = "thumb-768-fit";
  var HISTORY_GRID_DEFAULT_GAP = 14;
  var HISTORY_LAYOUT_STORAGE_KEY = "codex-image-history-layout";
  var HISTORY_LAYOUT_DEFAULTS = { left: 280, right: 380 };
  var HISTORY_LAYOUT_LIMITS = {
    leftMin: 220,
    leftMax: 420,
    rightMin: 300,
    rightMax: 620,
    middleMin: 360,
    resizerWidth: 8
  };
  var historyState = {
    q: "",
    month: "",
    prompt_mode: "",
    quality: "",
    ratio: "",
    orientation: "",
    backend: "",
    provider: "",
    archived: "",
    sort: "newest",
    view: "grid",
    nextCursor: null,
    newerExhausted: true,
    loading: false,
    exhausted: false,
    loadedTaskIds: /* @__PURE__ */ new Set(),
    loadedTaskSummaries: /* @__PURE__ */ new Map(),
    selectedTaskIds: /* @__PURE__ */ new Set(),
    selectedTaskId: "",
    selectionAnchorTaskId: "",
    deleteConfirming: false,
    deleteConfirmTaskId: "",
    deleteUnselectedConfirmTaskId: "",
    detailTask: null,
    contextMenuDeleteConfirmKey: "",
    contextMenu: {
      mode: "single",
      taskId: "",
      taskIds: [],
      x: 0,
      y: 0
    },
    requestId: 0
  };
  var historyGridLayoutFrame = 0;
  var pendingHistoryGridKeepTaskId = "";
  var historyContextMenuEl = null;
  var activeHistoryResizer = null;
  var els = {
    page: document.querySelector(".history-page"),
    sidebar: document.querySelector(".history-sidebar"),
    leftResizer: document.querySelector('[data-history-resizer="left"]'),
    rightResizer: document.querySelector('[data-history-resizer="right"]'),
    total: document.querySelector("#historyTotal"),
    search: document.querySelector("#historySearch"),
    searchClear: document.querySelector("#historySearchClear"),
    monthList: document.querySelector("#historyMonthList"),
    promptModeList: document.querySelector("#historyPromptModeList"),
    qualityList: document.querySelector("#historyQualityList"),
    ratioList: document.querySelector("#historyRatioList"),
    orientationList: document.querySelector("#historyOrientationList"),
    backendList: document.querySelector("#historyBackendList"),
    providerList: document.querySelector("#historyProviderList"),
    archiveList: document.querySelector("#historyArchiveList"),
    sortToggle: document.querySelector("#historySortToggle"),
    viewToggle: document.querySelector("#historyViewToggle"),
    resultSummary: document.querySelector("#historyResultSummary"),
    bulkToolbar: document.querySelector("#historyBulkToolbar"),
    bulkCount: document.querySelector("#historyBulkCount"),
    bulkArchive: document.querySelector("#historyBulkArchiveButton"),
    bulkRestore: document.querySelector("#historyBulkRestoreButton"),
    bulkDelete: document.querySelector("#historyBulkDeleteButton"),
    bulkDeleteCancel: document.querySelector("#historyBulkDeleteCancelButton"),
    taskList: document.querySelector("#historyTaskList"),
    detail: document.querySelector("#historyDetail"),
    sentinel: document.querySelector("[data-history-load-more]"),
    refresh: document.querySelector("#historyRefreshButton")
  };
  function escapeHtml2(value) {
    return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
  }
  function formatDate(value) {
    if (!value) return "";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value.slice(0, 16).replace("T", " ");
    return date.toLocaleString(void 0, { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }
  function setText(element, text) {
    if (element) element.textContent = text;
  }
  function normalizeHistoryThemePreference(value) {
    return value === "light" || value === "dark" ? value : "system";
  }
  function resolveHistoryTheme(preference) {
    if (preference === "light" || preference === "dark") return preference;
    return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
  }
  function restoreHistoryThemePreference() {
    let saved = "system";
    try {
      saved = localStorage.getItem(HISTORY_THEME_STORAGE_KEY) || "system";
    } catch {
      saved = "system";
    }
    const preference = normalizeHistoryThemePreference(saved);
    document.documentElement.dataset.themePreference = preference;
    document.documentElement.dataset.theme = resolveHistoryTheme(preference);
  }
  function bindHistoryThemePreference() {
    window.matchMedia?.("(prefers-color-scheme: dark)")?.addEventListener?.("change", () => {
      if (document.documentElement.dataset.themePreference === "system") {
        restoreHistoryThemePreference();
      }
    });
  }
  function applyHistoryLocale() {
    restoreLocalePreference();
    document.title = translate("history.documentTitle");
  }
  function truncateText(value, limit) {
    const text = String(value || "").replace(/\s+/g, " ").trim();
    return text.length <= limit ? text : text.slice(0, limit - 1).trimEnd() + "\u2026";
  }
  function historyFilterAttribute(key) {
    return key.replace(/_/g, "-");
  }
  function facetDisplayValue(key, value) {
    if (key === "prompt_mode") {
      if (value === "strict") return translate("history.promptMode.strict");
      if (value === "original") return translate("history.promptMode.original");
      if (value === "off") return translate("history.promptMode.off");
    }
    if (key === "quality") {
      if (value === "high") return translate("history.quality.high");
      if (value === "medium") return translate("history.quality.medium");
      if (value === "low") return translate("history.quality.low");
      if (value === "auto") return translate("history.quality.auto");
    }
    if (key === "orientation") {
      if (value === "portrait") return translate("output.portrait");
      if (value === "landscape") return translate("output.landscape");
      if (value === "square") return translate("output.square");
    }
    if (key === "ratio" && value === HISTORY_RATIO_OTHER_VALUE) return translate("history.ratioOther");
    return value;
  }
  function historyOrientationIconHtml(value) {
    if (value === "portrait") {
      return `<svg class="history-filter-icon history-filter-icon-portrait" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
        <rect x="6.5" y="3" width="7" height="14" rx="2"></rect>
      </svg>`;
    }
    if (value === "landscape") {
      return `<svg class="history-filter-icon history-filter-icon-landscape" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
        <rect x="3" y="6.5" width="14" height="7" rx="2"></rect>
      </svg>`;
    }
    if (value === "square") {
      return `<svg class="history-filter-icon history-filter-icon-square" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
        <rect x="5" y="5" width="10" height="10" rx="2"></rect>
      </svg>`;
    }
    return `<svg class="history-filter-icon history-filter-icon-all" viewBox="0 0 20 20" aria-hidden="true" focusable="false">
      <rect x="3.5" y="4" width="5" height="8" rx="1.5"></rect>
      <rect x="10.5" y="5" width="6" height="4.5" rx="1.4"></rect>
      <rect x="10.5" y="11.5" width="5" height="5" rx="1.4"></rect>
    </svg>`;
  }
  function historyFilterButtonLabelHtml(key, label, value = "") {
    if (key !== "orientation") return escapeHtml2(label);
    return `${historyOrientationIconHtml(value)}<span class="history-filter-label">${escapeHtml2(label)}</span>`;
  }
  function syncStateFromUrl() {
    const params = new URLSearchParams(window.location.search);
    historyState.q = params.get("q") || "";
    historyState.sort = params.get("sort") === "oldest" ? "oldest" : "newest";
    historyState.view = params.get("view") === "list" ? "list" : "grid";
    for (const key of HISTORY_FILTER_KEYS) {
      historyState[key] = params.get(key) || "";
    }
    historyState.selectedTaskId = params.get("task") || "";
    if (els.search) els.search.value = historyState.q;
    syncHistorySortMode();
    syncHistoryViewMode();
  }
  function updateHistoryUrl() {
    const params = new URLSearchParams();
    if (historyState.q) params.set("q", historyState.q);
    if (historyState.sort !== "newest") params.set("sort", historyState.sort);
    if (historyState.view !== "grid") params.set("view", historyState.view);
    for (const key of HISTORY_FILTER_KEYS) {
      if (historyState[key]) params.set(key, historyState[key]);
    }
    if (historyState.selectedTaskId) params.set("task", historyState.selectedTaskId);
    const query = params.toString();
    const nextUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname;
    window.history.replaceState(null, "", nextUrl);
  }
  async function loadSummary() {
    try {
      const response = await fetch("/api/task-history/summary");
      const summary = await response.json();
      if (!response.ok) throw new Error(summary.detail || translate("history.summaryFailed"));
      setText(els.total, formatTranslation("history.total", { total: summary.total, archived: summary.archived_total }));
      renderFacetButtons(els.monthList, "month", summary.months.map((item) => ({ value: item.month, count: item.count })), translate("history.allMonths"));
      renderFacetButtons(els.promptModeList, "prompt_mode", summary.prompt_modes || [], translate("history.allPromptModes"));
      renderFacetButtons(els.qualityList, "quality", summary.qualities || [], translate("history.allQualities"));
      renderFacetButtons(els.ratioList, "ratio", summary.ratios, translate("history.allRatios"));
      renderFacetButtons(els.orientationList, "orientation", summary.orientations || [], translate("history.allOrientations"));
      renderFacetButtons(els.backendList, "backend", summary.backends || [], translate("history.allBackends"));
      renderFacetButtons(els.providerList, "provider", summary.providers || [], translate("history.allProviders"));
      syncArchiveButtons();
    } catch (error) {
      setText(els.total, errorMessage(error, translate("history.summaryFailed")));
    }
  }
  function renderFacetButtons(root, key, items, allLabel) {
    if (!root) return;
    const current = String(historyState[key] || "");
    const attr = historyFilterAttribute(key);
    root.innerHTML = [
      `<button class="history-filter-button ${current ? "" : "active"}" type="button" data-history-filter-key="${key}" data-history-${attr}="">${historyFilterButtonLabelHtml(key, allLabel)}</button>`,
      ...items.map((item) => {
        const active = current === item.value ? " active" : "";
        return `<button class="history-filter-button${active}" type="button" data-history-filter-key="${key}" data-history-${attr}="${escapeHtml2(item.value)}">${historyFilterButtonLabelHtml(key, facetDisplayValue(key, item.value), item.value)}<span class="history-filter-count">${item.count}</span></button>`;
      })
    ].join("");
  }
  function syncArchiveButtons() {
    document.querySelectorAll("[data-history-archived]").forEach((button) => {
      button.classList.toggle("active", button.getAttribute("data-history-archived") === historyState.archived);
    });
  }
  function syncHistorySortMode() {
    const sort = historyState.sort === "oldest" ? "oldest" : "newest";
    historyState.sort = sort;
    els.sortToggle?.querySelectorAll("[data-history-sort]").forEach((button) => {
      const active = button.dataset.historySort === sort;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
  }
  function applyHistorySort(sort) {
    const nextSort = sort === "oldest" ? "oldest" : "newest";
    if (historyState.sort === nextSort) return;
    historyState.sort = nextSort;
    historyState.selectedTaskId = "";
    syncHistorySortMode();
    updateHistoryUrl();
    void loadTasks({ reset: true });
  }
  function queryParams(cursor, direction = "next") {
    const params = new URLSearchParams();
    params.set("limit", String(HISTORY_PAGE_LIMIT));
    params.set("sort", historyState.sort);
    if (cursor) params.set("cursor", cursor);
    if (direction !== "next") params.set("direction", direction);
    if (historyState.q) params.set("q", historyState.q);
    for (const key of HISTORY_FILTER_KEYS) {
      if (historyState[key]) params.set(key, historyState[key]);
    }
    return params.toString();
  }
  function syncHistoryViewMode() {
    const view = historyState.view === "list" ? "list" : "grid";
    historyState.view = view;
    els.taskList?.classList.toggle("history-view-grid", view === "grid");
    els.taskList?.classList.toggle("history-view-list", view === "list");
    els.viewToggle?.querySelectorAll("[data-history-view]").forEach((button) => {
      const active = button.dataset.historyView === view;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
    });
    if (view === "grid") scheduleHistoryGridLayout();
  }
  function setHistoryViewMode(view) {
    historyState.view = view === "list" ? "list" : "grid";
    syncHistoryViewMode();
    updateHistoryUrl();
  }
  function historyGridLayoutSettings() {
    if (window.matchMedia("(max-width: 760px)").matches) {
      return { targetHeight: 176, minWidth: 132, maxWidth: 320 };
    }
    return { targetHeight: 220, minWidth: 150, maxWidth: 430 };
  }
  function historyTaskCardElement(taskId) {
    if (!taskId || !els.taskList) return null;
    return historyTaskCards(els.taskList).find((card) => card.dataset.historyTaskCardId === taskId) || null;
  }
  function isHistoryTaskCardVisible(taskId) {
    const list = els.taskList;
    const card = historyTaskCardElement(taskId);
    if (!list || !card) return false;
    const listRect = list.getBoundingClientRect();
    const cardRect = card.getBoundingClientRect();
    return cardRect.bottom > listRect.top && cardRect.top < listRect.bottom && cardRect.right > listRect.left && cardRect.left < listRect.right;
  }
  function activeHistoryTaskVisible() {
    const taskId = historyState.selectedTaskId;
    return taskId && isHistoryTaskCardVisible(taskId) ? taskId : "";
  }
  function ensureHistoryTaskCardVisible(taskId) {
    historyTaskCardElement(taskId)?.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
  function scheduleHistoryGridLayout(options = {}) {
    if (options.keepTaskId) pendingHistoryGridKeepTaskId = options.keepTaskId;
    if (historyGridLayoutFrame) window.cancelAnimationFrame(historyGridLayoutFrame);
    historyGridLayoutFrame = window.requestAnimationFrame(() => {
      historyGridLayoutFrame = 0;
      const keepTaskId = pendingHistoryGridKeepTaskId;
      pendingHistoryGridKeepTaskId = "";
      layoutJustifiedHistoryGrid();
      if (keepTaskId) ensureHistoryTaskCardVisible(keepTaskId);
    });
  }
  function parseCssPixels(value) {
    const parsed = Number.parseFloat(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  function clampNumber(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }
  function isHistoryResizableLayout() {
    return Boolean(els.page) && !window.matchMedia("(max-width: 1100px)").matches;
  }
  function readHistoryLayoutPreference() {
    try {
      const raw = localStorage.getItem(HISTORY_LAYOUT_STORAGE_KEY);
      if (!raw) return { ...HISTORY_LAYOUT_DEFAULTS };
      const parsed = JSON.parse(raw);
      return {
        left: typeof parsed.left === "number" && Number.isFinite(parsed.left) ? parsed.left : HISTORY_LAYOUT_DEFAULTS.left,
        right: typeof parsed.right === "number" && Number.isFinite(parsed.right) ? parsed.right : HISTORY_LAYOUT_DEFAULTS.right
      };
    } catch {
      return { ...HISTORY_LAYOUT_DEFAULTS };
    }
  }
  function historyLayoutMaxCombinedWidth() {
    const pageWidth = els.page?.getBoundingClientRect().width || window.innerWidth || 0;
    return Math.max(
      HISTORY_LAYOUT_LIMITS.leftMin + HISTORY_LAYOUT_LIMITS.rightMin,
      pageWidth - HISTORY_LAYOUT_LIMITS.middleMin - HISTORY_LAYOUT_LIMITS.resizerWidth * 2
    );
  }
  function constrainHistoryLayoutWidths(left, right, prioritySide = "") {
    let nextLeft = clampNumber(Math.round(left), HISTORY_LAYOUT_LIMITS.leftMin, HISTORY_LAYOUT_LIMITS.leftMax);
    let nextRight = clampNumber(Math.round(right), HISTORY_LAYOUT_LIMITS.rightMin, HISTORY_LAYOUT_LIMITS.rightMax);
    let overflow = nextLeft + nextRight - historyLayoutMaxCombinedWidth();
    if (overflow > 0) {
      if (prioritySide === "left") {
        const rightReduction = Math.min(overflow, nextRight - HISTORY_LAYOUT_LIMITS.rightMin);
        nextRight -= rightReduction;
        overflow -= rightReduction;
        nextLeft -= Math.min(overflow, nextLeft - HISTORY_LAYOUT_LIMITS.leftMin);
      } else {
        const leftReduction = Math.min(overflow, nextLeft - HISTORY_LAYOUT_LIMITS.leftMin);
        nextLeft -= leftReduction;
        overflow -= leftReduction;
        nextRight -= Math.min(overflow, nextRight - HISTORY_LAYOUT_LIMITS.rightMin);
      }
    }
    return { left: Math.round(nextLeft), right: Math.round(nextRight) };
  }
  function getCurrentHistoryLayoutWidths() {
    const fromStyle = {
      left: parseCssPixels(els.page?.style.getPropertyValue("--history-sidebar-width") || ""),
      right: parseCssPixels(els.page?.style.getPropertyValue("--history-detail-width") || "")
    };
    if (fromStyle.left && fromStyle.right) return fromStyle;
    const sidebarWidth = els.sidebar?.getBoundingClientRect().width || HISTORY_LAYOUT_DEFAULTS.left;
    const detailWidth = els.detail?.getBoundingClientRect().width || HISTORY_LAYOUT_DEFAULTS.right;
    return constrainHistoryLayoutWidths(sidebarWidth, detailWidth);
  }
  function updateHistoryResizerAria(widths) {
    els.leftResizer?.setAttribute("aria-valuenow", String(widths.left));
    els.rightResizer?.setAttribute("aria-valuenow", String(widths.right));
  }
  function applyHistoryLayoutWidths(left, right, options = {}) {
    if (!els.page) return;
    const keepTaskId = options.preserveActiveTask ? activeHistoryTaskVisible() : "";
    const widths = constrainHistoryLayoutWidths(left, right, options.prioritySide || "");
    els.page.style.setProperty("--history-sidebar-width", `${widths.left}px`);
    els.page.style.setProperty("--history-detail-width", `${widths.right}px`);
    updateHistoryResizerAria(widths);
    scheduleHistoryGridLayout({ keepTaskId });
    if (options.persist) {
      try {
        localStorage.setItem(HISTORY_LAYOUT_STORAGE_KEY, JSON.stringify(widths));
      } catch {
      }
    }
  }
  function restoreHistoryLayoutPreference() {
    const stored = readHistoryLayoutPreference();
    const widths = constrainHistoryLayoutWidths(stored.left, stored.right);
    applyHistoryLayoutWidths(widths.left, widths.right);
  }
  function resetHistoryLayoutSide(side) {
    const widths = getCurrentHistoryLayoutWidths();
    const nextLeft = side === "left" ? HISTORY_LAYOUT_DEFAULTS.left : widths.left;
    const nextRight = side === "right" ? HISTORY_LAYOUT_DEFAULTS.right : widths.right;
    applyHistoryLayoutWidths(nextLeft, nextRight, { persist: true, preserveActiveTask: true, prioritySide: side });
  }
  function resizeHistoryLayoutByKeyboard(side, event) {
    const step = event.shiftKey ? 48 : 16;
    const widths = getCurrentHistoryLayoutWidths();
    let nextLeft = widths.left;
    let nextRight = widths.right;
    if (event.key === "ArrowLeft") {
      if (side === "left") nextLeft -= step;
      else nextRight += step;
    } else if (event.key === "ArrowRight") {
      if (side === "left") nextLeft += step;
      else nextRight -= step;
    } else if (event.key === "Home") {
      if (side === "left") nextLeft = HISTORY_LAYOUT_LIMITS.leftMin;
      else nextRight = HISTORY_LAYOUT_LIMITS.rightMax;
    } else if (event.key === "End") {
      if (side === "left") nextLeft = HISTORY_LAYOUT_LIMITS.leftMax;
      else nextRight = HISTORY_LAYOUT_LIMITS.rightMin;
    } else if (event.key === "Enter" || event.key === " ") {
      resetHistoryLayoutSide(side);
      return true;
    } else {
      return false;
    }
    applyHistoryLayoutWidths(nextLeft, nextRight, { persist: true, preserveActiveTask: true, prioritySide: side });
    return true;
  }
  function startHistoryResize(side, event, element) {
    if (event.button !== 0 || !isHistoryResizableLayout()) return;
    const widths = getCurrentHistoryLayoutWidths();
    activeHistoryResizer = {
      side,
      pointerId: event.pointerId,
      startX: event.clientX,
      startLeft: widths.left,
      startRight: widths.right,
      element
    };
    closeHistoryContextMenu();
    event.preventDefault();
    element.setPointerCapture?.(event.pointerId);
    els.page?.classList.add("history-resizing");
  }
  function updateHistoryResize(event) {
    if (!activeHistoryResizer || event.pointerId !== activeHistoryResizer.pointerId) return;
    const delta = event.clientX - activeHistoryResizer.startX;
    const nextLeft = activeHistoryResizer.side === "left" ? activeHistoryResizer.startLeft + delta : activeHistoryResizer.startLeft;
    const nextRight = activeHistoryResizer.side === "right" ? activeHistoryResizer.startRight - delta : activeHistoryResizer.startRight;
    applyHistoryLayoutWidths(nextLeft, nextRight, { preserveActiveTask: true, prioritySide: activeHistoryResizer.side });
  }
  function endHistoryResize(event) {
    if (!activeHistoryResizer) return;
    if (event && event.pointerId !== activeHistoryResizer.pointerId) return;
    if (activeHistoryResizer.element.hasPointerCapture?.(activeHistoryResizer.pointerId)) {
      activeHistoryResizer.element.releasePointerCapture?.(activeHistoryResizer.pointerId);
    }
    const widths = getCurrentHistoryLayoutWidths();
    applyHistoryLayoutWidths(widths.left, widths.right, { persist: true, preserveActiveTask: true, prioritySide: activeHistoryResizer.side });
    activeHistoryResizer = null;
    els.page?.classList.remove("history-resizing");
  }
  function bindHistoryResizerEvents() {
    for (const resizer of [els.leftResizer, els.rightResizer]) {
      const side = resizer?.dataset.historyResizer;
      if (!resizer || side !== "left" && side !== "right") continue;
      resizer.addEventListener("pointerdown", (event) => startHistoryResize(side, event, resizer));
      resizer.addEventListener("dblclick", () => resetHistoryLayoutSide(side));
      resizer.addEventListener("keydown", (event) => {
        if (!isHistoryResizableLayout()) return;
        if (!resizeHistoryLayoutByKeyboard(side, event)) return;
        event.preventDefault();
        event.stopPropagation();
      });
    }
    window.addEventListener("pointermove", updateHistoryResize);
    window.addEventListener("pointerup", endHistoryResize);
    window.addEventListener("pointercancel", endHistoryResize);
  }
  function historyTaskCardRatio(card) {
    const ratio = Number.parseFloat(card.style.getPropertyValue("--history-task-card-ratio"));
    return Number.isFinite(ratio) && ratio > 0 ? clampNumber(ratio, 0.42, 3.2) : 1;
  }
  function applyHistoryGridRowLayout(row, options) {
    if (!row.length) return;
    const { fillRow, availableWidth, gap, settings } = options;
    const gapWidth = gap * Math.max(0, row.length - 1);
    const availableContentWidth = Math.max(1, availableWidth - gapWidth);
    const ratioTotal = row.reduce((sum, item) => sum + item.ratio, 0) || 1;
    const rowHeight = fillRow ? availableContentWidth / ratioTotal : settings.targetHeight;
    let widths = row.map((item) => {
      const naturalWidth = item.ratio * rowHeight;
      return fillRow ? Math.max(1, Math.floor(naturalWidth)) : Math.round(clampNumber(naturalWidth, settings.minWidth, Math.min(settings.maxWidth, availableWidth)));
    });
    if (fillRow) {
      let delta = Math.round(availableContentWidth - widths.reduce((sum, width) => sum + width, 0));
      const direction = delta >= 0 ? 1 : -1;
      delta = Math.abs(delta);
      for (let index = 0; index < widths.length && delta > 0; index = (index + 1) % widths.length) {
        widths[index] = (widths[index] || 1) + direction;
        delta -= 1;
      }
    }
    row.forEach((item, index) => {
      item.card.style.setProperty("--history-task-row-height", `${Math.max(1, Math.round(rowHeight))}px`);
      item.card.style.setProperty("--history-task-card-width", `${Math.max(1, widths[index] || 1)}px`);
    });
  }
  function layoutJustifiedHistoryGrid() {
    const root = els.taskList;
    if (!root || historyState.view !== "grid" || !root.classList.contains("history-view-grid")) return;
    const cards = historyTaskCards(root);
    if (!cards.length) return;
    const rootStyle = window.getComputedStyle(root);
    const availableWidth = root.clientWidth - parseCssPixels(rootStyle.paddingLeft) - parseCssPixels(rootStyle.paddingRight);
    if (availableWidth < 80) return;
    const gap = parseCssPixels(rootStyle.columnGap || rootStyle.gap) || HISTORY_GRID_DEFAULT_GAP;
    const settings = historyGridLayoutSettings();
    let row = [];
    let rowRatioTotal = 0;
    for (const card of cards) {
      const ratio = historyTaskCardRatio(card);
      row.push({ card, ratio });
      rowRatioTotal += ratio;
      const projectedWidth = rowRatioTotal * settings.targetHeight + gap * Math.max(0, row.length - 1);
      if (row.length > 1 && projectedWidth >= availableWidth) {
        applyHistoryGridRowLayout(row, { fillRow: true, availableWidth, gap, settings });
        row = [];
        rowRatioTotal = 0;
      }
    }
    applyHistoryGridRowLayout(row, { fillRow: false, availableWidth, gap, settings });
  }
  function setLoadMoreState(label, options = {}) {
    if (!els.sentinel) return;
    els.sentinel.textContent = label;
    els.sentinel.hidden = Boolean(options.hidden);
    els.sentinel.toggleAttribute("aria-busy", Boolean(options.busy));
  }
  function maybeLoadMoreFromScroll() {
    if (!els.taskList || historyState.loading) return;
    if (els.taskList.scrollTop <= 320 && !historyState.newerExhausted) {
      void loadTasks({ direction: "previous" });
      return;
    }
    const remaining = els.taskList.scrollHeight - els.taskList.scrollTop - els.taskList.clientHeight;
    if (remaining <= 320 && !historyState.exhausted) void loadTasks({ direction: "next" });
  }
  async function loadTasks({ reset = false, direction = "next" } = {}) {
    if (historyState.loading) return;
    if (!reset && direction === "next" && historyState.exhausted) return;
    if (!reset && direction === "previous" && historyState.newerExhausted) return;
    const cursor = taskWindowCursor(reset, direction);
    if (!reset && !cursor) {
      if (direction === "previous") historyState.newerExhausted = true;
      if (direction === "next") historyState.exhausted = true;
      return;
    }
    historyState.loading = true;
    const requestId = ++historyState.requestId;
    if (reset) {
      historyState.nextCursor = null;
      historyState.newerExhausted = true;
      historyState.exhausted = false;
      historyState.loadedTaskIds.clear();
      historyState.loadedTaskSummaries.clear();
      historyState.selectedTaskIds.clear();
      historyState.selectionAnchorTaskId = "";
      historyState.deleteConfirming = false;
      historyState.deleteConfirmTaskId = "";
      historyState.contextMenuDeleteConfirmKey = "";
      if (els.taskList) els.taskList.innerHTML = "";
      renderBulkToolbar();
    }
    setLoadMoreState(translate("history.loadingMore"), { busy: true });
    try {
      const response = await fetch(`/api/task-history/tasks?${queryParams(cursor, direction)}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || translate("history.tasksFailed"));
      if (requestId !== historyState.requestId) return;
      const tasks = data.tasks || [];
      renderTasks(tasks, { position: reset ? "replace" : direction === "previous" ? "prepend" : "append" });
      if (direction === "previous") {
        historyState.newerExhausted = !data.previous_cursor || !tasks.length;
      } else {
        historyState.nextCursor = data.next_cursor || null;
        historyState.exhausted = !historyState.nextCursor;
        if (reset) historyState.newerExhausted = true;
      }
      setLoadMoreState(
        historyState.exhausted ? translate("history.noMore") : "",
        { hidden: !historyState.exhausted, busy: false }
      );
      window.requestAnimationFrame(maybeLoadMoreFromScroll);
    } catch (error) {
      if (requestId === historyState.requestId) {
        const message = errorMessage(error, translate("history.tasksFailed"));
        if (els.taskList && historyTaskCards(els.taskList).length) {
          setText(els.resultSummary, message);
        } else {
          renderTaskListMessage("history-error", message);
        }
      }
      if (direction === "previous") {
        historyState.newerExhausted = false;
      } else {
        historyState.exhausted = false;
      }
      setLoadMoreState(translate("history.loadFailed"));
    } finally {
      if (requestId === historyState.requestId) historyState.loading = false;
    }
  }
  function taskWindowCursor(reset, direction) {
    if (reset || !els.taskList) return null;
    if (direction === "previous") return historyWindowEdgeCursor(els.taskList, "top");
    return historyState.nextCursor || historyWindowEdgeCursor(els.taskList, "bottom");
  }
  function renderTasks(tasks, { position }) {
    if (!els.taskList) return;
    syncHistoryViewMode();
    const anchor = position === "replace" ? null : captureHistoryScrollAnchor(els.taskList);
    if (position === "replace") els.taskList.innerHTML = "";
    const uniqueTasks = tasks.filter((task) => {
      if (historyState.loadedTaskIds.has(task.task_id)) return false;
      historyState.loadedTaskIds.add(task.task_id);
      historyState.loadedTaskSummaries.set(task.task_id, task);
      return true;
    });
    const html = uniqueTasks.map(taskCardHtml).join("");
    if (html) {
      els.taskList.querySelector(".history-empty, .history-error")?.remove();
      if (position === "prepend") {
        els.taskList.insertAdjacentHTML("afterbegin", html);
      } else {
        els.taskList.insertAdjacentHTML("beforeend", html);
      }
    }
    trimMountedTaskCards(position === "prepend" ? "bottom" : "top");
    layoutJustifiedHistoryGrid();
    restoreHistoryScrollAnchor(els.taskList, anchor);
    if (!els.taskList.querySelector(".history-task-card")) {
      renderTaskListMessage("history-empty", translate("history.noMatches"));
    }
    setText(els.resultSummary, formatTranslation("history.loadedCount", { count: historyState.loadedTaskIds.size }));
    updateTaskSelectionVisuals();
  }
  function captureHistoryScrollAnchorSkipping(taskIds) {
    if (!els.taskList) return null;
    const rootTop = els.taskList.getBoundingClientRect().top;
    for (const card of historyTaskCards(els.taskList)) {
      const taskId = String(card.dataset.historyTaskCardId || "");
      if (!taskId || taskIds.has(taskId)) continue;
      const rect = card.getBoundingClientRect();
      if (rect.bottom < rootTop) continue;
      return { taskId, offset: rect.top - rootTop };
    }
    return null;
  }
  function refreshHistoryWindowAfterMutation(mutate, options = {}) {
    if (!els.taskList) {
      mutate();
      return;
    }
    const removedTaskIds = new Set(options.removedTaskIds || []);
    const currentAnchor = captureHistoryScrollAnchor(els.taskList);
    const anchor = currentAnchor && !removedTaskIds.has(currentAnchor.taskId) ? currentAnchor : captureHistoryScrollAnchorSkipping(removedTaskIds);
    mutate();
    if (!els.taskList.querySelector(".history-task-card")) {
      renderTaskListMessage("history-empty", translate("history.noMatches"));
    }
    layoutJustifiedHistoryGrid();
    restoreHistoryScrollAnchor(els.taskList, anchor);
    updateTaskSelectionVisuals();
    window.requestAnimationFrame(maybeLoadMoreFromScroll);
  }
  function removeHistoryTaskIdsFromWindow(taskIds) {
    const ids = taskIds.filter(Boolean);
    if (!ids.length) return;
    const idSet = new Set(ids);
    refreshHistoryWindowAfterMutation(() => {
      ids.forEach((taskId) => {
        historyState.loadedTaskIds.delete(taskId);
        historyState.loadedTaskSummaries.delete(taskId);
        historyState.selectedTaskIds.delete(taskId);
        if (historyState.selectionAnchorTaskId === taskId) historyState.selectionAnchorTaskId = "";
        historyTaskCardElement(taskId)?.remove();
      });
      if (idSet.has(historyState.selectedTaskId)) {
        historyState.selectedTaskId = "";
        historyState.detailTask = null;
        els.page?.classList.remove("history-detail-open");
        updateHistoryUrl();
        renderDetailShell(translate("history.detailEmpty"));
      }
    }, { removedTaskIds: ids });
  }
  function historyTaskMatchesCurrentArchiveFilter(task) {
    if (historyState.archived === "true") return historyTaskArchived(task);
    if (historyState.archived === "false") return !historyTaskArchived(task);
    return true;
  }
  function historyTaskSummaryFromDetail(taskId, task) {
    const previous = historyState.loadedTaskSummaries.get(taskId);
    const source = task || previous;
    if (!source) return null;
    const generatedCount = historyTaskGeneratedCount(source);
    const totalCount = positiveInt2(source.total_count) ?? previous?.total_count ?? generatedCount;
    return {
      ...previous || {},
      ...source || {},
      task_id: taskId || String(source.task_id || previous?.task_id || ""),
      created_at: String(source.created_at || previous?.created_at || ""),
      updated_at: String(source.updated_at || previous?.updated_at || ""),
      completed_at: String(source.completed_at || previous?.completed_at || ""),
      status: String(source.status || previous?.status || ""),
      mode: String(source.mode || previous?.mode || ""),
      size: String(source.size || source.output_size || source.params?.size || previous?.size || ""),
      quality: String(source.quality || source.params?.quality || previous?.quality || ""),
      prompt_mode: String(source.prompt_mode || source.params?.prompt_fidelity || previous?.prompt_mode || ""),
      ratio: String(source.ratio || source.params?.ratio || previous?.ratio || ""),
      orientation: String(source.orientation || source.params?.orientation || previous?.orientation || ""),
      backend: String(source.backend || previous?.backend || ""),
      provider: String(source.provider || source.api_provider_name || previous?.provider || ""),
      archived: historyTaskArchived(source),
      generated_count: generatedCount || previous?.generated_count || 0,
      failed_count: positiveInt2(source.failed_count) ?? previous?.failed_count ?? 0,
      total_count: totalCount || 0,
      thumbnail_url: String(source.thumbnail_url || previous?.thumbnail_url || ""),
      prompt_preview: String(source.prompt_preview || source.prompt || previous?.prompt_preview || "")
    };
  }
  function upsertHistoryTaskSummaryCard(taskId, task) {
    const summary = historyTaskSummaryFromDetail(taskId, task);
    if (!summary?.task_id) return;
    if (!historyTaskMatchesCurrentArchiveFilter(summary)) {
      removeHistoryTaskIdsFromWindow([summary.task_id]);
      return;
    }
    refreshHistoryWindowAfterMutation(() => {
      const card = historyTaskCardElement(summary.task_id);
      if (!card) return;
      historyState.loadedTaskIds.add(summary.task_id);
      historyState.loadedTaskSummaries.set(summary.task_id, summary);
      const template = document.createElement("template");
      template.innerHTML = taskCardHtml(summary).trim();
      const nextCard = template.content.firstElementChild;
      if (nextCard) card.replaceWith(nextCard);
    });
  }
  function renderTaskListMessage(className, message) {
    if (!els.taskList) return;
    els.taskList.innerHTML = `<div class="${className}">${escapeHtml2(message)}</div>`;
  }
  function trimMountedTaskCards(edge) {
    if (!els.taskList) return;
    const cards = historyTaskCards(els.taskList);
    const overflow = cards.length - MAX_MOUNTED_TASK_CARDS;
    if (overflow <= 0) return;
    const removedCards = edge === "bottom" ? cards.slice(cards.length - overflow) : cards.slice(0, overflow);
    for (const card of removedCards) {
      const taskId = card.dataset.historyTaskCardId || "";
      historyState.loadedTaskIds.delete(taskId);
      historyState.loadedTaskSummaries.delete(taskId);
      historyState.selectedTaskIds.delete(taskId);
      if (historyState.selectionAnchorTaskId === taskId) historyState.selectionAnchorTaskId = "";
      card.remove();
    }
    if (edge === "top") {
      historyState.newerExhausted = false;
    } else {
      historyState.exhausted = false;
      historyState.nextCursor = historyWindowEdgeCursor(els.taskList, "bottom") || historyState.nextCursor;
    }
    els.taskList.querySelector(".history-window-notice")?.remove();
  }
  function taskCardHtml(task) {
    const taskId = escapeHtml2(task.task_id);
    const thumbnailUrl = historyThumbnailUrl(task);
    const ratioStyle = historyThumbnailRatioStyle(task);
    const thumb = thumbnailUrl ? `<img src="${escapeHtml2(thumbnailUrl)}" alt="" loading="lazy" decoding="async" draggable="false">` : "";
    const counts = `${task.generated_count || 0}/${task.total_count || 0}`;
    const selected = historyState.selectedTaskIds.has(task.task_id);
    const active = historyState.selectedTaskId === task.task_id;
    const source = task.backend || task.provider || "";
    const promptMode = facetDisplayValue("prompt_mode", task.prompt_mode || "");
    const quality = facetDisplayValue("quality", task.quality || "");
    const metaItems = [
      { kind: "date", value: formatDate(task.created_at) },
      { kind: "status", value: task.status },
      { kind: "size", value: formatHistorySizeLabel(task.size || task.ratio || task.orientation || "") },
      { kind: "prompt-mode", value: promptMode },
      { kind: "quality", value: quality },
      { kind: "source", value: source },
      { kind: "count", value: counts }
    ].filter((item) => item.value);
    return `
    <article
      class="history-task-card${active ? " active" : ""}${selected ? " selected" : ""}"
      data-history-task-card-id="${taskId}"
      data-history-created-at="${escapeHtml2(task.created_at)}"
      role="option"
      aria-selected="${active ? "true" : "false"}"
      ${ratioStyle}
    >
      <label class="history-task-select" aria-label="${escapeHtml2(translate("history.selectTask"))}">
        <input type="checkbox" data-history-task-select="${taskId}" ${selected ? "checked" : ""}>
      </label>
      <span class="history-task-active-badge" aria-hidden="${active ? "false" : "true"}">${escapeHtml2(translate("history.viewing"))}</span>
      <button class="history-task-open" type="button" data-history-task-id="${taskId}">
        <span class="history-task-thumb">${thumb}</span>
        <span class="history-task-copy">
          <span class="history-task-title">${escapeHtml2(task.prompt_preview || task.mode || task.task_id)}</span>
          <span class="history-task-meta">
            ${metaItems.map((item) => `<span data-history-meta-kind="${escapeHtml2(item.kind)}">${escapeHtml2(item.value)}</span>`).join("")}
          </span>
        </span>
      </button>
    </article>
  `;
  }
  function historyThumbnailRatioStyle(task) {
    const fromSize = parseAspectRatioParts(task.size, "x");
    const fromRatio = fromSize || parseAspectRatioParts(task.ratio, ":");
    if (!fromRatio) return "";
    const [width, height] = fromRatio;
    const ratio = Math.min(3.2, Math.max(0.42, width / height));
    return `style="--history-task-thumb-ratio: ${width} / ${height}; --history-task-card-ratio: ${ratio.toFixed(4)}"`;
  }
  function parseAspectRatioParts(value, separator) {
    const text = String(value || "").trim().toLowerCase();
    const pattern = separator === "x" ? /^(\d+)\s*x\s*(\d+)$/ : /^(\d+)\s*:\s*(\d+)$/;
    const match = text.match(pattern);
    if (!match) return null;
    const width = Number.parseInt(match[1] || "", 10);
    const height = Number.parseInt(match[2] || "", 10);
    if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) return null;
    return [width, height];
  }
  function formatHistorySizeLabel(value) {
    return String(value || "").trim().replace(/^(\d+)\s*x\s*(\d+)$/i, "$1 x $2");
  }
  function historyThumbnailUrl(task) {
    const url = String(task.thumbnail_url || "");
    if (!url) return "";
    const staticThumbMatch = url.match(/(?:^|\/)(\d{14}-[a-f0-9]+)-image-(\d+)-thumb\.[a-z0-9]+(?:[?#].*)?$/i);
    if (url.includes("/outputs/thumbnails/") && staticThumbMatch && staticThumbMatch[1] === task.task_id) {
      const outputIndex = staticThumbMatch[2] || "1";
      return versionHistoryThumbnailUrl(`/api/tasks/${encodeURIComponent(task.task_id)}/outputs/${encodeURIComponent(outputIndex)}/thumbnail`);
    }
    return versionHistoryThumbnailUrl(url);
  }
  function versionHistoryThumbnailUrl(url) {
    if (!url.startsWith("/api/tasks/") || !url.includes("/thumbnail")) return url;
    const separator = url.includes("?") ? "&" : "?";
    return `${url}${separator}v=${HISTORY_THUMBNAIL_CACHE_VERSION}`;
  }
  function updateTaskSelectionVisuals(taskId = historyState.selectedTaskId) {
    els.taskList?.querySelectorAll(".history-task-card").forEach((card) => {
      const cardTaskId = card.dataset.historyTaskCardId || "";
      const active = Boolean(taskId && cardTaskId === taskId);
      const selected = historyState.selectedTaskIds.has(cardTaskId);
      card.classList.toggle("active", active);
      card.classList.toggle("selected", selected);
      card.setAttribute("aria-selected", active ? "true" : "false");
      const activeBadge = card.querySelector(".history-task-active-badge");
      activeBadge?.setAttribute("aria-hidden", active ? "false" : "true");
      const input = card.querySelector("[data-history-task-select]");
      if (input) input.checked = selected;
    });
  }
  function visibleHistoryTaskIds() {
    return Array.from(els.taskList?.querySelectorAll(".history-task-card[data-history-task-card-id]") || []).map((card) => String(card.dataset.historyTaskCardId || "")).filter(Boolean);
  }
  function applyHistoryTaskSelection(taskIds, anchorTaskId = "") {
    historyState.selectedTaskIds = new Set(taskIds.filter(Boolean));
    if (anchorTaskId) historyState.selectionAnchorTaskId = anchorTaskId;
    historyState.deleteConfirming = false;
    historyState.contextMenuDeleteConfirmKey = "";
    updateTaskSelectionVisuals();
    renderBulkToolbar();
  }
  function clearHistoryTaskSelection({ updateVisuals = true } = {}) {
    if (!historyState.selectedTaskIds.size && !historyState.selectionAnchorTaskId && !historyState.deleteConfirming) return;
    historyState.selectedTaskIds.clear();
    historyState.selectionAnchorTaskId = "";
    historyState.deleteConfirming = false;
    historyState.contextMenuDeleteConfirmKey = "";
    if (updateVisuals) updateTaskSelectionVisuals();
    renderBulkToolbar();
  }
  function toggleHistoryTaskSelection(taskId, anchor = true) {
    if (!taskId) return;
    const next = new Set(historyState.selectedTaskIds);
    if (next.has(taskId)) {
      next.delete(taskId);
    } else {
      next.add(taskId);
    }
    historyState.selectedTaskIds = next;
    if (anchor) historyState.selectionAnchorTaskId = taskId;
    historyState.deleteConfirming = false;
    historyState.contextMenuDeleteConfirmKey = "";
    updateTaskSelectionVisuals();
    renderBulkToolbar();
  }
  function selectHistoryTaskRange(anchorTaskId, taskId) {
    if (!taskId) return;
    const visibleIds = visibleHistoryTaskIds();
    const fallbackAnchor = historyState.selectionAnchorTaskId || historyState.selectedTaskId || taskId;
    const anchor = anchorTaskId || fallbackAnchor;
    const anchorIndex = visibleIds.indexOf(anchor);
    const targetIndex = visibleIds.indexOf(taskId);
    if (anchorIndex < 0 || targetIndex < 0) {
      applyHistoryTaskSelection([...historyState.selectedTaskIds, taskId], taskId);
      return;
    }
    const [start, end] = anchorIndex <= targetIndex ? [anchorIndex, targetIndex] : [targetIndex, anchorIndex];
    applyHistoryTaskSelection([...historyState.selectedTaskIds, ...visibleIds.slice(start, end + 1)], anchor);
  }
  function handleHistoryTaskShortcutSelection(taskId, event) {
    if (!taskId || !event.shiftKey && !event.metaKey && !event.ctrlKey) return false;
    event.preventDefault();
    event.stopPropagation();
    if (event.shiftKey) {
      selectHistoryTaskRange(historyState.selectionAnchorTaskId || historyState.selectedTaskId || taskId, taskId);
      return true;
    }
    toggleHistoryTaskSelection(taskId);
    return true;
  }
  async function loadTaskDetail(taskId) {
    if (!taskId) return;
    historyState.selectedTaskId = taskId;
    historyState.deleteConfirming = false;
    historyState.deleteConfirmTaskId = "";
    historyState.deleteUnselectedConfirmTaskId = "";
    updateHistoryUrl();
    updateTaskSelectionVisuals(taskId);
    els.page?.classList.add("history-detail-open");
    renderDetailShell(translate("history.loadingDetail"));
    try {
      renderTaskDetail(await fetchHistoryTaskDetail(taskId));
    } catch (error) {
      renderDetailShell(errorMessage(error, translate("history.detailFailed")), "history-error");
    }
  }
  async function fetchHistoryTaskDetail(taskId) {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || translate("history.detailFailed"));
    return data.task || {};
  }
  function renderDetailShell(message, className = "history-detail-empty") {
    if (!els.detail) return;
    els.detail.innerHTML = `
    <div class="history-detail-header">
      <div>
        <p class="history-detail-kicker">${escapeHtml2(translate("history.detail"))}</p>
        <h2 class="history-detail-title">${escapeHtml2(translate("history.detailTitle"))}</h2>
      </div>
      <button id="historyDetailClose" class="drawer-close-button history-detail-close" type="button" data-history-detail-close aria-label="${escapeHtml2(translate("history.closeDetail"))}">\xD7</button>
    </div>
    <div class="${className}">${escapeHtml2(message)}</div>
  `;
  }
  function historyTaskModeLabel(mode) {
    const value = String(mode || "");
    if (value === "generate") return translate("taskMode.generate");
    if (value === "edit") return translate("taskMode.edit");
    return value || translate("history.detail");
  }
  function renderTaskDetail(task) {
    if (!els.detail) return;
    historyState.detailTask = task;
    const taskId = String(task.task_id || historyState.selectedTaskId || "");
    const urls = taskOutputRecords(task);
    const selectedCount = taskSelectedOutputIndexes(task).size;
    const images = historyDetailImagesHtml(taskId, urls, selectedCount);
    const imageLayoutClass = historyDetailImagesLayoutClass(urls);
    const inputReferences = historyInputReferencesHtml(task);
    const zipHref = `/api/tasks/${encodeURIComponent(taskId)}/outputs.zip`;
    const canZip = urls.length > 1;
    const canDeleteUnselected = selectedCount > 0 && selectedCount < urls.length;
    const confirmingDeleteUnselected = historyState.deleteUnselectedConfirmTaskId === taskId;
    const archived = historyTaskArchived(task);
    const confirmingDeleteTask = historyState.deleteConfirmTaskId === taskId;
    const deleteBlocked = historyTaskDeleteBlocked(task);
    const title = detailTitle(task);
    els.detail.innerHTML = `
    <div class="history-detail-header">
      <div>
        <p class="history-detail-kicker">${escapeHtml2(historyTaskModeLabel(task.mode))}</p>
        <h2 class="history-detail-title" title="${escapeHtml2(task.prompt || title)}">${escapeHtml2(title)}</h2>
      </div>
      <button id="historyDetailClose" class="drawer-close-button history-detail-close" type="button" data-history-detail-close aria-label="${escapeHtml2(translate("history.closeDetail"))}">\xD7</button>
    </div>
    <div class="history-detail-meta">
      <span>${escapeHtml2(formatDate(task.created_at || ""))}</span>
      <span>${escapeHtml2(task.status || "")}</span>
      <span>${escapeHtml2(task.params?.size || task.output_size || "")}</span>
      <span>${escapeHtml2(facetDisplayValue("prompt_mode", task.params?.prompt_fidelity || ""))}</span>
      <span>${escapeHtml2(facetDisplayValue("quality", task.params?.quality || task.quality || ""))}</span>
      <span>${escapeHtml2(task.backend || task.api_provider_name || "")}</span>
    </div>
    <div class="history-detail-actions">
      <button class="ghost-button text-sm" type="button" data-history-reuse-task="${escapeHtml2(taskId)}">${escapeHtml2(translate("history.reuseTask"))}</button>
      <button class="ghost-button text-sm" type="button" data-history-archive-task="${escapeHtml2(taskId)}" data-history-archive-value="${archived ? "false" : "true"}">${escapeHtml2(archived ? translate("archive.restore") : translate("action.archive"))}</button>
      <button class="ghost-button text-sm danger-button" type="button" data-history-delete-task="${escapeHtml2(taskId)}" ${deleteBlocked ? "disabled" : ""}>${escapeHtml2(confirmingDeleteTask ? translate("history.confirmDelete") : translate("action.delete"))}</button>
      ${canZip ? `<a class="ghost-button text-sm" href="${escapeHtml2(zipHref)}" download>${escapeHtml2(translate("history.downloadAll"))}</a>` : ""}
      ${selectedCount > 1 ? `<a class="ghost-button text-sm" href="${escapeHtml2(zipHref)}?selected=1" download>${escapeHtml2(translate("history.downloadSelected"))}</a>` : ""}
      ${canDeleteUnselected ? `<button class="ghost-button text-sm danger-button" type="button" data-history-delete-unselected="${escapeHtml2(taskId)}">${escapeHtml2(confirmingDeleteUnselected ? translate("history.confirmDeleteUnselected") : translate("history.deleteUnselected"))}</button>` : ""}
      ${confirmingDeleteUnselected ? `<button class="ghost-button text-sm" type="button" data-history-delete-unselected-cancel>${escapeHtml2(translate("action.cancel"))}</button>` : ""}
    </div>
    <div class="history-detail-images${imageLayoutClass}">${images || `<div class="history-detail-empty">${escapeHtml2(translate("history.noPreview"))}</div>`}</div>
    ${inputReferences}
    ${promptCompareHtml(task)}
  `;
  }
  function detailTitle(task) {
    return truncateText(task.prompt_preview || task.prompt || task.mode || task.task_id || translate("history.untitled"), 120);
  }
  function historyTaskArchived(task) {
    return Boolean(task?.archived || task?.archived_at);
  }
  function historyTaskDeleteBlocked(task) {
    const status = String(task?.status || "");
    return Boolean(task?.local_pending || status === "running" || status === "submitting" || status === "queued");
  }
  function historyTaskGeneratedCount(task) {
    const generated = positiveInt2(task?.generated_count);
    if (generated !== null) return generated;
    const outputs = Array.isArray(task?.outputs) ? task.outputs.filter((output) => output && !output.deleted && output.status !== "failed") : [];
    if (outputs.length) return outputs.length;
    if (Array.isArray(task?.output_urls)) return task.output_urls.filter(Boolean).length;
    return task?.output_url ? 1 : 0;
  }
  function historyTaskSummary(taskId) {
    return historyState.loadedTaskSummaries.get(taskId) || null;
  }
  function historyTaskPromptForClipboard(task) {
    return String(task?.prompt || task?.prompt_preview || task?.prompt_for_model || "").trim();
  }
  function promptCompareHtml(task) {
    const originalPrompt = promptTextValue(task.prompt || "");
    const submittedPrompt = promptTextValue(task.prompt_for_model || "");
    const revisedPrompt = revisedPromptText(task);
    const hasDistinctOutputPrompts = hasDistinctOutputRevisedPrompts(task);
    const seen = /* @__PURE__ */ new Set();
    const panels = [];
    const addPanel = (kind, title, text) => {
      const value = promptTextValue(text);
      const key = normalizePromptForCompare(value);
      if (!key || seen.has(key)) return false;
      seen.add(key);
      panels.push(promptPanelHtml(kind, title, value));
      return true;
    };
    addPanel("original", translate("history.promptOriginal"), originalPrompt);
    const hasRevisedPanel = hasDistinctOutputPrompts ? false : addPanel("revised", translate("history.promptRevised"), revisedPrompt);
    if (!hasRevisedPanel) {
      addPanel("submitted", translate("history.promptSubmitted"), submittedPrompt);
    }
    if (hasDistinctOutputPrompts) {
      panels.push(`<p class="history-prompt-note">${escapeHtml2(translate("history.outputRevisedPromptNotice"))}</p>`);
    }
    return panels.length ? `<section class="history-prompt-compare" aria-label="${escapeHtml2(translate("history.promptCompare"))}">${panels.join("")}</section>` : "";
  }
  function promptTextValue(value) {
    return String(value || "").trim();
  }
  function normalizePromptForCompare(value) {
    return promptTextValue(value).replace(/\s+/g, " ").trim();
  }
  function uniquePromptTexts(values) {
    const seen = /* @__PURE__ */ new Set();
    const result = [];
    values.forEach((value) => {
      const text = promptTextValue(value);
      const key = normalizePromptForCompare(text);
      if (!key || seen.has(key)) return;
      seen.add(key);
      result.push(text);
    });
    return result;
  }
  function revisedPromptText(task) {
    const values = [];
    if (Array.isArray(task.revised_prompts)) values.push(...task.revised_prompts);
    if (task.revised_prompt) values.push(task.revised_prompt);
    if (Array.isArray(task.outputs)) {
      task.outputs.forEach((output) => {
        if (output?.revised_prompt) values.push(output.revised_prompt);
      });
    }
    return uniquePromptTexts(values).join("\n\n");
  }
  function outputRevisedPromptTexts(task) {
    return uniquePromptTexts(taskOutputRecords(task).map((record) => record.revisedPrompt));
  }
  function hasDistinctOutputRevisedPrompts(task) {
    return outputRevisedPromptTexts(task).length > 1;
  }
  function promptPanelHtml(kind, title, text) {
    return `
    <article class="history-prompt-panel">
      <div class="history-prompt-panel-header">
        <h3>${escapeHtml2(title)}</h3>
        <button
          class="ghost-button text-sm history-prompt-copy"
          type="button"
          data-history-copy-prompt-kind="${escapeHtml2(kind)}"
          aria-label="${escapeHtml2(formatTranslation("history.copyPromptPanel", { title }))}"
        >${escapeHtml2(translate("history.copyPromptShort"))}</button>
      </div>
      <div class="history-detail-prompt">${escapeHtml2(text || translate("history.promptEmpty"))}</div>
    </article>
  `;
  }
  function positiveInt2(value) {
    const parsed = Number.parseInt(String(value ?? ""), 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }
  function applyFilter(key, value) {
    historyState[key] = value;
    historyState.selectedTaskId = "";
    historyState.deleteConfirming = false;
    const attr = historyFilterAttribute(key);
    document.querySelectorAll(`[data-history-${attr}]`).forEach((node) => {
      node.classList.toggle("active", node.getAttribute(`data-history-${attr}`) === value);
    });
    updateHistoryUrl();
    void loadTasks({ reset: true });
  }
  function renderBulkToolbar() {
    if (!els.bulkToolbar || !els.bulkCount) return;
    const count = historyState.selectedTaskIds.size;
    els.page?.classList.toggle("history-bulk-selecting", count > 0);
    els.bulkToolbar.classList.toggle("hidden", count === 0);
    els.bulkToolbar.toggleAttribute("hidden", count === 0);
    els.bulkCount.textContent = count ? formatTranslation("history.selectedCount", { count }) : "";
    if (els.bulkDelete) {
      els.bulkDelete.textContent = historyState.deleteConfirming ? translate("history.confirmDelete") : translate("action.delete");
      els.bulkDelete.classList.toggle("danger-button", historyState.deleteConfirming);
    }
    els.bulkDeleteCancel?.classList.toggle("hidden", !historyState.deleteConfirming);
  }
  async function setTaskArchiveState(taskId, archived) {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/archive`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ archived })
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || (archived ? translate("taskActions.archiveFailed") : translate("archive.restoreFailed")));
    return data.task || null;
  }
  async function archiveSelectedTasks(archived) {
    await archiveHistoryTaskIds([...historyState.selectedTaskIds], archived);
  }
  async function archiveHistoryTaskIds(ids, archived) {
    if (!ids.length) return;
    setText(els.resultSummary, archived ? translate("archive.archiving") : translate("archive.restoring"));
    try {
      const tasks = await Promise.all(ids.map((taskId) => setTaskArchiveState(taskId, archived)));
      ids.forEach((taskId) => historyState.selectedTaskIds.delete(taskId));
      historyState.deleteConfirming = false;
      historyState.contextMenuDeleteConfirmKey = "";
      tasks.forEach((task, index) => {
        const taskId = ids[index] || String(task?.task_id || "");
        upsertHistoryTaskSummaryCard(taskId, task);
        if (taskId && String(historyState.detailTask?.task_id || "") === taskId && task) {
          historyState.detailTask = task;
          renderTaskDetail(task);
        }
      });
      await loadSummary();
      setText(els.resultSummary, archived ? formatTranslation("batch.archivedCount", { count: ids.length }) : formatTranslation("archive.restoredCount", { count: ids.length }));
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, archived ? translate("taskActions.archiveFailed") : translate("archive.restoreFailed")));
    } finally {
      renderBulkToolbar();
    }
  }
  async function archiveSingleTask(taskId, archived) {
    if (!taskId) return;
    setText(els.resultSummary, archived ? translate("archive.archiving") : translate("archive.restoring"));
    try {
      const task = await setTaskArchiveState(taskId, archived);
      historyState.deleteConfirmTaskId = "";
      historyState.contextMenuDeleteConfirmKey = "";
      if (String(historyState.detailTask?.task_id || "") === taskId && task) {
        historyState.detailTask = task;
        renderTaskDetail(task);
      }
      upsertHistoryTaskSummaryCard(taskId, task);
      await loadSummary();
      setText(els.resultSummary, archived ? translate("taskActions.archived") : translate("archive.restored"));
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, archived ? translate("taskActions.archiveFailed") : translate("archive.restoreFailed")));
    }
  }
  async function deleteSelectedTasks() {
    const ids = [...historyState.selectedTaskIds];
    if (!ids.length) return;
    if (!historyState.deleteConfirming) {
      historyState.deleteConfirming = true;
      renderBulkToolbar();
      return;
    }
    setText(els.resultSummary, translate("archive.deleting"));
    try {
      for (const taskId of ids) {
        const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(data.detail || translate("taskActions.deleteFailed"));
      }
      historyState.selectedTaskIds.clear();
      historyState.deleteConfirming = false;
      historyState.contextMenuDeleteConfirmKey = "";
      removeHistoryTaskIdsFromWindow(ids);
      await loadSummary();
      setText(els.resultSummary, formatTranslation("batch.deletedCount", { count: ids.length, skipped: "" }));
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, translate("taskActions.deleteFailed")));
    } finally {
      renderBulkToolbar();
    }
  }
  async function deleteSingleHistoryTask(taskId, { confirmInMenu = false } = {}) {
    if (!taskId) return false;
    const confirmKey = `task:${taskId}`;
    const confirmed = confirmInMenu ? historyState.contextMenuDeleteConfirmKey === confirmKey : historyState.deleteConfirmTaskId === taskId;
    if (!confirmed) {
      historyState.deleteConfirmTaskId = taskId;
      if (confirmInMenu) historyState.contextMenuDeleteConfirmKey = confirmKey;
      if (String(historyState.detailTask?.task_id || "") === taskId) renderTaskDetail(historyState.detailTask);
      if (confirmInMenu) rerenderHistoryContextMenu();
      return false;
    }
    setText(els.resultSummary, translate("archive.deleting"));
    try {
      const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}`, { method: "DELETE" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || translate("taskActions.deleteFailed"));
      historyState.selectedTaskIds.delete(taskId);
      historyState.loadedTaskIds.delete(taskId);
      historyState.loadedTaskSummaries.delete(taskId);
      historyState.deleteConfirmTaskId = "";
      historyState.contextMenuDeleteConfirmKey = "";
      removeHistoryTaskIdsFromWindow([taskId]);
      await loadSummary();
      setText(els.resultSummary, translate("taskActions.deleted"));
      return true;
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, translate("taskActions.deleteFailed")));
      return false;
    } finally {
      renderBulkToolbar();
    }
  }
  async function updateOutputSelection(button) {
    const taskId = button.dataset.historyOutputSelectedTaskId || historyState.selectedTaskId;
    const outputIndex = positiveInt2(button.dataset.historyOutputSelectedIndex);
    if (!taskId || outputIndex === null) return;
    const selected = button.getAttribute("aria-pressed") !== "true";
    try {
      const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/outputs/${encodeURIComponent(String(outputIndex))}/selected`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ selected })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || translate("taskActions.updated"));
      renderTaskDetail(data.task || {});
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, translate("taskContext.actionFailed")));
    }
  }
  async function deleteUnselectedOutputs(taskId) {
    if (!taskId) return;
    if (historyState.deleteUnselectedConfirmTaskId !== taskId) {
      historyState.deleteUnselectedConfirmTaskId = taskId;
      renderTaskDetail(historyState.detailTask || {});
      return;
    }
    try {
      const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/outputs/delete-unselected`, { method: "POST" });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || translate("taskActions.deleteFailed"));
      historyState.deleteUnselectedConfirmTaskId = "";
      renderTaskDetail(data.task || {});
      upsertHistoryTaskSummaryCard(taskId, data.task || {});
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, translate("taskActions.deleteFailed")));
    }
  }
  function promptTextForKind(kind) {
    const task = historyState.detailTask || {};
    if (kind === "submitted") return String(task.prompt_for_model || "").trim();
    if (kind === "revised") {
      return revisedPromptText(task);
    }
    return String(task.prompt || task.prompt_preview || "").trim();
  }
  function outputPromptTextForIndex(outputIndex) {
    const index = positiveInt2(outputIndex);
    if (index === null) return "";
    const record = taskOutputRecords(historyState.detailTask || {}).find((output) => output.index === index);
    return String(record?.revisedPrompt || "").trim();
  }
  async function writeClipboardText(text) {
    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(text);
        return;
      } catch {
      }
    }
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.append(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
  function setPromptCopyButtonFeedback(button, message) {
    const original = button.dataset.historyOriginalLabel || button.textContent || translate("history.copyPromptShort");
    button.dataset.historyOriginalLabel = original;
    button.textContent = message;
    button.classList.add("copied");
    window.setTimeout(() => {
      if (!button.isConnected) return;
      button.textContent = button.dataset.historyOriginalLabel || translate("history.copyPromptShort");
      button.classList.remove("copied");
    }, 1600);
  }
  async function copyPromptToClipboard(kind = "original", button) {
    const text = promptTextForKind(kind);
    if (!text) {
      if (button) {
        setPromptCopyButtonFeedback(button, translate("history.noPromptShort"));
      } else {
        setText(els.resultSummary, translate("history.noPrompt"));
      }
      return;
    }
    try {
      await writeClipboardText(text);
      if (button) setPromptCopyButtonFeedback(button, translate("history.promptCopiedShort"));
      setText(els.resultSummary, translate("history.promptCopied"));
    } catch (error) {
      if (button) setPromptCopyButtonFeedback(button, translate("history.promptCopyFailedShort"));
      setText(els.resultSummary, errorMessage(error, translate("history.promptCopyFailed")));
    }
  }
  async function copyOutputPromptToClipboard(outputIndex, button) {
    const text = outputPromptTextForIndex(outputIndex);
    if (!text) {
      if (button) {
        setPromptCopyButtonFeedback(button, translate("history.noPromptShort"));
      } else {
        setText(els.resultSummary, translate("history.noPrompt"));
      }
      return;
    }
    try {
      await writeClipboardText(text);
      if (button) setPromptCopyButtonFeedback(button, translate("history.promptCopiedShort"));
      setText(els.resultSummary, translate("history.promptCopied"));
    } catch (error) {
      if (button) setPromptCopyButtonFeedback(button, translate("history.promptCopyFailedShort"));
      setText(els.resultSummary, errorMessage(error, translate("history.promptCopyFailed")));
    }
  }
  function reuseHistoryTask(taskId) {
    const task = historyState.detailTask || {};
    const actualTaskId = String(taskId || task.task_id || "");
    if (!actualTaskId) return;
    try {
      localStorage.setItem(HISTORY_TASK_REUSE_HANDOFF_KEY, JSON.stringify({
        task_id: actualTaskId,
        source: "history",
        added_at: (/* @__PURE__ */ new Date()).toISOString()
      }));
      window.location.href = "/";
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, translate("taskContext.actionFailed")));
    }
  }
  async function copyHistoryTaskId(taskIds) {
    const ids = taskIds.filter(Boolean);
    if (!ids.length) return;
    try {
      await writeClipboardText(ids.join("\n"));
      setText(els.resultSummary, ids.length > 1 ? formatTranslation("history.taskIdsCopied", { count: ids.length }) : translate("taskContext.idCopied"));
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, translate("taskContext.actionFailed")));
    }
  }
  async function copyHistoryTaskPrompts(taskIds) {
    const prompts = [];
    for (const taskId of taskIds.filter(Boolean)) {
      try {
        const detail = await fetchHistoryTaskDetail(taskId);
        const prompt = historyTaskPromptForClipboard(detail);
        if (prompt) prompts.push(prompt);
      } catch {
        const fallback = historyTaskPromptForClipboard(historyTaskSummary(taskId));
        if (fallback) prompts.push(fallback);
      }
    }
    if (!prompts.length) {
      setText(els.resultSummary, translate("history.noPrompt"));
      return;
    }
    try {
      await writeClipboardText(prompts.join("\n\n---\n\n"));
      setText(els.resultSummary, taskIds.length > 1 ? formatTranslation("history.promptsCopied", { count: prompts.length }) : translate("history.promptCopied"));
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, translate("history.promptCopyFailed")));
    }
  }
  function triggerHistoryDownload(url, filename = "") {
    if (!url) return;
    const link = document.createElement("a");
    link.href = url;
    if (filename) {
      link.download = filename;
    } else {
      link.setAttribute("download", "");
    }
    link.style.display = "none";
    document.body.append(link);
    link.click();
    link.remove();
  }
  async function downloadHistoryTask(taskId) {
    const detail = await fetchHistoryTaskDetail(taskId);
    const records = taskOutputRecords(detail);
    if (!records.length) throw new Error(translate("history.noDownloadableOutputs"));
    if (records.length === 1) {
      triggerHistoryDownload(records[0]?.url || "");
    } else {
      triggerHistoryDownload(`/api/tasks/${encodeURIComponent(taskId)}/outputs.zip`, `${taskId}-images.zip`);
    }
    return true;
  }
  async function downloadHistoryTasks(taskIds) {
    let downloaded = 0;
    for (const taskId of taskIds.filter(Boolean)) {
      try {
        if (await downloadHistoryTask(taskId)) downloaded += 1;
      } catch {
      }
    }
    setText(
      els.resultSummary,
      downloaded > 1 ? formatTranslation("history.batchDownloadStarted", { count: downloaded }) : downloaded === 1 ? translate("history.downloadStarted") : translate("history.noDownloadableOutputs")
    );
  }
  function selectedHistoryContextTaskIds(clickedTaskId) {
    if (historyState.selectedTaskIds.size > 1 && historyState.selectedTaskIds.has(clickedTaskId)) {
      return [...historyState.selectedTaskIds].filter(Boolean);
    }
    if (historyState.selectedTaskIds.size !== 1 || !historyState.selectedTaskIds.has(clickedTaskId)) {
      historyState.selectedTaskIds = /* @__PURE__ */ new Set([clickedTaskId]);
      historyState.selectionAnchorTaskId = clickedTaskId;
      historyState.deleteConfirming = false;
      historyState.contextMenuDeleteConfirmKey = "";
      updateTaskSelectionVisuals();
      renderBulkToolbar();
    }
    return [clickedTaskId].filter(Boolean);
  }
  function openHistoryContextMenu(taskId, clientX, clientY) {
    if (!taskId) return;
    const taskIds = selectedHistoryContextTaskIds(taskId);
    const mode = taskIds.length > 1 ? "multi" : "single";
    historyState.contextMenu = { mode, taskId, taskIds, x: clientX, y: clientY };
    const menu = ensureHistoryContextMenu();
    menu.dataset.historyContextTaskId = taskId;
    menu.dataset.historyContextMode = mode;
    menu.innerHTML = historyContextMenuHtml(mode, taskIds);
    menu.classList.remove("hidden");
    bindHistoryContextMenuActionEvents(menu);
    positionHistoryContextMenu(menu, clientX, clientY);
    menu.querySelector(".history-context-menu-button:not(:disabled)")?.focus({ preventScroll: true });
  }
  function closeHistoryContextMenu() {
    if (!historyContextMenuEl) return;
    historyContextMenuEl.classList.add("hidden");
    historyContextMenuEl.removeAttribute("data-history-context-task-id");
    historyContextMenuEl.removeAttribute("data-history-context-mode");
  }
  function ensureHistoryContextMenu() {
    if (historyContextMenuEl) return historyContextMenuEl;
    historyContextMenuEl = document.createElement("div");
    historyContextMenuEl.className = "history-context-menu hidden";
    historyContextMenuEl.setAttribute("role", "menu");
    historyContextMenuEl.setAttribute("aria-label", translate("history.contextMenuLabel"));
    document.body.append(historyContextMenuEl);
    return historyContextMenuEl;
  }
  function rerenderHistoryContextMenu() {
    if (!historyContextMenuEl || historyContextMenuEl.classList.contains("hidden")) return;
    historyContextMenuEl.setAttribute("aria-label", translate("history.contextMenuLabel"));
    historyContextMenuEl.innerHTML = historyContextMenuHtml(historyState.contextMenu.mode, historyState.contextMenu.taskIds);
    bindHistoryContextMenuActionEvents(historyContextMenuEl);
    positionHistoryContextMenu(historyContextMenuEl, historyState.contextMenu.x, historyState.contextMenu.y);
  }
  function historyContextMenuHtml(mode, taskIds) {
    if (mode === "multi") return historyMultiContextMenuHtml(taskIds);
    return historySingleContextMenuHtml(taskIds[0] || "");
  }
  function historySingleContextMenuHtml(taskId) {
    const summary = historyTaskSummary(taskId);
    const archived = historyTaskArchived(summary);
    const blocked = historyTaskDeleteBlocked(summary);
    const hasOutput = historyTaskGeneratedCount(summary) > 0;
    const confirmingDelete = historyState.contextMenuDeleteConfirmKey === `task:${taskId}`;
    return `
    <div class="history-context-menu-section">
      ${historyContextButton("reuse", translate("history.reuseTask"))}
      ${historyContextButton("copy-prompt", translate("history.copyPrompt"))}
      ${historyContextButton("copy-id", translate("taskContext.copyId"))}
      ${historyContextButton("download", translate("history.downloadTask"), !hasOutput)}
    </div>
    <div class="history-context-menu-section">
      ${historyContextButton("archive", archived ? translate("archive.restore") : translate("action.archive"))}
      ${historyContextButton("delete", confirmingDelete ? translate("history.confirmDelete") : translate("action.delete"), blocked, true)}
    </div>
  `;
  }
  function historyMultiContextMenuHtml(taskIds) {
    const confirmKey = historySelectedDeleteConfirmKey(taskIds);
    const confirmingDelete = historyState.contextMenuDeleteConfirmKey === confirmKey;
    return `
    <div class="history-context-menu-section">
      ${historyContextButton("download-selected", translate("history.downloadSelectedTasks"))}
      ${historyContextButton("archive-selected", translate("action.archive"))}
      ${historyContextButton("restore-selected", translate("archive.restore"))}
      ${historyContextButton("delete-selected", confirmingDelete ? translate("history.confirmDeleteSelected") : translate("action.delete"), false, true)}
    </div>
  `;
  }
  function historyContextButton(action, label, disabled = false, danger = false) {
    const disabledAttr = disabled ? " disabled" : "";
    const dangerClass = danger ? " danger" : "";
    return `<button class="history-context-menu-button${dangerClass}" type="button" role="menuitem" data-history-context-action="${escapeHtml2(action)}"${disabledAttr}>${escapeHtml2(label)}</button>`;
  }
  function bindHistoryContextMenuActionEvents(menu) {
    menu.querySelectorAll("[data-history-context-action]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        if (button.disabled) return;
        void handleHistoryContextMenuAction(button);
      });
    });
  }
  async function handleHistoryContextMenuAction(button) {
    const action = String(button.dataset.historyContextAction || "");
    const taskId = historyState.contextMenu.taskId;
    const taskIds = historyState.contextMenu.taskIds.filter(Boolean);
    try {
      if (action === "delete") {
        const deleted = await deleteSingleHistoryTask(taskId, { confirmInMenu: true });
        if (deleted) closeHistoryContextMenu();
        return;
      }
      if (action === "delete-selected") {
        await deleteHistoryContextSelectedTasks(taskIds);
        return;
      }
      closeHistoryContextMenu();
      if (action === "reuse") {
        reuseHistoryTask(taskId);
      } else if (action === "copy-prompt") {
        await copyHistoryTaskPrompts([taskId]);
      } else if (action === "copy-id") {
        await copyHistoryTaskId([taskId]);
      } else if (action === "download") {
        await downloadHistoryTasks([taskId]);
      } else if (action === "archive") {
        const archived = historyTaskArchived(historyTaskSummary(taskId));
        await archiveSingleTask(taskId, !archived);
      } else if (action === "copy-prompts") {
        await copyHistoryTaskPrompts(taskIds);
      } else if (action === "copy-ids") {
        await copyHistoryTaskId(taskIds);
      } else if (action === "download-selected") {
        await downloadHistoryTasks(taskIds);
      } else if (action === "archive-selected") {
        await archiveHistoryTaskIds(taskIds, true);
      } else if (action === "restore-selected") {
        await archiveHistoryTaskIds(taskIds, false);
      }
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, translate("taskContext.actionFailed")));
    }
  }
  async function deleteHistoryContextSelectedTasks(taskIds) {
    const confirmKey = historySelectedDeleteConfirmKey(taskIds);
    if (historyState.contextMenuDeleteConfirmKey !== confirmKey) {
      historyState.contextMenuDeleteConfirmKey = confirmKey;
      historyState.deleteConfirming = true;
      renderBulkToolbar();
      rerenderHistoryContextMenu();
      return;
    }
    historyState.selectedTaskIds = new Set(taskIds);
    await deleteSelectedTasks();
    if (!historyState.deleteConfirming) closeHistoryContextMenu();
  }
  function historySelectedDeleteConfirmKey(taskIds) {
    return `selected:${taskIds.slice().sort().join("|")}`;
  }
  function positionHistoryContextMenu(menu, clientX, clientY) {
    const margin = 8;
    menu.style.left = "0px";
    menu.style.top = "0px";
    const width = menu.offsetWidth;
    const height = menu.offsetHeight;
    const left = clampNumber(clientX, margin, Math.max(margin, window.innerWidth - width - margin));
    const top = clampNumber(clientY, margin, Math.max(margin, window.innerHeight - height - margin));
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
  }
  function handoffReferenceToMain(url) {
    if (!url) return;
    localStorage.setItem(HISTORY_REFERENCE_HANDOFF_KEY, JSON.stringify([{ url, source: "history", added_at: (/* @__PURE__ */ new Date()).toISOString() }]));
    window.location.href = "/";
  }
  function openHistoryDetailLightbox(index) {
    const urls = historyLightboxUrlsFromTask(historyState.detailTask || {});
    openHistoryLightbox(urls, index, {
      taskId: historyState.selectedTaskId,
      onTaskNavigate: openHistoryTaskLightboxByDirection
    });
  }
  function openHistoryInputLightbox(index) {
    const urls = historyInputLightboxUrlsFromTask(historyState.detailTask || {});
    openHistoryLightbox(urls, index);
  }
  function historyAdjacentTaskId(taskId, direction) {
    if (!taskId) return "";
    const taskIds = visibleHistoryTaskIds();
    const index = taskIds.indexOf(taskId);
    if (index < 0) return "";
    const nextIndex = direction === "previous" ? index - 1 : index + 1;
    return taskIds[nextIndex] || "";
  }
  function shouldLoadHistoryAdjacentTask(taskId, direction) {
    if (!taskId) return false;
    const taskIds = visibleHistoryTaskIds();
    const index = taskIds.indexOf(taskId);
    if (index < 0) return false;
    if (direction === "previous") return index === 0 && !historyState.newerExhausted;
    return index === taskIds.length - 1 && !historyState.exhausted;
  }
  function syncHistoryLightboxDetail(taskId, detail) {
    historyState.selectedTaskId = taskId;
    historyState.deleteConfirming = false;
    historyState.deleteConfirmTaskId = "";
    historyState.deleteUnselectedConfirmTaskId = "";
    historyState.detailTask = detail;
    els.page?.classList.add("history-detail-open");
    updateHistoryUrl();
    updateTaskSelectionVisuals(taskId);
    ensureHistoryTaskCardVisible(taskId);
    renderTaskDetail(detail);
  }
  async function openHistoryTaskLightboxByDirection(direction, context) {
    const currentTaskId = context.taskId || historyState.selectedTaskId;
    let nextTaskId = historyAdjacentTaskId(currentTaskId, direction);
    if (!nextTaskId && shouldLoadHistoryAdjacentTask(currentTaskId, direction)) {
      await loadTasks({ direction });
      nextTaskId = historyAdjacentTaskId(currentTaskId, direction);
    }
    if (!nextTaskId) {
      setText(els.resultSummary, translate("history.noMore"));
      return;
    }
    await openHistoryTaskLightbox(nextTaskId, context.imageIndex);
  }
  async function openHistoryTaskLightbox(taskId, index = 0) {
    if (!taskId) return;
    try {
      const detail = historyState.detailTask?.task_id === taskId ? historyState.detailTask : await fetchHistoryTaskDetail(taskId);
      const urls = historyLightboxUrlsFromTask(detail);
      if (!urls.length) throw new Error(translate("history.noPreview"));
      syncHistoryLightboxDetail(taskId, detail);
      openHistoryLightbox(urls, index, {
        taskId,
        onTaskNavigate: openHistoryTaskLightboxByDirection
      });
    } catch (error) {
      setText(els.resultSummary, errorMessage(error, translate("history.detailFailed")));
    }
  }
  function closeDetail() {
    historyState.selectedTaskId = "";
    els.page?.classList.remove("history-detail-open");
    updateHistoryUrl();
    updateTaskSelectionVisuals("");
    renderDetailShell(translate("history.detailEmpty"));
  }
  function bindEvents() {
    bindHistoryResizerEvents();
    let searchTimer = 0;
    els.search?.addEventListener("input", () => {
      window.clearTimeout(searchTimer);
      searchTimer = window.setTimeout(() => {
        historyState.q = els.search?.value.trim() || "";
        historyState.selectedTaskId = "";
        updateHistoryUrl();
        void loadTasks({ reset: true });
      }, 180);
    });
    els.searchClear?.addEventListener("click", () => {
      if (els.search) els.search.value = "";
      historyState.q = "";
      historyState.selectedTaskId = "";
      updateHistoryUrl();
      void loadTasks({ reset: true });
    });
    els.sortToggle?.addEventListener("click", (event) => {
      const target = event.target;
      const button = target?.closest("[data-history-sort]");
      if (!button || !els.sortToggle?.contains(button)) return;
      applyHistorySort(button.dataset.historySort || "newest");
    });
    document.addEventListener("change", (event) => {
      const target = event.target;
      const checkbox = target?.closest("[data-history-task-select]");
      if (!checkbox) return;
      const taskId = checkbox.dataset.historyTaskSelect || "";
      if (checkbox.checked) {
        historyState.selectedTaskIds.add(taskId);
      } else {
        historyState.selectedTaskIds.delete(taskId);
      }
      historyState.selectionAnchorTaskId = taskId;
      historyState.deleteConfirming = false;
      updateTaskSelectionVisuals();
      renderBulkToolbar();
    });
    document.addEventListener("click", (event) => {
      const target = event.target;
      const historySelect = target?.closest("[data-history-task-select]");
      if (historySelect) {
        if (handleHistoryTaskShortcutSelection(historySelect.dataset.historyTaskSelect || "", event)) return;
        event.stopPropagation();
        return;
      }
      const viewButton = target?.closest("[data-history-view]");
      if (viewButton) {
        setHistoryViewMode(viewButton.dataset.historyView || "grid");
        return;
      }
      const taskButton = target?.closest("[data-history-task-id]");
      if (taskButton) {
        if (handleHistoryTaskShortcutSelection(taskButton.dataset.historyTaskId || "", event)) return;
        clearHistoryTaskSelection({ updateVisuals: false });
        void loadTaskDetail(taskButton.dataset.historyTaskId || "");
        return;
      }
      const selectButton = target?.closest("[data-history-output-selected-task-id]");
      if (selectButton) {
        void updateOutputSelection(selectButton);
        return;
      }
      const deleteUnselectedButton = target?.closest("[data-history-delete-unselected]");
      if (deleteUnselectedButton) {
        void deleteUnselectedOutputs(deleteUnselectedButton.dataset.historyDeleteUnselected || "");
        return;
      }
      const archiveTaskButton = target?.closest("[data-history-archive-task]");
      if (archiveTaskButton) {
        void archiveSingleTask(archiveTaskButton.dataset.historyArchiveTask || "", archiveTaskButton.dataset.historyArchiveValue === "true");
        return;
      }
      const deleteTaskButton = target?.closest("[data-history-delete-task]");
      if (deleteTaskButton) {
        void deleteSingleHistoryTask(deleteTaskButton.dataset.historyDeleteTask || "");
        return;
      }
      const referenceHandoffButton = target?.closest("[data-history-reference-handoff-url]");
      if (referenceHandoffButton) {
        handoffReferenceToMain(referenceHandoffButton.dataset.historyReferenceHandoffUrl || "");
        return;
      }
      const copyOutputPromptButton = target?.closest("[data-history-copy-output-prompt-index]");
      if (copyOutputPromptButton) {
        void copyOutputPromptToClipboard(copyOutputPromptButton.dataset.historyCopyOutputPromptIndex, copyOutputPromptButton);
        return;
      }
      const copyPromptButton = target?.closest("[data-history-copy-prompt-kind]");
      if (copyPromptButton) {
        void copyPromptToClipboard(copyPromptButton.dataset.historyCopyPromptKind || "original", copyPromptButton);
        return;
      }
      const reuseTaskButton = target?.closest("[data-history-reuse-task]");
      if (reuseTaskButton) {
        reuseHistoryTask(reuseTaskButton.dataset.historyReuseTask || "");
        return;
      }
      const lightboxButton = target?.closest("[data-history-lightbox-url]");
      if (lightboxButton) {
        const index = Number.parseInt(lightboxButton.dataset.historyLightboxIndex || "0", 10) || 0;
        openHistoryDetailLightbox(index);
        return;
      }
      const inputLightboxButton = target?.closest("[data-history-input-lightbox-index]");
      if (inputLightboxButton) {
        const index = Number.parseInt(inputLightboxButton.dataset.historyInputLightboxIndex || "0", 10) || 0;
        openHistoryInputLightbox(index);
        return;
      }
      if (target?.closest("[data-history-lightbox-close]")) {
        closeHistoryLightbox();
        return;
      }
      const lightbox = target?.closest(".history-lightbox");
      if (lightbox && target === lightbox) {
        closeHistoryLightbox();
        return;
      }
      if (target?.closest("[data-history-delete-unselected-cancel]")) {
        historyState.deleteUnselectedConfirmTaskId = "";
        renderTaskDetail(historyState.detailTask || {});
        return;
      }
      if (target?.closest("[data-history-detail-close]")) {
        closeDetail();
        return;
      }
      for (const key of HISTORY_FILTER_KEYS) {
        const attr = historyFilterAttribute(key);
        const button = target?.closest(`[data-history-${attr}]`);
        if (button) {
          applyFilter(key, button.getAttribute(`data-history-${attr}`) || "");
          return;
        }
      }
    });
    els.taskList?.addEventListener("contextmenu", (event) => {
      const target = event.target;
      const card = target?.closest(".history-task-card[data-history-task-card-id]");
      if (!card || !els.taskList?.contains(card)) return;
      event.preventDefault();
      event.stopPropagation();
      openHistoryContextMenu(card.dataset.historyTaskCardId || "", event.clientX, event.clientY);
    });
    els.taskList?.addEventListener("dblclick", (event) => {
      const target = event.target;
      if (target?.closest("[data-history-task-select]")) return;
      const card = target?.closest(".history-task-card[data-history-task-card-id]");
      if (!card || !els.taskList?.contains(card)) return;
      event.preventDefault();
      event.stopPropagation();
      void openHistoryTaskLightbox(card.dataset.historyTaskCardId || "");
    });
    els.taskList?.addEventListener("keydown", (event) => {
      if (event.key !== "ContextMenu" && !(event.shiftKey && event.key === "F10")) return;
      const target = event.target;
      const card = target?.closest(".history-task-card[data-history-task-card-id]");
      if (!card || !els.taskList?.contains(card)) return;
      event.preventDefault();
      const rect = card.getBoundingClientRect();
      openHistoryContextMenu(card.dataset.historyTaskCardId || "", rect.left + 18, rect.top + 18);
    });
    document.addEventListener("click", (event) => {
      if (!historyContextMenuEl || historyContextMenuEl.classList.contains("hidden")) return;
      const target = event.target;
      if (target && historyContextMenuEl.contains(target)) return;
      closeHistoryContextMenu();
    }, true);
    els.bulkArchive?.addEventListener("click", () => void archiveSelectedTasks(true));
    els.bulkRestore?.addEventListener("click", () => void archiveSelectedTasks(false));
    els.bulkDelete?.addEventListener("click", () => void deleteSelectedTasks());
    els.bulkDeleteCancel?.addEventListener("click", () => {
      historyState.deleteConfirming = false;
      renderBulkToolbar();
    });
    els.refresh?.addEventListener("click", () => {
      void loadSummary();
      void loadTasks({ reset: true });
    });
    els.taskList?.addEventListener("dragstart", (event) => {
      const target = event.target;
      if (target?.closest(".history-task-thumb img")) event.preventDefault();
    });
    els.taskList?.addEventListener("scroll", () => {
      closeHistoryContextMenu();
      maybeLoadMoreFromScroll();
    }, { passive: true });
    window.addEventListener("resize", () => {
      closeHistoryContextMenu();
      const widths = getCurrentHistoryLayoutWidths();
      applyHistoryLayoutWidths(widths.left, widths.right, { preserveActiveTask: true });
    }, { passive: true });
    document.addEventListener(LOCALE_CHANGE_EVENT, () => {
      document.title = translate("history.documentTitle");
      syncHistoryViewMode();
      syncArchiveButtons();
      els.taskList?.querySelectorAll(".history-task-active-badge").forEach((badge) => {
        badge.textContent = translate("history.viewing");
      });
      if (historyState.detailTask) {
        renderTaskDetail(historyState.detailTask);
      } else if (!historyState.selectedTaskId) {
        renderDetailShell(translate("history.detailEmpty"));
      }
      rerenderHistoryContextMenu();
      renderBulkToolbar();
      setLoadMoreState(historyState.loading ? translate("history.loadingMore") : historyState.exhausted ? translate("history.noMore") : "", {
        hidden: !historyState.loading && !historyState.exhausted,
        busy: historyState.loading
      });
    });
    window.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (historyContextMenuEl && !historyContextMenuEl.classList.contains("hidden")) {
        closeHistoryContextMenu();
        return;
      }
      if (isHistoryLightboxOpen()) {
        closeHistoryLightbox();
        return;
      }
      if (historyState.selectedTaskId) closeDetail();
    });
  }
  function errorMessage(error, fallback) {
    return error instanceof Error && error.message ? error.message : fallback;
  }
  async function bootHistoryPage() {
    restoreHistoryThemePreference();
    bindHistoryThemePreference();
    applyHistoryLocale();
    restoreHistoryLayoutPreference();
    syncStateFromUrl();
    initSegmentedIndicatorFeature();
    renderDetailShell(translate("history.detailEmpty"));
    bindEvents();
    await loadSummary();
    await loadTasks({ reset: true });
    if (historyState.selectedTaskId) {
      void loadTaskDetail(historyState.selectedTaskId);
    }
  }
  void bootHistoryPage();
})();
//# sourceMappingURL=history.js.map
