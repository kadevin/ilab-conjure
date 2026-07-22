import { getLegacyBridge } from "./state";
import { formatTranslation, LOCALE_CHANGE_EVENT, translate } from "./i18n";
import { groundingAttributionKey, syncGroundingAttribution } from "./grounding-attribution";

const bridge = getLegacyBridge();
const state = bridge.state;
const els = bridge.els;

let previewGridEventsBound = false;
let pendingPreviewRenderToken = 0;

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy bridge method " + name + " is not available");
  }
  return method(...args);
}

function escapeHtml(...args: any[]) { return legacyMethod("escapeHtml", ...args); }
function isTaskArchived(...args: any[]) { return legacyMethod("isTaskArchived", ...args); }
function updatePreviewElapsedDisplay(...args: any[]) { return legacyMethod("updatePreviewElapsedDisplay", ...args); }
function closePromptPopover(...args: any[]) { return legacyMethod("closePromptPopover", ...args); }
function currentSize(...args: any[]) { return legacyMethod("currentSize", ...args); }
function syncActiveLightboxUrls(...args: any[]) { return legacyMethod("syncActiveLightboxUrls", ...args); }
function collectReferenceOutput(...args: any[]) { return legacyMethod("collectReferenceOutput", ...args); }
function openPromptPopover(...args: any[]) { return legacyMethod("openPromptPopover", ...args); }
function retryFailedTask(...args: any[]) { return legacyMethod("retryFailedTask", ...args); }
function acceptTaskSuccesses(...args: any[]) { return legacyMethod("acceptTaskSuccesses", ...args); }
function openConfirmPopover(...args: any[]) { return legacyMethod("openConfirmPopover", ...args); }
function setStatus(...args: any[]) { return legacyMethod("setStatus", ...args); }
function updateTaskInState(...args: any[]) { return legacyMethod("updateTaskInState", ...args); }
function renderTasks(...args: any[]) { return legacyMethod("renderTasks", ...args); }
function taskApiProviderId(...args: any[]) { return legacyMethod("taskApiProviderId", ...args); }
function taskApiProviderLabel(...args: any[]) { return legacyMethod("taskApiProviderLabel", ...args); }
const taskOutputUrls = (...args: any[]) => legacyMethod("taskOutputUrls", ...args);
const taskSelectedOutputIndexes = (...args: any[]) => legacyMethod("taskSelectedOutputIndexes", ...args);
const taskOutputSelected = (...args: any[]) => legacyMethod("taskOutputSelected", ...args);
const positiveInt = (...args: any[]) => legacyMethod("positiveInt", ...args);
const taskFailureMessage = (...args: any[]) => legacyMethod("taskFailureMessage", ...args);
const canRetryFailedTask = (...args: any[]) => legacyMethod("canRetryFailedTask", ...args);
const canAcceptTaskSuccesses = (...args: any[]) => legacyMethod("canAcceptTaskSuccesses", ...args);
const taskRetryStateText = (...args: any[]) => legacyMethod("taskRetryStateText", ...args);
const elapsedTimerSpan = (...args: any[]) => legacyMethod("elapsedTimerSpan", ...args);
const taskGeneratedCount = (...args: any[]) => legacyMethod("taskGeneratedCount", ...args);
const taskTotalCount = (...args: any[]) => legacyMethod("taskTotalCount", ...args);
const taskOutputIndex = (...args: any[]) => legacyMethod("taskOutputIndex", ...args);
const taskProgressStartValue = (...args: any[]) => legacyMethod("taskProgressStartValue", ...args);

function taskRequestPreviewPayload(task: any) {
  if (!task?.request) return null;
  const request = { ...task.request };
  const providerId = taskApiProviderId(task);
  const providerLabel = taskApiProviderLabel(task);
  if (providerId && !request.webui_api_provider_id) {
    request.webui_api_provider_id = providerId;
  }
  if (providerLabel && !request.webui_api_provider_name) {
    request.webui_api_provider_name = providerLabel;
  }
  return request;
}

function queueContainsTask(items: any[] | undefined, taskId: string) {
  if (!taskId || !Array.isArray(items)) return false;
  return items.some((item: any) => String(item?.task_id || "") === taskId);
}

const TERMINAL_TASK_STATUSES = new Set(["completed", "failed", "partial_failed"]);

function taskPreviewStatus(task: any) {
  const status = String(task?.status || "");
  const taskId = String(task?.task_id || "");
  if (TERMINAL_TASK_STATUSES.has(status)) return status;
  if (queueContainsTask(state.queue.running, taskId)) return "running";
  if (queueContainsTask(state.queue.waiting, taskId)) return status === "submitting" ? "submitting" : "queued";
  return status;
}

