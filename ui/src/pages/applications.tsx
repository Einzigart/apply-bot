import { useSearchParams } from "react-router";
import { ExternalLink } from "lucide-react";
import { useApplications } from "../api/hooks";
import { Card, Badge, Button } from "../components/ui/core";

export function ApplicationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = parseInt(searchParams.get("page") || "1", 10);

  const { data, isLoading } = useApplications(page);

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
                <th className="py-2.5 px-4 font-normal">Applied</th>
                <th className="py-2.5 px-4 font-normal">Role</th>
                <th className="py-2.5 px-4 font-normal">Company</th>
                <th className="py-2.5 px-4 font-normal">Location</th>
                <th className="py-2.5 px-4 font-normal">Salary Entered</th>
                <th className="py-2.5 px-4 font-normal">Status</th>
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
                    <Badge variant="apply">{a.status}</Badge>
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
                onClick={() => setSearchParams({ page: String(page - 1) })}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                disabled={!data.has_next}
                onClick={() => setSearchParams({ page: String(page + 1) })}
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
