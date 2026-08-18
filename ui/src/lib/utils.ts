import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number | string | undefined | null) {
  if (!amount) return "—";
  const num = typeof amount === "string" ? parseInt(amount.replace(/[^0-9]/g, ""), 10) : amount;
  if (isNaN(num)) return String(amount);
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
  }).format(num);
}

/**
 * Format ISO or DB timestamp into readable, elegant date + time.
 * Handles "2026-08-16T21:46:14" or "2026-08-16 21:46:14"
 */
export function formatDateTime(dateStr?: string | null): { date: string; time: string; full: string } {
  if (!dateStr) return { date: "—", time: "", full: "—" };
  try {
    const cleanStr = dateStr.replace(" ", "T");
    const d = new Date(cleanStr);
    if (isNaN(d.getTime())) {
      return { date: dateStr, time: "", full: dateStr };
    }
    
    // Format: Aug 16, 2026
    const date = d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
    // Format: 21:46:14
    const time = d.toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
    return { date, time, full: `${date} ${time}` };
  } catch {
    return { date: dateStr, time: "", full: dateStr };
  }
}

/**
 * Calculate human-readable duration between two ISO timestamps.
 * e.g., "15s", "2m 10s", "1h 4m"
 */
export function formatDuration(startStr?: string | null, endStr?: string | null): string {
  if (!startStr) return "—";
  try {
    const s = new Date(startStr.replace(" ", "T")).getTime();
    const e = endStr ? new Date(endStr.replace(" ", "T")).getTime() : Date.now();
    if (isNaN(s) || isNaN(e) || e < s) return "—";
    
    const diffSec = Math.floor((e - s) / 1000);
    if (diffSec < 60) return `${diffSec}s`;
    
    const minutes = Math.floor(diffSec / 60);
    const remainingSec = diffSec % 60;
    if (minutes < 60) {
      return remainingSec > 0 ? `${minutes}m ${remainingSec}s` : `${minutes}m`;
    }
    
    const hours = Math.floor(minutes / 60);
    const remMin = minutes % 60;
    return remMin > 0 ? `${hours}h ${remMin}m` : `${hours}h`;
  } catch {
    return "—";
  }
}

export interface ParsedCommand {
  action: string;
  args: string[];
  flags: Array<{ name: string; value?: string }>;
  isDryRun: boolean;
  isOffline: boolean;
}

/**
 * Parse CLI command string into structured parts for clean badge/tag rendering.
 * e.g. "src.run pipeline --pages 2 --offline"
 */
export function parseCommand(rawCmd: string): ParsedCommand {
  const parts = rawCmd.trim().split(/\s+/);
  let action = "run";
  const args: string[] = [];
  const flags: Array<{ name: string; value?: string }> = [];
  
  // Skip "src.run" or "python -m src.run" prefix if present
  let i = 0;
  while (i < parts.length && (parts[i] === "python" || parts[i] === "-m" || parts[i] === "src.run" || parts[i].endsWith(".py"))) {
    i++;
  }
  
  if (i < parts.length && !parts[i].startsWith("-")) {
    action = parts[i];
    i++;
  }

  let isOffline = false;
  let isDryRun = true;

  while (i < parts.length) {
    const part = parts[i];
    if (part.startsWith("--")) {
      const flagName = part.slice(2);
      if (flagName === "offline") isOffline = true;
      if (flagName === "execute") isDryRun = false;

      // Check if next item is a value (doesn't start with --)
      if (i + 1 < parts.length && !parts[i + 1].startsWith("-")) {
        flags.push({ name: flagName, value: parts[i + 1] });
        i += 2;
      } else {
        flags.push({ name: flagName });
        i++;
      }
    } else {
      args.push(part);
      i++;
    }
  }

  return { action, args, flags, isDryRun, isOffline };
}

/**
 * Detect whether the app is running inside macOS Electron (where traffic light buttons need spacer area).
 */
export function isMacElectron(): boolean {
  if (typeof window === "undefined") return false;
  const api = (window as unknown as { electronAPI?: { platform?: string; isElectron?: boolean } }).electronAPI;
  if (api?.platform) {
    return api.platform === "darwin";
  }
  return /Macintosh|Mac OS X/i.test(navigator.userAgent);
}

