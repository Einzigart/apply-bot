import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { Play, ArrowUpDown } from "lucide-react";
import { useRuns, useStartRun } from "../api/hooks";
import { Card, Badge, Button } from "../components/ui/core";
import { cn } from "../lib/utils";

export function RunsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const sort = searchParams.get("sort") || "";
  const order = searchParams.get("order") || "";

  const { data } = useRuns({
    sort: sort || undefined,
    order: order || undefined,
  });
  const startMutation = useStartRun();

  const handleSort = (key: string) => {
    const next = new URLSearchParams(searchParams);
    if (sort === key) {
      next.set("order", order === "asc" ? "desc" : "asc");
    } else {
      next.set("sort", key);
      next.set("order", "desc");
    }
    setSearchParams(next);
  };

  const renderSortableHeader = (
    label: string,
    key: string,
    className: string = ""
  ) => {
    const isCurrent = sort === key;
    return (
      <th
        onClick={() => handleSort(key)}
        className={cn(
          "py-2.5 px-4 font-normal cursor-pointer select-none hover:bg-slate-100 transition-colors group",
          className
        )}
      >
        <div className="flex items-center gap-1">
          <span
            className={cn(
              "group-hover:text-slate-900 transition-colors",
              isCurrent ? "font-semibold text-slate-900" : ""
            )}
          >
            {label}
          </span>
          <ArrowUpDown
            className={cn(
              "w-3 h-3 transition-colors",
              isCurrent
                ? "text-slate-900"
                : "text-slate-300 group-hover:text-slate-500"
            )}
          />
        </div>
      </th>
    );
  };

  const [command, setCommand] = useState("pipeline");

  // Pipeline options
  const [pipelinePages, setPipelinePages] = useState(2);
  const [pipelineLimit, setPipelineLimit] = useState("");
  const [pipelineOffline, setPipelineOffline] = useState(true);
  const [pipelineCardsOnly, setPipelineCardsOnly] = useState(false);
  const [pipelineHeadless, setPipelineHeadless] = useState(false);
  const [pipelineLlmLetter, setPipelineLlmLetter] = useState(false);
  const [pipelineExecute, setPipelineExecute] = useState(false);

  // Discover options
  const [discoverPages, setDiscoverPages] = useState(2);
  const [discoverCardsOnly, setDiscoverCardsOnly] = useState(false);

  // Score options
  const [scoreOffline, setScoreOffline] = useState(true);
  const [scoreLimit, setScoreLimit] = useState("");

  // Apply options
  const [applyLimit, setApplyLimit] = useState("10");
  const [applyHeadless, setApplyHeadless] = useState(false);
  const [applyLlmLetter, setApplyLlmLetter] = useState(false);
  const [applyExecute, setApplyExecute] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const isExecutingReal =
      (command === "pipeline" && pipelineExecute) ||
      (command === "apply" && applyExecute);

    if (isExecutingReal && !confirm("This submits REAL job applications. Continue?")) {
      return;
    }

    const payload: any = { command };
    if (command === "pipeline") {
      payload.pipeline_pages = pipelinePages;
      if (pipelineLimit) payload.pipeline_limit = parseInt(pipelineLimit, 10);
      payload.pipeline_offline = pipelineOffline;
      payload.pipeline_cards_only = pipelineCardsOnly;
      payload.pipeline_headless = pipelineHeadless;
      payload.pipeline_llm_letter = pipelineLlmLetter;
      payload.pipeline_execute = pipelineExecute;
    } else if (command === "discover") {
      payload.discover_pages = discoverPages;
      payload.discover_cards_only = discoverCardsOnly;
    } else if (command === "score") {
      payload.score_offline = scoreOffline;
      if (scoreLimit) payload.score_limit = parseInt(scoreLimit, 10);
    } else if (command === "apply") {
      if (applyLimit) payload.apply_limit = parseInt(applyLimit, 10);
      payload.apply_headless = applyHeadless;
      payload.apply_llm_letter = applyLlmLetter;
      payload.apply_execute = applyExecute;
    }

    startMutation.mutate(payload, {
      onSuccess: (res) => {
        if (res.run_id) {
          navigate(`/runs/${res.run_id}`);
        }
      },
    });
  };

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Runs
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Execute automation pipelines and inspect execution logs
        </p>
      </div>

      {/* Trigger Form */}
      <Card className="p-5">
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-slate-900">
              Start Execution
            </h2>
            <select
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              className="text-xs font-medium bg-slate-100 border border-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-hidden focus:ring-1 focus:ring-blue-500"
            >
              <option value="pipeline">Pipeline (Full Auto)</option>
              <option value="discover">Discover (Scrape Only)</option>
              <option value="score">Score</option>
              <option value="apply">Apply</option>
              <option value="calibrate">Calibrate</option>
            </select>
          </div>

          {command === "pipeline" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-slate-100">
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Pages per role
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={pipelinePages}
                    onChange={(e) => setPipelinePages(parseInt(e.target.value, 10))}
                    className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Max applications cap
                  </label>
                  <input
                    type="number"
                    placeholder="Unlimited"
                    value={pipelineLimit}
                    onChange={(e) => setPipelineLimit(e.target.value)}
                    className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5"
                  />
                </div>
              </div>

              <div className="space-y-2 text-xs text-slate-600">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={pipelineOffline}
                    onChange={(e) => setPipelineOffline(e.target.checked)}
                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>Offline scorer (rule-based, no LLM)</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={pipelineCardsOnly}
                    onChange={(e) => setPipelineCardsOnly(e.target.checked)}
                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>Cards only (skip detail pages)</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={pipelineHeadless}
                    onChange={(e) => setPipelineHeadless(e.target.checked)}
                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>Headless browser</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={pipelineLlmLetter}
                    onChange={(e) => setPipelineLlmLetter(e.target.checked)}
                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>AI Cover Letter Tailoring</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer pt-2 border-t border-slate-100 font-semibold text-red-600">
                  <input
                    type="checkbox"
                    checked={pipelineExecute}
                    onChange={(e) => setPipelineExecute(e.target.checked)}
                    className="rounded border-red-300 text-red-600 focus:ring-red-500"
                  />
                  <span>Execute Real Applications (Unchecked = Dry Run)</span>
                </label>
              </div>
            </div>
          )}

          {command === "discover" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-slate-100">
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Pages per role
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={discoverPages}
                    onChange={(e) => setDiscoverPages(parseInt(e.target.value, 10))}
                    className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5"
                  />
                </div>
              </div>
              <div className="space-y-2 text-xs text-slate-600">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={discoverCardsOnly}
                    onChange={(e) => setDiscoverCardsOnly(e.target.checked)}
                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>Cards only (skip detail pages)</span>
                </label>
              </div>
            </div>
          )}

          {command === "score" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-slate-100">
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Limit jobs to score
                  </label>
                  <input
                    type="number"
                    placeholder="All pending jobs"
                    value={scoreLimit}
                    onChange={(e) => setScoreLimit(e.target.value)}
                    className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5"
                  />
                </div>
              </div>
              <div className="space-y-2 text-xs text-slate-600">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={scoreOffline}
                    onChange={(e) => setScoreOffline(e.target.checked)}
                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>Offline scorer (rule-based, no LLM)</span>
                </label>
              </div>
            </div>
          )}

          {command === "apply" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-slate-100">
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Application limit
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={applyLimit}
                    onChange={(e) => setApplyLimit(e.target.value)}
                    className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5"
                  />
                </div>
              </div>
              <div className="space-y-2 text-xs text-slate-600">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={applyHeadless}
                    onChange={(e) => setApplyHeadless(e.target.checked)}
                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>Headless browser</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={applyLlmLetter}
                    onChange={(e) => setApplyLlmLetter(e.target.checked)}
                    className="rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>AI Cover Letter Tailoring</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer pt-2 border-t border-slate-100 font-semibold text-red-600">
                  <input
                    type="checkbox"
                    checked={applyExecute}
                    onChange={(e) => setApplyExecute(e.target.checked)}
                    className="rounded border-red-300 text-red-600 focus:ring-red-500"
                  />
                  <span>Execute Real Applications (Unchecked = Dry Run)</span>
                </label>
              </div>
            </div>
          )}

          {command === "calibrate" && (
            <div className="pt-2 border-t border-slate-100 text-xs text-slate-500">
              Re-checks historical application records against current filtering rules to identify any discrepancies. No extra parameters needed.
            </div>
          )}

          <div className="pt-2 flex items-center justify-between">
            <span className="text-xs text-slate-400">
              Headed browser opens on localhost
            </span>
            <Button
              type="submit"
              size="sm"
              disabled={startMutation.isPending}
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>{startMutation.isPending ? "Starting..." : "Start Run"}</span>
            </Button>
          </div>
        </form>
      </Card>

      {/* History */}
      <div className="space-y-3">
        <h2 className="text-base font-semibold tracking-tight text-slate-900">
          Run History
        </h2>
        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50/75 text-xs font-medium text-slate-500 border-b border-slate-200">
                <tr>
                  {renderSortableHeader("No.", "id")}
                  {renderSortableHeader("Command", "command")}
                  {renderSortableHeader("Started", "started_at")}
                  {renderSortableHeader("Finished", "finished_at")}
                  {renderSortableHeader("Status", "notes")}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data?.runs.map((r) => (
                  <tr
                    key={r.id}
                    className="hover:bg-slate-50/60 transition-colors cursor-pointer"
                    onClick={() => navigate(`/runs/${r.id}`)}
                  >
                    <td className="py-3 px-4 font-mono text-xs text-slate-400">
                      {r.id}
                    </td>
                    <td className="py-3 px-4 font-medium text-slate-900">
                      <code className="text-xs bg-slate-100 px-2 py-0.5 rounded text-slate-700 font-mono">
                        {r.command}
                      </code>
                    </td>
                    <td className="py-3 px-4 text-xs text-slate-500">
                      {r.started_at}
                    </td>
                    <td className="py-3 px-4 text-xs text-slate-500">
                      {r.finished_at || "—"}
                    </td>
                    <td className="py-3 px-4">
                      {r.finished_at ? (
                        r.notes === "ok" ? (
                          <Badge variant="apply">Completed</Badge>
                        ) : (
                          <Badge variant="danger">{r.notes || "Error"}</Badge>
                        )
                      ) : (
                        <Badge variant="running">Running</Badge>
                      )}
                    </td>
                  </tr>
                ))}
                {data?.runs.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-12 text-center text-sm text-slate-400">
                      No runs recorded yet
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
