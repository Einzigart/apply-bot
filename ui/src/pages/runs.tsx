import { useState, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { Play, Search, Terminal, ChevronRight, Filter, AlertCircle } from "lucide-react";
import { useRuns, useStartRun } from "../api/hooks";
import { Card, Button } from "../components/ui/core";
import {
  SortableHeader,
  RunStatusBadge,
  CommandPill,
  RunDurationCell,
  RunTimeCell,
} from "../components/ui/table-helpers";
import { cn } from "../lib/utils";

export function RunsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const sort = searchParams.get("sort") || "";
  const order = searchParams.get("order") || "";

  const { data, isLoading } = useRuns({
    sort: sort || undefined,
    order: order || undefined,
  });
  const startMutation = useStartRun();

  // Local filter states for instant table searching and status filtering
  const [searchFilter, setSearchFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "completed" | "running" | "failed">("all");
  const [runError, setRunError] = useState<string | null>(null);

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

  const [command, setCommand] = useState("pipeline");

  // Pipeline options
  const [pipelinePages, setPipelinePages] = useState(2);
  const [pipelineLimit, setPipelineLimit] = useState("");
  const [pipelineOffline, setPipelineOffline] = useState(true);
  const [pipelineCardsOnly, setPipelineCardsOnly] = useState(false);
  const [pipelineHeadless, setPipelineHeadless] = useState(true);
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
  const [applyHeadless, setApplyHeadless] = useState(true);
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

    setRunError(null);
    startMutation.mutate(payload, {
      onSuccess: (res) => {
        if (res.run_id) {
          navigate(`/runs/${res.run_id}`);
        }
      },
      onError: (err: any) => {
        setRunError(err.message || "A run is already in progress or failed to start.");
      },
    });
  };

  // Filter runs locally
  const filteredRuns = useMemo(() => {
    if (!data?.runs) return [];
    return data.runs.filter((r) => {
      // Status filter
      if (statusFilter === "completed" && (!r.finished_at || (r.notes && r.notes !== "ok"))) {
        return false;
      }
      if (statusFilter === "running" && r.finished_at) {
        return false;
      }
      if (statusFilter === "failed" && (!r.finished_at || r.notes === "ok")) {
        return false;
      }

      // Search query
      if (searchFilter.trim()) {
        const term = searchFilter.toLowerCase();
        const matchesId = String(r.id).includes(term);
        const matchesCmd = (r.command || "").toLowerCase().includes(term);
        const matchesNotes = (r.notes || "").toLowerCase().includes(term);
        return matchesId || matchesCmd || matchesNotes;
      }

      return true;
    });
  }, [data?.runs, statusFilter, searchFilter]);

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
          Runs
        </h1>
        <p className="text-sm text-neutral-500 mt-0.5">
          Execute automation pipelines and inspect execution logs
        </p>
      </div>

      {/* Trigger Form */}
      <Card className="p-5">
        <form onSubmit={handleSubmit} className="space-y-4">
          {runError && (
            <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 font-medium">
              <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
              <span>{runError}</span>
            </div>
          )}
          <div className="flex items-center justify-between">
            <h2 className="text-base font-semibold text-neutral-900">
              Start Execution
            </h2>
            <select
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              className="text-xs font-medium bg-neutral-100 border border-neutral-200 rounded-xl px-3 py-1.5 focus:outline-hidden focus:ring-1 focus:ring-neutral-800 cursor-pointer"
            >
              <option value="pipeline">Pipeline (Full Auto)</option>
              <option value="discover">Discover (Scrape Only)</option>
              <option value="score">Score</option>
              <option value="apply">Apply</option>
              <option value="calibrate">Calibrate</option>
            </select>
          </div>

          {command === "pipeline" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-neutral-100">
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-neutral-700 mb-1">
                    Pages per role
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={pipelinePages}
                    onChange={(e) => setPipelinePages(parseInt(e.target.value, 10))}
                    className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-1.5 focus:bg-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-neutral-700 mb-1">
                    Max applications cap
                  </label>
                  <input
                    type="number"
                    placeholder="Unlimited"
                    value={pipelineLimit}
                    onChange={(e) => setPipelineLimit(e.target.value)}
                    className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-1.5 focus:bg-white"
                  />
                </div>
              </div>

              <div className="space-y-2 text-xs text-neutral-600">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={pipelineOffline}
                    onChange={(e) => setPipelineOffline(e.target.checked)}
                    className="rounded border-neutral-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>Offline scorer (rule-based, no LLM)</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={pipelineCardsOnly}
                    onChange={(e) => setPipelineCardsOnly(e.target.checked)}
                    className="rounded border-neutral-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>Cards only (skip detail pages)</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={pipelineHeadless}
                    onChange={(e) => setPipelineHeadless(e.target.checked)}
                    className="rounded border-neutral-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>Headless browser</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={pipelineLlmLetter}
                    onChange={(e) => setPipelineLlmLetter(e.target.checked)}
                    className="rounded border-neutral-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>AI Cover Letter Tailoring</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer pt-2 border-t border-neutral-100 font-semibold text-red-600">
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
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-neutral-100">
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-neutral-700 mb-1">
                    Pages per role
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={discoverPages}
                    onChange={(e) => setDiscoverPages(parseInt(e.target.value, 10))}
                    className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-1.5 focus:bg-white"
                  />
                </div>
              </div>
              <div className="space-y-2 text-xs text-neutral-600">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={discoverCardsOnly}
                    onChange={(e) => setDiscoverCardsOnly(e.target.checked)}
                    className="rounded border-neutral-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>Cards only (skip detail pages)</span>
                </label>
              </div>
            </div>
          )}

          {command === "score" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-neutral-100">
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-neutral-700 mb-1">
                    Limit jobs to score
                  </label>
                  <input
                    type="number"
                    placeholder="All pending jobs"
                    value={scoreLimit}
                    onChange={(e) => setScoreLimit(e.target.value)}
                    className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-1.5 focus:bg-white"
                  />
                </div>
              </div>
              <div className="space-y-2 text-xs text-neutral-600">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={scoreOffline}
                    onChange={(e) => setScoreOffline(e.target.checked)}
                    className="rounded border-neutral-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>Offline scorer (rule-based, no LLM)</span>
                </label>
              </div>
            </div>
          )}

          {command === "apply" && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2 border-t border-neutral-100">
              <div className="space-y-3">
                <div>
                  <label className="block text-xs font-medium text-neutral-700 mb-1">
                    Application limit
                  </label>
                  <input
                    type="number"
                    min={1}
                    value={applyLimit}
                    onChange={(e) => setApplyLimit(e.target.value)}
                    className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-1.5 focus:bg-white"
                  />
                </div>
              </div>
              <div className="space-y-2 text-xs text-neutral-600">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={applyHeadless}
                    onChange={(e) => setApplyHeadless(e.target.checked)}
                    className="rounded border-neutral-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>Headless browser</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={applyLlmLetter}
                    onChange={(e) => setApplyLlmLetter(e.target.checked)}
                    className="rounded border-neutral-300 text-blue-600 focus:ring-blue-500"
                  />
                  <span>AI Cover Letter Tailoring</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer pt-2 border-t border-neutral-100 font-semibold text-red-600">
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
            <div className="pt-2 border-t border-neutral-100 text-xs text-neutral-500">
              Re-checks historical application records against current filtering rules to identify any discrepancies. No extra parameters needed.
            </div>
          )}

          <div className="pt-2 flex items-center justify-between">
            <span className="text-xs text-neutral-400">
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
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold tracking-tight text-neutral-900">
              Run History
            </h2>
            <span className="text-xs text-neutral-400 font-mono">
              ({filteredRuns.length} {filteredRuns.length === 1 ? "run" : "runs"})
            </span>
          </div>

          {/* Filter and Search Bar */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Status Pills */}
            <div className="flex items-center gap-1 bg-neutral-100 p-1 rounded-xl border border-neutral-200/80">
              {(
                [
                  { id: "all", label: "All" },
                  { id: "completed", label: "Completed" },
                  { id: "running", label: "Running" },
                  { id: "failed", label: "Failed / Interrupted" },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setStatusFilter(tab.id)}
                  className={cn(
                    "px-3 py-1.5 text-xs font-medium rounded-xl transition-all cursor-pointer",
                    statusFilter === tab.id
                      ? "bg-white text-neutral-900 shadow-2xs font-semibold"
                      : "text-neutral-600 hover:text-neutral-900"
                  )}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* Quick Search */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
              <input
                type="search"
                placeholder="Search run ID, command..."
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                className="w-48 pl-8 pr-2.5 py-1.5 text-xs bg-white border border-neutral-200 rounded-xl focus:outline-hidden focus:ring-1 focus:ring-neutral-800"
              />
            </div>
          </div>
        </div>

        <Card>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm border-collapse">
              <thead className="bg-neutral-50/80 text-xs font-medium text-neutral-500 border-b border-neutral-200/80">
                <tr>
                  <SortableHeader
                    label="Run ID"
                    sortKey="id"
                    currentSort={sort}
                    currentOrder={order}
                    onSort={handleSort}
                    className="w-20"
                  />
                  <SortableHeader
                    label="Command & Options"
                    sortKey="command"
                    currentSort={sort}
                    currentOrder={order}
                    onSort={handleSort}
                  />
                  <SortableHeader
                    label="Time"
                    sortKey="started_at"
                    currentSort={sort}
                    currentOrder={order}
                    onSort={handleSort}
                  />
                  <SortableHeader
                    label="Duration"
                    sortKey="finished_at"
                    currentSort={sort}
                    currentOrder={order}
                    onSort={handleSort}
                    className="w-24"
                  />
                  <SortableHeader
                    label="Status"
                    sortKey="notes"
                    currentSort={sort}
                    currentOrder={order}
                    onSort={handleSort}
                  />
                  <th className="py-2.5 px-4 w-10"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-neutral-100">
                {isLoading ? (
                  <tr>
                    <td colSpan={6} className="py-12 text-center text-sm text-neutral-400">
                      Loading runs...
                    </td>
                  </tr>
                ) : filteredRuns.map((r) => (
                  <tr
                    key={r.id}
                    className="group hover:bg-neutral-50/80 transition-colors cursor-pointer"
                    onClick={() => navigate(`/runs/${r.id}`)}
                  >
                    <td className="py-3 px-3.5 font-mono text-xs font-medium text-neutral-500 group-hover:text-neutral-900">
                      #{r.id}
                    </td>
                    <td className="py-3 px-3.5">
                      <CommandPill command={r.command} />
                    </td>
                    <td className="py-3 px-3.5">
                      <RunTimeCell startedAt={r.started_at} finishedAt={r.finished_at} />
                    </td>
                    <td className="py-3 px-3.5">
                      <RunDurationCell startedAt={r.started_at} finishedAt={r.finished_at} />
                    </td>
                    <td className="py-3 px-3.5">
                      <RunStatusBadge finishedAt={r.finished_at} notes={r.notes} />
                    </td>
                    <td className="py-3 px-3.5 text-right text-neutral-400 group-hover:text-neutral-700">
                      <ChevronRight className="w-4 h-4 ml-auto transition-transform group-hover:translate-x-0.5 duration-120" />
                    </td>
                  </tr>
                ))}
                {!isLoading && filteredRuns.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-12 text-center text-sm text-neutral-400">
                      <div className="flex flex-col items-center justify-center gap-2">
                        {data?.runs.length === 0 ? (
                          <>
                            <Terminal className="w-8 h-8 text-neutral-300 stroke-[1.5]" />
                            <span className="font-medium text-neutral-600">No runs recorded yet</span>
                            <span className="text-xs text-neutral-400">Execute a command above to start your first run</span>
                          </>
                        ) : (
                          <>
                            <Filter className="w-8 h-8 text-neutral-300 stroke-[1.5]" />
                            <span className="font-medium text-neutral-600">No runs match your filter</span>
                            <button
                              type="button"
                              onClick={() => {
                                setStatusFilter("all");
                                setSearchFilter("");
                              }}
                              className="text-xs text-blue-600 hover:underline cursor-pointer"
                            >
                              Reset filters
                            </button>
                          </>
                        )}
                      </div>
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
