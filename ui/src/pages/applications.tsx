import { useSearchParams } from "react-router";
import { ExternalLink, ArrowUpDown, ChevronDown } from "lucide-react";
import { useApplications, useUpdateApplicationStatus } from "../api/hooks";
import { Card, Badge, Button } from "../components/ui/core";
import { cn } from "../lib/utils";

const STATUS_OPTIONS = [
  { value: "Submitted", label: "Submitted", variant: "default" as const },
  { value: "Follow Up", label: "Follow Up", variant: "blue" as const },
  { value: "HR Interview", label: "HR Interview", variant: "purple" as const },
  { value: "User Interview", label: "User Interview", variant: "amber" as const },
  { value: "Offering", label: "Offering", variant: "emerald" as const },
  { value: "Declined", label: "Declined", variant: "danger" as const },
];

export function ApplicationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = parseInt(searchParams.get("page") || "1", 10);
  const sort = searchParams.get("sort") || "";
  const order = searchParams.get("order") || "";

  const { data, isLoading } = useApplications({
    page,
    sort: sort || undefined,
    order: order || undefined,
  });

  const updateStatusMutation = useUpdateApplicationStatus();

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

  const getStatusVariant = (status: string) => {
    const found = STATUS_OPTIONS.find(
      (opt) => opt.value.toLowerCase() === (status || "").toLowerCase()
    );
    return found ? found.variant : "default";
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
          "py-2.5 px-4 font-normal cursor-pointer select-none hover:bg-neutral-100/70 transition-colors group",
          className
        )}
      >
        <div className="flex items-center gap-1">
          <span
            className={cn(
              "group-hover:text-neutral-900 transition-colors",
              isCurrent ? "font-semibold text-neutral-900" : ""
            )}
          >
            {label}
          </span>
          <ArrowUpDown
            className={cn(
              "w-3 h-3 transition-colors",
              isCurrent
                ? "text-neutral-900"
                : "text-neutral-300 group-hover:text-neutral-500"
            )}
          />
        </div>
      </th>
    );
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

      {/* Applications Table */}
      <Card>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-neutral-50/80 text-xs font-medium text-neutral-500 border-b border-neutral-200/80">
              <tr>
                {renderSortableHeader("Applied", "applied_at")}
                {renderSortableHeader("Role", "title")}
                {renderSortableHeader("Company", "company")}
                {renderSortableHeader("Location", "location")}
                {renderSortableHeader("Salary Entered", "salary_entered")}
                {renderSortableHeader("Status", "status")}
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
                <tr key={a.id} className="hover:bg-neutral-50/70 transition-colors">
                  <td className="py-3 px-4 text-xs font-mono text-neutral-500">
                    {a.applied_at}
                  </td>
                  <td className="py-3 px-4 font-medium text-neutral-900">
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
                  <td className="py-3 px-4 text-neutral-700">{a.company || "—"}</td>
                  <td className="py-3 px-4 text-xs text-neutral-500">
                    {a.location || "—"}
                  </td>
                  <td className="py-3 px-4 text-xs font-mono text-neutral-700">
                    {a.salary_entered || "—"}
                  </td>
                  <td className="py-3 px-4">
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
                    No submitted applications recorded yet
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
