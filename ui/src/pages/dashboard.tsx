import { Link, useNavigate, useSearchParams } from "react-router";
import { Play, ArrowRight, ArrowUpDown } from "lucide-react";
import { useDashboard } from "../api/hooks";
import { Card, Badge, Button } from "../components/ui/core";
import { cn } from "../lib/utils";

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

  if (isLoading || !data) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-slate-200 rounded-md w-48" />
        <div className="grid grid-cols-5 gap-4">
          {[...Array(5)].map((_, i) => (
            <div key={i} className="h-24 bg-slate-200 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  const stats = [
    { label: "Discovered", value: data.total_jobs, href: "/jobs" },
    { label: "Ready", value: data.apply_queue, href: "/jobs?decision=apply" },
    { label: "Review", value: data.counts["review"] || 0, href: "/jobs?decision=review" },
    { label: "Skipped", value: data.counts["skip"] || 0, href: "/jobs?decision=skip" },
    { label: "Applied", value: data.total_apps, href: "/applications" },
  ];

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Dashboard
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
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
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3.5">
        {stats.map((s) => (
          <Link key={s.label} to={s.href} className="group block">
            <Card className="p-4 transition-all duration-150 group-hover:border-blue-400/80 group-hover:shadow-sm">
              <div className="text-2xl font-bold tracking-tight text-slate-900 group-hover:text-blue-600 transition-colors">
                {s.value}
              </div>
              <div className="text-xs font-medium text-slate-500 mt-1">
                {s.label}
              </div>
            </Card>
          </Link>
        ))}
      </div>

      {/* Recent Runs Table */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold tracking-tight text-slate-900">
            Recent Runs
          </h2>
          <Link
            to="/runs"
            className="text-xs font-medium text-blue-600 hover:text-blue-700 flex items-center gap-1"
          >
            <span>View all</span>
            <ArrowRight className="w-3 h-3" />
          </Link>
        </div>

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
                {data.runs.map((r) => (
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
                {data.runs.length === 0 && (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-sm text-slate-400">
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
