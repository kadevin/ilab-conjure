# Global Image Request Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add global, persistent image-request timeout and transient-retry controls to System Settings → Network, with a 1–30 minute timeout range, a 0–5 retry range, and unchanged defaults of 10 minutes and 2 retries.

**Architecture:** Extend the existing network-egress settings document so one immutable snapshot owns route, proxy, effective timeout, retry count, and timeout source for each queue execution attempt. Pass that snapshot through `QueueExecutionContract` into both the HTTP transport and the outer WebUI request guard. Keep the existing transient-error classifier and queue/channel failover unchanged. Add a small pure TypeScript value module so form parsing and minutes/seconds conversion can be tested without a browser.

**Tech Stack:** Python 3, FastAPI, `httpx`, `unittest`, TypeScript, esbuild, HTML/CSS, the existing WebUI i18n dictionaries, and browser acceptance against the isolated provider fixture.

## Global Constraints

- The approved behavior contract is [2026-08-07-global-image-request-controls-design.md](../specs/2026-08-07-global-image-request-controls-design.md). If implementation pressure conflicts with it, stop and update the spec only after user confirmation.
- Work from the repository root on `codex/feat-global-request-controls`; preserve unrelated user changes.
- Use test-first steps: add the focused failing assertion, run it and confirm the expected failure, implement the minimum complete behavior, then rerun it.
- Do not change queue-level channel failover, manual failed-slot retry, transient-error classification, provider concurrency, CLI timeout behavior, or connection-test target selection.
- Do not edit generated `static/app.js`, source maps, or `static/styles.css` by hand. Edit TypeScript/CSS sources and regenerate them with project commands.
- Do not add dependencies.
- Do not edit `RELEASES.md` during feature implementation. Release notes are assembled only for an explicitly authorized release and must use the repository's P0–P3 classification rules.
- Every commit step below is conditional. Run it only after the user explicitly authorizes commits; otherwise report the suggested commit message and continue with uncommitted local changes.

---

## Task 1: Extend the persisted settings and API contract

**Files:**

- Modify: `codex_image/webui/network_egress.py`
- Modify: `codex_image/webui/routes/network_egress.py`
- Modify: `tests/test_network_egress.py`

- [ ] **Step 1: Add failing settings normalization and migration tests**

  Add `import json` to the test module, then extend `NetworkEgressSettingsTests` with these cases:

  ```python
  def test_network_settings_add_request_policy_defaults(self) -> None:
      with patch.dict(
          "os.environ",
          {"CODEX_IMAGE_REQUEST_TIMEOUT_SECONDS": ""},
      ):
          self.assertEqual(
              self.settings.read(),
              {
                  "mode": "system",
                  "custom_proxy_url": "",
                  "image_request_timeout_seconds": 600,
                  "image_request_retry_count": 2,
              },
          )

  def test_network_settings_validate_request_policy_boundaries(self) -> None:
      for timeout_seconds, retry_count in ((60, 0), (1800, 5), (600, 2)):
          with self.subTest(
              timeout_seconds=timeout_seconds,
              retry_count=retry_count,
          ):
              saved = self.settings.write(
                  {
                      "mode": "direct",
                      "image_request_timeout_seconds": timeout_seconds,
                      "image_request_retry_count": retry_count,
                  }
              )
              self.assertEqual(
                  saved["image_request_timeout_seconds"],
                  timeout_seconds,
              )
              self.assertEqual(saved["image_request_retry_count"], retry_count)

  def test_invalid_persisted_policy_preserves_valid_network_route(self) -> None:
      self.path.write_text(
          json.dumps(
              {
                  "mode": "custom",
                  "custom_proxy_url": "https://proxy.example.test:8443",
                  "image_request_timeout_seconds": "slow",
                  "image_request_retry_count": 99,
              }
          ),
          encoding="utf-8",
      )
      self.assertEqual(
          self.settings.read(),
          {
              "mode": "custom",
              "custom_proxy_url": "https://proxy.example.test:8443",
              "image_request_timeout_seconds": 600,
              "image_request_retry_count": 2,
          },
      )
  ```

  Add a table-driven rejection test covering booleans, strings, floats, empty values, `59`, `1801`, `-1`, and `6`. Assert the error text names either `image_request_timeout_seconds` or `image_request_retry_count`.

- [ ] **Step 2: Run the focused settings tests and confirm they fail for missing fields**

  Run:

  ```bash
  .venv/bin/python -m unittest tests.test_network_egress.NetworkEgressSettingsTests -v
  ```

  Expected pre-implementation result: the new default, validation, and per-field fallback assertions fail while the pre-existing route/proxy tests still pass.

