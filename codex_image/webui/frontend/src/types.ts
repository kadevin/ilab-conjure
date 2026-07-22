export type TaskStatus = "submitting" | "queued" | "running" | "completed" | "failed" | "partial_failed" | "cancelled";
export type TaskMode = "generate" | "edit";
export type OutputStatus = "running" | "completed" | "failed";
export type AuthSource = "codex" | "api";
export type ApiMode = "images" | "responses";
export type ModelFamilyId = string;
export type GenerationOperation = "generate" | "edit";

export interface ProviderModelBindingSettings {
  id: string;
  canonical_model_id: string;
  remote_model_id: string;
  protocol_profile: string;
  parameter_codec: string;
  operations: GenerationOperation[];
  append_aspect_ratio_prompt?: boolean;
}

export interface ProviderConnectionSettings {
  id: string;
  name: string;
  icon_emoji?: string;
  base_url: string;
  concurrency: number;
  bindings: ProviderModelBindingSettings[];
  api_key?: string;
  api_key_set?: boolean;
  api_key_masked?: string;
  api_key_source_provider_id?: string;
  image_model?: string;
  api_mode?: ApiMode;
  images_concurrency?: number;
}

export interface ProviderSettingsV2 {
  schema_version: 2;
  codex_mode: ApiMode;
  active_provider_id: string;
  default_provider_by_model: Record<string, string>;
  providers: ProviderConnectionSettings[];
}

export interface CatalogParameterVisibility {
  parameter_id: string;
  operator: "equals" | "not_equals" | "in";
  value: unknown;
}

export interface CatalogObjectChoiceRow {
  key: string;
  label_key: string;
  default: string;
  allowed_values: string[];
  label_keys: string[];
}

export interface CatalogObjectPreset {
  id: string;
  label_key: string;
  value: Record<string, unknown>;
  matches_empty: boolean;
}

export interface CatalogParameterDefinition {
  id: string;
  label_key: string;
  group: "model" | "canvas" | "generation" | "advanced";
  control: "select" | "segmented" | "boolean_segmented" | "toggle" | "slider" | "number" | "text" | "notice" | "choice_grid" | "object_presets" | "aspect_ratio_grid";
  value_type: "string" | "integer" | "boolean" | "object";
  default: unknown;
  allowed_values: unknown[];
  scope: "application" | "model";
  minimum: number | null;
  maximum: number | null;
  step: number | null;
  visible_when: CatalogParameterVisibility[];
  operations: GenerationOperation[];
  full_width: boolean;
  object_choices?: CatalogObjectChoiceRow[];
  object_presets?: CatalogObjectPreset[];
}

export interface CatalogModel {
  id: string;
  family_id: ModelFamilyId;
  display_name: string;
  official_model_id: string;
  version: number;
  operations: GenerationOperation[];
  parameters: CatalogParameterDefinition[];
  input_constraints: {
    max_images: number;
    supports_mask: boolean;
    supports_reference_files: boolean;
  };
  expand_advanced_parameters?: boolean;
}

export interface CatalogFamily {
  id: ModelFamilyId;
  display_name: string;
  short_name: string;
  label_key: string;
}

export interface CatalogProviderBinding {
  id: string;
  canonical_model_id: string;
  remote_model_id: string;
  protocol_profile: string;
  parameter_codec: string;
  operations: GenerationOperation[];
  append_aspect_ratio_prompt?: boolean;
  available?: boolean;
  display_name?: string;
}

export interface CatalogProvider {
  id: string;
  name: string;
  builtin: boolean;
  available: boolean;
  bindings: CatalogProviderBinding[];
  icon_emoji?: string;
}

export interface GenerationCatalog {
  schema_version: 1;
  manifest_version: number;
  families: CatalogFamily[];
  models: CatalogModel[];
  providers: CatalogProvider[];
  default_provider_by_model: Record<string, string>;
  codex: { available: boolean; mode: ApiMode };
}

export interface GenerationSnapshotView {
  schema_version: number;
  family_id: ModelFamilyId;
  canonical_model_id: string;
  model_manifest_version: number;
  provider_id: string;
  provider_name: string;
  binding_id: string;
  remote_model_id: string;
  protocol_profile: string;
  parameter_codec: string;
  requested_parameters: Record<string, unknown>;
  mapped_request: Record<string, unknown>;
  legacy: boolean;
}

export interface ParameterMigrationReport {
  values: Record<string, unknown>;
  defaulted: Array<{ id: string; previous: unknown; replacement: unknown }>;
  dropped: Array<{ id: string; previous: unknown }>;
}

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
  tool_usage?: Record<string, unknown>;
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

export interface ReferenceFileRef {
  kind?: "upload" | "asset";
  id?: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  family: "pdf" | "spreadsheet" | "document" | "text";
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
  reference_files?: ReferenceFileRef[];
  reference_file_count?: number;
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
  generation_snapshot?: Partial<GenerationSnapshotView> & Record<string, unknown>;
  tool_usage?: Record<string, unknown>;
  tool_usages?: Array<Record<string, unknown>>;
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
