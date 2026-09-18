import type { HistoryOrganization, HistoryTag } from "./history-organization";
import { HISTORY_FILTER_QUERY_KEYS } from "./history-scroll-memory";

export type HistoryFacet = { value: string; count: number };

export type HistoryMonth = { month: string; count: number };

export type HistorySummary = {
  total: number;
  archived_total: number;
  favorite_total: number;
  untagged_total: number;
  tags: HistoryTag[];
  months: HistoryMonth[];
  modes: HistoryFacet[];
  prompt_modes: HistoryFacet[];
  qualities: HistoryFacet[];
  ratios: HistoryFacet[];
  orientations: HistoryFacet[];
  backends: HistoryFacet[];
  providers: HistoryFacet[];
};

export type HistoryTask = HistoryOrganization & {
  task_id: string;
  created_at: string;
  updated_at: string;
  completed_at: string;
  status: string;
  mode: string;
  size: string;
  quality: string;
  prompt_mode: string;
  ratio: string;
  orientation: string;
  backend: string;
  provider: string;
  archived: boolean;
  generated_count: number;
  failed_count: number;
  total_count: number;
  thumbnail_url: string;
  prompt_preview: string;
};

export type HistoryFilterKey = (typeof HISTORY_FILTER_QUERY_KEYS)[number];

export type HistoryViewMode = "grid" | "list";

export type HistoryRenderPosition = "replace" | "append" | "prepend";

export type HistoryTaskPage = { tasks: HistoryTask[]; next_cursor: string | null; previous_cursor?: string | null; anchor_found?: boolean; detail?: string };

export type HistoryContextMenuMode = "single" | "multi";

export type HistoryResizerSide = "left" | "right";

export type HistoryOrganizationChange = {
  favorite?: boolean | null;
  add_tag_ids?: string[];
  remove_tag_ids?: string[];
};