- [ ] **Step 3: Add strict persisted-value constants and policy resolution**

  Define the settings contract in `network_egress.py`:

  ```python
  ImageRequestTimeoutSource = Literal["settings", "environment", "default"]

  IMAGE_REQUEST_TIMEOUT_ENV = "CODEX_IMAGE_REQUEST_TIMEOUT_SECONDS"
  DEFAULT_IMAGE_REQUEST_TIMEOUT_SECONDS = 600
  MIN_IMAGE_REQUEST_TIMEOUT_SECONDS = 60
  MAX_IMAGE_REQUEST_TIMEOUT_SECONDS = 1800
  DEFAULT_IMAGE_REQUEST_RETRY_COUNT = 2
  MIN_IMAGE_REQUEST_RETRY_COUNT = 0
  MAX_IMAGE_REQUEST_RETRY_COUNT = 5

  _DEFAULT_SETTINGS: dict[str, str | int] = {
      "mode": "system",
      "custom_proxy_url": "",
      "image_request_timeout_seconds": DEFAULT_IMAGE_REQUEST_TIMEOUT_SECONDS,
      "image_request_retry_count": DEFAULT_IMAGE_REQUEST_RETRY_COUNT,
  }

  @dataclass(frozen=True)
  class ImageRequestPolicy:
      timeout_seconds: float
      retry_count: int
      timeout_source: ImageRequestTimeoutSource
  ```

  Add a strict integer validator that rejects `bool`, non-`int` JSON values, and out-of-range values:

  ```python
  def _bounded_integer(
      value: Any,
      *,
      field: str,
      minimum: int,
      maximum: int,
  ) -> int:
      if isinstance(value, bool) or not isinstance(value, int):
          raise ValueError(f"{field} must be an integer")
      if value < minimum or value > maximum:
          raise ValueError(f"{field} must be between {minimum} and {maximum}")
      return value
  ```

  Split route normalization from request-policy normalization so an invalid saved policy field cannot erase an otherwise valid route. Keep incoming `write()` values strict, but make `read()` fall back independently for timeout and retry.

  Preserve environment compatibility by resolving timeout from raw persisted presence rather than the default-filled `read()` result:

  ```python
  def _environment_timeout_seconds() -> float | None:
      raw = os.getenv(IMAGE_REQUEST_TIMEOUT_ENV, "").strip()
      if not raw:
          return None
      try:
          parsed = float(raw)
      except ValueError:
          return None
      return parsed if parsed > 0 else None
  ```

  `NetworkEgressSettings.request_policy()` must use a valid explicitly persisted timeout first, then a valid positive environment value, then 600 seconds. Retry uses a valid persisted integer or 2. A partial write that does not contain either policy key must preserve the raw key if valid and must not materialize a missing timeout key, so a mode-only PATCH does not accidentally suppress the environment fallback.

  Retain the existing `NamedTemporaryFile` + `fsync` + `os.replace` atomic-write path and its local temporary-file behavior; only the normalized payload shape changes.

- [ ] **Step 4: Extend the immutable snapshot and transport timeout**

  Change the snapshot to carry the effective policy and source:

  ```python
  @dataclass(frozen=True)
  class NetworkEgressSnapshot:
      mode: NetworkEgressMode
      route: NetworkEgressRoute
      proxy_map: Mapping[str, str] | None
      image_request_timeout_seconds: float
      image_request_retry_count: int
      image_request_timeout_source: ImageRequestTimeoutSource

      def task_metadata(self) -> dict[str, str | int | float]:
          return {
              "mode": self.mode,
              "route": self.route,
              "image_request_timeout_seconds": self.image_request_timeout_seconds,
              "image_request_retry_count": self.image_request_retry_count,
              "image_request_timeout_source": self.image_request_timeout_source,
          }
  ```

  Build every route variant with the same policy object, and make the normal transport use the frozen timeout:

  ```python
  @staticmethod
  def transport(
      snapshot: NetworkEgressSnapshot,
      *,
      timeout_seconds: float | None = None,
  ) -> HttpxTransport:
      return HttpxTransport(
          timeout=(
              snapshot.image_request_timeout_seconds
              if timeout_seconds is None
              else timeout_seconds
          ),
          proxy_map=snapshot.proxy_map,
      )
  ```

- [ ] **Step 5: Add API/source/probe tests before changing the route**

  Extend `NetworkEgressApiTests` to assert:

  - GET returns editable/default `600` and `2` under `settings`.
  - PATCH accepts both inclusive boundaries and round-trips them.
  - Invalid PATCH values return `400` with the failing field name.
  - With no saved timeout and `CODEX_IMAGE_REQUEST_TIMEOUT_SECONDS=2400.5`, GET still exposes editable timeout `600`, but `resolved.image_request_timeout_seconds` is `2400.5` and `resolved.image_request_timeout_source` is `environment`.
  - A mode-only PATCH preserves that environment fallback until a timeout value is explicitly PATCHed.
  - The connection-test route calls `transport(snapshot, timeout_seconds=10.0)` even when the saved generation timeout is 1800 seconds.

  Run the API tests and confirm the new assertions fail:

  ```bash
  .venv/bin/python -m unittest tests.test_network_egress.NetworkEgressApiTests -v
  ```

- [ ] **Step 6: Return the resolved policy and isolate the connection-test timeout**

  Add this fixed probe constant in `routes/network_egress.py`:

  ```python
  NETWORK_EGRESS_TEST_TIMEOUT_SECONDS = 10.0
  ```

  Make `_settings_payload()` call `snapshot()` with no default-filled settings payload, so it can distinguish a missing persisted timeout from an explicit 600-second setting:

  ```python
  def _settings_payload(ctx: WebUIContext) -> dict[str, Any]:
      settings = ctx.network_egress_settings.read()
      snapshot = ctx.network_egress_manager.snapshot()
      return {
          "settings": settings,
          "resolved": {
              "mode": snapshot.mode,
              "route": snapshot.route,
              "image_request_timeout_seconds": (
                  snapshot.image_request_timeout_seconds
              ),
              "image_request_retry_count": snapshot.image_request_retry_count,
              "image_request_timeout_source": (
                  snapshot.image_request_timeout_source
              ),
          },
          "restart_required": False,
      }
  ```

  Construct the probe transport with the explicit 10-second override. The probe request body must continue accepting only route fields plus `provider_id`; request-policy fields must not alter probe behavior.

- [ ] **Step 7: Run the complete network-egress module**

  Run:

  ```bash
  .venv/bin/python -m unittest tests.test_network_egress -v
  ```

  Expected result: defaults, migration, environment compatibility, strict API validation, proxy redaction, target selection, and the independently bounded probe all pass.

