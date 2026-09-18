export type QueueTaskIdSections = { running: Map<string, number>; waiting: Map<string, number> };

export type TaskListScrollAnchor = {
  scroller: HTMLElement;
  root: HTMLElement;
  scrollTop: number;
  taskId?: string;
  offsetTop?: number;
  retryMissingTask?: boolean;
};
