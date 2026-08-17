import { useState, useRef, useEffect } from "react";
import { useSearchParams } from "react-router";
import {
  Search,
  ExternalLink,
  ChevronDown,
  Download,
  Upload,
  Plus,
  FileSpreadsheet,
  FileText,
  Pencil,
  Trash2,
  Check,
  X,
  AlertCircle,
} from "lucide-react";
import {
  useApplications,
  useUpdateApplicationStatus,
  useCreateApplication,
  useUpdateApplication,
  useDeleteApplication,
  useImportApplications,
} from "../api/hooks";
import { Card, Button } from "../components/ui/core";
import { SortableHeader } from "../components/ui/table-helpers";
import { cn } from "../lib/utils";

const STATUS_OPTIONS = [
  { value: "Submitted", label: "Submitted", variant: "default" as const },
  { value: "Process", label: "Process", variant: "blue" as const },
  { value: "Interview", label: "Interview", variant: "purple" as const },
  { value: "Offering", label: "Offering", variant: "emerald" as const },
  { value: "Declined", label: "Declined", variant: "amber" as const },
  { value: "Rejected", label: "Rejected", variant: "danger" as const },
];

interface EditingRowState {
  id: number;
  applied_at: string;
  title: string;
  company: string;
  location: string;
  salary_entered: string;
  status: string;
  url: string;
}