- [ ] **Step 8: Conditional commit gate**

  If commits are authorized, commit only these backend settings/API changes with:

  ```bash
  git add codex_image/webui/network_egress.py codex_image/webui/routes/network_egress.py tests/test_network_egress.py
  git commit -m "feat(webui): add global image request policy settings"
  ```

---

## Task 2: Freeze and enforce the policy for each queue attempt

**Files:**

- Modify: `codex_image/webui/executor_transport.py`
- Modify: `codex_image/webui/executor.py`
- Modify: `codex_image/webui/queue_runtime.py`
- Modify: `tests/test_webui_cancellable_transport.py`
- Modify: `tests/test_webui_settings.py`
- Modify: `tests/test_network_egress.py`

- [ ] **Step 1: Add failing retry-count unit coverage**

  Add this table-driven test to `WebUICancellableTransportTests`:

  ```python
  def test_transient_retry_count_means_retries_after_the_first_attempt(self) -> None:
      from codex_image.webui.executor_transport import _call_image_client

      for retry_count, expected_attempts in ((0, 1), (2, 3), (5, 6)):
          calls = 0

          def fail_transiently() -> object:
              nonlocal calls
              calls += 1
              raise ConnectionResetError(54, "Connection reset by peer")

          with (
              self.subTest(retry_count=retry_count),
              patch(
                  "codex_image.webui.executor_transport._transient_image_retry_delay_seconds",
                  return_value=0,
              ),
              self.assertRaises(ConnectionResetError),
          ):
              asyncio.run(
                  _call_image_client(
                      None,
                      {},
                      fail_transiently,
                      timeout_seconds=1,
                      retry_count=retry_count,
                  )
              )
          self.assertEqual(calls, expected_attempts)
  ```

  Add a companion non-transient `ValueError` case with `retry_count=5` and assert one call.

- [ ] **Step 2: Run the new retry tests and confirm the missing keyword failure**

  Run:

  ```bash
  .venv/bin/python -m unittest tests.test_webui_cancellable_transport.WebUICancellableTransportTests.test_transient_retry_count_means_retries_after_the_first_attempt -v
  ```

  Expected pre-implementation result: `_call_image_client()` rejects the new `retry_count` keyword or still uses three fixed attempts.

- [ ] **Step 3: Parameterize the existing transient retry loop**

  Import the retry defaults/ranges from `network_egress.py`, preserve `MAX_TRANSIENT_IMAGE_REQUEST_ATTEMPTS` as a compatibility alias, and change the callable contract:

  ```python
  MAX_TRANSIENT_IMAGE_REQUEST_ATTEMPTS = DEFAULT_IMAGE_REQUEST_RETRY_COUNT + 1

  async def _call_image_client(
      request_context: Callable[[dict[str, Any]], AsyncContextManager[None]] | None,
      params: dict[str, Any],
      method: Callable[..., ImageResult],
      timeout_seconds: float | None = None,
      retry_count: int = DEFAULT_IMAGE_REQUEST_RETRY_COUNT,
      **kwargs: Any,
  ) -> ImageResult:
      normalized_retry_count = min(
          MAX_IMAGE_REQUEST_RETRY_COUNT,
          max(MIN_IMAGE_REQUEST_RETRY_COUNT, int(retry_count)),
      )
      total_attempts = normalized_retry_count + 1
      for attempt in range(1, total_attempts + 1):
          context = (
              request_context(params)
              if request_context is not None
              else _noop_request_context()
          )
          try:
              async with context:
                  result = await _call_image_client_once(
                      method,
                      timeout_seconds=timeout_seconds,
                      kwargs=kwargs,
                  )
          except Exception as exc:
              try:
                  setattr(exc, "_image_request_attempts", attempt)
              except Exception:
                  pass
              if (
                  attempt >= total_attempts
                  or not _is_retryable_transient_image_error(exc)
              ):
                  raise
              await asyncio.sleep(_transient_image_retry_delay_seconds(attempt))
              continue
          setattr(result, "_image_request_attempts", attempt)
          return result
      raise RuntimeError("Image request retry loop completed without a result")
  ```

  Keep `_image_request_timeout_seconds()` as a compatibility helper for direct/private callers and make it delegate to the same environment parser used by `NetworkEgressSettings`; do not alter `codex_image/http.py` or CLI transport behavior.

- [ ] **Step 4: Add explicit executor arguments and pass them at every image call site**

  Extend `_execute_stored_task()`:

  ```python
  async def _execute_stored_task(
      *,
      storage: TaskStorage,
      gallery_storage: GalleryStorage,
      reference_asset_storage: ReferenceAssetStorage,
      reference_file_storage: ReferenceFileStorage,
      task_id: str,
      client: Any,
      batch_delay_seconds: float,
      request_context: Callable[[dict[str, Any]], AsyncContextManager[None]] | None = None,
      image_request_timeout_seconds: float | None = None,
      image_request_retry_count: int = DEFAULT_IMAGE_REQUEST_RETRY_COUNT,
  ) -> dict[str, Any]:
      effective_image_request_timeout_seconds = (
          _image_request_timeout_seconds()
          if image_request_timeout_seconds is None
          else image_request_timeout_seconds
      )
  ```

  Replace every use of the locally reread timeout with `effective_image_request_timeout_seconds`, and pass both values into all generate/edit and sequential/concurrent `_call_image_client()` paths:

  ```python
  result = await _call_image_client(
      request_context,
      params,
      method,
      timeout_seconds=effective_image_request_timeout_seconds,
      retry_count=image_request_retry_count,
      **request_kwargs,
  )
  ```

  `snapshot(payload)` may use `payload` to override only route/proxy values for a user-triggered connection test. It must always resolve generation timeout/retries from `NetworkEgressSettings.request_policy()`, never from unsaved probe fields.

