import type { StreamMessage } from "./types";

export type ConnectionState = "connecting" | "open" | "closed";

export interface StreamHandlers {
  onMessage: (msg: StreamMessage) => void;
  onState: (state: ConnectionState) => void;
}

/** WebSocket client with exponential-backoff reconnect. */
export class StreamClient {
  private ws: WebSocket | null = null;
  private attempt = 0;
  private timer: number | null = null;
  private stopped = false;

  constructor(
    private readonly url: string,
    private readonly handlers: StreamHandlers,
  ) {}

  start(): void {
    this.stopped = false;
    this.connect();
  }

  stop(): void {
    this.stopped = true;
    if (this.timer !== null) window.clearTimeout(this.timer);
    this.ws?.close();
    this.ws = null;
  }

  send(payload: unknown): boolean {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
      return true;
    }
    return false;
  }

  private connect(): void {
    this.handlers.onState("connecting");
    const ws = new WebSocket(this.url);
    this.ws = ws;
    ws.onopen = () => {
      this.attempt = 0;
      this.handlers.onState("open");
    };
    ws.onmessage = (ev) => {
      try {
        this.handlers.onMessage(JSON.parse(ev.data as string) as StreamMessage);
      } catch (err) {
        console.warn("bad stream message", err);
      }
    };
    ws.onclose = () => {
      this.handlers.onState("closed");
      if (!this.stopped) this.scheduleReconnect();
    };
    ws.onerror = () => ws.close();
  }

  private scheduleReconnect(): void {
    const delay = Math.min(10_000, 500 * 2 ** this.attempt++);
    this.timer = window.setTimeout(() => this.connect(), delay);
  }
}

export function streamUrl(path = "/ws/stream"): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${path}`;
}