function renderPreview(task: any = null) {
  const selectedTask = state.tasks.find((item: any) => String(item.task_id) === String(state.selectedTaskId));
  const visibleSelectedTask = selectedTask && !isTaskArchived(selectedTask.task_id) ? selectedTask : null;
  const selected = task || visibleSelectedTask || state.tasks.find((item: any) => !isTaskArchived(item.task_id)) || selectedTask || state.tasks[0];
  const status = taskPreviewStatus(selected);
  syncGroundingAttribution(els.previewGrid, selected, "preview");
  updatePreviewDownloadActions(selected);
  const nextPreviewKey = previewStructureKey(selected);
  if (state.previewRenderKey === nextPreviewKey) {
    return updatePreviewElapsedDisplay();
  }
  state.previewRenderKey = nextPreviewKey;
  if (status === "running") {
    if (taskOutputUrls(selected).length) {
      renderOutputPreview(selected, { running: true });
      return;
    }
    closePromptPopover();
    cancelDeferredPreviewRender();
    renderRunningPreview(selected);
    return;
  }
  if (status === "submitting" || status === "queued") {
    if (status === "queued" && taskOutputUrls(selected).length) {
      renderOutputPreview(selected, { waiting: true });
      return;
    }
    closePromptPopover();
    cancelDeferredPreviewRender();
    renderWaitingPreview(selected);
    return;
  }
  if (selected?.status === "failed" || selected?.status === "partial_failed") {
    if (taskOutputUrls(selected).length) {
      renderOutputPreview(selected, { failure: true });
      return;
    }
    closePromptPopover();
    cancelDeferredPreviewRender();
    clearPreviewGridLayout();
    els.previewGrid.innerHTML = `
      <div class="empty-preview error-preview">
        <p>${escapeHtml(taskFailureMessage(selected) || translate("preview.taskFailed"))}</p>
        ${retryFailureSummaryButton(selected)}
      </div>
    `;
    bindPreviewRetryButtons();
    return;
  }
  const outputUrls = taskOutputUrls(selected);
  if (!selected || !outputUrls.length) {
    closePromptPopover();
    cancelDeferredPreviewRender();
    clearPreviewGridLayout();
    els.previewGrid.innerHTML = `<div class="empty-preview">${escapeHtml(translate("preview.empty"))}</div>`;
    return;
  }

  renderOutputPreview(selected);
}

function previewStructureKey(task: any) {
  if (!task) return "empty:none";
  const taskId = String(task.task_id || "");
  const status = taskPreviewStatus(task);
  const outputUrls = taskOutputUrls(task).join("|");
  const selectedIndexes = taskSelectedOutputIndexes(task).join(",");
  const size = task.params?.size || task.output_size || currentSize();
  if (status === "failed" || status === "partial_failed") {
    return ["failed", taskId, status, outputUrls, selectedIndexes, taskFailureMessage(task), taskRetryStateText(task), canRetryFailedTask(task), canAcceptTaskSuccesses(task)].join("|");
  }
  if (status === "submitting" || status === "queued") {
    return ["waiting", taskId, status, outputUrls, selectedIndexes, taskGeneratedCount(task, 0), taskTotalCount(task), size, task.last_error || task.error || "", taskRetryStateText(task)].join("|");
  }
  if (status === "running") {
    return ["running", taskId, outputUrls, selectedIndexes, taskGeneratedCount(task, 0), taskTotalCount(task), size, task.mode || "", taskRetryStateText(task), taskRunningFailureKey(task)].join("|");
  }
  if (outputUrls) {
    return ["output", taskId, status, outputUrls, selectedIndexes, previewPromptKey(task), groundingAttributionKey(task)].join("|");
  }
  return ["empty", taskId, status].join("|");
}

function previewPromptKey(task: any) {
  const revisedPrompts = Array.isArray(task?.revised_prompts) ? task.revised_prompts.join("\u001f") : "";
  return [task?.prompt_for_model || task?.prompt || "", task?.revised_prompt || "", revisedPrompts].join("\u001f");
}

function taskRunningFailureKey(task: any) {
  return taskFailedOutputRecords(task)
    .map((failure: any) => `${failure.index}:${failure.error}`)
    .join("\u001f");
}

function taskFirstFailedOutput(task: any) {
  return taskFailedOutputRecords(task)[0] || null;
}

function taskFailedOutputRecords(task: any) {
  if (!Array.isArray(task?.outputs)) return [];
  return task.outputs
    .map((record: any, outputPosition: number) => {
      if (!record || record.status !== "failed") return null;
      const error = String(record.error || record.message || record.failure_reason || "").trim();
      if (!error) return null;
      return {
        index: positiveInt(record.index) || outputPosition + 1,
        error,
      };
    })
    .filter(Boolean)
    .sort((left: any, right: any) => left.index - right.index);
}

function runningFailureNotice(task: any) {
  const failure = taskFirstFailedOutput(task);
  if (!failure) return "";
  return `
    <div class="running-failure-notice" data-preview-running-failure role="status">
      <strong>${escapeHtml(formatTranslation("preview.failedOutput", { index: failure.index }))}</strong>
      <p>${escapeHtml(failure.error)}</p>
    </div>
  `;
}

function previewElapsedLineHtml(key: string, values: Record<string, any>, elapsedHtml: string) {
  const marker = "__CODEX_IMAGE_ELAPSED_TIMER__";
  return formatTranslation(key, { ...values, elapsed: marker })
    .split(marker)
    .map((part) => escapeHtml(part))
    .join(elapsedHtml);
}

function scheduleDeferredPreviewRender(task: any, { running, failure, waiting, outputUrls, totalCount, itemCount }: any) {
  const renderToken = ++pendingPreviewRenderToken;
  void (async () => {
    const allImagesLoaded = await preloadPreviewImages(outputUrls);
    if (renderToken !== pendingPreviewRenderToken) return;
    commitOutputPreviewRender(task, {
      running,
      failure,
      waiting,
      outputUrls,
      totalCount,
      itemCount,
      preservePreviousImages: false,
      imageAlreadyLoaded: allImagesLoaded,
    });
  })();
}

function cancelDeferredPreviewRender() {
  pendingPreviewRenderToken += 1;
}

