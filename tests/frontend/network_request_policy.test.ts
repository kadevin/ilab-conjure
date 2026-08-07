import assert from "node:assert/strict";
import test from "node:test";

import {
  editableTimeoutMinutes,
  networkEgressRoutePayload,
  parseNetworkRequestPolicy,
} from "../../codex_image/webui/frontend/src/network-request-policy";

test("request policy accepts inclusive whole-number boundaries", () => {
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

test("request policy rejects invalid timeout values", () => {
  for (const raw of ["", "1.5", "slow", "0", "31"]) {
    assert.deepEqual(parseNetworkRequestPolicy(raw, "2"), {
      ok: false,
      field: "timeout",
      errorKey: "networkEgress.timeoutInvalid",
    });
  }
});

test("request policy rejects invalid retry values", () => {
  for (const raw of ["", "1.5", "slow", "-1", "6"]) {
    assert.deepEqual(parseNetworkRequestPolicy("10", raw), {
      ok: false,
      field: "retry",
      errorKey: "networkEgress.retryInvalid",
    });
  }
});

test("legacy environment values do not escape the editable timeout range", () => {
  assert.equal(editableTimeoutMinutes(60), 1);
  assert.equal(editableTimeoutMinutes(600), 10);
  assert.equal(editableTimeoutMinutes(1800), 30);
  assert.equal(editableTimeoutMinutes(2400.5), 10);
  assert.equal(editableTimeoutMinutes(Number.NaN), 10);
});

test("connection-test payload strips generation request policy", () => {
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
