# Global Image Request Controls Design

Date: 2026-08-07
Status: Approved

## Problem

iLab CONJURE currently applies a fixed 600-second timeout to image-generation requests and allows at most three total attempts for retryable transient failures. Some OpenAI-compatible relay providers need more than ten minutes because of upstream caching, queuing, or network conditions. Users currently cannot adjust either behavior from the WebUI.

The timeout exists at both the WebUI task wrapper and the HTTP transport. Changing only one layer would still terminate a slow request at the unchanged layer. The existing retry constant also represents total attempts, while users naturally understand a setting as the number of retries after the first failure.

## Goals

- Add global image-request timeout and transient retry controls to `系统设置 → 网络`.
- Preserve the current defaults: 10 minutes and 2 retries after the first failed attempt.
- Apply one frozen policy consistently to both the HTTP transport and WebUI request wrapper.
- Apply the policy to all providers and both generation and editing operations.
- Persist the settings locally and apply them without restarting the WebUI.
- Keep current queue-level channel failover behavior unchanged.
- Preserve the existing timeout environment variable as a compatibility fallback until a UI value is explicitly saved.

## Non-goals

- Per-provider, per-model, per-task, or per-output timeout and retry settings.
- Unlimited timeouts or retries.
- Making connection detection inherit generation timeout or retry behavior.
- Changing which errors are classified as transient and retryable.
- Changing queue-level retries, manual failed-slot retry, provider concurrency, or channel failover.

## User Experience

The existing Network tab gains a compact two-column request-policy row below the optional custom proxy field and above the current-route summary. It reuses existing `.field` and `.control` patterns rather than adding another card.

The fields are:

1. `单次生图超时`
   - Integer input.
   - Range: 1–30.
   - Unit: minutes.
   - Default: 10.
2. `失败后重试`
   - Integer input.
   - Range: 0–5.
   - Unit: times.
   - Default: 2.

The fields share this helper text:

> 仅影响之后开始的生图请求；每次自动重试都会重新计算超时时间。

The row collapses to one column on narrow viewports. Labels, units, helper text, range errors, and save feedback are translated for every supported locale. Inputs retain visible focus, keyboard operation, associated labels, and error text that does not rely on color alone.

The two values are saved with the existing network-egress form through the existing `保存并应用` action. Saving requires no restart. The existing `检测连接` action retains a separate short probe timeout and does not use either generation policy value.

## Configuration Contract

`NetworkEgressSettings` adds two normalized persisted fields:

- `image_request_timeout_seconds`: integer, inclusive range 60–1800.
- `image_request_retry_count`: integer, inclusive range 0–5.

The frontend converts timeout minutes to seconds before saving and converts stored seconds to minutes when rendering. The backend remains authoritative and rejects booleans, fractions, empty values, non-numeric values, and out-of-range values with a field-specific `400` response. These ranges govern values saved through the WebUI or settings API.

For an existing settings file without these fields:

- A valid positive `CODEX_IMAGE_REQUEST_TIMEOUT_SECONDS` value remains the effective compatibility fallback for timeout, retaining the environment variable's existing positive-number behavior even when it is not representable by the new integer-minute form.
- Otherwise timeout defaults to 600 seconds.
- Retry count defaults to 2.

The settings response distinguishes the editable persisted/default value from the resolved effective timeout and reports whether the effective source is `settings`, `environment`, or `default`. If a legacy environment fallback is outside the form's supported integer-minute range, the form keeps a valid 10-minute editable value and shows a neutral compatibility notice containing the effective environment value; saving replaces that fallback with the selected WebUI value.

Once a valid timeout is explicitly saved by the WebUI, the stored value is authoritative for WebUI execution. Core and CLI transport behavior outside this WebUI settings path continues to use its existing environment-variable contract.

An unreadable settings file or non-object payload falls back safely to the complete defaults. Invalid persisted request-policy fields fall back individually while preserving otherwise valid network mode and proxy settings. Invalid incoming API values are rejected rather than silently normalized. Writes continue to use the existing atomic replacement behavior and local-only file permissions contract.

## Runtime Data Flow

At the start of each queue execution attempt:

1. `NetworkEgressManager.snapshot()` reads and normalizes network mode, proxy, timeout, and retry count.
2. The immutable snapshot carries both request-policy values.
3. `NetworkEgressManager.transport()` constructs the HTTP transport with the frozen timeout.
4. `QueueExecutionContract` carries the same timeout and retry count alongside the client and backend.
5. `_execute_stored_task()` passes both values into each image-client call.
6. `_call_image_client()` performs one initial attempt plus at most `image_request_retry_count` retries.
7. Task metadata records the effective timeout and retry count under the non-sensitive network execution snapshot for diagnostics.

