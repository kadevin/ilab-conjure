export interface StateSyncVersion {
  instance: string;
  revision: number;
}

interface SyncState {
  instance: string;
  retired: Set<string>;
  queue: number;
  tasks: number;
  lastChange: number;
  changes: Map<string, { revision: number; task: any }>;
}

const syncStates = new WeakMap<object, SyncState>();

function versionState(state: object, version?: StateSyncVersion): SyncState | null | false {
  // Older servers and local-only updates retain their existing behavior.
  if (!version || !version.instance || !Number.isSafeInteger(version.revision) || version.revision < 1) return null;
  let current = syncStates.get(state);
  if (current?.retired.has(version.instance)) return false;
  if (!current || current.instance !== version.instance) {
    const retired = current?.retired || new Set<string>();
    if (current) retired.add(current.instance);
    current = { instance: version.instance, retired, queue: 0, tasks: 0, lastChange: 0, changes: new Map() };
    syncStates.set(state, current);
  }
  return current;
}

export function acceptQueueSnapshot(state: object, version?: StateSyncVersion): boolean {
  const current = versionState(state, version);
  if (current === false) return false;
  if (!current || !version) return true;
  if (version.revision < Math.max(current.queue, current.tasks, current.lastChange)) return false;
  current.queue = version.revision;
  return true;
}

export function queueSnapshotIsNewer(state: object, version?: StateSyncVersion): boolean {
  const current = versionState(state, version);
  return current === null || Boolean(current && version && current.queue > version.revision);
}

export function reconcileTaskSnapshot(state: object, tasks: any[], version?: StateSyncVersion): any[] | null {
  const current = versionState(state, version);
  if (current === false) return null;
  if (!current || !version) return tasks;
  if (version.revision < current.tasks) return null;
  current.tasks = version.revision;
  const remainingChanges = new Map(current.changes);
  const reconciled = tasks.map((task) => {
    const id = String(task.task_id);
    const change = remainingChanges.get(id);
    remainingChanges.delete(id);
    return change && change.revision > version.revision ? change.task : task;
  });
  for (const change of remainingChanges.values()) {
    if (change.revision > version.revision) reconciled.push(change.task);
  }
  for (const [id, change] of current.changes) {
    if (change.revision <= version.revision) current.changes.delete(id);
  }
  return reconciled;
}

export function acceptTaskUpdate(state: object, task: any, version?: StateSyncVersion): boolean {
  const current = versionState(state, version);
  if (current === false || !task?.task_id) return false;
  if (!current || !version) return true;
  const id = String(task.task_id);
  if (version.revision < current.tasks || version.revision < (current.changes.get(id)?.revision || 0)) return false;
  current.lastChange = Math.max(current.lastChange, version.revision);
  current.changes.set(id, { revision: version.revision, task });
  return true;
}
