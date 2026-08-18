import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { apiFetch } from "./client";

export interface DashboardData {
  total_jobs: number;
  apply_queue: number;
  counts: Record<string, number>;
  total_apps: number;
  runs: Array<{
    id: number;
    command: string;
    started_at: string;
    finished_at?: string;
    notes?: string;
  }>;
}

export function useDashboard(params: {
  sort?: string;
  order?: string;
} = {}) {
  const qs = new URLSearchParams();
  if (params.sort) qs.set("sort", params.sort);
  if (params.order) qs.set("order", params.order);

  return useQuery<DashboardData>({
    queryKey: ["dashboard", params],
    queryFn: () => apiFetch<DashboardData>(`/api/dashboard?${qs.toString()}`),
    refetchInterval: 10000,
  });
}

export interface JobsData {
  jobs: Array<{
    id: number;
    jobstreet_id?: string;
    title?: string;
    company?: string;
    location?: string;
    url?: string;
    decision?: string;
    match_pct?: number;
    model?: string;
    last_seen?: string;
    reason?: string;
    is_external?: number;
    application_id?: number | null;
  }>;
  total: number;
  page: number;
  per_page: number;
  total_pages: number;
}

export function useJobs(params: {
  decision?: string;
  q?: string;
  is_external?: boolean;
  sort?: string;
  order?: string;
  page?: number;
}) {
  const qs = new URLSearchParams();
  if (params.decision) qs.set("decision", params.decision);
  if (params.q) qs.set("q", params.q);
  if (params.is_external !== undefined) qs.set("is_external", String(params.is_external));
  if (params.sort) qs.set("sort", params.sort);
  if (params.order) qs.set("order", params.order);
  if (params.page) qs.set("page", String(params.page));

  return useQuery<JobsData>({
    queryKey: ["jobs", params],
    queryFn: () => apiFetch<JobsData>(`/api/jobs?${qs.toString()}`),
    placeholderData: keepPreviousData,
  });
}

export function useDecideJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      jobId,
      decision,
      reason,
    }: {
      jobId: string;
      decision: "apply" | "skip";
      reason?: string;
    }) =>
      apiFetch<{ success: boolean; message: string }>(
        `/api/jobs/${jobId}/decide`,
        {
          method: "POST",
          body: JSON.stringify({ decision, reason }),
        }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useMarkJobApplied() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (jobId: string | number) =>
      apiFetch<{ success: boolean; message: string }>(
        `/api/jobs/${jobId}/mark-applied`,
        {
          method: "POST",
        }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export interface ApplicationsData {
  apps: Array<{
    id: number;
    job_id: number;
    applied_at: string;
    salary_entered?: string;
    status: string;
    confirmation?: string;
    title?: string;
    company?: string;
    location?: string;
    url?: string;
  }>;
  page: number;
  has_next: boolean;
  total: number;
}

export function useApplications(params: {
  page?: number;
  status?: string;
  q?: string;
  sort?: string;
  order?: string;
} = {}) {
  const qs = new URLSearchParams();
  if (params.page) qs.set("page", String(params.page));
  if (params.status) qs.set("status", params.status);
  if (params.q) qs.set("q", params.q);
  if (params.sort) qs.set("sort", params.sort);
  if (params.order) qs.set("order", params.order);

  return useQuery<ApplicationsData>({
    queryKey: ["applications", params],
    queryFn: () => apiFetch<ApplicationsData>(`/api/applications?${qs.toString()}`),
    placeholderData: keepPreviousData,
  });
}

export function useUpdateApplicationStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      appId,
      status,
    }: {
      appId: number;
      status: string;
    }) =>
      apiFetch<{ success: boolean; message: string }>(
        `/api/applications/${appId}/status`,
        {
          method: "PATCH",
          body: JSON.stringify({ status }),
        }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
    },
  });
}

export interface CreateApplicationPayload {
  title: string;
  company: string;
  url: string;
  applied_at?: string;
  location?: string;
  salary_entered?: string;
  status?: string;
}

export function useCreateApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CreateApplicationPayload) =>
      apiFetch<{ success: boolean; message: string }>("/api/applications", {
        method: "POST",
        body: JSON.stringify(payload),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export interface UpdateApplicationPayload {
  title?: string;
  company?: string;
  location?: string;
  url?: string;
  applied_at?: string;
  salary_entered?: string;
  status?: string;
}

export function useUpdateApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      appId,
      payload,
    }: {
      appId: number;
      payload: UpdateApplicationPayload;
    }) =>
      apiFetch<{ success: boolean; message: string }>(
        `/api/applications/${appId}`,
        {
          method: "PUT",
          body: JSON.stringify(payload),
        }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
    },
  });
}

