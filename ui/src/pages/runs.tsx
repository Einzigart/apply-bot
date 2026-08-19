import { useState, useMemo } from "react";
import { useNavigate, useSearchParams } from "react-router";
import {
  Play,
  Search,
  Terminal,
  ChevronRight,
  Filter,
  AlertCircle,
  Zap,
  Layers,
  Sliders,
  Send,
  Scale,
  ShieldCheck,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { useRuns, useStartRun } from "../api/hooks";
import { Card, Button, InfoTooltip, Badge } from "../components/ui/core";
import {
  SortableHeader,
  RunStatusBadge,
  CommandPill,
  RunDurationCell,
  RunTimeCell,
} from "../components/ui/table-helpers";
import { cn } from "../lib/utils";

interface RunTypeDefinition {
  id: string;
  name: string;
  shortDesc: string;
  tooltip: string;
  icon: typeof Zap;
}

const RUN_TYPES: RunTypeDefinition[] = [
  {
    id: "pipeline",
    name: "Pipeline",
    shortDesc: "Scrape, score, and apply",
    tooltip:
      "Scrapes job listings, filters and scores each match, and prepares or submits applications.",
    icon: Zap,
  },
  {
    id: "discover",
    name: "Discover",
    shortDesc: "Scrape only",
    tooltip:
      "Scrapes job listings from Jobstreet for target roles and locations into the database.",
    icon: Layers,
  },
  {
    id: "score",
    name: "Score",
    shortDesc: "Score pending",
    tooltip:
      "Evaluates pending jobs against your profile and salary preferences without scraping new listings.",
    icon: Sliders,
  },
  {
    id: "apply",
    name: "Apply",
    shortDesc: "Submit applications",
    tooltip:
      "Submits applications for jobs marked with the apply decision.",
    icon: Send,
  },
  {
    id: "calibrate",
    name: "Calibrate",
    shortDesc: "Audit rules",
    tooltip:
      "Tests current filters against historical applications to detect rule discrepancies.",
    icon: Scale,
  },
];

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

  // Active command preview string
  const commandPreview = useMemo(() => {
    const parts = ["src.run", command];
    if (command === "pipeline") {
      if (pipelinePages) parts.push(`--pages ${pipelinePages}`);
      if (pipelineLimit) parts.push(`--limit ${pipelineLimit}`);
      if (pipelineCardsOnly) parts.push("--cards-only");
      if (pipelineOffline) parts.push("--offline");
      if (pipelineLlmLetter) parts.push("--llm-letter");
      if (pipelineHeadless) parts.push("--headless");
      if (pipelineExecute) parts.push("--execute");
    } else if (command === "discover") {
      if (discoverPages) parts.push(`--pages ${discoverPages}`);
      if (discoverCardsOnly) parts.push("--cards-only");
    } else if (command === "score") {
      if (scoreOffline) parts.push("--offline");
      if (scoreLimit) parts.push(`--limit ${scoreLimit}`);
    } else if (command === "apply") {
      if (applyLimit) parts.push(`--limit ${applyLimit}`);
      if (applyHeadless) parts.push("--headless");
      if (applyLlmLetter) parts.push("--llm-letter");
      if (applyExecute) parts.push("--execute");
    }
    return parts.join(" ");
  }, [
    command,
    pipelinePages,
    pipelineLimit,
    pipelineOffline,
    pipelineCardsOnly,
    pipelineHeadless,
    pipelineLlmLetter,
    pipelineExecute,
    discoverPages,
    discoverCardsOnly,
    scoreOffline,
    scoreLimit,
    applyLimit,
    applyHeadless,
    applyLlmLetter,
    applyExecute,
  ]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    const isExecutingReal =
      (command === "pipeline" && pipelineExecute) ||
      (command === "apply" && applyExecute);

    if (isExecutingReal && !confirm("This submits REAL job applications to Jobstreet. Continue?")) {
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

  const activeRunType = RUN_TYPES.find((t) => t.id === command) || RUN_TYPES[0];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
          Runs
        </h1>
        <p className="text-sm text-neutral-500 mt-0.5">
          Execute automation pipelines and inspect logs
        </p>
      </div>

      {/* Trigger Form */}
      <Card className="p-5 border-neutral-200/90 shadow-2xs">
        <form onSubmit={handleSubmit} className="space-y-5">
          {runError && (
            <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 font-medium">
              <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
              <span>{runError}</span>
            </div>
          )}

          {/* Section 1: Run Type Selector */}
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-semibold text-neutral-900 uppercase tracking-wider">
                  Select run type
                </span>
                <InfoTooltip
                  text="Choose a run command. The pipeline command runs all steps from start to finish."
                />
              </div>
            </div>

            {/* Segmented Run Type Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
              {RUN_TYPES.map((type, idx) => {
                const Icon = type.icon;
                const isSelected = command === type.id;
                const tooltipAlign = idx >= 3 ? "end" : "center";
                return (
                  <div
                    key={type.id}
                    onClick={() => setCommand(type.id)}
                    className={cn(
                      "relative p-3 rounded-xl border text-left cursor-pointer transition-all duration-140 select-none flex flex-col justify-between gap-2 squircle",
                      isSelected
                        ? "bg-neutral-900 text-white border-neutral-900 shadow-xs"
                        : "bg-neutral-50/70 hover:bg-neutral-100/80 border-neutral-200/80 text-neutral-700 hover:text-neutral-900"
                    )}
                  >
                    <div className="flex items-center justify-between gap-1">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <Icon
                          className={cn(
                            "w-3.5 h-3.5 shrink-0",
                            isSelected ? "text-white" : "text-neutral-500"
                          )}
                        />
                        <span className="text-xs font-semibold truncate">
                          {type.name}
                        </span>
                      </div>
                      <div
                        onClick={(e) => e.stopPropagation()}
                        className="shrink-0"
                      >
                        <InfoTooltip
                          text={type.tooltip}
                          align={tooltipAlign}
                          className={isSelected ? "text-neutral-900 bg-white" : undefined}
                        />
                      </div>
                    </div>
                    <span
                      className={cn(
                        "text-[11px] leading-tight line-clamp-1",
                        isSelected ? "text-neutral-300" : "text-neutral-400"
                      )}
                    >
                      {type.shortDesc}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Section 2: Parameters Grid */}
          <div className="pt-3 border-t border-neutral-100">
            {command === "pipeline" && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Left Column: Scope & Limits */}
                  <div className="p-4 bg-neutral-50/60 rounded-xl border border-neutral-200/60 space-y-3.5 squircle">
                    <div className="text-xs font-semibold text-neutral-800 flex items-center gap-1.5">
                      <span>Scope and search limits</span>
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <label className="text-xs font-medium text-neutral-700 flex items-center gap-1.5">
                          <span>Pages per role</span>
                          <InfoTooltip
                            text="Number of result pages to scrape on Jobstreet for each role."
                          />
                        </label>
                      </div>
                      <input
                        type="number"
                        min={1}
                        value={pipelinePages}
                        onChange={(e) => setPipelinePages(parseInt(e.target.value, 10))}
                        className="w-full text-xs font-mono bg-white border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-900 transition-colors squircle"
                      />
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <label className="text-xs font-medium text-neutral-700 flex items-center gap-1.5">
                          <span>Maximum applications</span>
                          <InfoTooltip
                            text="Limit on how many applications to prepare or submit. Leave empty for no limit."
                          />
                        </label>
                      </div>
                      <input
                        type="number"
                        placeholder="Unlimited"
                        value={pipelineLimit}
                        onChange={(e) => setPipelineLimit(e.target.value)}
                        className="w-full text-xs font-mono bg-white border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-900 transition-colors squircle"
                      />
                    </div>
                  </div>

                  {/* Right Column: Execution Flags */}
                  <div className="p-4 bg-neutral-50/60 rounded-xl border border-neutral-200/60 space-y-2.5 squircle flex flex-col justify-center">
                    <div className="text-xs font-semibold text-neutral-800 flex items-center gap-1.5 mb-1">
                      <span>Scoring and browser options</span>
                    </div>

                    <label className="flex items-center justify-between p-2 rounded-xl bg-white border border-neutral-200/70 hover:border-neutral-300 transition-colors cursor-pointer select-none squircle">
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={pipelineOffline}
                          onChange={(e) => setPipelineOffline(e.target.checked)}
                          className="rounded border-neutral-300 text-neutral-900 focus:ring-neutral-800"
                        />
                        <span className="text-xs font-medium text-neutral-700">Offline scorer (rule-based, no LLM)</span>
                      </div>
                      <InfoTooltip
                        text="Uses local keyword matching and rules without calling external AI APIs."
                      />
                    </label>

                    <label className="flex items-center justify-between p-2 rounded-xl bg-white border border-neutral-200/70 hover:border-neutral-300 transition-colors cursor-pointer select-none squircle">
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={pipelineCardsOnly}
                          onChange={(e) => setPipelineCardsOnly(e.target.checked)}
                          className="rounded border-neutral-300 text-neutral-900 focus:ring-neutral-800"
                        />
                        <span className="text-xs font-medium text-neutral-700">Cards only (skip detail pages)</span>
                      </div>
                      <InfoTooltip
                        text="Extracts summaries from listing cards instead of visiting each job page."
                      />
                    </label>

                    <label className="flex items-center justify-between p-2 rounded-xl bg-white border border-neutral-200/70 hover:border-neutral-300 transition-colors cursor-pointer select-none squircle">
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={pipelineHeadless}
                          onChange={(e) => setPipelineHeadless(e.target.checked)}
                          className="rounded border-neutral-300 text-neutral-900 focus:ring-neutral-800"
                        />
                        <span className="text-xs font-medium text-neutral-700">Headless browser</span>
                      </div>
                      <InfoTooltip
                        text="Runs browser automation in the background without opening a visible window."
                      />
                    </label>

                    <label className="flex items-center justify-between p-2 rounded-xl bg-white border border-neutral-200/70 hover:border-neutral-300 transition-colors cursor-pointer select-none squircle">
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={pipelineLlmLetter}
                          onChange={(e) => setPipelineLlmLetter(e.target.checked)}
                          className="rounded border-neutral-300 text-neutral-900 focus:ring-neutral-800"
                        />
                        <span className="text-xs font-medium text-neutral-700">AI cover letter tailoring</span>
                      </div>
                      <InfoTooltip
                        text="Uses the configured AI model to write custom cover letters."
                      />
                    </label>
                  </div>
                </div>

                {/* Safety Gate Card */}
                <div
                  onClick={() => setPipelineExecute(!pipelineExecute)}
                  className={cn(
                    "p-3.5 rounded-xl border flex items-center justify-between cursor-pointer transition-all duration-140 squircle",
                    pipelineExecute
                      ? "bg-red-50/80 border-red-200 text-red-900"
                      : "bg-emerald-50/60 border-emerald-200/80 text-emerald-900"
                  )}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={cn(
                        "p-2 rounded-xl shrink-0 squircle",
                        pipelineExecute ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"
                      )}
                    >
                      {pipelineExecute ? (
                        <ShieldAlert className="w-4 h-4" />
                      ) : (
                        <ShieldCheck className="w-4 h-4" />
                      )}
                    </div>
                    <div>
                      <div className="text-xs font-semibold flex items-center gap-1.5">
                        <span>{pipelineExecute ? "Live application mode active" : "Test run mode (default)"}</span>
                        <div onClick={(e) => e.stopPropagation()}>
                          <InfoTooltip
                            text={
                              pipelineExecute
                                ? "Real applications will be submitted to Jobstreet."
                                : "Applications will be prepared and tested without final submission."
                            }
                          />
                        </div>
                      </div>
                      <p className="text-[11px] opacity-80 mt-0.5">
                        {pipelineExecute
                          ? "The bot submits live applications to Jobstreet."
                          : "Simulates form filling without submitting to employers."}
                      </p>
                    </div>
                  </div>

                  <input
                    type="checkbox"
                    checked={pipelineExecute}
                    onChange={(e) => setPipelineExecute(e.target.checked)}
                    className="rounded border-neutral-300 text-red-600 focus:ring-red-500 w-4 h-4 cursor-pointer"
                  />
                </div>
              </div>
            )}

            {command === "discover" && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 bg-neutral-50/60 rounded-xl border border-neutral-200/60 space-y-3.5 squircle">
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-xs font-medium text-neutral-700 flex items-center gap-1.5">
                        <span>Pages per role</span>
                        <InfoTooltip
                          text="Number of pagination search result pages to scrape on Jobstreet for each configured target role."
                        />
                      </label>
                    </div>
                    <input
                      type="number"
                      min={1}
                      value={discoverPages}
                      onChange={(e) => setDiscoverPages(parseInt(e.target.value, 10))}
                      className="w-full text-xs font-mono bg-white border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-900 transition-colors squircle"
                    />
                  </div>
                </div>

                <div className="p-4 bg-neutral-50/60 rounded-xl border border-neutral-200/60 space-y-2.5 squircle flex flex-col justify-center">
                  <label className="flex items-center justify-between p-2 rounded-xl bg-white border border-neutral-200/70 hover:border-neutral-300 transition-colors cursor-pointer select-none squircle">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={discoverCardsOnly}
                        onChange={(e) => setDiscoverCardsOnly(e.target.checked)}
                        className="rounded border-neutral-300 text-neutral-900 focus:ring-neutral-800"
                      />
                      <span className="text-xs font-medium text-neutral-700">Cards only (skip detail pages)</span>
                    </div>
                    <InfoTooltip
                      text="Extracts basic summaries directly from search cards without opening full job description pages."
                    />
                  </label>
                </div>
              </div>
            )}

            {command === "score" && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 bg-neutral-50/60 rounded-xl border border-neutral-200/60 space-y-3.5 squircle">
                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-xs font-medium text-neutral-700 flex items-center gap-1.5">
                        <span>Limit jobs to score</span>
                        <InfoTooltip
                          text="Upper limit of pending unscored jobs to evaluate in this run. Leave empty to score all pending jobs."
                        />
                      </label>
                    </div>
                    <input
                      type="number"
                      placeholder="All pending jobs"
                      value={scoreLimit}
                      onChange={(e) => setScoreLimit(e.target.value)}
                      className="w-full text-xs font-mono bg-white border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-900 transition-colors squircle"
                    />
                  </div>
                </div>

                <div className="p-4 bg-neutral-50/60 rounded-xl border border-neutral-200/60 space-y-2.5 squircle flex flex-col justify-center">
                  <label className="flex items-center justify-between p-2 rounded-xl bg-white border border-neutral-200/70 hover:border-neutral-300 transition-colors cursor-pointer select-none squircle">
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={scoreOffline}
                        onChange={(e) => setScoreOffline(e.target.checked)}
                        className="rounded border-neutral-300 text-neutral-900 focus:ring-neutral-800"
                      />
                      <span className="text-xs font-medium text-neutral-700">Offline scorer (rule-based, no LLM)</span>
                    </div>
                    <InfoTooltip
                      text="Uses local keyword matching and hard constraints (salary, experience, title blacklist) without calling external AI APIs."
                    />
                  </label>
                </div>
              </div>
            )}

            {command === "apply" && (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 bg-neutral-50/60 rounded-xl border border-neutral-200/60 space-y-3.5 squircle">
                    <div>
                      <div className="flex items-center justify-between mb-1.5">
                        <label className="text-xs font-medium text-neutral-700 flex items-center gap-1.5">
                          <span>Application limit</span>
                          <InfoTooltip
                            text="Maximum number of applications to process from the approved queue in this run."
                          />
                        </label>
                      </div>
                      <input
                        type="number"
                        min={1}
                        value={applyLimit}
                        onChange={(e) => setApplyLimit(e.target.value)}
                        className="w-full text-xs font-mono bg-white border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-900 transition-colors squircle"
                      />
                    </div>
                  </div>

                  <div className="p-4 bg-neutral-50/60 rounded-xl border border-neutral-200/60 space-y-2.5 squircle flex flex-col justify-center">
                    <label className="flex items-center justify-between p-2 rounded-xl bg-white border border-neutral-200/70 hover:border-neutral-300 transition-colors cursor-pointer select-none squircle">
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={applyHeadless}
                          onChange={(e) => setApplyHeadless(e.target.checked)}
                          className="rounded border-neutral-300 text-neutral-900 focus:ring-neutral-800"
                        />
                        <span className="text-xs font-medium text-neutral-700">Headless browser</span>
                      </div>
                      <InfoTooltip
                        text="Runs Playwright in the background. Uncheck if you wish to inspect the browser form-filling process live."
                      />
                    </label>

                    <label className="flex items-center justify-between p-2 rounded-xl bg-white border border-neutral-200/70 hover:border-neutral-300 transition-colors cursor-pointer select-none squircle">
                      <div className="flex items-center gap-2">
                        <input
                          type="checkbox"
                          checked={applyLlmLetter}
                          onChange={(e) => setApplyLlmLetter(e.target.checked)}
                          className="rounded border-neutral-300 text-neutral-900 focus:ring-neutral-800"
                        />
                        <span className="text-xs font-medium text-neutral-700">AI cover letter tailoring</span>
                      </div>
                      <InfoTooltip
                        text="Uses the configured AI model to write custom cover letters."
                      />
                    </label>
                  </div>
                </div>

                {/* Safety Gate Card */}
                <div
                  onClick={() => setApplyExecute(!applyExecute)}
                  className={cn(
                    "p-3.5 rounded-xl border flex items-center justify-between cursor-pointer transition-all duration-140 squircle",
                    applyExecute
                      ? "bg-red-50/80 border-red-200 text-red-900"
                      : "bg-emerald-50/60 border-emerald-200/80 text-emerald-900"
                  )}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={cn(
                        "p-2 rounded-xl shrink-0 squircle",
                        applyExecute ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"
                      )}
                    >
                      {applyExecute ? (
                        <ShieldAlert className="w-4 h-4" />
                      ) : (
                        <ShieldCheck className="w-4 h-4" />
                      )}
                    </div>
                    <div>
                      <div className="text-xs font-semibold flex items-center gap-1.5">
                        <span>{applyExecute ? "Live application mode active" : "Test run mode (default)"}</span>
                        <div onClick={(e) => e.stopPropagation()}>
                          <InfoTooltip
                            text={
                              applyExecute
                                ? "Real applications will be submitted to Jobstreet."
                                : "Applications will be prepared and tested without final submission."
                            }
                          />
                        </div>
                      </div>
                      <p className="text-[11px] opacity-80 mt-0.5">
                        {applyExecute
                          ? "The bot submits live applications to Jobstreet."
                          : "Simulates form filling without submitting to employers."}
                      </p>
                    </div>
                  </div>

                  <input
                    type="checkbox"
                    checked={applyExecute}
                    onChange={(e) => setApplyExecute(e.target.checked)}
                    className="rounded border-neutral-300 text-red-600 focus:ring-red-500 w-4 h-4 cursor-pointer"
                  />
                </div>
              </div>
            )}

            {command === "calibrate" && (
              <div className="p-4 bg-neutral-50/60 rounded-xl border border-neutral-200/60 space-y-2 squircle">
                <div className="flex items-center gap-2 text-xs font-semibold text-neutral-800">
                  <Scale className="w-4 h-4 text-neutral-600" />
                  <span>Historical rule audit</span>
                </div>
                <p className="text-xs text-neutral-600 leading-relaxed">
                  Evaluates past applications against current filters, salary ranges, and keywords to identify discrepancies.
                </p>
              </div>
            )}
          </div>

          {/* Section 3: Execution Footer & Command Preview */}
          <div className="pt-3 border-t border-neutral-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-[11px] text-neutral-400 font-mono shrink-0">
                Command:
              </span>
              <code className="text-[11px] font-mono bg-neutral-100 text-neutral-700 px-2 py-0.5 rounded-lg truncate border border-neutral-200/60">
                {commandPreview}
              </code>
            </div>

            <Button
              type="submit"
              size="sm"
              disabled={startMutation.isPending}
              className="shrink-0"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>{startMutation.isPending ? "Starting..." : "Start Run"}</span>
            </Button>
          </div>
        </form>
      </Card>

      {/* Run History Section */}
      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold tracking-tight text-neutral-900">
              Run history
            </h2>
            <span className="text-xs text-neutral-400 font-mono">
              ({filteredRuns.length} {filteredRuns.length === 1 ? "run" : "runs"})
            </span>
          </div>

          {/* Filter and Search Bar */}
          <div className="flex items-center gap-2 flex-wrap">
            {/* Status Pills */}
            <div className="flex items-center gap-1 bg-neutral-100 p-1 rounded-xl border border-neutral-200/80 squircle">
              {(
                [
                  { id: "all", label: "All" },
                  { id: "completed", label: "Completed" },
                  { id: "running", label: "Running" },
                  { id: "failed", label: "Failed" },
                ] as const
              ).map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setStatusFilter(tab.id)}
                  className={cn(
                    "px-3 py-1.5 text-xs font-medium rounded-xl transition-all cursor-pointer squircle",
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
                className="w-48 pl-8 pr-2.5 py-1.5 text-xs bg-white border border-neutral-200 rounded-xl focus:outline-hidden focus:ring-1 focus:ring-neutral-800 squircle"
              />
            </div>
          </div>
        </div>

        <Card className="overflow-hidden">
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
                    label="Command and options"
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