function renderOutputPreview(task: any, { running = false, failure = false, waiting = false }: any = {}) {
  const outputUrls = taskOutputUrls(task);
  const hasStatusCard = running || failure || waiting;
  const totalCount = hasStatusCard ? taskTotalCount(task) : outputUrls.length;
  const itemCount = outputUrls.length + (hasStatusCard ? 1 : 0);
  const previousOutputCount = currentPreviewOutputCardCount();
  const preservePreviousImages = previousOutputCount === outputUrls.length;
  const shouldDeferLayoutSwitch = !preservePreviousImages && outputUrls.length > 0;
  if (shouldDeferLayoutSwitch) {
    scheduleDeferredPreviewRender(task, { running, failure, waiting, outputUrls, totalCount, itemCount });
    return;
  }
  pendingPreviewRenderToken += 1;
  commitOutputPreviewRender(task, { running, failure, waiting, outputUrls, totalCount, itemCount, preservePreviousImages });
}

function commitOutputPreviewRender(task: any, { running = false, failure = false, waiting = false, outputUrls, totalCount, itemCount, preservePreviousImages = true, imageAlreadyLoaded = false }: any) {
  applyPreviewGridLayout(totalCount, itemCount);
  state.previewTask = task || null;
  state.previewOutputUrls = outputUrls.slice();
  bindPreviewGridEvents();
  reconcilePreviewOutputCards(task, outputUrls, totalCount, { preservePreviousImages, imageAlreadyLoaded });
  reconcilePreviewStatusCard(task, { running, failure, waiting }, outputUrls.length);
  syncActiveLightboxUrls(outputUrls);
  window.requestAnimationFrame(syncPreviewImageOrientation);
}

function reconcilePreviewOutputCards(task: any, outputUrls: any[], totalCount: any, { preservePreviousImages = true, imageAlreadyLoaded = false }: any = {}) {
  if (!els.previewGrid) return;
  const desiredKeys = new Set(outputUrls.map((url: any, index: any) => previewOutputCardKey(task, url, index)));
  removeStalePreviewNodes(desiredKeys);
  outputUrls.forEach((url: any, index: any) => {
    const key = previewOutputCardKey(task, url, index);
    const card = ensurePreviewOutputCard(key);
    if (els.previewGrid.children[index] !== card) {
      els.previewGrid.insertBefore(card, els.previewGrid.children[index] || null);
    }
    updatePreviewOutputCard(card, task, url, index, totalCount, { preservePreviousImage: preservePreviousImages, imageAlreadyLoaded });
  });
}

function currentPreviewOutputCardCount() {
  if (!els.previewGrid) return 0;
  return els.previewGrid.querySelectorAll(".preview-card[data-preview-card-key]").length;
}

function removeStalePreviewNodes(desiredKeys: Set<string>) {
  [...els.previewGrid.children].forEach((child: any) => {
    if (!(child instanceof HTMLElement)) return;
    const key = child.dataset.previewCardKey;
    if (key) {
      if (!desiredKeys.has(key)) child.remove();
      return;
    }
    if (child.dataset.previewStatusCard === "true") return;
    child.remove();
  });
}

function previewOutputCardKey(task: any, url: any, index: any) {
  return `slot-${taskOutputIndex(task, url, index) || index + 1}`;
}

function ensurePreviewOutputCard(key: string) {
  const existing = [...els.previewGrid.querySelectorAll(".preview-card[data-preview-card-key]")].find((card: any) => {
    return card instanceof HTMLElement && card.dataset.previewCardKey === key;
  });
  if (existing instanceof HTMLElement) return existing;
  const card = document.createElement("div");
  card.className = "preview-card";
  card.setAttribute("data-preview-card-key", key);
  const featuredLabel = translate("preview.featured");
  const addFeaturedLabel = translate("preview.addFeatured");
  const addReferenceLabel = translate("preview.addReference");
  const stageLabel = translate("preview.stage");
  const stageReferenceLabel = translate("preview.stageReference");
  const promptLabel = translate("preview.prompt");
  const downloadLabel = translate("preview.download");
  const downloadImageLabel = translate("preview.downloadImage");
  card.innerHTML = `
    <span class="preview-index hidden"></span>
    <button type="button" class="preview-select-button" data-preview-select-output-index="" aria-pressed="false" aria-label="${addFeaturedLabel}" title="${addFeaturedLabel}" data-i18n-attr="aria-label:preview.addFeatured;title:preview.addFeatured" hidden disabled>
      <svg class="preview-select-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
        <path d="M12 3.5l2.7 5.5 6 .9-4.3 4.2 1 6-5.4-2.8-5.4 2.8 1-6-4.3-4.2 6-.9L12 3.5z" />
      </svg>
      <span class="preview-select-label" data-preview-select-label data-i18n="preview.featured">${featuredLabel}</span>
    </button>
    <img alt="" data-lightbox-url="">
    <div class="preview-overlay">
       <div class="prompt-action-row">
         <button type="button" class="add-to-input-btn" data-add-input-url="" aria-label="${addReferenceLabel}" data-i18n="preview.addReference" data-i18n-attr="aria-label:preview.addReference">${addReferenceLabel}</button>
         <button type="button" class="collect-input-btn" data-collect-input-url="" data-collect-output-index="" data-collect-output-name="" aria-label="${stageReferenceLabel}" title="${stageReferenceLabel}" data-i18n="preview.stage" data-i18n-attr="aria-label:preview.stageReference;title:preview.stageReference">${stageLabel}</button>
         <button type="button" class="prompt-popover-button" data-prompt-popover-index="" data-i18n="preview.prompt">${promptLabel}</button>
         <a class="preview-download-link" href="#" download="" data-download-output-url="" title="${downloadImageLabel}" aria-label="${downloadImageLabel}" data-i18n="preview.download" data-i18n-attr="aria-label:preview.downloadImage;title:preview.downloadImage">${downloadLabel}</a>
       </div>
    </div>
  `;
  const image = card.querySelector("img");
  image?.addEventListener("load", syncPreviewImageOrientation);
  return card;
}

