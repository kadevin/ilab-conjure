import { formatTranslation, translate } from "./i18n";

type GroundingSource = {
  page_uri?: string;
  image_uri?: string;
  title?: string;
};

type GroundingEntry = {
  rendered_content?: string;
  sources: GroundingSource[];
};

function record(value: unknown): Record<string, any> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, any>
    : null;
}

function groundingFromToolUsage(value: unknown): unknown[] {
  const usage = record(value);
  if (!usage) return [];
  const providerMetadata = record(usage.provider_metadata);
  const grounding = providerMetadata?.grounding ?? usage.grounding;
  return Array.isArray(grounding) ? grounding : [];
}

function toolUsages(task: any): unknown[] {
  const values: unknown[] = [];
  if (task?.tool_usage) values.push(task.tool_usage);
  if (Array.isArray(task?.tool_usages)) values.push(...task.tool_usages);
  if (Array.isArray(task?.outputs)) {
    task.outputs.forEach((output: any) => {
      if (output?.tool_usage) values.push(output.tool_usage);
    });
  }
  return values;
}

export function taskGroundingEntries(task: any): GroundingEntry[] {
  const entries: GroundingEntry[] = [];
  const seen = new Set<string>();
  toolUsages(task).forEach((usage) => {
    groundingFromToolUsage(usage).forEach((rawEntry) => {
      const sourceEntry = record(rawEntry);
      if (!sourceEntry) return;
      const sources = Array.isArray(sourceEntry.sources)
        ? sourceEntry.sources.map(record).filter(Boolean).map((source) => {
            const normalized: GroundingSource = {};
            if (typeof source?.page_uri === "string") normalized.page_uri = source.page_uri;
            if (typeof source?.image_uri === "string") normalized.image_uri = source.image_uri;
            if (typeof source?.title === "string") normalized.title = source.title;
            return normalized;
          })
        : [];
      const entry: GroundingEntry = { sources };
      if (typeof sourceEntry.rendered_content === "string") {
        entry.rendered_content = sourceEntry.rendered_content;
      }
      const key = JSON.stringify(entry);
      if (seen.has(key)) return;
      seen.add(key);
      entries.push(entry);
    });
  });
  return entries;
}

function safeHttpsUrl(value: unknown): string | null {
  if (typeof value !== "string" || !value.trim()) return null;
  try {
    const url = new URL(value);
    if (url.protocol !== "https:") return null;
    return url.href;
  } catch {
    return null;
  }
}

function usableSources(entries: GroundingEntry[]): GroundingSource[] {
  const sources: GroundingSource[] = [];
  const seen = new Set<string>();
  entries.forEach((entry) => {
    entry.sources.forEach((source) => {
      const pageUri = safeHttpsUrl(source.page_uri);
      if (!pageUri || seen.has(pageUri)) return;
      seen.add(pageUri);
      const normalized: GroundingSource = { page_uri: pageUri };
      const imageUri = safeHttpsUrl(source.image_uri);
      if (imageUri) normalized.image_uri = imageUri;
      if (source.title) normalized.title = source.title;
      sources.push(normalized);
    });
  });
  return sources;
}

export function groundingSourceCount(task: any): number {
  return usableSources(taskGroundingEntries(task)).length;
}

export function groundingAttributionKey(task: any): string {
  return JSON.stringify(taskGroundingEntries(task));
}

function renderedContentFrame(renderedContent: string): HTMLIFrameElement {
  const frame = document.createElement("iframe");
  frame.className = "grounding-search-entry-frame";
  frame.title = translate("grounding.searchSuggestions");
  frame.setAttribute("sandbox", "allow-popups allow-popups-to-escape-sandbox");
  frame.referrerPolicy = "no-referrer";
  frame.loading = "lazy";
  frame.srcdoc = `<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'none'; connect-src 'none'; frame-src 'none'; form-action 'none'; img-src https: data:; style-src 'unsafe-inline'; font-src https: data:; base-uri 'none'"><base target="_blank"><style>html{color-scheme:light dark}body{margin:0;padding:4px;font:12px/1.35 system-ui,sans-serif;overflow:auto}a{color:inherit}</style></head><body>${renderedContent}</body></html>`;
  return frame;
}

export function createGroundingAttribution(task: any): HTMLElement | null {
  const entries = taskGroundingEntries(task);
  const renderedContent = entries
    .map((entry) => entry.rendered_content?.trim() || "")
    .find(Boolean) || "";
  const sources = usableSources(entries);
  if (!renderedContent && !sources.length) return null;

  const section = document.createElement("section");
  section.className = "grounding-attribution";
  section.setAttribute("aria-label", translate("grounding.title"));

  const header = document.createElement("div");
  header.className = "grounding-attribution-header";
  const title = document.createElement("strong");
  title.textContent = translate("grounding.title");
  const count = document.createElement("span");
  count.textContent = formatTranslation("grounding.sourceCount", { count: sources.length });
  header.append(title, count);
  section.append(header);

  if (renderedContent) {
    section.append(renderedContentFrame(renderedContent));
  }
  if (sources.length) {
    const sourceList = document.createElement("div");
    sourceList.className = "grounding-source-list";
    sources.forEach((source, index) => {
      const link = document.createElement("a");
      link.className = "grounding-source-link";
      link.href = source.page_uri || "";
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.referrerPolicy = "no-referrer";
      link.textContent = source.title?.trim()
        || formatTranslation("grounding.source", { index: index + 1 });
      sourceList.append(link);
    });
    section.append(sourceList);
  }
  return section;
}

export function syncGroundingAttribution(
  anchor: HTMLElement | null,
  task: any,
  location: string,
): void {
  const parent = anchor?.parentElement;
  if (!anchor || !parent) return;
  const existing = parent.querySelector<HTMLElement>(
    `[data-grounding-location="${location}"]`,
  );
  const next = createGroundingAttribution(task);
  if (!next) {
    existing?.remove();
    return;
  }
  next.dataset.groundingLocation = location;
  if (existing) {
    existing.replaceWith(next);
  } else {
    anchor.insertAdjacentElement("afterend", next);
  }
}
