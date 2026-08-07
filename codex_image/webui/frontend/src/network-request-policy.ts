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

export type NetworkEgressRouteFields = Pick<
  NetworkEgressUpdatePayload,
  "mode" | "custom_proxy_url"
> & Partial<
  Pick<
    NetworkEgressUpdatePayload,
    "image_request_timeout_seconds" | "image_request_retry_count"
  >
>;

const DEFAULT_TIMEOUT_MINUTES = 10;

function boundedInteger(
  raw: string,
  minimum: number,
  maximum: number,
): number | null {
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

export function networkEgressRoutePayload(
  payload: NetworkEgressRouteFields,
): Pick<NetworkEgressUpdatePayload, "mode" | "custom_proxy_url"> {
  return {
    mode: payload.mode,
    custom_proxy_url: payload.custom_proxy_url,
  };
}
