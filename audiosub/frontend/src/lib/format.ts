/** 83.456 -> "01:23.456" (or "1:01:23.456" past an hour). */
export function formatTime(seconds: number, withMs = true): string {
  if (!Number.isFinite(seconds) || seconds < 0) seconds = 0;
  const totalMs = Math.round(seconds * 1000);
  const h = Math.floor(totalMs / 3_600_000);
  const m = Math.floor((totalMs % 3_600_000) / 60_000);
  const s = Math.floor((totalMs % 60_000) / 1000);
  const ms = totalMs % 1000;
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  const base = h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
  return withMs ? `${base}.${String(ms).padStart(3, "0")}` : base;
}

/** "01:02:03.5", "2:03,250", "83.4" -> seconds; null when unparseable. */
export function parseTime(input: string): number | null {
  const text = input.trim().replace(",", ".");
  if (!text) return null;
  const parts = text.split(":");
  if (parts.length > 3) return null;
  let total = 0;
  for (const part of parts) {
    if (!/^\d+(\.\d+)?$/.test(part)) return null;
    total = total * 60 + parseFloat(part);
  }
  return Math.round(total * 1000) / 1000;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const t = Math.round(seconds);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(Math.floor(t / 3600))}:${pad(Math.floor((t % 3600) / 60))}:${pad(t % 60)}`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  const units = ["B", "KB", "MB", "GB"];
  let v = bytes;
  let i = 0;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getDate()).padStart(2, "0")}/${String(d.getMonth() + 1).padStart(2, "0")}/${d.getFullYear()}`;
}
