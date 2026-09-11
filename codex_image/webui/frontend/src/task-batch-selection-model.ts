export function waitingBatchTaskIds(queue: any): string[] {
  const taskIds = (queue?.waiting || [])
    .map((task: any) => String(task?.task_id || ""))
    .filter(Boolean);
  return Array.from(new Set(taskIds));
}

export function isBatchScopeSelected(selectedIds: string[], scopeIds: string[]): boolean {
  const selected = new Set(selectedIds);
  return scopeIds.length > 0 && scopeIds.every((id) => selected.has(id));
}

export function toggleBatchScopeIds(selectedIds: string[], scopeIds: string[]): string[] {
  const scope = new Set(scopeIds);
  return isBatchScopeSelected(selectedIds, scopeIds)
    ? selectedIds.filter((id) => !scope.has(id))
    : Array.from(new Set([...selectedIds, ...scopeIds]));
}