This freezes the policy for a running attempt. Saving new values affects only later task attempts, including later automatic or manual task retries. It does not interrupt or mutate an in-flight request.

The timeout applies to each upstream image request attempt, not to the total duration of a multi-image task. Each automatic retry receives a new timeout window. Existing retry backoff remains unchanged. Queue-level failover may still run a later task attempt under its existing rules.

## Retry and Error Semantics

The UI setting describes retries after the initial attempt:

- `0` means one total request attempt.
- `2` means up to three total request attempts and preserves current behavior.
- `5` means up to six total request attempts.

Only errors already recognized by `_is_retryable_transient_image_error()` consume automatic retries. Authentication failures, invalid parameters, usage limits, explicit provider rejections, cancellation, and other non-retryable errors continue to fail immediately.

Output records continue to report the actual number of attempts. Timeout failures include the effective timeout limit. Invalid UI values block saving and produce a specific visible error; invalid API payloads receive a field-specific `400` response.

## Implementation Boundaries

- Extend `codex_image/webui/network_egress.py` for normalization, persistence, snapshot data, and transport construction.
- Extend `codex_image/webui/queue_runtime.py` to freeze and pass the policy through `QueueExecutionContract`.
- Extend `codex_image/webui/executor.py` and `executor_transport.py` so the execution path accepts explicit timeout and retry values rather than rereading mutable process state.
- Extend the existing network settings route and frontend module; do not introduce a second settings endpoint.
- Add the two fields to `codex_image/webui/static/index.html`, the nearest system-settings CSS source fragment, element bindings, and all locale dictionaries.
- Regenerate checked-in static CSS and JavaScript through existing project commands rather than editing generated bundles directly.
- Update `DESIGN.md` with the visible Network-tab contract and update user documentation with the setting path, ranges, defaults, and per-attempt semantics.

No unrelated provider, queue, model-catalog, or settings refactor is included.

## Testing

Backend coverage will prove:

- Defaults and migration from settings files without the new fields.
- Compatibility fallback from the existing timeout environment variable.
- Separation of editable settings from an out-of-range legacy environment fallback and its effective-source notice.
- Inclusive minimum and maximum boundaries and rejection of invalid types or values.
- Atomic settings persistence and GET/PATCH round trips.
- Snapshot immutability and propagation of identical timeout values to both transport and executor.
- Metadata records the effective non-sensitive values.
- Retry counts `0`, `2`, and `5` produce at most `1`, `3`, and `6` attempts.
- Transient errors retry while non-retryable errors do not.
- A running attempt retains its frozen policy and a later attempt reads newly saved values.
- Connection detection remains independently bounded.

Frontend and static-contract coverage will prove:

- Values load, render, validate, and save correctly.
- Minutes and seconds are converted without rounding ambiguity.
- Empty, fractional, non-numeric, and out-of-range values block the save request and show specific feedback.
- The connection-test payload excludes generation timeout and retry policy.
- Element bindings, locale dictionaries, source assets, and generated assets remain synchronized.

Browser acceptance will cover desktop and narrow viewports, light and dark themes, keyboard and focus behavior, persistence after reopening settings, and absence of unexpected console or network errors.

Final verification will run focused settings, network-egress, queue, executor-transport, and frontend tests, followed by the full Python test suite and `npm run check:webui` because the change crosses persistence, execution, transport, and visible UI boundaries.

## Acceptance Criteria

- A user can save any integer timeout from 1 through 30 minutes and any retry count from 0 through 5.
- Reopening Network settings shows the saved values.
- A new image request uses the saved timeout at both enforcement layers.
- A retryable transient failure makes no more than the configured number of extra attempts.
- A non-retryable failure is not retried.
- Changing settings does not alter a running request and affects the next execution attempt without restart.
- Existing installations retain 10 minutes and 2 retries unless a compatible environment fallback or saved UI value says otherwise.
- Connection detection stays short and independent.
- The UI remains usable at representative desktop and narrow widths in both themes with keyboard-visible errors and no horizontal overflow.

## Release Note Classification

- Primary category: `新增`; the reliability benefit is described within the same item rather than duplicated under `变更与优化`.
- Weight: `P2 · 常规`, because the feature improves reliability for slow relay providers without changing the default behavior for existing users.
- User-facing summary: Network settings now allow a global 1–30 minute image-request timeout and 0–5 transient retries; defaults remain 10 minutes and 2 retries.