- [ ] **Step 5: Add failing queue snapshot propagation tests**

  Extend `QueueAttemptNetworkEgressTests` so the fake executor captures:

  ```python
  observed_policy = {
      "timeout": kwargs["image_request_timeout_seconds"],
      "retries": kwargs["image_request_retry_count"],
  }
  ```

  Save `900` seconds and `4` retries before the queue attempt, then assert:

  - the client transport timeout is `900`;
  - executor arguments are `900` and `4`;
  - metadata contains the same values and no proxy URL;
  - changing settings after the contract is built does not mutate that contract;
  - a newly built contract reads the new values.

  Run:

  ```bash
  .venv/bin/python -m unittest tests.test_network_egress.QueueAttemptNetworkEgressTests -v
  ```

  Expected pre-implementation result: `QueueExecutionContract` has no policy fields and the fake executor receives no explicit policy.

- [ ] **Step 6: Carry the frozen values through `QueueExecutionContract`**

  Extend the dataclass and all three construction branches:

  ```python
  @dataclass(frozen=True)
  class QueueExecutionContract:
      client: Any
      backend: str
      reference_file_capability_key: CapabilityKey
      image_request_timeout_seconds: float
      image_request_retry_count: int
  ```

  Each return must copy values from the single `network_snapshot` built at the top of `_queue_execution_contract()`. Pass them into `_execute_stored_task()` in `execute_task()`:

  ```python
  image_request_timeout_seconds=(
      execution_contract.image_request_timeout_seconds
  ),
  image_request_retry_count=execution_contract.image_request_retry_count,
  ```

  Do not reread settings inside the executor and do not add these fields to `QueueChannel`.

- [ ] **Step 7: Prove default and configured behavior end to end**

  Keep the existing `test_api_images_stops_after_two_transient_output_retries` assertion at three total attempts to protect the default. Add an integration test that PATCHes retry count `0`, runs a retryable failure through the queue, and asserts exactly one provider call and one output attempt.

  The existing real cancellation test using `CODEX_IMAGE_REQUEST_TIMEOUT_SECONDS=0.5` must continue passing. Because no UI timeout has been saved in that test, the queue snapshot must resolve the legacy environment fallback once and use `0.5` at both enforcement layers.

  Run:

  ```bash
  .venv/bin/python -m unittest \
    tests.test_webui_cancellable_transport \
    tests.test_webui_settings.WebUISettingsTests.test_api_images_retries_retryable_transient_output_errors \
    tests.test_webui_settings.WebUISettingsTests.test_api_images_stops_after_two_transient_output_retries \
    tests.test_network_egress.QueueAttemptNetworkEgressTests \
    -v
  ```

- [ ] **Step 8: Conditional commit gate**

  If commits are authorized, commit the runtime slice with:

  ```bash
  git add codex_image/webui/executor_transport.py codex_image/webui/executor.py codex_image/webui/queue_runtime.py tests/test_webui_cancellable_transport.py tests/test_webui_settings.py tests/test_network_egress.py
  git commit -m "feat(webui): enforce configurable image request retries"
  ```

---

## Task 3: Add a testable frontend value model and form behavior

**Files:**

- Create: `codex_image/webui/frontend/src/network-request-policy.ts`
- Create: `tests/frontend/network_request_policy.test.ts`
- Modify: `tests/test_webui_frontend_behavior.py`
- Modify: `codex_image/webui/frontend/src/network-egress-settings.ts`
- Modify: `codex_image/webui/frontend/src/elements.ts`

- [ ] **Step 1: Write the failing pure TypeScript behavior test**

  Create `tests/frontend/network_request_policy.test.ts`:

  ```typescript
  import assert from "node:assert/strict";
  import test from "node:test";

  import {
    editableTimeoutMinutes,
    networkEgressRoutePayload,
    parseNetworkRequestPolicy,
  } from "../../codex_image/webui/frontend/src/network-request-policy";

  test("request policy accepts inclusive integer boundaries", () => {
    assert.deepEqual(parseNetworkRequestPolicy("1", "0"), {
      ok: true,
      value: {
        image_request_timeout_seconds: 60,
        image_request_retry_count: 0,
      },
    });
    assert.deepEqual(parseNetworkRequestPolicy("30", "5"), {
      ok: true,
      value: {
        image_request_timeout_seconds: 1800,
        image_request_retry_count: 5,
      },
    });
  });

  test("request policy rejects empty fractional nonnumeric and out-of-range values", () => {
    for (const raw of ["", "1.5", "slow", "0", "31"]) {
      assert.deepEqual(parseNetworkRequestPolicy(raw, "2"), {
        ok: false,
        field: "timeout",
        errorKey: "networkEgress.timeoutInvalid",
      });
    }
    for (const raw of ["", "1.5", "slow", "-1", "6"]) {
      assert.deepEqual(parseNetworkRequestPolicy("10", raw), {
        ok: false,
        field: "retry",
        errorKey: "networkEgress.retryInvalid",
      });
    }
  });

  test("rendering falls back to ten editable minutes for legacy values", () => {
    assert.equal(editableTimeoutMinutes(600), 10);
    assert.equal(editableTimeoutMinutes(1800), 30);
    assert.equal(editableTimeoutMinutes(2400.5), 10);
  });

  test("connection-test payload excludes generation policy", () => {
    assert.deepEqual(
      networkEgressRoutePayload({
        mode: "direct",
        custom_proxy_url: "",
        image_request_timeout_seconds: 1800,
        image_request_retry_count: 5,
      }),
      {mode: "direct", custom_proxy_url: ""},
    );
  });
  ```

  Add a matching esbuild + `node --test` method to `WebUIFrontendBehaviorTests`, following the existing provider-binding test harness exactly but using the new test path and output name.

