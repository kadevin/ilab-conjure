export type TaskStatus = "submitting" | "queued" | "running" | "completed" | "failed" | "partial_failed" | "cancelled";
export type TaskMode = "generate" | "edit";
export type OutputStatus = "running" | "completed" | "failed";
export type AuthSource = "codex" | "api";
export type ApiMode = "images" | "responses";

export interface TaskOutputRecord {
  index?: number;
  status?: OutputStatus;
  file?: string;
  url?: string;
  thumbnail_file?: string;
  thumbnail_url?: string;
  size?: string;
  format?: string;
  quality?: string;
  background?: string;
  revised_prompt?: string;
  usage?: Record<string, unknown>;
  error?: string;
  attempts?: number;
}

export interface TaskNotification {
  id: string;
  task_id: string;
  status: Extract<TaskStatus, "completed" | "failed" | "partial_failed">;
  title: string;
  message: string;
  success_count?: number;
  failed_count?: number;
  prompt_snippet?: string;
  error_message?: string;
  created_at: string;
  thumbnail_url?: string;
  unread: boolean;
}

export interface TaskNotificationSettings {
  inApp: boolean;
  system: boolean;
}

export interface GalleryRef {
  id: string;
  name: string;
  category?: string;
  category_name?: string;
  category_prompt_role?: string;
  prompt_note?: string;
  image_url?: string;
  missing?: boolean;
}

export interface ReferenceAsset {
  id: string;
  name?: string;
  filename?: string;
  image_url?: string;
  mime_type?: string;
  missing?: boolean;
}

export interface TaskParams {
  main_model?: string;
  model?: string;
  size?: string;
  quality?: string;
  background?: string | null;
  output_format?: string;
  output_compression?: number | null;
  n?: number;
  web_search?: boolean;
  prompt_fidelity?: "strict" | "original" | "off";
  codex_mode?: ApiMode;
  api_mode?: ApiMode;
  api_provider_id?: string;
  api_provider_name?: string;
  api_images_concurrency?: number;
}

export interface WebUITask {
  [key: string]: any;
  task_id: string;
  created_at?: string;
  updated_at?: string;
  viewed_at?: string;
  queued_at?: string;
  started_at?: string;
  attempt_started_at?: string;
  completed_at?: string;
  mode?: TaskMode;
  status?: TaskStatus;
  prompt?: string;
  prompt_for_model?: string;
  params?: TaskParams;
  input_urls?: string[];
  input_files?: string[];
  output_url?: string;
  output_urls?: string[];
  outputs?: TaskOutputRecord[];
  generated_count?: number;
  failed_count?: number;
  total_count?: number;
  gallery_refs?: GalleryRef[];
  reference_assets?: ReferenceAsset[];
  input_sources?: Array<Record<string, unknown>>;
  last_error?: string;
  error?: string;
  channel_id?: string;
  account_id?: string | null;
  requested_backend?: string;
  backend?: string;
  local_pending?: boolean;
  preview_url?: string;
  output_size?: string;
  queue_position?: number;
  attempts?: number;
  max_attempts?: number;
  retry_requested_at?: string;
  retrying_failed_slots?: unknown[];
  request?: Record<string, any>;
}

export interface QueueSummary {
  waiting_count: number;
  running_count: number;
  channel_count: number;
  usable_channel_count?: number;
}

export interface QueueState {
  waiting: WebUITask[];
  running: WebUITask[];
  summary: QueueSummary;
}

export interface RealtimePayload {
  type?: "snapshot" | "queue" | "task";
  tasks?: WebUITask[];
  queue?: QueueState;
  task?: WebUITask;
  gallery?: unknown[];
  auth?: Record<string, unknown>;
}
