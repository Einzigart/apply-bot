import { useState } from "react";
import { useSearchParams } from "react-router";
import { Search, ExternalLink, ChevronDown } from "lucide-react";
import { useApplications, useUpdateApplicationStatus } from "../api/hooks";
import { Card, Button } from "../components/ui/core";
import { SortableHeader } from "../components/ui/table-helpers";
import { cn } from "../lib/utils";

const STATUS_OPTIONS = [
  { value: "Submitted", label: "Submitted", variant: "default" as const },
  { value: "Process", label: "Process", variant: "blue" as const },
  { value: "Declined", label: "Declined", variant: "amber" as const },
  { value: "Rejected", label: "Rejected", variant: "danger" as const },
];

export function ApplicationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = parseInt(searchParams.get("page") || "1", 10);
  const status = searchParams.get("status") || "";
  const q = searchParams.get("q") || "";
  const sort = searchParams.get("sort") || "";
  const order = searchParams.get("order") || "";

  const [searchInput, setSearchInput] = useState(q);

  const { data, isLoading } = useApplications({
    page,
    status: status || undefined,
    q: q || undefined,
    sort: sort || undefined,
    order: order || undefined,
  });

  const updateStatusMutation = useUpdateApplicationStatus();

  const handleFilter = (e: React.FormEvent) => {
    e.preventDefault();
    const next = new URLSearchParams(searchParams);
    if (searchInput.trim()) next.set("q", searchInput.trim());
    else next.delete("q");
    next.set("page", "1");
    setSearchParams(next);
  };

  const handleStatusChange = (val: string) => {
    const next = new URLSearchParams(searchParams);
    if (val) next.set("status", val);
    else next.delete("status");
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

  const getStatusVariant = (st: string) => {
    const found = STATUS_OPTIONS.find(
      (opt) => opt.value.toLowerCase() === (st || "").toLowerCase()
    );
    return found ? found.variant : "default";
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
          Applications
        </h1>
        <p className="text-sm text-neutral-500 mt-0.5">
          History of all submitted Jobstreet applications ({data?.total ?? 0})
        </p>
      </div>

      {/* Filter Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <form onSubmit={handleFilter} className="flex-1 min-w-[240px] relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <input
            type="search"
            placeholder="Search role, company, or location..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="w-full pl-9 pr-4 py-1.5 text-sm bg-white border border-neutral-200 rounded-lg focus:outline-hidden focus:ring-1 focus:ring-neutral-800"
          />
        </form>

        {/* Status selector pills */}
        <div className="flex items-center gap-1 bg-neutral-100 p-0.5 rounded-lg border border-neutral-200/80 overflow-x-auto max-w-full">
          <button
            key="all"
            type="button"
            onClick={() => handleStatusChange("")}
            className={cn(
              "px-2.5 py-1 text-xs font-medium rounded-md whitespace-nowrap transition-colors cursor-pointer",
              !status
                ? "bg-white text-neutral-900 shadow-2xs font-semibold"
                : "text-neutral-600 hover:text-neutral-900"
            )}
          >
            All
          </button>
          {STATUS_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => handleStatusChange(opt.value)}
              className={cn(
                "px-2.5 py-1 text-xs font-medium rounded-md whitespace-nowrap transition-colors cursor-pointer",
                status.toLowerCase() === opt.value.toLowerCase()
                  ? "bg-white text-neutral-900 shadow-2xs font-semibold"
                  : "text-neutral-600 hover:text-neutral-900"
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {/* Applications Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm border-collapse">
            <thead className="bg-neutral-50/80 text-xs font-medium text-neutral-500 border-b border-neutral-200/80">
              <tr>
                <SortableHeader
                  label="Applied"
                  sortKey="applied_at"
                  currentSort={sort}
                  currentOrder={order}
                  onSort={handleSort}
                  className="w-36"
                />
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
                <SortableHeader
                  label="Location"
                  sortKey="location"
                  currentSort={sort}
                  currentOrder={order}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Salary Entered"
                  sortKey="salary_entered"
                  currentSort={sort}
                  currentOrder={order}
                  onSort={handleSort}
                />
                <SortableHeader
                  label="Status"
                  sortKey="status"
                  currentSort={sort}
                  currentOrder={order}
                  onSort={handleSort}
                />
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100">
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-sm text-neutral-400">
                    Loading applications...
                  </td>
                </tr>
              ) : data?.apps.map((a) => (
                <tr key={a.id} className="hover:bg-neutral-50/80 transition-colors">
                  <td className="py-3 px-3.5 text-xs font-mono text-neutral-500">
                    {a.applied_at}
                  </td>
                  <td className="py-3 px-3.5 font-medium text-neutral-900">
                    {a.url ? (
                      <a
                        href={a.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 text-blue-600 hover:underline"
                      >
                        <span>{a.title || "Unknown Position"}</span>
                        <ExternalLink className="w-3 h-3 shrink-0" />
                      </a>
                    ) : (
                      a.title || "—"
                    )}
                  </td>
                  <td className="py-3 px-3.5 text-neutral-700">{a.company || "—"}</td>
                  <td className="py-3 px-3.5 text-xs text-neutral-500">
                    {a.location || "—"}
                  </td>
                  <td className="py-3 px-3.5 text-xs font-mono text-neutral-700">
                    {a.salary_entered || "—"}
                  </td>
                  <td className="py-3 px-3.5">
                    <div className="relative inline-block">
                      <select
                        value={a.status || "Submitted"}
                        onChange={(e) =>
                          updateStatusMutation.mutate({
                            appId: a.id,
                            status: e.target.value,
                          })
                        }
                        className={cn(
                          "appearance-none text-xs font-medium px-2.5 py-1 pr-6 rounded-md border cursor-pointer focus:outline-hidden transition-all duration-120 shadow-2xs",
                          getStatusVariant(a.status) === "emerald" &&
                            "bg-emerald-50 text-emerald-800 border-emerald-300 focus:border-emerald-500",
                          getStatusVariant(a.status) === "purple" &&
                            "bg-purple-50 text-purple-800 border-purple-300 focus:border-purple-500",
                          getStatusVariant(a.status) === "amber" &&
                            "bg-amber-50 text-amber-800 border-amber-300 focus:border-amber-500",
                          getStatusVariant(a.status) === "blue" &&
                            "bg-sky-50 text-sky-800 border-sky-300 focus:border-sky-500",
                          getStatusVariant(a.status) === "danger" &&
                            "bg-red-50 text-red-800 border-red-300 focus:border-red-500",
                          getStatusVariant(a.status) === "default" &&
                            "bg-neutral-50 text-neutral-700 border-neutral-200 focus:border-neutral-400"
                        )}
                      >
                        {STATUS_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value} className="bg-white text-neutral-800">
                            {opt.label}
                          </option>
                        ))}
                      </select>
                      <ChevronDown className="w-3 h-3 text-neutral-400 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" />
                    </div>
                  </td>
                </tr>
              ))}
              {data?.apps.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-sm text-neutral-400">
                    No submitted applications match your criteria
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Bar */}
        {data && (page > 1 || data.has_next) && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-neutral-100 text-xs text-neutral-500">
            <div>
              Page <strong>{page}</strong>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                disabled={page <= 1}
                onClick={() => {
                  const next = new URLSearchParams(searchParams);
                  next.set("page", String(page - 1));
                  setSearchParams(next);
                }}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!data.has_next}
                onClick={() => {
                  const next = new URLSearchParams(searchParams);
                  next.set("page", String(page + 1));
                  setSearchParams(next);
                }}
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