- [ ] **Step 2: Run the new frontend test and confirm the module is missing**

  Run:

  ```bash
  .venv/bin/python -m unittest tests.test_webui_frontend_behavior.WebUIFrontendBehaviorTests.test_network_request_policy_behavior -v
  ```

  Expected pre-implementation result: esbuild cannot resolve `network-request-policy`.

- [ ] **Step 3: Implement the pure parsing and conversion module**

  Create `network-request-policy.ts` with this public contract:

  ```typescript
  export type NetworkEgressMode = "system" | "direct" | "custom";

  export interface NetworkEgressUpdatePayload {
    mode: NetworkEgressMode;
    custom_proxy_url: string;
    image_request_timeout_seconds: number;
    image_request_retry_count: number;
  }

  export type NetworkRequestPolicyResult =
    | {
        ok: true;
        value: Pick<
          NetworkEgressUpdatePayload,
          "image_request_timeout_seconds" | "image_request_retry_count"
        >;
      }
    | {
        ok: false;
        field: "timeout" | "retry";
        errorKey:
          | "networkEgress.timeoutInvalid"
          | "networkEgress.retryInvalid";
      };

  const DEFAULT_TIMEOUT_MINUTES = 10;

  function boundedInteger(raw: string, minimum: number, maximum: number): number | null {
    const candidate = raw.trim();
    if (!/^\d+$/.test(candidate)) return null;
    const value = Number(candidate);
    if (!Number.isSafeInteger(value) || value < minimum || value > maximum) {
      return null;
    }
    return value;
  }

  export function parseNetworkRequestPolicy(
    timeoutMinutesRaw: string,
    retryCountRaw: string,
  ): NetworkRequestPolicyResult {
    const timeoutMinutes = boundedInteger(timeoutMinutesRaw, 1, 30);
    if (timeoutMinutes === null) {
      return {
        ok: false,
        field: "timeout",
        errorKey: "networkEgress.timeoutInvalid",
      };
    }
    const retryCount = boundedInteger(retryCountRaw, 0, 5);
    if (retryCount === null) {
      return {
        ok: false,
        field: "retry",
        errorKey: "networkEgress.retryInvalid",
      };
    }
    return {
      ok: true,
      value: {
        image_request_timeout_seconds: timeoutMinutes * 60,
        image_request_retry_count: retryCount,
      },
    };
  }

  export function editableTimeoutMinutes(timeoutSeconds: number): number {
    const minutes = timeoutSeconds / 60;
    return Number.isInteger(minutes) && minutes >= 1 && minutes <= 30
      ? minutes
      : DEFAULT_TIMEOUT_MINUTES;
  }

  export type NetworkEgressRouteFields = Pick<
    NetworkEgressUpdatePayload,
    "mode" | "custom_proxy_url"
  > & Partial<
    Pick<
      NetworkEgressUpdatePayload,
      "image_request_timeout_seconds" | "image_request_retry_count"
    >
  >;

  export function networkEgressRoutePayload(
    payload: NetworkEgressRouteFields,
  ): Pick<NetworkEgressUpdatePayload, "mode" | "custom_proxy_url"> {
    return {
      mode: payload.mode,
      custom_proxy_url: payload.custom_proxy_url,
    };
  }
  ```

  Run the new frontend behavior test and confirm it passes.

- [ ] **Step 4: Extend payload typing and rendering in the existing settings module**

  Add the new settings and resolved fields to `NetworkEgressPayload`:

  ```typescript
  settings: {
    mode: NetworkEgressMode;
    custom_proxy_url: string;
    image_request_timeout_seconds: number;
    image_request_retry_count: number;
  };
  resolved: {
    mode: NetworkEgressMode;
    route: "system" | "direct" | "proxy";
    image_request_timeout_seconds: number;
    image_request_retry_count: number;
    image_request_timeout_source: "settings" | "environment" | "default";
  };
  ```

  On render:

  - set the timeout input from `editableTimeoutMinutes(payload.settings.image_request_timeout_seconds)`;
  - set the retry input from `payload.settings.image_request_retry_count`;
  - clear stale `aria-invalid` and field errors;
  - show a neutral compatibility notice whenever the source is `environment`, including the exact effective seconds and explaining that Save replaces it;
  - hide the compatibility notice for `settings` and `default`.

- [ ] **Step 5: Make Save validate policy fields, while Test validates only routing**

  Save must combine route fields with the successful pure parser result. If parsing fails, reveal the matching translated error, set `aria-invalid="true"`, focus that input, and make no PATCH request.

  Connection testing must read route/proxy controls directly, without calling the request-policy parser, and build only this payload:

  ```typescript
  const routePayload = networkEgressRoutePayload({
    mode: selectedNetworkEgressMode(),
    custom_proxy_url: String(els.networkEgressCustomProxy?.value || "").trim(),
  });
  const testPayload = {
    ...routePayload,
    ...(selectedProviderId ? {provider_id: selectedProviderId} : {}),
  };
  ```

  It must not parse, submit, or wait on the generation timeout/retry fields. Keep existing custom-proxy validation for both actions.

- [ ] **Step 6: Bind the new elements**

  Add these selectors in `elements.ts`:

  ```typescript
  networkEgressTimeoutMinutes: document.querySelector("#networkEgressTimeoutMinutes"),
  networkEgressRetryCount: document.querySelector("#networkEgressRetryCount"),
  networkEgressTimeoutError: document.querySelector("#networkEgressTimeoutError"),
  networkEgressRetryError: document.querySelector("#networkEgressRetryError"),
  networkEgressCompatibilityNotice: document.querySelector("#networkEgressCompatibilityNotice"),
  ```

