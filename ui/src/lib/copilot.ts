import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "../api/client";

export type CopilotPollResponse = {
  status: "pending" | "slow_down" | "success" | "expired" | "error";
  interval: number;
  message?: string;
};

export type CopilotFlowState = {
  userCode?: string;
  verificationUri?: string;
  status: string;
};

type CopilotDeviceCode = {
  user_code: string;
  verification_uri: string;
  device_code: string;
  interval: number;
  expires_in: number;
};

type PollCopilot = (
  deviceCode: string,
  interval: number,
  signal: AbortSignal
) => Promise<CopilotPollResponse>;

const DEFAULT_INTERVAL = 5;

function throwIfAborted(signal: AbortSignal) {
  if (signal.aborted) throw new DOMException("Copilot login cancelled.", "AbortError");
}

function wait(ms: number, signal: AbortSignal): Promise<void> {
  throwIfAborted(signal);
  return new Promise((resolve, reject) => {
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException("Copilot login cancelled.", "AbortError"));
    };
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

export function isCopilotAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

export async function pollCopilotDeviceFlow(
  deviceCode: string,
  interval: number,
  expiresIn: number,
  poll: PollCopilot,
  signal: AbortSignal
): Promise<void> {
  const deadline = Date.now() + expiresIn * 1000;
  let nextInterval = interval > 0 ? interval : DEFAULT_INTERVAL;

  while (Date.now() < deadline) {
    await wait(Math.min(nextInterval * 1000, deadline - Date.now()), signal);
    throwIfAborted(signal);
    const result = await poll(deviceCode, nextInterval, signal);
    throwIfAborted(signal);
    if (result.status === "success") return;
    if (result.status === "pending" || result.status === "slow_down") {
      nextInterval = result.interval > 0 ? result.interval : DEFAULT_INTERVAL;
      continue;
    }
    throw new Error(result.message || "GitHub Copilot authentication failed.");
  }
  throw new Error("GitHub device code expired; please try again.");
}

export function useCopilotDeviceFlow(refetch: () => void) {
  const [flow, setFlow] = useState<CopilotFlowState | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const successTimerRef = useRef<number | null>(null);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    if (successTimerRef.current !== null) {
      window.clearTimeout(successTimerRef.current);
      successTimerRef.current = null;
    }
    setFlow(null);
  }, []);

  useEffect(() => () => {
    abortRef.current?.abort();
    if (successTimerRef.current !== null) {
      window.clearTimeout(successTimerRef.current);
    }
  }, []);

  const start = useCallback(async () => {
    cancel();
    const controller = new AbortController();
    abortRef.current = controller;
    const isCurrent = () => abortRef.current === controller && !controller.signal.aborted;
    try {
      setFlow({ status: "Requesting device code..." });
      const data = await apiFetch<CopilotDeviceCode>(
        "/api/settings/oauth/copilot/device-code",
        { method: "POST", signal: controller.signal }
      );
      if (!isCurrent()) return;

      setFlow({
        userCode: data.user_code,
        verificationUri: data.verification_uri,
        status: "Waiting for authorization in browser...",
      });
      window.open(data.verification_uri, "_blank");
      await pollCopilotDeviceFlow(
        data.device_code,
        data.interval,
        data.expires_in,
        (deviceCode, interval, signal) => apiFetch<CopilotPollResponse>(
          "/api/settings/oauth/copilot/poll",
          {
            method: "POST",
            body: JSON.stringify({ device_code: deviceCode, interval }),
            signal,
          }
        ),
        controller.signal
      );
      if (!isCurrent()) return;
      setFlow({ status: "Authenticated!" });
      successTimerRef.current = window.setTimeout(() => {
        if (!isCurrent()) return;
        successTimerRef.current = null;
        setFlow(null);
        refetch();
      }, 1500);
    } catch (error: unknown) {
      if (controller.signal.aborted || !isCurrent() || isCopilotAbort(error)) return;
      const message = error instanceof Error ? error.message : "GitHub Copilot authentication failed.";
      setFlow({ status: `Failed: ${message}` });
    }
  }, [cancel, refetch]);

  return { flow, start, cancel };
}
