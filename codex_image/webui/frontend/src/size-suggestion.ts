/** Nearest legal grid size, prioritizing the requested aspect ratio. No input mutation. */
export function suggestLegalSize(width: number, height: number): { width: number; height: number } {
  const w = Number.isFinite(width) && width > 0 ? width : 1024;
  const h = Number.isFinite(height) && height > 0 ? height : 1024;
  const ratio = Math.min(3, Math.max(1 / 3, w / h));
  const pixels = Math.min(8294400, Math.max(655360, w * h));
  let best = { width: 1024, height: 1024, score: Infinity };
  for (let x = 16; x <= 3840; x += 16) {
    const min = Math.ceil(Math.max(16, x / 3, 655360 / x) / 16) * 16;
    const max = Math.floor(Math.min(3840, x * 3, 8294400 / x) / 16) * 16;
    for (let y = min; y <= max; y += 16) {
      const score = 8 * Math.abs(Math.log((x / y) / ratio)) + Math.abs(Math.log((x * y) / pixels));
      if (score < best.score) best = { width: x, height: y, score };
    }
  }
  return { width: best.width, height: best.height };
}