export function useDeleteApplication() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (appId: number) =>
      apiFetch<{ success: boolean; message: string }>(
        `/api/applications/${appId}`,
        {
          method: "DELETE",
        }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export interface ImportApplicationsResponseData {
  success: boolean;
  imported: number;
  skipped: number;
  errors: string[];
  message: string;
}

export function useImportApplications() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiFetch<ImportApplicationsResponseData>(
        "/api/applications/import",
        {
          method: "POST",
          body: formData,
        }
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["applications"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export interface RunsData {
  runs: Array<{
    id: number;
    command: string;
    started_at: string;
    finished_at?: string;
    notes?: string;
  }>;
}

export function useRuns(params: {
  sort?: string;
  order?: string;
} = {}) {
  const qs = new URLSearchParams();
  if (params.sort) qs.set("sort", params.sort);
  if (params.order) qs.set("order", params.order);

  return useQuery<RunsData>({
    queryKey: ["runs", params],
    queryFn: () => apiFetch<RunsData>(`/api/runs?${qs.toString()}`),
    refetchInterval: 5000,
  });
}

export function useRunDetail(runId: number) {
  return useQuery<{
    run: {
      id: number;
      command: string;
      started_at: string;
      finished_at?: string;
      notes?: string;
      alive?: boolean;
    };
    log: string;
  }>({
    queryKey: ["runDetail", runId],
    queryFn: () => apiFetch(`/api/runs/${runId}`),
    refetchInterval: (query) => {
      if (query.state.status === "error") return false;
      const data = query.state.data;
      if (data?.run?.finished_at) return false;
      return 2000;
    },
    retry: 1,
  });
}

export function useStartRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: any) =>
      apiFetch<{ success: boolean; run_id: number; message: string }>(
        "/api/runs",
        {
          method: "POST",
          body: JSON.stringify(payload),
        }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });
}

export function useCancelRun() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (runId: number) =>
      apiFetch<{ success: boolean; message: string }>(
        `/api/runs/${runId}/cancel`,
        {
          method: "POST",
        }
      ),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs"] });
      queryClient.invalidateQueries({ queryKey: ["runDetail"] });
    },
  });
}

export interface ProfileResponseData {
  profile: any;
  raw: Record<string, string>;
  has_profile: boolean;
}

export function useProfile() {
  return useQuery<ProfileResponseData>({
    queryKey: ["profile"],
    queryFn: () => apiFetch<ProfileResponseData>("/api/profile"),
  });
}

export interface ImportCVResponseData {
  success: boolean;
  profile: any;
  extracted_text_preview?: string;
  message?: string;
}

export function useImportCV() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiFetch<ImportCVResponseData>("/api/profile/import-cv", {
        method: "POST",
        body: formData,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });
}

export function useSaveProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (profile: any) =>
      apiFetch<{ success: boolean; message: string }>("/api/profile", {
        method: "POST",
        body: JSON.stringify(profile),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });
}

export interface SettingsData {
  cfg: any;
  llm_cfg: any;
  active_llm: any;
  env_overrides: any;
  has_auth: boolean;
  auth_mtime?: number;
  sec_filters: any;
  profile: any;
  has_api_key?: boolean;
  masked_suffix?: string;
  api_key_masked?: string;
  auth_tokens: Record<string, { connected: boolean; expires_at?: number | null }>;
  oauth_configs: any;
}

export function useSettings() {
  return useQuery<SettingsData>({
    queryKey: ["settings"],
    queryFn: () => apiFetch("/api/settings"),
    refetchInterval: 3000,
  });
}

export function useSaveSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ section, data }: { section: string; data: any }) =>
      apiFetch<{ success: boolean; message: string }>("/api/settings", {
        method: "POST",
        body: JSON.stringify({ section, data }),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["settings"] });
    },
  });
}

export function useProviderModels(provider: string) {
  return useQuery<{ provider: string; models: Array<{ id: string; name?: string }> }>({
    queryKey: ["models", provider],
    queryFn: () => apiFetch(`/api/settings/models/${provider}`),
    enabled: !!provider,
  });
}

export function useTestLlm() {
  return useMutation({
    mutationFn: () =>
      apiFetch<{ success: boolean; response?: string; error?: string }>(
        "/api/settings/test-llm",
        {
          method: "POST",
        }
      ),
  });
}

export function useDeleteAllData() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () =>
      apiFetch<{ success: boolean; message: string }>("/api/settings/all-data", {
        method: "DELETE",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries();
    },
  });
}