- [ ] **Step 7: Run type and behavior checks**

  Run:

  ```bash
  npm run typecheck:webui
  .venv/bin/python -m unittest tests.test_webui_frontend_behavior.WebUIFrontendBehaviorTests.test_network_request_policy_behavior -v
  ```

- [ ] **Step 8: Conditional commit gate**

  If commits are authorized, commit the pure frontend behavior slice with:

  ```bash
  git add codex_image/webui/frontend/src/network-request-policy.ts codex_image/webui/frontend/src/network-egress-settings.ts codex_image/webui/frontend/src/elements.ts tests/frontend/network_request_policy.test.ts tests/test_webui_frontend_behavior.py
  git commit -m "feat(webui): validate request timeout and retry controls"
  ```

---

## Task 4: Add accessible Network-tab controls, responsive styles, and translations

**Files:**

- Modify: `codex_image/webui/static/index.html`
- Modify: `codex_image/webui/static/styles/74-api-system-settings.css`
- Modify: `codex_image/webui/frontend/src/i18n/zh-cn.ts`
- Modify: `codex_image/webui/frontend/src/i18n/zh-tw.ts`
- Modify: `codex_image/webui/frontend/src/i18n/zh-hk.ts`
- Modify: `codex_image/webui/frontend/src/i18n/ja.ts`
- Modify: `codex_image/webui/frontend/src/i18n/ko.ts`
- Modify: `codex_image/webui/frontend/src/i18n/en.ts`
- Modify: `codex_image/webui/frontend/src/i18n/vi.ts`
- Modify: `codex_image/webui/frontend/src/i18n/es.ts`
- Modify: `codex_image/webui/frontend/src/i18n/pt.ts`
- Modify: `codex_image/webui/frontend/src/i18n/fr.ts`
- Modify: `codex_image/webui/frontend/src/i18n/de.ts`
- Modify: `codex_image/webui/frontend/src/i18n/ru.ts`
- Modify: `codex_image/webui/frontend/src/i18n/it.ts`
- Modify: `codex_image/webui/frontend/src/i18n/hi.ts`
- Modify: `tests/test_webui_static_layout.py`
- Modify: `tests/test_webui_static_i18n.py`

- [ ] **Step 1: Add failing static layout and locale assertions**

  Extend `test_system_settings_has_four_tabs_and_network_controls` to require the two inputs, shared helper, two error elements, and compatibility notice. Extend `test_network_settings_strings_exist_in_every_locale` with:

  ```python
  "networkEgress.timeout",
  "networkEgress.timeoutUnit",
  "networkEgress.retryCount",
  "networkEgress.retryUnit",
  "networkEgress.requestPolicyHelp",
  "networkEgress.timeoutInvalid",
  "networkEgress.retryInvalid",
  "networkEgress.environmentTimeoutActive",
  ```

  Add CSS assertions for a two-column policy grid and a one-column narrow-screen override.

  Run and confirm failure:

  ```bash
  .venv/bin/python -m unittest \
    tests.test_webui_static_layout.WebUIStaticLayoutTests.test_system_settings_has_four_tabs_and_network_controls \
    tests.test_webui_static_i18n.WebUIStaticI18nTests.test_network_settings_strings_exist_in_every_locale \
    -v
  ```

- [ ] **Step 2: Add the semantic HTML below the optional proxy field**

  Add this structure without introducing a nested card:

  ```html
  <div class="network-request-policy-grid">
    <label class="field network-request-policy-field">
      <span data-i18n="networkEgress.timeout">单次生图超时</span>
      <span class="network-request-policy-input">
        <input id="networkEgressTimeoutMinutes" class="control" type="number" min="1" max="30" step="1" inputmode="numeric" value="10" aria-describedby="networkRequestPolicyHelp networkEgressTimeoutError" />
        <span class="network-request-policy-unit" data-i18n="networkEgress.timeoutUnit">分钟</span>
      </span>
      <small id="networkEgressTimeoutError" class="network-request-policy-error" data-i18n="networkEgress.timeoutInvalid" role="alert" hidden>请输入 1–30 的整数分钟</small>
    </label>
    <label class="field network-request-policy-field">
      <span data-i18n="networkEgress.retryCount">失败后重试</span>
      <span class="network-request-policy-input">
        <input id="networkEgressRetryCount" class="control" type="number" min="0" max="5" step="1" inputmode="numeric" value="2" aria-describedby="networkRequestPolicyHelp networkEgressRetryError" />
        <span class="network-request-policy-unit" data-i18n="networkEgress.retryUnit">次</span>
      </span>
      <small id="networkEgressRetryError" class="network-request-policy-error" data-i18n="networkEgress.retryInvalid" role="alert" hidden>请输入 0–5 的整数次数</small>
    </label>
  </div>
  <p id="networkRequestPolicyHelp" class="network-request-policy-help" data-i18n="networkEgress.requestPolicyHelp">仅影响之后开始的生图请求；每次自动重试都会重新计算超时时间。</p>
  <p id="networkEgressCompatibilityNotice" class="network-egress-compatibility-notice" aria-live="polite" hidden></p>
  ```

