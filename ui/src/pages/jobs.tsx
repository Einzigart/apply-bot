import { useState } from "react";
import { useSearchParams } from "react-router";
import { Search, ExternalLink, Check, X, CheckCircle2 } from "lucide-react";
import { useJobs, useDecideJob, useMarkJobApplied } from "../api/hooks";
import { Card, Badge, Button } from "../components/ui/core";
import { SortableHeader } from "../components/ui/table-helpers";
import { cn } from "../lib/utils";

export function JobsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const decision = searchParams.get("decision") || "";
  const externalParam = searchParams.get("external") || "";
  const isExternal =
    externalParam === "true" ? true : externalParam === "false" ? false : undefined;
  const q = searchParams.get("q") || "";
  const sort = searchParams.get("sort") || "";
  const order = searchParams.get("order") || "";
  const page = parseInt(searchParams.get("page") || "1", 10);

  const [searchInput, setSearchInput] = useState(q);

  const { data, isLoading } = useJobs({
    decision: decision || undefined,
    is_external: isExternal,
    q: q || undefined,
    sort: sort || undefined,
    order: order || undefined,
    page,
  });

  const decideMutation = useDecideJob();
  const markJobAppliedMutation = useMarkJobApplied();

  const handleFilter = (e: React.FormEvent) => {
    e.preventDefault();
    const next = new URLSearchParams(searchParams);
    if (searchInput) next.set("q", searchInput);
    else next.delete("q");
    next.set("page", "1");
    setSearchParams(next);
  };

  const handleDecisionChange = (val: string) => {
    const next = new URLSearchParams(searchParams);
    if (val) next.set("decision", val);
    else next.delete("decision");
    next.set("page", "1");
    setSearchParams(next);
  };

  const handleExternalChange = (val: string) => {
    const next = new URLSearchParams(searchParams);
    if (val) next.set("external", val);
    else next.delete("external");
    next.set("page", "1");
    setSearchParams(next);
  };

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

  const handlePageChange = (newPage: number) => {
    const next = new URLSearchParams(searchParams);
    next.set("page", String(newPage));
    setSearchParams(next);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Jobs
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Discovered and evaluated positions
          </p>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <form onSubmit={handleFilter} className="flex-1 min-w-[240px] relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <input
            type="search"
            placeholder="Search role or company..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-sm bg-white border border-neutral-200 rounded-xl focus:outline-hidden focus:ring-1 focus:ring-neutral-800"
          />
        </form>

        {/* Decision selector pills */}
        <div className="flex items-center gap-1 bg-neutral-100 p-1 rounded-xl border border-neutral-200/80">
          {["", "apply", "review", "skip"].map((d) => (
            <button
              key={d}
              onClick={() => handleDecisionChange(d)}
              className={cn(
                "px-3.5 py-1.5 text-xs font-medium rounded-xl capitalize transition-colors cursor-pointer",
                decision === d
                  ? "bg-white text-neutral-900 shadow-2xs font-semibold"
                  : "text-neutral-600 hover:text-neutral-900"
              )}
            >
              {d || "All"}
            </button>
          ))}
        </div>

        {/* Platform/External filter pills */}
        <div className="flex items-center gap-1 bg-neutral-100 p-1 rounded-xl border border-neutral-200/80">
          {[
            { value: "", label: "All Types" },
            { value: "false", label: "Direct" },
            { value: "true", label: "External" },
          ].map((opt) => (
            <button
              key={opt.value}
              onClick={() => handleExternalChange(opt.value)}
              className={cn(
                "px-3.5 py-1.5 text-xs font-medium rounded-xl transition-colors cursor-pointer",
                externalParam === opt.value
                  ? "bg-white text-neutral-900 shadow-2xs font-semibold"
                  : "text-neutral-600 hover:text-neutral-900"
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Jobs Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm border-collapse">
            <thead className="bg-neutral-50/80 text-xs font-medium text-neutral-500 border-b border-neutral-200/80">
              <tr>
                <SortableHeader
                  label="Role"
                  sortKey="title"
                  currentSort={sort}
                  currentOrder={order}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Company"
                  sortKey="company"
                  currentSort={sort}
                  currentOrder={order}
                  onSort={handleSort}
                />
                <th className="py-2.5 px-4 text-xs font-normal text-neutral-500">
                  Location
                </th>
                <th className="py-2.5 px-4 text-xs font-normal text-neutral-500">
                  Decision
                </th>
                <SortableHeader
                  label="Match"
                  sortKey="match"
                  currentSort={sort}
                  currentOrder={order}
                  onSort={handleSort}
                  className="w-24"
                />
                <th className="py-2.5 px-4 text-xs font-normal text-neutral-500 text-right">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100">
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-sm text-neutral-400">
                    Loading jobs...
                  </td>
                </tr>
              ) : data?.jobs.map((j) => (
                <tr key={j.id} className="hover:bg-neutral-50/80 transition-colors">
                  <td className="py-3 px-3.5 font-medium text-neutral-900">
                    <div className="flex flex-col items-start gap-1">
                      {j.url ? (
                        <a
                          href={j.url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1.5 text-blue-600 hover:text-blue-700 font-medium"
                        >
                          <span>{j.title || "Unknown Title"}</span>
                          <ExternalLink className="w-3 h-3 shrink-0" />
                        </a>
                      ) : (
                        <span>{j.title || "—"}</span>
                      )}
                      {j.is_external === 1 && (
                        <Badge variant="amber" className="text-[10px] px-1.5 py-0">
                          External Apply
                        </Badge>
                      )}
                    </div>
                  </td>
                  <td className="py-3 px-3.5 text-neutral-700">{j.company || "—"}</td>
                  <td className="py-3 px-3.5 text-xs text-neutral-500">
                    {j.location || "—"}
                  </td>
                  <td className="py-3 px-3.5">
                    {j.decision === "apply" && <Badge variant="apply">Apply</Badge>}
                    {j.decision === "review" && <Badge variant="review">Review</Badge>}
                    {j.decision === "skip" && <Badge variant="skip">Skip</Badge>}
                    {!j.decision && <Badge variant="default">Unevaluated</Badge>}
                  </td>
                  <td className="py-3 px-3.5 text-xs font-semibold text-neutral-700">
                    {j.match_pct !== null && j.match_pct !== undefined
                      ? `${j.match_pct}%`
                      : "—"}
                  </td>
                  <td className="py-3 px-3.5 text-right">
                    <div className="flex items-center justify-end gap-1.5">
                      {j.application_id ? (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-700 bg-emerald-50 border border-emerald-200/80 px-2 py-0.5 rounded-lg">
                          <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                          Applied
                        </span>
                      ) : (
                        <>
                          {j.is_external === 1 && (
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-7 px-2 text-xs font-medium text-emerald-700 border-emerald-300 hover:bg-emerald-50 hover:border-emerald-400"
                              onClick={() =>
                                markJobAppliedMutation.mutate(j.jobstreet_id || j.id)
                              }
                              disabled={markJobAppliedMutation.isPending}
                              title="Mark as Applied"
                            >
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 mr-1" />
                              <span>Mark Applied</span>
                            </Button>
                          )}

                          {j.jobstreet_id && (
                            <>
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-7 px-2 text-emerald-600 hover:bg-emerald-50 hover:border-emerald-200"
                                onClick={() =>
                                  decideMutation.mutate({
                                    jobId: j.jobstreet_id!,
                                    decision: "apply",
                                    reason: "manual UI review",
                                  })
                                }
                                title="Approve to Apply"
                              >
                                <Check className="w-3.5 h-3.5" />
                              </Button>
                              <Button
                                variant="outline"
                                size="sm"
                                className="h-7 px-2 text-neutral-400 hover:text-red-600 hover:bg-red-50 hover:border-red-200"
                                onClick={() =>
                                  decideMutation.mutate({
                                    jobId: j.jobstreet_id!,
                                    decision: "skip",
                                    reason: "manual UI skip",
                                  })
                                }
                                title="Skip Role"
                              >
                                <X className="w-3.5 h-3.5" />
                              </Button>
                            </>
                          )}
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {data?.jobs.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-sm text-neutral-400">
                    No jobs match your filter criteria
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        {data && data.total_pages > 1 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-neutral-100 text-xs text-neutral-500">
            <div>
              Showing{" "}
              <strong>{(data.page - 1) * data.per_page + 1}</strong> to{" "}
              <strong>{Math.min(data.page * data.per_page, data.total)}</strong>{" "}
              of <strong>{data.total}</strong>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => handlePageChange(page - 1)}
              >
                Previous
              </Button>
              <span className="px-2 font-medium text-neutral-700">
                {page} / {data.total_pages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= data.total_pages}
                onClick={() => handlePageChange(page + 1)}
              >
                Next
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
