import { Link, useNavigate, useSearchParams } from "react-router";
import { Play, ArrowRight, Terminal, ChevronRight } from "lucide-react";
import { useDashboard } from "../api/hooks";
import { Card, Button } from "../components/ui/core";
import {
  SortableHeader,
  RunStatusBadge,
  CommandPill,
  RunDurationCell,
  RunTimeCell,
} from "../components/ui/table-helpers";

export function DashboardPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const sort = searchParams.get("sort") || "";
  const order = searchParams.get("order") || "";

  const { data, isLoading } = useDashboard({
    sort: sort || undefined,
    order: order || undefined,
  });

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

  if (isLoading || !data) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-neutral-200 rounded-md w-48" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-20 bg-neutral-100 rounded-lg border border-neutral-200" />
          ))}
        </div>
        <div className="h-64 bg-neutral-100 rounded-lg border border-neutral-200" />
      </div>
    );
  }

  const stats = [
    { label: "Discovered", value: data.total_jobs, href: "/jobs" },
    { label: "Ready", value: data.apply_queue, href: "/jobs?decision=apply" },
    { label: "Skipped", value: data.counts["skip"] || 0, href: "/jobs?decision=skip" },
    { label: "Applied", value: data.total_apps, href: "/applications" },
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
            Dashboard
          </h1>
          <p className="text-sm text-neutral-500 mt-0.5">
            Automated application overview and recent runs
          </p>
        </div>
        <Link to="/runs">
          <Button variant="primary" size="sm">
            <Play className="w-3.5 h-3.5 fill-current" />
            <span>New Run</span>
          </Button>
        </Link>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
        {stats.map((s) => (
          <Link key={s.label} to={s.href} className="group block">
            <Card className="p-4 transition-all duration-140 hover:border-neutral-400/80 hover:shadow-sm">
              <div className="text-2xl font-bold tracking-tight text-neutral-900 group-hover:text-blue-600 transition-colors">
                {s.value}
              </div>
              <div className="text-xs font-medium text-neutral-500 mt-1">
                {s.label}
              </div>
            </Card>
          </Link>
        ))}
      </div>

      {/* Recent Runs Table */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold tracking-tight text-neutral-900">
              Recent Runs
            </h2>
            <span className="text-xs text-neutral-400 font-mono">
              ({data.runs.length} shown)
            </span>
          </div>
          <Link
            to="/runs"
            className="text-xs font-medium text-neutral-600 hover:text-neutral-900 flex items-center gap-1 transition-colors"
          >
            <span>View all runs</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </Link>
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
                {data.runs.map((r) => (
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
                {data.runs.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-12 text-center text-sm text-neutral-400">
                      <div className="flex flex-col items-center justify-center gap-2">
                        <Terminal className="w-8 h-8 text-neutral-300 stroke-[1.5]" />
                        <span className="font-medium text-neutral-600">No runs executed yet</span>
                        <span className="text-xs text-neutral-400">Start a run to see execution history here</span>
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