- [ ] **Step 3: Add source-fragment styles with narrow-screen collapse**

  Add these base rules near `.network-egress-panel`:

  ```css
  .network-request-policy-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 12px;
  }

  .network-request-policy-field {
    min-width: 0;
  }

  .network-request-policy-input {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 8px;
    align-items: center;
  }

  .network-request-policy-unit,
  .network-request-policy-help,
  .network-egress-compatibility-notice {
    color: var(--text-muted);
    font-size: 12px;
    line-height: 1.5;
  }

  .network-request-policy-help,
  .network-egress-compatibility-notice {
    margin: 0;
  }

  .network-request-policy-error {
    color: var(--danger);
    font-size: 12px;
    line-height: 1.4;
  }

  .network-request-policy-error[hidden],
  .network-egress-compatibility-notice[hidden] {
    display: none;
  }

  @media (max-width: 520px) {
    .network-request-policy-grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }
  ```

  Use existing `.control` focus styling; add no parallel focus system. Ensure error visibility is conveyed by text plus `aria-invalid`, not color alone.

- [ ] **Step 4: Add native-language strings in all 14 locale dictionaries**

  Use these Simplified Chinese source strings:

  ```typescript
  "networkEgress.timeout": "单次生图超时",
  "networkEgress.timeoutUnit": "分钟",
  "networkEgress.retryCount": "失败后重试",
  "networkEgress.retryUnit": "次",
  "networkEgress.requestPolicyHelp": "仅影响之后开始的生图请求；每次自动重试都会重新计算超时时间。",
  "networkEgress.timeoutInvalid": "请输入 1–30 的整数分钟",
  "networkEgress.retryInvalid": "请输入 0–5 的整数次数",
  "networkEgress.environmentTimeoutActive": "当前使用环境变量超时：{seconds} 秒；保存后将改用上方设置。",
  ```

  Use these English source strings and translate their meaning naturally into every other locale rather than copying the English block:

  ```typescript
  "networkEgress.timeout": "Image request timeout",
  "networkEgress.timeoutUnit": "min",
  "networkEgress.retryCount": "Retries after failure",
  "networkEgress.retryUnit": "times",
  "networkEgress.requestPolicyHelp": "Applies only to image requests started later. Each automatic retry gets a new timeout window.",
  "networkEgress.timeoutInvalid": "Enter a whole number from 1 to 30 minutes",
  "networkEgress.retryInvalid": "Enter a whole number from 0 to 5 retries",
  "networkEgress.environmentTimeoutActive": "The environment timeout is active: {seconds} seconds. Saving replaces it with the setting above.",
  ```

- [ ] **Step 5: Run source-level UI contracts**

  Run:

  ```bash
  .venv/bin/python -m unittest tests.test_webui_static_layout tests.test_webui_static_i18n -v
  npm run typecheck:webui
  ```

- [ ] **Step 6: Conditional commit gate**

  If commits are authorized, commit the visible UI source slice with:

  ```bash
  git add codex_image/webui/static/index.html codex_image/webui/static/styles/74-api-system-settings.css codex_image/webui/frontend/src/i18n tests/test_webui_static_layout.py tests/test_webui_static_i18n.py
  git commit -m "feat(webui): add timeout and retry controls to network settings"
  ```

---

## Task 5: Regenerate assets, bump cache identity, and document the behavior

**Files:**

- Modify by generator: `codex_image/webui/static/styles.css`
- Modify by generator: `codex_image/webui/static/app.js`
- Modify by generator: `codex_image/webui/static/app.js.map`
- Modify: `codex_image/webui/static/index.html`
- Modify: `codex_image/webui/static/history.html`
- Modify: `codex_image/webui/static/service-worker.js`
- Modify: `tests/test_webui_static_reference_files.py`
- Modify: `tests/test_webui_static_prompt.py`
- Modify: `tests/test_webui_static_history.py`
- Modify: `tests/test_webui_static_layout.py`
- Modify: `tests/test_webui_static_pwa.py`
- Modify: `tests/test_webui_static_build.py`
- Modify: `DESIGN.md`
- Modify: `README.md`
- Modify: `README.en.md`

- [ ] **Step 1: Add the new module to generated-source-map coverage**

  Extend `test_frontend_source_map_matches_typescript_entrypoint_sources` with:

  ```python
  self.assertIn("../frontend/src/network-request-policy.ts", sources)
  self.assertIn("../frontend/src/network-egress-settings.ts", sources)
  ```

- [ ] **Step 2: Regenerate checked-in CSS and JavaScript from sources**

  Run:

  ```bash
  npm run check:webui
  ```

  This command must produce `styles.css`, `app.js`, and `app.js.map` from their source files. Review the generated diff to confirm it contains the request-policy module and styles but no unrelated dependency or formatting churn.

- [ ] **Step 3: Bump the application-shell cache identity once**

  Change `runtime-768` to `runtime-769` consistently in:

  - `codex_image/webui/static/index.html`
  - `codex_image/webui/static/history.html`
  - `codex_image/webui/static/service-worker.js`
  - `tests/test_webui_static_reference_files.py`
  - `tests/test_webui_static_prompt.py`
  - `tests/test_webui_static_history.py`
  - `tests/test_webui_static_layout.py`
  - `tests/test_webui_static_pwa.py`

  Verify there are no remaining old references:

  ```bash
  rg -n "runtime-768|runtime-769" codex_image/webui/static tests
  ```

  Expected result: every application-shell and matching test reference uses `runtime-769`; `runtime-768` has zero matches.

- [ ] **Step 4: Update the design contract**

  In the Network section of `DESIGN.md`, add the visible contract:

  - two compact fields below the custom proxy: per-request timeout and retries after the first failure;
  - timeout is an integer 1–30 minutes, retry is an integer 0–5;
  - defaults remain 10 and 2;
  - the two-column row collapses on narrow screens;
  - values apply only to later queue execution attempts without restart;
  - one attempt freezes its values, and each transient retry receives a fresh timeout window;
  - connection detection remains a separate short probe and ignores these values;
  - a legacy environment fallback is disclosed neutrally until the user saves a WebUI timeout.