function updatePreviewOutputCard(card: HTMLElement, task: any, url: any, index: any, totalCount: any, { preservePreviousImage = true, imageAlreadyLoaded = false }: any = {}) {
  const outputIndex = taskOutputIndex(task, url, index);
  const outputUrl = String(url || "");
  const downloadName = outputDownloadFilename(task, url, index);
  card.setAttribute("data-preview-card-key", previewOutputCardKey(task, url, index));
  card.setAttribute("data-preview-output-url", outputUrl);
  card.dataset.previewTaskId = String(task?.task_id || "");
  updatePreviewIndexLabel(card, outputIndex, totalCount);
  updatePreviewImage(card, outputUrl, { preservePreviousImage, imageAlreadyLoaded });
  const addButton = card.querySelector<HTMLElement>("[data-add-input-url]");
  const collectButton = card.querySelector<HTMLElement>("[data-collect-input-url]");
  const promptButton = card.querySelector<HTMLElement>("[data-prompt-popover-index]");
  const downloadLink = card.querySelector<HTMLAnchorElement>("[data-download-output-url]");
  const selectButton = card.querySelector<HTMLButtonElement>("[data-preview-select-output-index]");
  if (addButton) addButton.dataset.addInputUrl = outputUrl;
  if (collectButton) {
    collectButton.dataset.collectInputUrl = outputUrl;
    collectButton.dataset.collectOutputIndex = String(outputIndex);
    collectButton.dataset.collectOutputName = downloadName;
  }
  if (promptButton) promptButton.dataset.promptPopoverIndex = String(index);
  if (downloadLink) {
    downloadLink.href = outputUrl;
    downloadLink.download = downloadName;
    downloadLink.dataset.downloadOutputUrl = outputUrl;
  }
  if (selectButton) {
    const selectable = Number(totalCount) > 1;
    const selected = taskOutputSelected(task, outputIndex);
    selectButton.hidden = !selectable;
    selectButton.disabled = !selectable;
    selectButton.dataset.previewSelectOutputIndex = String(outputIndex);
    selectButton.dataset.previewSelectTaskId = String(task?.task_id || "");
    selectButton.setAttribute("aria-pressed", selected ? "true" : "false");
    selectButton.setAttribute("aria-label", selected ? translate("preview.removeFeatured") : translate("preview.addFeatured"));
    selectButton.title = selected ? translate("preview.removeFeatured") : translate("preview.addFeatured");
    selectButton.querySelector("[data-preview-select-label]")!.textContent = selected ? translate("preview.selectedFeatured") : translate("preview.featured");
    card.classList.toggle("can-select-output", selectable);
    card.classList.toggle("is-selected", selected);
  }
}

function updatePreviewIndexLabel(card: HTMLElement, outputIndex: any, totalCount: any) {
  const label = card.querySelector<HTMLElement>(".preview-index");
  if (!label) return;
  if (totalCount > 1) {
    label.textContent = `${outputIndex} / ${totalCount}`;
    label.classList.remove("hidden");
    return;
  }
  label.textContent = "";
  label.classList.add("hidden");
}

function updatePreviewImage(card: HTMLElement, url: string, { preservePreviousImage = true, imageAlreadyLoaded = false }: any = {}) {
  const visibleImage = card.querySelector<HTMLImageElement>("img[data-lightbox-url]");
  if (!visibleImage) return;
  if (visibleImage.getAttribute("src") === url) {
    visibleImage.dataset.lightboxUrl = url;
    if (visibleImage.complete) window.requestAnimationFrame(syncPreviewImageOrientation);
    return;
  }
  const token = `${url}:${Date.now()}:${Math.random()}`;
  card.dataset.previewImageToken = token;
  card.dataset.previewPendingUrl = url;
  if (imageAlreadyLoaded) {
    commitPreviewImageUrl(card, visibleImage, url, token);
    return;
  }
  if (!visibleImage.getAttribute("src")) {
    commitPreviewImageUrl(card, visibleImage, url, token);
    return;
  }
  if (!preservePreviousImage) {
    clearPreviewImageBeforeLoad(visibleImage);
  }
  card.classList.add("is-loading-next");
  void preloadPreviewImage(url).then((loaded) => {
    if (!loaded) {
      cancelPreviewImagePending(card, token);
      return;
    }
    commitPreviewImageUrl(card, visibleImage, url, token);
  });
}

function commitPreviewImageUrl(card: HTMLElement, visibleImage: HTMLImageElement, url: string, token: string) {
  if (!card.isConnected || card.dataset.previewImageToken !== token) return;
  visibleImage.src = url;
  visibleImage.hidden = false;
  visibleImage.dataset.lightboxUrl = url;
  delete card.dataset.previewPendingUrl;
  card.classList.remove("is-loading-next");
  if (visibleImage.complete) window.requestAnimationFrame(syncPreviewImageOrientation);
}

