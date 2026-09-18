(() => {
  // codex_image/webui/frontend/src/image-editor-fill.ts
  function enclosedFillPatch(boundary, width, height, x, y, color) {
    if (width < 1 || height < 1 || boundary.length !== width * height * 4) return null;
    x = Math.max(0, Math.min(width - 1, Math.floor(x)));
    y = Math.max(0, Math.min(height - 1, Math.floor(y)));
    const visited = new Uint8Array(width * height);
    const open = (index) => !visited[index] && boundary[index * 4 + 3] === 0;
    const seeds = [y * width + x];
    const spans = [];
    let minX = width, maxX = 0, minY = height, maxY = 0;
    while (seeds.length) {
      const seed = seeds.pop();
      if (!open(seed)) continue;
      const row = Math.floor(seed / width), column = seed % width;
      let left = column, right = column;
      while (left > 0 && open(row * width + left - 1)) left--;
      while (right < width - 1 && open(row * width + right + 1)) right++;
      if (left === 0 || right === width - 1 || row === 0 || row === height - 1) return null;
      visited.fill(1, row * width + left, row * width + right + 1);
      spans.push(row, left, right);
      minX = Math.min(minX, left);
      maxX = Math.max(maxX, right);
      minY = Math.min(minY, row);
      maxY = Math.max(maxY, row);
      for (const adjacent of [row - 1, row + 1]) {
        let inRun = false;
        for (let col = left; col <= right; col++) {
          const index = adjacent * width + col;
          const available = open(index);
          if (available && !inRun) seeds.push(index);
          inRun = available;
        }
      }
    }
    if (!spans.length) return null;
    const patchWidth = maxX - minX + 1, patchHeight = maxY - minY + 1;
    const pixels = new Uint8ClampedArray(patchWidth * patchHeight * 4);
    for (let i = 0; i < spans.length; i += 3) {
      const row = spans[i], left = spans[i + 1], right = spans[i + 2];
      for (let col = left; col <= right; col++) {
        const offset = ((row - minY) * patchWidth + col - minX) * 4;
        pixels[offset] = color[0];
        pixels[offset + 1] = color[1];
        pixels[offset + 2] = color[2];
        pixels[offset + 3] = 255;
      }
    }
    return { left: minX, top: minY, width: patchWidth, height: patchHeight, pixels };
  }

  // codex_image/webui/frontend/src/image-editor-fill-worker.ts
  self.onmessage = (event) => {
    const { boundary, width, height, point, color } = event.data;
    const patch = enclosedFillPatch(boundary, width, height, point.x, point.y, color);
    self.postMessage(patch, patch ? [patch.pixels.buffer] : []);
  };
})();
//# sourceMappingURL=image-editor-fill-worker.js.map
