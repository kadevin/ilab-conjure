import { translate } from "./i18n";
import { imageEditorLayerThumbnailUrl } from "./image-editor-canvas";
import type { ImageEditorLayer } from "./image-editor-types";

export interface ImageEditorPanelDependencies {
  getSources: () => any[];
  getEditorSnapshot: () => { sourceIndex: number | null; layers: readonly ImageEditorLayer[]; selectedLayerId: string | null };
  getPanelElements: () => { imageEditorInsertList: HTMLElement | null; imageEditorLayerList: HTMLElement | null };
  isEditableImageSource: (source: any) => boolean;
  sourcePreviewUrlForEditor: (source: any) => string;
  sourceName: (source: any) => string;
  imageEditorSourceName: (source: any) => string;
  insertImageEditorLayerFromSource: (source: any) => void;
  selectImageEditorLayer: (id: string, options: { updateTool: boolean }) => void;
  updateImageEditorControls: () => void;
}

export function createImageEditorPanel(dependencies: ImageEditorPanelDependencies) {
  const { getSources, getEditorSnapshot, getPanelElements, isEditableImageSource, sourcePreviewUrlForEditor, sourceName, imageEditorSourceName, insertImageEditorLayerFromSource, selectImageEditorLayer, updateImageEditorControls } = dependencies;

  function renderImageEditorInsertList() {
    const list = getPanelElements().imageEditorInsertList;
    if (!list) return;
    list.textContent = "";
    const sources = getSources()
      .map((source: any, index: number) => ({ source, index }))
      .filter((item: any) => item.index !== getEditorSnapshot().sourceIndex && isEditableImageSource(item.source));
    if (!sources.length) {
      const empty = document.createElement("div");
      empty.className = "image-editor-insert-empty";
      empty.textContent = translate("imageEditor.emptyInsertList");
      list.append(empty);
      return;
    }
    sources.forEach(({ source, index }: any) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "image-editor-insert-item";
      row.dataset.sourceIndex = String(index);
      const thumbUrl = sourcePreviewUrlForEditor(source);
      if (thumbUrl) {
        const img = document.createElement("img");
        img.src = thumbUrl;
        img.alt = "";
        img.loading = "lazy";
        row.append(img);
      } else {
        const placeholder = document.createElement("span");
        placeholder.className = "image-editor-layer-thumb";
        placeholder.textContent = "IMG";
        row.append(placeholder);
      }
      const text = document.createElement("span");
      text.className = "image-editor-insert-name";
      text.textContent = sourceName(source) || imageEditorSourceName(source);
      row.append(text);
      row.addEventListener("click", () => insertImageEditorLayerFromSource(source));
      list.append(row);
    });
  }

  function renderImageEditorLayerList() {
    const list = getPanelElements().imageEditorLayerList;
    if (!list) return;
    list.textContent = "";
    [...getEditorSnapshot().layers].reverse().forEach((layer) => {
      const row = document.createElement("button");
      row.type = "button";
      row.className = "image-editor-layer-item";
      row.classList.toggle("active", layer.id === getEditorSnapshot().selectedLayerId);
      row.dataset.layerId = layer.id;
      const thumb = document.createElement("span");
      thumb.className = "image-editor-layer-thumb";
      const thumbnailUrl = imageEditorLayerThumbnailUrl(layer);
      if (thumbnailUrl) {
        const thumbnail = document.createElement("img");
        thumbnail.src = thumbnailUrl;
        thumbnail.alt = "";
        thumbnail.decoding = "async";
        thumbnail.draggable = false;
        thumb.append(thumbnail);
      } else {
        thumb.textContent = String(getEditorSnapshot().layers.indexOf(layer) + 1);
      }
      row.append(thumb);
      const content = document.createElement("span");
      const name = document.createElement("span");
      name.className = "image-editor-layer-name";
      name.textContent = layer.name || translate("imageEditor.baseLayer");
      const meta = document.createElement("span");
      meta.className = "image-editor-layer-meta";
      const width = Math.max(1, Math.round(layer.node.width() * layer.node.scaleX()));
      const height = Math.max(1, Math.round(layer.node.height() * layer.node.scaleY()));
      meta.textContent = `${width}×${height}`;
      content.append(name, meta);
      row.append(content);
      row.addEventListener("click", () => selectImageEditorLayer(layer.id, { updateTool: true }));
      list.append(row);
    });
    updateImageEditorControls();
  }

  return { renderImageEditorInsertList, renderImageEditorLayerList };
}
