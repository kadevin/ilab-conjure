const MAX_REFERENCE_BYTES = 50 * 1024 * 1024;
const MAX_REFERENCE_EDGE = 16_384;
const MAX_REFERENCE_PIXELS = 64 * 1024 * 1024;

/** Rasterize a served SVG for reference input, leaving the original output intact. */
export async function svgReferenceFile(blob: Blob, filename: string): Promise<File> {
  if (!blob.size || blob.size > MAX_REFERENCE_BYTES) throw new Error("Invalid SVG size");
  const source = await blob.text();
  if (/<!\s*(?:DOCTYPE|ENTITY)/i.test(source)) throw new Error("Unsupported SVG declaration");
  const svgDocument = new DOMParser().parseFromString(source, "image/svg+xml");
  const root = svgDocument.documentElement;
  if (svgDocument.querySelector("parsererror") || root.localName !== "svg" || root.namespaceURI !== "http://www.w3.org/2000/svg") {
    throw new Error("Invalid SVG document");
  }
  const viewBox = (root.getAttribute("viewBox") || "").trim().split(/[\s,]+/);
  const dimension = (name: string, index: number) => {
    const value = root.getAttribute(name) || "";
    const number = /^[\d.]+(?:px)?$/.test(value) ? Number(value.replace(/px$/, ""))
      : viewBox.length === 4 ? Number(viewBox[index]) : NaN;
    if (!Number.isFinite(number) || number <= 0 || number > MAX_REFERENCE_EDGE) throw new Error("Invalid SVG dimensions");
    return Math.max(1, Math.round(number));
  };
  const width = dimension("width", 2), height = dimension("height", 3);
  if (width * height > MAX_REFERENCE_PIXELS) throw new Error("SVG exceeds reference pixel limit");
  // Explicit dimensions avoid the browser's 300×150 fallback for viewBox-only SVGs.
  root.setAttribute("width", String(width));
  root.setAttribute("height", String(height));
  const imageUrl = URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(root)], { type: "image/svg+xml" }));
  const canvas = document.createElement("canvas");
  try {
    const image = new Image();
    image.decoding = "async";
    image.src = imageUrl;
    await image.decode();
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Reference canvas unavailable");
    context.drawImage(image, 0, 0, width, height);
    const png = await new Promise<Blob>((resolve, reject) => canvas.toBlob(
      value => value ? resolve(value) : reject(new Error("Reference conversion failed")), "image/png",
    ));
    if (png.size > MAX_REFERENCE_BYTES) throw new Error("PNG exceeds reference byte limit");
    const name = filename.replace(/[\\/:*?"<>|]+/g, "-").trim().replace(/\.(?:svg|png|jpe?g|webp|gif)$/i, "") || "reference";
    return new File([png], `${name}.png`, { type: "image/png" });
  } finally {
    URL.revokeObjectURL(imageUrl);
    canvas.width = canvas.height = 0;
  }
}