function clearPreviewImageBeforeLoad(visibleImage: HTMLImageElement) {
  visibleImage.hidden = true;
  visibleImage.removeAttribute("src");
  visibleImage.dataset.lightboxUrl = "";
}

function cancelPreviewImagePending(card: HTMLElement, token: string) {
  if (!card.isConnected || card.dataset.previewImageToken !== token) return;
  delete card.dataset.previewPendingUrl;
  card.classList.remove("is-loading-next");
}

async function preloadPreviewImage(url: string) {
  const image = document.createElement("img");
  const loadedPromise = waitForPreviewImageLoad(image);
  image.decoding = "async";
  image.src = url;
  const loaded = image.complete && image.naturalWidth > 0 ? true : await loadedPromise;
  if (!loaded) return false;
  try {
    await image.decode?.();
  } catch {
    // Decode failures should not block a loaded preview image from appearing.
  }
  return true;
}

async function preloadPreviewImages(outputUrls: any[]) {
  const results = await Promise.all(outputUrls.map((url) => preloadPreviewImage(String(url || ""))));
  return results.every(Boolean);
}

function waitForPreviewImageLoad(image: HTMLImageElement) {
  return new Promise<boolean>((resolve) => {
    image.onload = () => resolve(true);
    image.onerror = () => resolve(false);
  });
}

function reconcilePreviewStatusCard(task: any, flags: any, visibleOutputCount: any) {
  const existing = els.previewGrid.querySelector("[data-preview-status-card]");
  const html = flags.running
    ? runningProgressCard(task, visibleOutputCount)
    : flags.waiting
      ? waitingProgressCard(task, visibleOutputCount)
      : flags.failure
        ? failureSummaryCard(task, visibleOutputCount)
        : "";
  if (!html) {
    existing?.remove();
    return;
  }
  const template = document.createElement("template");
  template.innerHTML = html.trim();
  const next = template.content.firstElementChild;
  if (!(next instanceof HTMLElement)) return;
  next.dataset.previewStatusCard = "true";
  if (existing) {
    existing.replaceWith(next);
  } else {
    els.previewGrid.append(next);
  }
}

function bindPreviewGridEvents() {
  if (previewGridEventsBound || !els.previewGrid) return;
  previewGridEventsBound = true;
  els.previewGrid.addEventListener("click", handlePreviewGridClick);
}

function handlePreviewGridClick(event: any) {
  const target = event.target instanceof Element ? event.target : null;
  if (!target) return;
  if (target.closest("[data-download-output-url]")) return;
  const retryButton = target.closest("[data-preview-retry-failed-task-id]") as HTMLElement | null;
  if (retryButton) {
    retryFailedTask(retryButton.dataset.previewRetryFailedTaskId);
    return;
  }
  const acceptButton = target.closest("[data-preview-accept-successes-task-id]") as HTMLElement | null;
  if (acceptButton) {
    acceptTaskSuccesses(acceptButton.dataset.previewAcceptSuccessesTaskId);
    return;
  }
  const selectButton = target.closest("[data-preview-select-output-index]") as HTMLElement | null;
  if (selectButton) {
    event.stopPropagation();
    const outputIndex = positiveInt(selectButton.dataset.previewSelectOutputIndex);
    const taskId = selectButton.dataset.previewSelectTaskId || state.previewTask?.task_id || "";
    if (!taskId || outputIndex === null) return;
    const selected = selectButton.getAttribute("aria-pressed") !== "true";
    void updateTaskOutputSelection(taskId, outputIndex, selected);
    return;
  }
  const addButton = target.closest("[data-add-input-url]") as HTMLElement | null;
  if (addButton) {
    void window.addToInput?.(addButton.dataset.addInputUrl || "");
    return;
  }
  const collectButton = target.closest("[data-collect-input-url]") as HTMLElement | null;
  if (collectButton) {
    collectReferenceOutput(collectButton.dataset.collectInputUrl, {
      name: collectButton.dataset.collectOutputName || "",
      sourceTaskId: state.previewTask?.task_id || "",
      outputIndex: positiveInt(collectButton.dataset.collectOutputIndex) || null,
    });
    return;
  }
  const promptButton = target.closest("[data-prompt-popover-index]") as HTMLElement | null;
  if (promptButton) {
    event.stopPropagation();
    const index = Number.parseInt(promptButton.dataset.promptPopoverIndex || "0", 10);
    openPromptPopover(promptButton, promptPopoverData(state.previewTask, index));
    return;
  }
  const image = target.closest("[data-lightbox-url]") as HTMLImageElement | null;
  if (!image) return;
  const images = [...els.previewGrid.querySelectorAll("[data-lightbox-url]")] as HTMLImageElement[];
  const urls = images
    .map((item) => item.dataset.lightboxUrl || item.currentSrc || item.src)
    .filter((url): url is string => Boolean(url));
  const currentUrl = image.dataset.lightboxUrl || image.currentSrc || image.src;
  if (!currentUrl) return;
  window.openLightbox?.(currentUrl, urls, Math.max(0, images.indexOf(image)));
}

function bindPreviewRetryButtons() {
  bindPreviewGridEvents();
}

function updatePreviewDownloadActions(task: any) {
  updatePreviewSelectionActions(task);
  const outputUrls = taskOutputUrls(task);
  if (!els.downloadAllButton) return;
  if (!task?.task_id || outputUrls.length < 2) {
    els.downloadAllButton.classList.add("hidden");
    els.downloadAllButton.removeAttribute("href");
    els.downloadAllButton.removeAttribute("download");
    return;
  }
  els.downloadAllButton.href = taskOutputZipUrl(task);
  els.downloadAllButton.download = `${task.task_id}-images.zip`;
  els.downloadAllButton.classList.remove("hidden");
}

