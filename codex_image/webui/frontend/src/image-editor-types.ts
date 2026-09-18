export interface ImageEditorLayer {
  id: string;
  source: any;
  sourceIndex: number | null;
  name: string;
  canvas: HTMLCanvasElement;
  node: any;
  edited: boolean;
}

export interface ImageEditorLayerSnapshot {
  id: string;
  sourceIndex: number | null;
  name: string;
  canvas: HTMLCanvasElement;
  attrs: Record<string, any>;
  edited: boolean;
}

export interface ImageEditorSnapshot {
  layers: ImageEditorLayerSnapshot[];
  workCanvas: HTMLCanvasElement;
  brushBoundaryCanvas: HTMLCanvasElement | null;
  brushOverlayCanvas: HTMLCanvasElement | null;
  canvasScope: "base" | "fit";
  crop: any;
  selectedLayerId: string | null;
  hasInstructionMarks: boolean;
}

export interface ImageEditorState {
  sessionId: number;
  sourceIndex: number | null;
  source: any;
  originalFile: File | null;
  image: HTMLImageElement | null;
  baseCanvas: HTMLCanvasElement | null;
  workCanvas: HTMLCanvasElement | null;
  brushBoundaryCanvas: HTMLCanvasElement | null;
  brushOverlayCanvas: HTMLCanvasElement | null;
  konvaStage: any;
  konvaLayer: any;
  konvaTransformer: any;
  markNode: any;
  layers: ImageEditorLayer[];
  selectedLayerId: string | null;
  displayScale: number;
  tool: string;
  color: string;
  strokeWidth: number;
  crop: any;
  canvasScope: "base" | "fit";
  hasInstructionMarks: boolean;
}