export function ApplicationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = parseInt(searchParams.get("page") || "1", 10);
  const status = searchParams.get("status") || "";
  const q = searchParams.get("q") || "";
  const sort = searchParams.get("sort") || "";
  const order = searchParams.get("order") || "";

  const [searchInput, setSearchInput] = useState(q);
  const [exportOpen, setExportOpen] = useState(false);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [importStatusMessage, setImportStatusMessage] = useState<{
    text: string;
    type: "success" | "error";
  } | null>(null);

  // Editing state
  const [editingRow, setEditingRow] = useState<EditingRowState | null>(null);

  // New Application Form state
  const [formData, setFormData] = useState({
    title: "",
    company: "",
    url: "",
    applied_at: new Date().toISOString().split("T")[0],
    location: "",
    salary_entered: "",
    status: "Submitted",
  });
  const [formError, setFormError] = useState("");

  const dropdownRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setExportOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const { data, isLoading } = useApplications({
    page,
    status: status || undefined,
    q: q || undefined,
    sort: sort || undefined,
    order: order || undefined,
  });

  const updateStatusMutation = useUpdateApplicationStatus();
  const createApplicationMutation = useCreateApplication();
  const updateApplicationMutation = useUpdateApplication();
  const deleteApplicationMutation = useDeleteApplication();
  const importApplicationsMutation = useImportApplications();

  const handleExport = (format: "csv" | "excel" | "tsv") => {
    setExportOpen(false);
    const qs = new URLSearchParams();
    qs.set("format", format);
    if (status) qs.set("status", status);
    if (q) qs.set("q", q);
    if (sort) qs.set("sort", sort);
    if (order) qs.set("order", order);

    const ext = format === "excel" ? "xlsx" : format === "tsv" ? "tsv" : "csv";
    const exportUrl = `/api/applications/export?${qs.toString()}`;
    const a = document.createElement("a");
    a.href = exportUrl;
    a.setAttribute("download", `applications.${ext}`);
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  };

  const handleFileImport = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setImportStatusMessage(null);
    importApplicationsMutation.mutate(file, {
      onSuccess: (res) => {
        setImportStatusMessage({
          text: res.message,
          type: res.errors && res.errors.length > 0 && res.imported === 0 ? "error" : "success",
        });
        if (fileInputRef.current) fileInputRef.current.value = "";
      },
      onError: (err: any) => {
        setImportStatusMessage({
          text: err.message || "Failed to import applications",
          type: "error",
        });
        if (fileInputRef.current) fileInputRef.current.value = "";
      },
    });
  };

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

  const startEditing = (app: any) => {
    setEditingRow({
      id: app.id,
      applied_at: app.applied_at || "",
      title: app.title || "",
      company: app.company || "",
      location: app.location || "",
      salary_entered: app.salary_entered || "",
      status: app.status || "Submitted",
      url: app.url || "",
    });
  };

  const cancelEditing = () => {
    setEditingRow(null);
  };

  const saveEditing = () => {
    if (!editingRow) return;
    updateApplicationMutation.mutate(
      {
        appId: editingRow.id,
        payload: {
          applied_at: editingRow.applied_at,
          title: editingRow.title,
          company: editingRow.company,
          location: editingRow.location,
          salary_entered: editingRow.salary_entered,
          status: editingRow.status,
          url: editingRow.url,
        },
      },
      {
        onSuccess: () => {
          setEditingRow(null);
        },
      }
    );
  };

  const handleDelete = (appId: number, title?: string) => {
    if (window.confirm(`Are you sure you want to delete the application for "${title || "this position"}"?`)) {
      deleteApplicationMutation.mutate(appId);
    }
  };

  const handleCreateSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.title.trim() || !formData.company.trim() || !formData.url.trim()) {
      setFormError("Title, Company, and Job URL are required.");
      return;
    }
    setFormError("");
    createApplicationMutation.mutate(
      {
        title: formData.title.trim(),
        company: formData.company.trim(),
        url: formData.url.trim(),
        applied_at: formData.applied_at || new Date().toISOString().split("T")[0],
        location: formData.location.trim() || undefined,
        salary_entered: formData.salary_entered.trim() || undefined,
        status: formData.status || "Submitted",
      },
      {
        onSuccess: () => {
          setIsAddModalOpen(false);
          setFormData({
            title: "",
            company: "",
            url: "",
            applied_at: new Date().toISOString().split("T")[0],
            location: "",
            salary_entered: "",
            status: "Submitted",
          });
        },
        onError: (err: any) => {
          setFormError(err.message || "Failed to create application");
        },
      }
    );
  };

  const getStatusVariant = (st: string) => {
    const found = STATUS_OPTIONS.find(
      (opt) => opt.value.toLowerCase() === (st || "").toLowerCase()
    );
    return found ? found.variant : "default";
  };

  return (
    <div className="space-y-6">
      {/* Hidden File Input for Import */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleFileImport}
        accept=".csv,.xlsx,.xls,.tsv"
        className="hidden"
      />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
            Applications
          </h1>
          <p className="text-sm text-neutral-500 mt-0.5">
            History of all submitted Jobstreet applications ({data?.total ?? 0})
          </p>
        </div>

        {/* Top Action Buttons */}
        <div className="flex items-center gap-2">
          {/* Add Manual Application Button */}
          <Button
            size="sm"
            variant="primary"
            onClick={() => {
              setFormError("");
              setIsAddModalOpen(true);
            }}
            className="flex items-center gap-1.5 font-medium shadow-2xs cursor-pointer"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Add Application</span>
          </Button>

          {/* Import Button */}
          <Button
            size="sm"
            variant="outline"
            onClick={() => fileInputRef.current?.click()}
            disabled={importApplicationsMutation.isPending}
            className="flex items-center gap-1.5 font-medium shadow-2xs cursor-pointer"
          >
            <Upload className="w-3.5 h-3.5" />
            <span>{importApplicationsMutation.isPending ? "Importing..." : "Import"}</span>
          </Button>

          {/* Export Dropdown */}
          <div className="relative shrink-0" ref={dropdownRef}>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setExportOpen(!exportOpen)}
              className="flex items-center gap-1.5 font-medium shadow-2xs cursor-pointer"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Export</span>
              <ChevronDown
                className={cn("w-3.5 h-3.5 transition-transform", exportOpen && "rotate-180")}
              />
            </Button>

            {exportOpen && (
              <div className="absolute right-0 mt-1.5 w-44 bg-white border border-neutral-200 rounded-xl shadow-lg p-1.5 z-30 space-y-0.5 animate-in fade-in zoom-in-95 duration-100">
                <button
                  type="button"
                  onClick={() => handleExport("excel")}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-neutral-700 hover:bg-neutral-100 hover:text-neutral-900 rounded-xl transition-colors text-left cursor-pointer"
                >
                  <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                  <div>
                    <div className="font-medium">Excel (.xlsx)</div>
                    <div className="text-[10px] text-neutral-400">Native Excel spreadsheet</div>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => handleExport("csv")}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-neutral-700 hover:bg-neutral-100 hover:text-neutral-900 rounded-xl transition-colors text-left cursor-pointer"
                >
                  <FileText className="w-3.5 h-3.5 text-blue-600 shrink-0" />
                  <div>
                    <div className="font-medium">Standard CSV</div>
                    <div className="text-[10px] text-neutral-400">Plain comma-delimited</div>
                  </div>
                </button>

                <button
                  type="button"
                  onClick={() => handleExport("tsv")}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-xs text-neutral-700 hover:bg-neutral-100 hover:text-neutral-900 rounded-xl transition-colors text-left cursor-pointer"
                >
                  <FileText className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                  <div>
                    <div className="font-medium">TSV (Tab-separated)</div>
                    <div className="text-[10px] text-neutral-400">Tab-delimited text</div>
                  </div>
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Import Status Alert Banner */}
      {importStatusMessage && (
        <div
          className={cn(
            "p-3 rounded-xl border text-xs flex items-center justify-between",
            importStatusMessage.type === "success"
              ? "bg-emerald-50 text-emerald-800 border-emerald-200"
              : "bg-red-50 text-red-800 border-red-200"
          )}
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{importStatusMessage.text}</span>
          </div>
          <button
            type="button"
            onClick={() => setImportStatusMessage(null)}
            className="p-1 hover:bg-black/5 rounded-lg cursor-pointer"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Filter Toolbar */}
      <div className="flex flex-wrap items-center gap-3">
        <form onSubmit={handleFilter} className="flex-1 min-w-[240px] relative">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400" />
          <input
            type="search"
            placeholder="Search role, company, or location..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="w-full pl-9 pr-4 py-2 text-sm bg-white border border-neutral-200 rounded-xl focus:outline-hidden focus:ring-1 focus:ring-neutral-800"
          />
        </form>

        {/* Status selector pills */}
        <div className="flex items-center gap-1 bg-neutral-100 p-1 rounded-xl border border-neutral-200/80 overflow-x-auto max-w-full">
          <button
            key="all"
            type="button"
            onClick={() => handleStatusChange("")}
            className={cn(
              "px-3 py-1.5 text-xs font-medium rounded-xl whitespace-nowrap transition-colors cursor-pointer",
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
                "px-3 py-1.5 text-xs font-medium rounded-xl whitespace-nowrap transition-colors cursor-pointer",
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
                  className="w-32"
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
                  className="w-36"
                />
                <th className="py-3 px-3.5 text-right font-medium text-neutral-500 w-24">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-neutral-100">
              {isLoading ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-sm text-neutral-400">
                    Loading applications...
                  </td>
                </tr>
              ) : (
                data?.apps.map((a) => {
                  const isEditing = editingRow?.id === a.id;

                  if (isEditing && editingRow) {
                    return (
                      <tr key={a.id} className="bg-neutral-50/90 transition-colors">
                        {/* Edit: Applied Date */}
                        <td className="py-2.5 px-3.5">
                          <input
                            type="date"
                            value={editingRow.applied_at}
                            onChange={(e) =>
                              setEditingRow({ ...editingRow, applied_at: e.target.value })
                            }
                            className="w-full text-xs bg-white border border-neutral-300 rounded-lg px-2 py-1 focus:ring-1 focus:ring-neutral-800"
                          />
                        </td>

                        {/* Edit: Title + URL */}
                        <td className="py-2.5 px-3.5 space-y-1">
                          <input
                            type="text"
                            placeholder="Role title"
                            value={editingRow.title}
                            onChange={(e) =>
                              setEditingRow({ ...editingRow, title: e.target.value })
                            }
                            className="w-full text-xs bg-white border border-neutral-300 rounded-lg px-2 py-1 font-medium focus:ring-1 focus:ring-neutral-800"
                          />
                          <input
                            type="url"
                            placeholder="Job URL"
                            value={editingRow.url}
                            onChange={(e) =>
                              setEditingRow({ ...editingRow, url: e.target.value })
                            }
                            className="w-full text-[11px] bg-white border border-neutral-200 rounded-lg px-2 py-0.5 text-neutral-600 focus:ring-1 focus:ring-neutral-800"
                          />
                        </td>

                        {/* Edit: Company */}
                        <td className="py-2.5 px-3.5">
                          <input
                            type="text"
                            placeholder="Company"
                            value={editingRow.company}
                            onChange={(e) =>
                              setEditingRow({ ...editingRow, company: e.target.value })
                            }
                            className="w-full text-xs bg-white border border-neutral-300 rounded-lg px-2 py-1 focus:ring-1 focus:ring-neutral-800"
                          />
                        </td>

                        {/* Edit: Location */}
                        <td className="py-2.5 px-3.5">
                          <input
                            type="text"
                            placeholder="Location"
                            value={editingRow.location}
                            onChange={(e) =>
                              setEditingRow({ ...editingRow, location: e.target.value })
                            }
                            className="w-full text-xs bg-white border border-neutral-300 rounded-lg px-2 py-1 focus:ring-1 focus:ring-neutral-800"
                          />
                        </td>

                        {/* Edit: Salary Entered */}
                        <td className="py-2.5 px-3.5">
                          <input
                            type="text"
                            placeholder="e.g. $5,000"
                            value={editingRow.salary_entered}
                            onChange={(e) =>
                              setEditingRow({ ...editingRow, salary_entered: e.target.value })
                            }
                            className="w-full text-xs bg-white border border-neutral-300 rounded-lg px-2 py-1 focus:ring-1 focus:ring-neutral-800"
                          />
                        </td>

                        {/* Edit: Status */}
                        <td className="py-2.5 px-3.5">
                          <select
                            value={editingRow.status}
                            onChange={(e) =>
                              setEditingRow({ ...editingRow, status: e.target.value })
                            }
                            className="w-full text-xs bg-white border border-neutral-300 rounded-lg px-2 py-1 focus:ring-1 focus:ring-neutral-800"
                          >
                            {STATUS_OPTIONS.map((opt) => (
                              <option key={opt.value} value={opt.value}>
                                {opt.label}
                              </option>
                            ))}
                          </select>
                        </td>

                        {/* Edit Actions: Save / Cancel */}
                        <td className="py-2.5 px-3.5 text-right whitespace-nowrap">
                          <div className="flex items-center justify-end gap-1">
                            <button
                              type="button"
                              onClick={saveEditing}
                              disabled={updateApplicationMutation.isPending}
                              title="Save changes"
                              className="p-1 text-emerald-600 hover:bg-emerald-50 rounded-lg transition-colors cursor-pointer"
                            >
                              <Check className="w-4 h-4" />
                            </button>
                            <button
                              type="button"
                              onClick={cancelEditing}
                              title="Cancel"
                              className="p-1 text-neutral-400 hover:bg-neutral-200 rounded-lg transition-colors cursor-pointer"
                            >
                              <X className="w-4 h-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    );
                  }

                  return (
                    <tr key={a.id} className="hover:bg-neutral-50/80 transition-colors group">
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
                              "appearance-none text-xs font-medium px-3 py-1.5 pr-7 rounded-xl border cursor-pointer focus:outline-hidden transition-all duration-120 shadow-2xs",
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
                              <option
                                key={opt.value}
                                value={opt.value}
                                className="bg-white text-neutral-800"
                              >
                                {opt.label}
                              </option>
                            ))}
                          </select>
                          <ChevronDown className="w-3 h-3 text-neutral-400 absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none" />
                        </div>
                      </td>
                      <td className="py-3 px-3.5 text-right whitespace-nowrap">
                        <div className="flex items-center justify-end gap-1 opacity-80 group-hover:opacity-100 transition-opacity">
                          <button
                            type="button"
                            onClick={() => startEditing(a)}
                            title="Edit row"
                            className="p-1.5 text-neutral-500 hover:text-neutral-900 hover:bg-neutral-100 rounded-lg transition-colors cursor-pointer"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDelete(a.id, a.title)}
                            title="Delete application"
                            className="p-1.5 text-neutral-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition-colors cursor-pointer"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
              {data?.apps.length === 0 && (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-sm text-neutral-400">
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

      {/* Add Application Modal */}
      {isAddModalOpen && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4 z-50 animate-in fade-in duration-100">
          <div className="bg-white rounded-2xl border border-neutral-200 shadow-xl max-w-md w-full p-6 space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-neutral-900">Add Application</h2>
              <button
                type="button"
                onClick={() => setIsAddModalOpen(false)}
                className="text-neutral-400 hover:text-neutral-600 p-1 rounded-lg hover:bg-neutral-100 transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {formError && (
              <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs rounded-xl flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{formError}</span>
              </div>
            )}

            <form onSubmit={handleCreateSubmit} className="space-y-3.5 text-xs">
              <div>
                <label className="block font-medium text-neutral-700 mb-1">
                  Role Title <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Senior Frontend Engineer"
                  value={formData.title}
                  onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                  className="w-full bg-white border border-neutral-200 rounded-xl px-3 py-2 text-sm focus:ring-1 focus:ring-neutral-800"
                />
              </div>

              <div>
                <label className="block font-medium text-neutral-700 mb-1">
                  Company Name <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Acme Corp"
                  value={formData.company}
                  onChange={(e) => setFormData({ ...formData, company: e.target.value })}
                  className="w-full bg-white border border-neutral-200 rounded-xl px-3 py-2 text-sm focus:ring-1 focus:ring-neutral-800"
                />
              </div>

              <div>
                <label className="block font-medium text-neutral-700 mb-1">
                  Job URL <span className="text-red-500">*</span>
                </label>
                <input
                  type="url"
                  required
                  placeholder="https://..."
                  value={formData.url}
                  onChange={(e) => setFormData({ ...formData, url: e.target.value })}
                  className="w-full bg-white border border-neutral-200 rounded-xl px-3 py-2 text-sm focus:ring-1 focus:ring-neutral-800"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-medium text-neutral-700 mb-1">
                    Applied Date
                  </label>
                  <input
                    type="date"
                    value={formData.applied_at}
                    onChange={(e) => setFormData({ ...formData, applied_at: e.target.value })}
                    className="w-full bg-white border border-neutral-200 rounded-xl px-3 py-2 text-sm focus:ring-1 focus:ring-neutral-800"
                  />
                </div>
                <div>
                  <label className="block font-medium text-neutral-700 mb-1">
                    Status
                  </label>
                  <select
                    value={formData.status}
                    onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                    className="w-full bg-white border border-neutral-200 rounded-xl px-3 py-2 text-sm focus:ring-1 focus:ring-neutral-800 cursor-pointer"
                  >
                    {STATUS_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-medium text-neutral-700 mb-1">
                    Location (Optional)
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Remote, Singapore"
                    value={formData.location}
                    onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                    className="w-full bg-white border border-neutral-200 rounded-xl px-3 py-2 text-sm focus:ring-1 focus:ring-neutral-800"
                  />
                </div>
                <div>
                  <label className="block font-medium text-neutral-700 mb-1">
                    Salary Entered (Optional)
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. $6,000"
                    value={formData.salary_entered}
                    onChange={(e) => setFormData({ ...formData, salary_entered: e.target.value })}
                    className="w-full bg-white border border-neutral-200 rounded-xl px-3 py-2 text-sm focus:ring-1 focus:ring-neutral-800"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-3">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setIsAddModalOpen(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  size="sm"
                  disabled={createApplicationMutation.isPending}
                >
                  {createApplicationMutation.isPending ? "Creating..." : "Save Application"}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