function updatePreviewSelectionActions(task: any) {
  const outputUrls = taskOutputUrls(task);
  const selectedUrls = taskSelectedOutputUrls(task);
  const selectedCount = selectedUrls.length;
  const totalCount = outputUrls.length;
  const hasSelection = Boolean(task?.task_id && selectedCount > 0 && totalCount > 1);
  els.previewSelectionActions?.classList.toggle("hidden", !hasSelection);
  if (els.previewSelectionCount) {
    els.previewSelectionCount.textContent = selectedCount
      ? formatTranslation("preview.selectedCount", { selected: selectedCount, total: totalCount })
      : translate("preview.selectedZero");
  }
  if (els.downloadSelectedButton) {
    if (!hasSelection) {
      els.downloadSelectedButton.classList.add("hidden");
      els.downloadSelectedButton.removeAttribute("href");
      els.downloadSelectedButton.removeAttribute("download");
    } else {
      els.downloadSelectedButton.href = taskSelectedOutputDownloadUrl(task);
      els.downloadSelectedButton.download = taskSelectedOutputDownloadName(task);
      els.downloadSelectedButton.classList.remove("hidden");
    }
  }
  if (els.deleteUnselectedOutputsButton) {
    const canDeleteUnselected = hasSelection && selectedCount < totalCount;
    els.deleteUnselectedOutputsButton.classList.toggle("hidden", !canDeleteUnselected);
    if (canDeleteUnselected) {
      els.deleteUnselectedOutputsButton.dataset.deleteUnselectedTaskId = String(task.task_id || "");
    } else {
      delete els.deleteUnselectedOutputsButton.dataset.deleteUnselectedTaskId;
    }
  }
}

function taskSelectedOutputUrls(task: any) {
  const selectedIndexes = new Set(taskSelectedOutputIndexes(task));
  return taskOutputUrls(task).filter((url: any, index: any) => {
    return selectedIndexes.has(taskOutputIndex(task, url, index));
  });
}

function taskSelectedOutputDownloadUrl(task: any) {
  const selectedUrls = taskSelectedOutputUrls(task);
  if (selectedUrls.length === 1) return selectedUrls[0];
  return taskOutputZipUrl(task, { selected: true });
}

function taskSelectedOutputDownloadName(task: any) {
  const selectedUrls = taskSelectedOutputUrls(task);
  if (selectedUrls.length === 1) {
    const outputUrls = taskOutputUrls(task);
    const index = Math.max(0, outputUrls.indexOf(selectedUrls[0]));
    return outputDownloadFilename(task, selectedUrls[0], index);
  }
  return `${safeDownloadStem(task?.task_id || "image")}-selected-images.zip`;
}

function taskOutputZipUrl(task: any, { selected = false }: any = {}) {
  const url = `/api/tasks/${encodeURIComponent(String(task?.task_id || ""))}/outputs.zip`;
  return selected ? `${url}?selected=1` : url;
}

