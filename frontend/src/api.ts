export type Status = any;

const json = async (url: string, init?: RequestInit) => {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
};

export const api = {
  status: () => json("/api/status"),
  devices: () => json("/api/devices"),
  connect: (body: object) => json("/api/connect", { method: "POST", body: JSON.stringify(body) }),
  disconnect: () => json("/api/disconnect", { method: "POST", body: "{}" }),
  camera: (body: object) => json("/api/camera", { method: "POST", body: JSON.stringify(body) }),
  preview: (body: object = {}) => json("/api/preview", { method: "POST", body: JSON.stringify(body) }),
  solve: (sync = false) => json("/api/solve", { method: "POST", body: JSON.stringify({ sync }) }),
  goto: (body: object) => json("/api/goto", { method: "POST", body: JSON.stringify(body) }),
  slew: (direction: string, rate = 1) => json("/api/slew", { method: "POST", body: JSON.stringify({ direction, rate }) }),
  park: () => json("/api/park", { method: "POST", body: "{}" }),
  tracking: (on: boolean) => json("/api/tracking", { method: "POST", body: JSON.stringify({ on }) }),
  focus: (body: object) => json("/api/focus", { method: "POST", body: JSON.stringify(body) }),
  autofocus: () => json("/api/autofocus", { method: "POST", body: "{}" }),
  filter: (index: number) => json("/api/filter", { method: "POST", body: JSON.stringify({ index }) }),
  power: (port: number, on: boolean) => json("/api/power", { method: "POST", body: JSON.stringify({ port, on }) }),
  guideStart: () => json("/api/guide/start", { method: "POST", body: "{}" }),
  guideStop: () => json("/api/guide/stop", { method: "POST", body: "{}" }),
  polarStart: () => json("/api/polar/start", { method: "POST", body: "{}" }),
  polarCapture: () => json("/api/polar/capture", { method: "POST", body: "{}" }),
  polarAdjust: (az: number, alt: number) => json("/api/polar/adjust", { method: "POST", body: JSON.stringify({ az, alt }) }),
  autorunStart: (body: object) => json("/api/autorun/start", { method: "POST", body: JSON.stringify(body) }),
  autorunStop: () => json("/api/autorun/stop", { method: "POST", body: "{}" }),
  autorunPause: (paused: boolean) => json("/api/autorun/pause", { method: "POST", body: JSON.stringify({ paused }) }),
  images: () => json("/api/images"),
  catalog: (q = "") => json(`/api/catalog?q=${encodeURIComponent(q)}`),
  atlas: () => json("/api/atlas"),
  stackReset: () => json("/api/stack/reset", { method: "POST", body: "{}" }),
};

export function wsUrl() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}/ws`;
}
