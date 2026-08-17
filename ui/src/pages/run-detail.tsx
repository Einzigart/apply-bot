import { useEffect, useRef } from "react";
import { useParams, Link } from "react-router";
import { ArrowLeft, Square } from "lucide-react";
import { useRunDetail, useCancelRun } from "../api/hooks";
import { Card, Badge, Button } from "../components/ui/core";

export function RunDetailPage() {
  const { id } = useParams<{ id: string }>();
  const runId = parseInt(id || "0", 10);

  const { data, isLoading } = useRunDetail(runId);
  const cancelMutation = useCancelRun();
  const logRef = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight;
    }
  }, [data?.log]);

  if (isLoading || !data) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-6 bg-slate-200 rounded-xl w-32" />
        <div className="h-64 bg-slate-200 rounded-xl" />
      </div>
    );
  }

  const { run, log } = data;
  const isFinished = !!run.finished_at;

  return (
    <div className="space-y-6">
      {/* Top Nav */}
      <div className="flex items-center justify-between">
        <Link
          to="/runs"
          className="inline-flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-slate-900"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Runs</span>
        </Link>
        {!isFinished && (
          <Button
            variant="danger"
            size="sm"
            onClick={() => cancelMutation.mutate(runId)}
            disabled={cancelMutation.isPending}
          >
            <Square className="w-3.5 h-3.5 fill-current" />
            <span>Cancel Run</span>
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
            Started {run.started_at}
            {run.finished_at && ` · Finished ${run.finished_at}`}
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

      {/* Live Log Terminal Output */}
      <Card className="bg-slate-950 border-slate-900 overflow-hidden shadow-md">
        <div className="px-4 py-2 bg-slate-900 border-b border-slate-800 flex items-center justify-between text-xs text-slate-400 font-mono">
          <span>logs/runs/{run.id}.log</span>
          {!isFinished && (
            <span className="flex items-center gap-1.5 text-blue-400">
              <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
              Live Streaming
            </span>
          )}
        </div>
        <pre
          ref={logRef}
          className="p-4 text-xs font-mono text-slate-200 overflow-y-auto max-h-[60vh] min-h-[16rem] whitespace-pre-wrap leading-relaxed select-text"
        >
          {log || "(No log output recorded yet)"}
        </pre>
      </Card>
    </div>
  );
}
