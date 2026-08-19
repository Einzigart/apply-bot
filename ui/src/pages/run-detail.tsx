import { useEffect, useRef, useMemo } from "react";
import { useParams, Link } from "react-router";
import { ArrowLeft, Square, AlertCircle, Loader2 } from "lucide-react";
import { useRunDetail, useCancelRun } from "../api/hooks";
import { Card, Badge, Button } from "../components/ui/core";
import { formatDateTime } from "../lib/utils";

export function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const runId = parseInt(id || "0", 10);

  const { data, isLoading, isError, error } = useRunDetail(runId);
  const cancelMutation = useCancelRun();
  const logRef = useRef<HTMLPreElement>(null);

  // Auto-scroll when new log entries arrive while user hasn't explicitly scrolled up
  useEffect(() => {
    if (logRef.current) {
      const el = logRef.current;
      el.scrollTop = el.scrollHeight;
    }
  }, [data?.log]);

  const { run, log } = data || {};
  const isFinished = !!run?.finished_at;

  const startedFmt = formatDateTime(run?.started_at);
  const finishedFmt = formatDateTime(run?.finished_at);

  // Extract current operational step and last line for human-friendly active status
  const activeStatus = useMemo(() => {
    if (!log) return "Starting runner process...";
    const lines = log.trim().split("\n").filter((l) => l.trim().length > 0);
    if (lines.length === 0) return "Starting runner process...";

    const lastLine = lines[lines.length - 1];

    if (lastLine.includes("Discovering jobs") || lastLine.includes("Fetching /id/job")) {
      return "Scraping job listings from Jobstreet...";
    }
    if (lastLine.includes("Scoring") || lastLine.includes("[Score") || lastLine.includes("LLM")) {
      return "Scoring jobs with AI...";
    }
    if (lastLine.includes("Generating answers") || lastLine.includes("Writing cover letter") || lastLine.includes("Navigating to job page")) {
      return "Preparing application and cover letter...";
    }
    if (lastLine.includes("Submitting application") || lastLine.includes("Verifying application")) {
      return "Submitting application on Jobstreet...";
    }
    if (lastLine.includes("Pipeline Summary") || lastLine.includes("SUBMITTED") || lastLine.includes("DRY-RUN")) {
      return "Saving results...";
    }

    // Clean up arrow prefixes
    return lastLine.replace(/^(\s*->\s*|\s*\[\d+\/\d+\]\s*)/, "").trim();
  }, [log]);

  if (isError) {
    return (
      <div className="space-y-4">
        <Link
          to="/runs"
          className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-900"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to runs</span>
        </Link>
        <Card className="p-6 text-center space-y-3 border-red-200 bg-red-50/50">
          <div className="inline-flex p-2 bg-red-100 rounded-full text-red-600">
            <AlertCircle className="w-5 h-5" />
          </div>
          <div className="space-y-1">
            <p className="text-sm font-semibold text-red-900">Run #{runId} not found</p>
            <p className="text-xs text-red-600">{(error as any)?.message || "The requested run does not exist or has been deleted."}</p>
          </div>
        </Card>
      </div>
    );
  }

  if (isLoading || !data || !run) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-6 bg-slate-200 rounded-xl w-32" />
        <div className="h-64 bg-slate-200 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Top Nav */}
      <div className="flex items-center justify-between">
        <Link
          to="/runs"
          className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-900"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to runs</span>
        </Link>
        {!isFinished && (
          <Button
            variant="danger"
            size="sm"
            onClick={() => cancelMutation.mutate(runId)}
            disabled={cancelMutation.isPending}
          >
            <Square className="w-3.5 h-3.5 fill-current" />
            <span>Cancel run</span>
          </Button>
        )}
      </div>

      {/* Run Summary Header */}
      <Card className="p-4 flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-bold text-slate-900">
              Run #{run.id}
            </h1>
            <code className="text-xs bg-slate-100 px-2.5 py-0.5 rounded-xl text-slate-700 font-mono">
              {run.command}
            </code>
          </div>
          <div className="text-xs text-slate-500">
            Started {startedFmt.full}
            {run.finished_at && ` · Finished ${finishedFmt.full}`}
          </div>
        </div>

        <div>
          {isFinished ? (
            run.notes === "ok" ? (
              <Badge variant="apply">Completed</Badge>
            ) : (
              <Badge variant="danger">{run.notes || "Error"}</Badge>
            )
          ) : (
            <Badge variant="running">Running</Badge>
          )}
        </div>
      </Card>

      {/* Active Animated Step Banner when running */}
      {!isFinished && (
        <div className="relative overflow-hidden rounded-xl border border-blue-200/90 bg-gradient-to-r from-blue-50/90 via-indigo-50/70 to-blue-50/90 p-3.5 shadow-2xs">
          {/* Shimmer loading bar at top edge */}
          <div className="absolute top-0 left-0 right-0 h-[2px] bg-blue-200/50 overflow-hidden">
            <div className="h-full w-1/3 bg-blue-600 rounded-full animate-shimmer" />
          </div>

          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="relative flex items-center justify-center w-6 h-6 rounded-lg bg-blue-600 text-white shrink-0 shadow-2xs">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] font-semibold uppercase tracking-wider text-blue-900">
                    Current step
                  </span>
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-600 animate-ping" />
                </div>
                <p className="text-xs font-medium text-blue-950 truncate mt-0.5">
                  {activeStatus}
                </p>
              </div>
            </div>

            <div className="shrink-0 flex items-center gap-2">
              <span className="text-[11px] text-blue-700/80 font-mono hidden sm:inline-block">
                Running in background...
              </span>
            </div>
          </div>
        </div>
      )}

      {/* Live Log Terminal Output */}
      <Card className="bg-slate-950 border-slate-900 overflow-hidden shadow-md">
        <div className="px-4 py-2 bg-slate-900 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400 font-mono">
          <span className="text-slate-400 font-mono">logs/runs/{run.id}.log</span>
        </div>
        <pre
          ref={logRef}
          className="p-4 text-xs font-mono text-slate-200 overflow-y-auto max-h-[60vh] min-h-[16rem] whitespace-pre-wrap leading-relaxed select-text"
        >
          {log || "(No log output recorded yet)"}
          {!isFinished && (
            <span className="inline-block w-2 h-4 ml-1 bg-blue-400 align-middle animate-cursor" />
          )}
        </pre>
      </Card>
    </div>
  );
}