- [ ] **Step 5: Update user documentation without creating release notes early**

  Replace the current Network feature bullet in `README.md` with wording that includes the path, ranges, defaults, and per-attempt semantics:

  ```text
  系统设置 → 网络除系统、直连和自定义 HTTP(S) 代理外，还可全局设置单次生图超时（1–30 分钟，默认 10）和失败后的瞬时错误重试次数（0–5 次，默认 2）。保存无需重启，只影响之后开始的执行尝试；每次自动重试重新计算超时时间。
  ```

  Add the equivalent English wording to `README.en.md`. Leave `README.zh-CN.md` unchanged because it intentionally redirects to `README.md`.

  Do not add the item to `RELEASES.md` yet. Preserve this release-note candidate for the future release inventory:

  ```text
  P2 · 新增：系统设置的“网络”页现在可以全局设置 1–30 分钟的单次生图超时，以及 0–5 次瞬时错误重试；默认仍为 10 分钟和 2 次，适合响应较慢的中转站。
  ```

- [ ] **Step 6: Verify generated/static/doc contracts**

  Run:

  ```bash
  npm run check:webui
  .venv/bin/python -m unittest \
    tests.test_webui_static_build \
    tests.test_webui_static_layout \
    tests.test_webui_static_i18n \
    tests.test_webui_static_pwa \
    tests.test_webui_static_reference_files \
    tests.test_webui_static_prompt \
    tests.test_webui_static_history \
    -v
  ```

- [ ] **Step 7: Conditional commit gate**

  If commits are authorized, commit generated assets and documentation with:

  ```bash
  git add DESIGN.md README.md README.en.md codex_image/webui/static tests/test_webui_static_build.py tests/test_webui_static_reference_files.py tests/test_webui_static_prompt.py tests/test_webui_static_history.py tests/test_webui_static_layout.py tests/test_webui_static_pwa.py
  git commit -m "docs(webui): document global image request controls"
  ```

---

## Task 6: Full verification and browser acceptance

**Files:**

- Verify only; modify the smallest owning source/test file if a failure exposes a real defect.

- [ ] **Step 1: Run focused cross-layer regression tests**

  Run:

  ```bash
  .venv/bin/python -m unittest \
    tests.test_network_egress \
    tests.test_webui_cancellable_transport \
    tests.test_webui_settings \
    tests.test_webui_frontend_behavior \
    tests.test_webui_static_i18n \
    tests.test_webui_static_layout \
    tests.test_webui_static_build \
    tests.test_webui_static_pwa \
    tests.test_webui_static_reference_files \
    -v
  ```

  Confirm the evidence maps directly to the accepted spec: defaults/migration, strict ranges, environment source, frozen snapshot, two timeout layers, 0/2/5 retries, non-transient one-shot failure, independent probe, frontend conversions, i18n, and generated assets.

- [ ] **Step 2: Run complete repository checks**

  Run:

  ```bash
  npm run check:webui
  .venv/bin/python -m unittest discover -s tests -v
  .venv/bin/python scripts/check-release-contracts.py
  git diff --check
  ```

  Do not claim completion if a validator itself errors or if a relevant test is skipped because a required local dependency is missing; report that gap explicitly.

- [ ] **Step 3: Start the isolated real-browser fixture**

  Run the fixture on an unused local port so it uses temporary data and cannot touch the user's real task history or settings:

  ```bash
  .venv/bin/python scripts/run-webui-provider-fixture.py --host 127.0.0.1 --port 8791
  ```

  Keep this process only for the acceptance session and stop it afterward. The fixture deletes its temporary directory on exit.

- [ ] **Step 4: Verify desktop and narrow UI states in a real browser**

  At `http://127.0.0.1:8791`, verify both `1440×900` and `390×844`:

  1. Open System Settings → Network in light theme; confirm defaults `10` and `2`, aligned labels/units/helper text, no horizontal overflow, and a two-column desktop layout.
  2. Use only the keyboard to reach both inputs, enter `30` and `5`, save, close settings, reopen it, and confirm persistence.
  3. Confirm the narrow viewport collapses to one column and retains visible focus outlines.
  4. Enter empty, fractional, non-numeric, and out-of-range values; confirm field-specific visible text, `aria-invalid`, focus on the invalid field, and no PATCH request.
  5. Set valid request-policy values, click Test connection, and inspect the POST body: it contains route fields and optional `provider_id`, never timeout or retry fields.
  6. Repeat the visual check in dark theme.
  7. Confirm no unexpected console errors or failed application requests.

  Use structured DOM, computed-style, console, and network evidence. Capture at most one minimal screenshot per distinct viewport/theme state only if visual judgment is required.

- [ ] **Step 5: Review final scope and prepare handoff**

  Run:

  ```bash
  git status --short --branch
  git diff --stat
  git diff -- codex_image/webui/network_egress.py codex_image/webui/routes/network_egress.py codex_image/webui/queue_runtime.py codex_image/webui/executor.py codex_image/webui/executor_transport.py
  ```

  Confirm there are no credentials, local output data, screenshots, fixture files, or unrelated changes. Report:

  - implemented behavior;
  - exact focused/full/browser verification evidence;
  - any skipped check or residual risk;
  - suggested PR title `feat(webui): configure global image request timeout and retries`;
  - the P2 release-note candidate from Task 5.

- [ ] **Step 6: Final conditional commit gate**

  If the user authorizes one final squash-style local commit instead of the task-level commits, stage only the reviewed files and use:

  ```bash
  git commit -m "feat(webui): configure image request timeout and retries"
  ```

  Do not push, open a PR, merge, tag, or release without separate explicit authorization.