async function updateTaskOutputSelection(taskId: any, outputIndex: any, selected: boolean) {
  try {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/outputs/${encodeURIComponent(String(outputIndex))}/selected`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ selected }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || translate("preview.selectionUpdateFailed"));
    const updatedTask = data.task;
    updateTaskInState(updatedTask);
    renderPreview(updatedTask);
    setStatus(selected ? translate("preview.selectionAdded") : translate("preview.selectionRemoved"), "ok");
  } catch (error) {
    setStatus(error instanceof Error ? error.message : translate("preview.selectionUpdateFailed"), "error");
  }
}

function openDeleteUnselectedOutputsConfirm(button: HTMLElement) {
  const taskId = button.dataset.deleteUnselectedTaskId || state.previewTask?.task_id || state.selectedTaskId || "";
  const task = state.tasks.find((item: any) => String(item.task_id) === String(taskId)) || state.previewTask;
  const selectedCount = taskSelectedOutputUrls(task).length;
  const totalCount = taskOutputUrls(task).length;
  const deleteCount = Math.max(0, totalCount - selectedCount);
  if (!task?.task_id || selectedCount <= 0 || deleteCount <= 0) {
    setStatus(translate("preview.noUnselectedOutputs"), "error");
    return;
  }
  openConfirmPopover(button, {
    title: translate("preview.deleteUnselectedTitle"),
    message: translate("preview.deleteUnselectedMessage"),
    detail: formatTranslation("preview.deleteUnselectedDetail", { selected: selectedCount, deleted: deleteCount }),
    confirmText: translate("action.delete"),
    onConfirm: async () => {
      await deleteUnselectedOutputs(task.task_id);
    },
  });
}

async function deleteUnselectedOutputs(taskId: any) {
  closePromptPopover();
  try {
    const response = await fetch(`/api/tasks/${encodeURIComponent(taskId)}/outputs/delete-unselected`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || translate("preview.deleteUnselectedFailed"));
    const updatedTask = data.task;
    updateTaskInState(updatedTask);
    state.selectedTaskId = updatedTask.task_id;
    renderTasks();
    renderPreview(updatedTask);
    setStatus(translate("preview.deleteUnselectedDone"), "ok");
  } catch (error) {
    setStatus(error instanceof Error ? error.message : translate("preview.deleteUnselectedFailed"), "error");
  }
}

function outputDownloadFilename(task: any, url: any, index: any) {
  return outputFilenameFromUrl(url) || `${safeDownloadStem(task?.task_id || "image")}-image-${taskOutputIndex(task, url, index)}.png`;
}

function outputFilenameFromUrl(url: any) {
  try {
    const parsed = new URL(String(url || ""), window.location.origin);
    const parts = parsed.pathname.split("/").filter(Boolean);
    return decodeURIComponent(parts[parts.length - 1] || "");
  } catch {
    const clean = (String(url || "").split("?")[0] || "").split("#")[0] || "";
    const parts = clean.split("/").filter(Boolean);
    try {
      return decodeURIComponent(parts[parts.length - 1] || "");
    } catch {
      return parts[parts.length - 1] || "";
    }
  }
}

function safeDownloadStem(value: any) {
  return String(value || "image").replace(/[^\w.-]+/g, "-") || "image";
}

function clearPreviewGridLayout() {
  if (!els.previewGrid) return;
  els.previewGrid.classList.remove("multi-output");
  [...els.previewGrid.classList].forEach((className: any) => {
    if (className.startsWith("preview-count-") || className.startsWith("preview-orientation-")) {
      els.previewGrid.classList.remove(className);
    }
  });
}

function applyPreviewGridLayout(outputCount: any, itemCount: any) {
  const previousOrientationClass = currentPreviewOrientationClass();
  clearPreviewGridLayout();
  if (!els.previewGrid) return;
  els.previewGrid.classList.toggle("multi-output", itemCount > 1);
  els.previewGrid.classList.add(`preview-count-${outputCount}`);
  els.previewGrid.classList.add(previousOrientationClass || "preview-orientation-unknown");
}

function currentPreviewOrientationClass() {
  if (!els.previewGrid) return "";
  return [...els.previewGrid.classList].find((className: any) => className.startsWith("preview-orientation-")) || "";
}

function syncPreviewImageOrientation() {
  if (!els.previewGrid) return;
  const images = [...els.previewGrid.querySelectorAll("[data-lightbox-url]")];
  const loadedImages = images.filter((image: any) => image.naturalWidth > 0 && image.naturalHeight > 0);
  if (!loadedImages.length) return;
  const portraitCount = loadedImages.filter((image: any) => image.naturalHeight > image.naturalWidth).length;
  const landscapeCount = loadedImages.filter((image: any) => image.naturalWidth > image.naturalHeight).length;
  const orientation = portraitCount > landscapeCount
    ? "portrait"
    : landscapeCount > portraitCount
      ? "landscape"
      : "square";
  els.previewGrid.classList.remove("preview-orientation-unknown", "preview-orientation-portrait", "preview-orientation-landscape", "preview-orientation-square");
  els.previewGrid.classList.add(`preview-orientation-${orientation}`);
}

function promptPopoverData(task: any, index: any) {
  const originalPrompt = task.prompt || task.prompt_for_model || "";
  const submittedPrompt = task.prompt_for_model || originalPrompt || "";
  const optimizedPrompt = task.revised_prompts?.[index] || task.revised_prompt || "";
  return { originalPrompt, submittedPrompt, optimizedPrompt };
}

function runningProgressCard(task: any, visibleOutputCount: any) {
  const elapsed = elapsedTimerSpan("running", taskProgressStartValue(task));
  const generated = taskGeneratedCount(task, visibleOutputCount);
  const total = taskTotalCount(task);
  const size = escapeHtml(task.params?.size || currentSize());
  const retryState = taskRetryStateText(task);
  const retryStateHtml = retryState ? `<p data-preview-retry-state>${escapeHtml(retryState)}</p>` : "";
  const failureNotice = runningFailureNotice(task);
  return `
    <div class="running-progress-card">
      <div class="waiting-spinner" aria-hidden="true"></div>
      <div>
        <strong>${escapeHtml(translate("preview.continueGenerating"))}</strong>
        <p class="elapsed-line">${previewElapsedLineHtml("preview.progressLine", { generated, total }, elapsed)}</p>
        <p class="elapsed-meta">${size}</p>
        ${retryStateHtml}
        ${failureNotice}
      </div>
      <div class="waiting-bar"><span></span></div>
    </div>
  `;
}

function waitingProgressCard(task: any, visibleOutputCount: any) {
  const elapsedFrom = task.queued_at || task.updated_at || task.created_at;
  const elapsed = elapsedTimerSpan("waiting", elapsedFrom);
  const generated = taskGeneratedCount(task, visibleOutputCount);
  const total = taskTotalCount(task);
  const size = escapeHtml(task.params?.size || currentSize());
  const retryReason = task.last_error
    ? `<p>${escapeHtml(formatTranslation("preview.lastError", { error: task.last_error }))}</p>`
    : "";
  const retryState = taskRetryStateText(task);
  const retryStateHtml = retryState ? `<p data-preview-retry-state>${escapeHtml(retryState)}</p>` : "";
  return `
    <div class="running-progress-card waiting-progress-card">
      <div class="waiting-spinner" aria-hidden="true"></div>
      <div>
        <strong>${escapeHtml(translate("preview.waitingContinue"))}</strong>
        <p class="elapsed-line">${previewElapsedLineHtml("preview.progressLine", { generated, total }, elapsed)}</p>
        <p class="elapsed-meta">${size}</p>
        ${retryStateHtml}
        ${retryReason}
      </div>
      <div class="waiting-bar"><span></span></div>
    </div>
  `;
}

function failureSummaryCard(task: any, visibleOutputCount: any) {
  const generated = taskGeneratedCount(task, visibleOutputCount);
  const failed = Number.parseInt(task?.failed_count ?? "", 10);
  const failedCount = Number.isNaN(failed) ? Math.max(0, taskTotalCount(task) - generated) : failed;
  const total = taskTotalCount(task);
  const message = escapeHtml(taskFailureMessage(task) || translate("preview.partialFailed"));
  const retryState = taskRetryStateText(task);
  const retryStateHtml = retryState ? `<p data-preview-retry-state>${escapeHtml(retryState)}</p>` : "";
  return `
    <div class="failure-summary-card">
      <strong>${escapeHtml(task.status === "partial_failed" ? translate("preview.partialFailed") : translate("preview.taskFailed"))}</strong>
      <p>${escapeHtml(formatTranslation("preview.failureLine", { generated, total, failed: failedCount }))}</p>
      ${retryStateHtml}
      <p>${message}</p>
      ${retryFailureSummaryButton(task)}
    </div>
  `;
}

function retryFailureSummaryButton(task: any) {
  const taskId = escapeHtml(task.task_id || "");
  const actions = [];
  if (canRetryFailedTask(task)) {
    actions.push(`<button class="ghost-button text-sm" type="button" data-preview-retry-failed-task-id="${taskId}">${escapeHtml(translate("preview.retryFailed"))}</button>`);
  }
  if (canAcceptTaskSuccesses(task)) {
    actions.push(`<button class="ghost-button text-sm" type="button" data-preview-accept-successes-task-id="${taskId}">${escapeHtml(translate("preview.acceptSuccesses"))}</button>`);
  }
  if (!actions.length) return "";
  return `
    <div class="failure-summary-actions">
      ${actions.join("")}
    </div>
  `;
}

function renderRunningPreview(task: any) {
  clearPreviewGridLayout();
  const elapsed = elapsedTimerSpan("running", taskProgressStartValue(task));
  const size = escapeHtml(task.params?.size || currentSize());
  const modeLabel = task.mode === "edit" ? translate("preview.editMode") : translate("preview.generateMode");
  const retryState = taskRetryStateText(task);
  const retryStateHtml = retryState ? `<p data-preview-retry-state>${escapeHtml(retryState)}</p>` : "";
  const failureNotice = runningFailureNotice(task);
  els.previewGrid.innerHTML = `
    <div class="waiting-preview">
      <div class="waiting-spinner" aria-hidden="true"></div>
      <div>
        <strong>${escapeHtml(formatTranslation("preview.runningTitle", { mode: modeLabel }))}</strong>
        <p class="elapsed-line">${previewElapsedLineHtml("preview.elapsedLine", {}, elapsed)}</p>
        <p class="elapsed-meta">${size}</p>
        ${retryStateHtml}
        ${failureNotice}
      </div>
      <div class="waiting-bar"><span></span></div>
    </div>
  `;
}

function renderWaitingPreview(task: any) {
  clearPreviewGridLayout();
  const submitting = task.status === "submitting";
  const elapsedFrom = task.started_at || task.queued_at || task.created_at;
  const elapsed = elapsedTimerSpan("waiting", elapsedFrom);
  const size = escapeHtml(task.params?.size || currentSize());
  const title = submitting ? translate("preview.submittingTitle") : translate("preview.queuedTitle");
  const detail = submitting
    ? translate("preview.submittingDetail")
    : translate("preview.queuedDetail");
  const retryReason = !submitting && task.last_error
    ? `<p>${escapeHtml(formatTranslation("preview.lastError", { error: task.last_error }))}</p>`
    : "";
  const retryState = taskRetryStateText(task);
  const retryStateHtml = retryState ? `<p data-preview-retry-state>${escapeHtml(retryState)}</p>` : "";
  els.previewGrid.innerHTML = `
    <div class="waiting-preview">
      <div class="waiting-spinner" aria-hidden="true"></div>
      <div>
        <strong>${escapeHtml(title)}</strong>
        <p class="elapsed-line">${previewElapsedLineHtml("preview.elapsedLine", {}, elapsed)}</p>
        <p class="elapsed-meta">${size}</p>
        ${retryStateHtml}
        <p>${escapeHtml(detail)}</p>
        ${retryReason}
      </div>
      <div class="waiting-bar"><span></span></div>
    </div>
  `;
}

export function initTaskPreviewFeature() {
  els.deleteUnselectedOutputsButton?.addEventListener("click", () => {
    openDeleteUnselectedOutputsConfirm(els.deleteUnselectedOutputsButton);
  });
  document.addEventListener(LOCALE_CHANGE_EVENT, () => {
    state.previewRenderKey = null;
    renderPreview(state.previewTask);
  });
  Object.assign(getLegacyBridge().methods, {
    taskRequestPreviewPayload,
    renderPreview,
    previewStructureKey,
    previewPromptKey,
    renderOutputPreview,
    bindPreviewRetryButtons,
    updatePreviewDownloadActions,
    updatePreviewSelectionActions,
    taskSelectedOutputUrls,
    taskSelectedOutputDownloadUrl,
    taskSelectedOutputDownloadName,
    taskOutputZipUrl,
    updateTaskOutputSelection,
    openDeleteUnselectedOutputsConfirm,
    deleteUnselectedOutputs,
    outputDownloadFilename,
    outputFilenameFromUrl,
    retryFailureSummaryButton,
  });
}
