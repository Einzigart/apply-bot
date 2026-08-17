import { ArrowUpDown, ArrowUp, ArrowDown } from "lucide-react";
import { cn, formatDateTime, formatDuration, parseCommand } from "../../lib/utils";
import { Badge } from "./core";

interface SortableHeaderProps {
  label: string;
  sortKey: string;
  currentSort: string;
  currentOrder: string;
  onSort: (key: string) => void;
  className?: string;
  align?: "left" | "center" | "right";
}

export function SortableHeader({
  label,
  sortKey,
  currentSort,
  currentOrder,
  onSort,
  className = "",
  align = "left",
}: SortableHeaderProps) {
  const isCurrent = currentSort === sortKey;
  const isAsc = isCurrent && currentOrder.toLowerCase() === "asc";
  const isDesc = isCurrent && currentOrder.toLowerCase() === "desc";

  return (
    <th
      onClick={() => onSort(sortKey)}
      className={cn(
        "py-2.5 px-4 text-xs font-normal text-neutral-500 select-none cursor-pointer hover:bg-neutral-100/70 transition-colors group",
        align === "right" && "text-right",
        align === "center" && "text-center",
        className
      )}
    >
      <div
        className={cn(
          "inline-flex items-center gap-1",
          align === "right" && "justify-end flex-row-reverse",
          align === "center" && "justify-center"
        )}
      >
        <span
          className={cn(
            "transition-colors",
            isCurrent ? "font-semibold text-neutral-900" : "group-hover:text-neutral-900"
          )}
        >
          {label}
        </span>
        {isCurrent ? (
          isAsc ? (
            <ArrowUp className="w-3 h-3 text-neutral-900 shrink-0" />
          ) : (
            <ArrowDown className="w-3 h-3 text-neutral-900 shrink-0" />
          )
        ) : (
          <ArrowUpDown className="w-3 h-3 text-neutral-300 group-hover:text-neutral-500 transition-colors shrink-0" />
        )}
      </div>
    </th>
  );
}

export function RunStatusBadge({
  finishedAt,
  notes,
  className,
}: {
  finishedAt?: string | null;
  notes?: string | null;
  className?: string;
}) {
  if (!finishedAt) {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200/80",
          className
        )}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-ping shrink-0" />
        <span>Running</span>
      </span>
    );
  }

  const isSuccess = notes === "ok" || !notes;
  const isInterrupted =
    notes?.toLowerCase().includes("interrupt") ||
    notes?.toLowerCase().includes("exit");
  const isCancelled = notes?.toLowerCase().includes("cancel");

  if (isSuccess) {
    return (
      <Badge variant="apply" className={className}>
        Completed
      </Badge>
    );
  }

  if (isCancelled) {
    return (
      <Badge variant="review" className={className}>
        Cancelled
      </Badge>
    );
  }

  if (isInterrupted) {
    return (
      <Badge variant="amber" className={className}>
        Interrupted
      </Badge>
    );
  }

  return (
    <Badge
      variant="danger"
      className={cn("max-w-[220px] truncate", className)}
      title={notes}
    >
      {notes.startsWith("error:") ? notes.replace(/^error:\s*/i, "") : notes}
    </Badge>
  );
}

export function CommandPill({ command }: { command: string }) {
  const parsed = parseCommand(command);

  return (
    <div className="flex flex-wrap items-center gap-1.5 font-mono text-xs">
      <span className="font-semibold text-neutral-900 bg-neutral-100 border border-neutral-200/80 px-2 py-0.5 rounded-md">
        {parsed.action}
      </span>
      {parsed.flags.map((f, idx) => (
        <span
          key={idx}
          className="text-[11px] text-neutral-600 bg-neutral-50 border border-neutral-200/50 px-1.5 py-0.5 rounded"
        >
          --{f.name}
          {f.value ? `=${f.value}` : ""}
        </span>
      ))}
    </div>
  );
}

export function RunDurationCell({
  startedAt,
  finishedAt,
}: {
  startedAt: string;
  finishedAt?: string | null;
}) {
  const duration = formatDuration(startedAt, finishedAt);
  const isRunning = !finishedAt;

  return (
    <div className="flex flex-col">
      <span
        className={cn(
          "font-mono text-xs",
          isRunning ? "text-blue-600 font-medium animate-pulse" : "text-neutral-700"
        )}
      >
        {duration}
      </span>
    </div>
  );
}

export function RunTimeCell({
  startedAt,
  finishedAt,
}: {
  startedAt: string;
  finishedAt?: string | null;
}) {
  const startFmt = formatDateTime(startedAt);
  const endFmt = formatDateTime(finishedAt);

  return (
    <div className="flex flex-col text-xs">
      <span className="font-medium text-neutral-800">{startFmt.date}</span>
      <span className="text-[11px] font-mono text-neutral-400">
        {startFmt.time}
        {endFmt.time && ` → ${endFmt.time}`}
      </span>
    </div>
  );
}
