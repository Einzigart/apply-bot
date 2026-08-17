import { useState, useEffect, useId, useMemo, useRef } from "react";
import { useNavigate } from "react-router";
import {
  Key,
  ShieldCheck,
  Zap,
  Target,
  ExternalLink,
  RefreshCw,
  LogOut,
  LogIn,
  CheckCircle2,
  AlertCircle,
  Globe,
  FileText,
  Sliders,
  Copy,
  Check,
  Eye,
  EyeOff,
  ChevronDown,
  ChevronRight,
  MoreVertical,
  Layers,
  X,
  Trash2,
} from "lucide-react";
import {
  useSettings,
  useSaveSettings,
  useTestLlm,
  useProviderModels,
  useDeleteAllData,
} from "../api/hooks";
import { Card, Button, Badge } from "../components/ui/core";
import {
  OpenAIIcon,
  ClaudeIcon,
  CopilotIcon,
  AntigravityIcon,
  JobstreetIcon,
  ProviderIcon,
} from "../components/ui/provider-icons";
import { apiFetch } from "../api/client";
import { cn, formatCurrency } from "../lib/utils";

// Provider readable labels
const PROVIDER_NAMES: Record<string, string> = {
  openai: "OpenAI Compatible",
  claude: "Claude Code",
  codex: "ChatGPT / Codex",
  chatgpt: "ChatGPT / Codex",
  copilot: "GitHub Copilot",
  gemini: "Google Antigravity",
  antigravity: "Google Antigravity",
};

export function SettingsPage() {
  const navigate = useNavigate();
  const { data: settings, isLoading, refetch } = useSettings();
  const saveMutation = useSaveSettings();
  const testLlmMutation = useTestLlm();
  const deleteAllDataMutation = useDeleteAllData();

  // Primary LLM configuration state
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("gpt-4o-mini");
  const [endpoint, setEndpoint] = useState("https://api.openai.com/v1");
  const [apiKey, setApiKey] = useState("");
  const [prefix, setPrefix] = useState("");

  // Persisted state cache for dirty checking
  const [initialLlmState, setInitialLlmState] = useState<{
    provider: string;
    model: string;
    endpoint: string;
    apiKey: string;
    prefix: string;
  } | null>(null);

  // UI interaction states
  const [showApiKey, setShowApiKey] = useState(false);
  const [copiedEndpoint, setCopiedEndpoint] = useState(false);
  const [isAdvancedOpen, setIsAdvancedOpen] = useState(false);
  const [manageProvider, setManageProvider] = useState<string | null>(null);
  const [disconnectCandidate, setDisconnectCandidate] = useState<string | null>(null);
  const [disconnecting, setDisconnecting] = useState(false);
  const [isJobstreetDeleteOpen, setIsJobstreetDeleteOpen] = useState(false);
  const [deletingJobstreetAuth, setDeletingJobstreetAuth] = useState(false);
  const [isDeleteAllOpen, setIsDeleteAllOpen] = useState(false);
  const [deleteConfirmationText, setDeleteConfirmationText] = useState("");

  // Inline connection test status
  const [testResult, setTestResult] = useState<{
    success?: boolean;
    response?: string;
    error?: string;
  } | null>(null);

  // Targets state
  const [rolesText, setRolesText] = useState("");
  const [locationsText, setLocationsText] = useState("");

  // Cover Letter state
  const [pitch, setPitch] = useState("");
  const [customInstructions, setCustomInstructions] = useState("");

  // Scoring threshold state
  const [matchThreshold, setMatchThreshold] = useState(60);

  // Salary state
  const [preferredSalary, setPreferredSalary] = useState(7000000);
  const [minAcceptableSalary, setMinAcceptableSalary] = useState(6000000);

  // Filters state
  const [cooldownDays, setCooldownDays] = useState(28);
  const [minYearsExp, setMinYearsExp] = useState(0);
  const [maxYearsExp, setMaxYearsExp] = useState(1);
  const [locationWhitelist, setLocationWhitelist] = useState("");
  const [roleKeywords, setRoleKeywords] = useState("");
  const [titleBlacklist, setTitleBlacklist] = useState("");

  // Copilot device code state
  const [copilotFlow, setCopilotFlow] = useState<{
    userCode?: string;
    verificationUri?: string;
    status?: string;
  } | null>(null);

  const [saveStatus, setSaveStatus] = useState<{
    section: string;
    message: string;
    error?: boolean;
  } | null>(null);

  // Accessible unique IDs
  const providerSelectId = useId();
  const modelSelectId = useId();
  const endpointInputId = useId();
  const apiKeyInputId = useId();
  const prefixInputId = useId();
  const prefixHelpId = useId();

  // Models query
  const {
    data: modelsData,
    isLoading: modelsLoading,
    refetch: refetchModels,
  } = useProviderModels(provider);

  useEffect(() => {
    if (settings) {
      // LLM
      const llm = settings.llm_cfg || {};
      const active = settings.active_llm || {};
      const p = active.provider || llm.provider || "openai";
      const m = active.raw_model || llm.model || "gpt-4o-mini";
      const ep = llm.endpoint || "https://api.openai.com/v1";
      const key = llm.api_key || "";
      const pfx = llm.prefix || "";

      setProvider(p);
      setModel(m);
      setEndpoint(ep);
      setApiKey(key);
      setPrefix(pfx);

      setInitialLlmState({
        provider: p,
        model: m,
        endpoint: ep,
        apiKey: key,
        prefix: pfx,
      });

      // Targets
      const search = settings.cfg?.search || {};
      const roles = (search.roles || [])
        .map((r: any) => `${r.name}: ${r.slug}`)
        .join("\n");
      const locs = (search.locations || [])
        .map((l: any) => `${l.name}: ${l.slug}`)
        .join("\n");
      setRolesText(roles);
      setLocationsText(locs);

      // Cover Letter
      const letter = settings.profile?.letter || {};
      setPitch(letter.pitch || "");
      setCustomInstructions(letter.custom_instructions || "");

      // Scoring
      const scoring = settings.cfg?.scoring || {};
      setMatchThreshold(Math.round((scoring.match_threshold || 0.6) * 100));

      // Salary
      const sal = settings.profile?.salary || {};
      setPreferredSalary(sal.preferred || 7000000);
      setMinAcceptableSalary(sal.min_acceptable || 6000000);

      // Filters
      const f = settings.cfg?.filters || {};
      setCooldownDays(f.company_cooldown_days ?? 28);
      setMinYearsExp(f.min_years_experience ?? 0);
      setMaxYearsExp(f.max_years_experience ?? 1);
      setLocationWhitelist((f.location_whitelist || []).join(", "));
      setRoleKeywords((f.role_keywords || []).join(", "));
      setTitleBlacklist((f.title_blacklist || []).join(", "));
    }
  }, [settings]);

  // Dirty state calculation
  const isLlmDirty = useMemo(() => {
    if (!initialLlmState) return false;
    return (
      provider !== initialLlmState.provider ||
      model !== initialLlmState.model ||
      endpoint !== initialLlmState.endpoint ||
      apiKey !== initialLlmState.apiKey ||
      prefix !== initialLlmState.prefix
    );
  }, [provider, model, endpoint, apiKey, prefix, initialLlmState]);

  const showStatus = (section: string, message: string, error = false) => {
    setSaveStatus({ section, message, error });
    setTimeout(() => setSaveStatus(null), 3500);
  };

  const handleCopyEndpoint = async () => {
    try {
      await navigator.clipboard.writeText(endpoint);
      setCopiedEndpoint(true);
      setTimeout(() => setCopiedEndpoint(false), 2000);
    } catch {
      // Fallback
    }
  };

  const handleSaveLlm = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    saveMutation.mutate(
      {
        section: "llm",
        data: { provider, endpoint, model, prefix, api_key: apiKey },
      },
      {
        onSuccess: (res) => {
          showStatus("llm", res.message || "Provider configuration saved");
          setInitialLlmState({
            provider,
            model,
            endpoint,
            apiKey,
            prefix,
          });
        },
        onError: (err) => showStatus("llm", err.message, true),
      }
    );
  };

  const handleTestConnection = () => {
    setTestResult(null);
    // If dirty, persist first so test-llm evaluates against active configuration
    if (isLlmDirty) {
      saveMutation.mutate(
        {
          section: "llm",
          data: { provider, endpoint, model, prefix, api_key: apiKey },
        },
        {
          onSuccess: () => {
            setInitialLlmState({
              provider,
              model,
              endpoint,
              apiKey,
              prefix,
            });
            executeLlmTest();
          },
          onError: (err) => {
            setTestResult({
              success: false,
              error: `Unable to save pending configuration: ${err.message}`,
            });
          },
        }
      );
    } else {
      executeLlmTest();
    }
  };

  const executeLlmTest = () => {
    testLlmMutation.mutate(undefined, {
      onSuccess: (res) => {
        setTestResult(res);
      },
      onError: (err) => {
        setTestResult({
          success: false,
          error: err.message || "Connection failed. Please check network and credentials.",
        });
      },
    });
  };

  const handleSaveTargets = (e: React.FormEvent) => {
    e.preventDefault();
    const parsedRoles = rolesText
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => {
        if (l.includes(":")) {
          const [name, slug] = l.split(":", 2);
          return { name: name.trim(), slug: slug.trim() };
        }
        return { name: l, slug: l.toLowerCase().replace(/\s+/g, "-") };
      });

    const parsedLocations = locationsText
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => {
        if (l.includes(":")) {
          const [name, slug] = l.split(":", 2);
          return { name: name.trim(), slug: slug.trim() };
        }
        return { name: l, slug: l.replace(/\s+/g, "-") };
      });

    saveMutation.mutate(
      {
        section: "roles_search",
        data: { roles: parsedRoles, locations: parsedLocations },
      },
      {
        onSuccess: () => showStatus("targets", "Search targets updated"),
        onError: (err) => showStatus("targets", err.message, true),
      }
    );
  };

  const handleSaveLetter = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate(
      {
        section: "letter",
        data: {
          pitch: pitch.trim(),
          custom_instructions: customInstructions.trim(),
        },
      },
      {
        onSuccess: () => showStatus("letter", "Cover letter instructions saved"),
        onError: (err) => showStatus("letter", err.message, true),
      }
    );
  };

  const handleSaveScoring = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate(
      {
        section: "scoring",
        data: { match_threshold: matchThreshold / 100 },
      },
      {
        onSuccess: () => showStatus("scoring", "Scoring threshold updated"),
        onError: (err) => showStatus("scoring", err.message, true),
      }
    );
  };

  const handleSaveSalary = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate(
      {
        section: "salary",
        data: {
          preferred: preferredSalary,
          min_acceptable: minAcceptableSalary,
        },
      },
      {
        onSuccess: () => showStatus("salary", "Salary preferences updated"),
        onError: (err) => showStatus("salary", err.message, true),
      }
    );
  };

  const handleSaveFilters = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate(
      {
        section: "filters",
        data: {
          company_cooldown_days: cooldownDays,
          min_years_experience: minYearsExp,
          max_years_experience: maxYearsExp,
          location_whitelist: locationWhitelist
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          role_keywords: roleKeywords
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          title_blacklist: titleBlacklist
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        },
      },
      {
        onSuccess: () => showStatus("filters", "Filter constraints updated"),
        onError: (err) => showStatus("filters", err.message, true),
      }
    );
  };

  const handleOAuthLogin = async (prov: string) => {
    try {
      const res = await apiFetch<{ success: boolean; message?: string }>(
        `/api/settings/oauth/${prov}/login`,
        { method: "POST" }
      );
      showStatus("oauth", res.message || `Connected to ${PROVIDER_NAMES[prov] || prov}`);
      refetch();
    } catch (err: any) {
      showStatus("oauth", err.message, true);
    }
  };

  const handleConfirmDisconnect = async () => {
    if (!disconnectCandidate) return;
    setDisconnecting(true);
    try {
      await apiFetch(`/api/settings/oauth/${disconnectCandidate}/logout`, {
        method: "POST",
      });
      showStatus("oauth", `Disconnected ${PROVIDER_NAMES[disconnectCandidate] || disconnectCandidate}`);
      setDisconnectCandidate(null);
      setManageProvider(null);
      refetch();
    } catch (err: any) {
      showStatus("oauth", err.message, true);
    } finally {
      setDisconnecting(false);
    }
  };

  const handleDeleteJobstreetAuth = async () => {
    setDeletingJobstreetAuth(true);
    try {
      const res = await apiFetch<{ success: boolean; message: string }>(
        "/api/settings/jobstreet/auth",
        { method: "DELETE" }
      );
      showStatus("oauth", res.message || "Jobstreet auth removed");
      setIsJobstreetDeleteOpen(false);
      refetch();
    } catch (err: any) {
      showStatus("oauth", err.message, true);
    } finally {
      setDeletingJobstreetAuth(false);
    }
  };

  const handleDeleteAllData = async () => {
    deleteAllDataMutation.mutate(undefined, {
      onSuccess: (res) => {
        showStatus("danger", res.message || "User profile and database deleted");
        setIsDeleteAllOpen(false);
        setDeleteConfirmationText("");
        // Redirect to onboarding / setup wizard screen
        navigate("/setup", { replace: true });
      },
      onError: (err: any) => {
        showStatus("danger", err.message || "Failed to delete user profile and database", true);
      },
    });
  };

  const startCopilotFlow = async () => {
    try {
      setCopilotFlow({ status: "Requesting device code..." });
      const data = await apiFetch<{
        user_code: string;
        verification_uri: string;
        device_code: string;
        interval: number;
      }>("/api/settings/oauth/copilot/device-code", { method: "POST" });

      setCopilotFlow({
        userCode: data.user_code,
        verificationUri: data.verification_uri,
        status: "Waiting for authorization in browser...",
      });

      window.open(data.verification_uri, "_blank");

      const pollRes = await apiFetch<{ success: boolean }>(
        "/api/settings/oauth/copilot/poll",
        {
          method: "POST",
          body: JSON.stringify({
            device_code: data.device_code,
            interval: data.interval,
          }),
        }
      );

      if (pollRes.success) {
        setCopilotFlow({ status: "Authenticated!" });
        setTimeout(() => {
          setCopilotFlow(null);
          refetch();
        }, 1500);
      }
    } catch (err: any) {
      setCopilotFlow({ status: `Failed: ${err.message}` });
    }
  };

  const isSubscription = [
    "claude",
    "codex",
    "chatgpt",
    "copilot",
    "gemini",
    "antigravity",
  ].includes(provider);

  if (isLoading || !settings) {
    return (
      <div className="space-y-6 animate-pulse" aria-busy="true" aria-label="Loading settings">
        <div className="space-y-2">
          <div className="h-7 bg-neutral-200 rounded-xl w-36" />
          <div className="h-4 bg-neutral-100 rounded-xl w-72" />
        </div>
        <div className="h-80 bg-neutral-100 rounded-xl border border-neutral-200/60" />
        <div className="h-48 bg-neutral-100 rounded-xl border border-neutral-200/60" />
      </div>
    );
  }

  const { has_auth, auth_tokens = {}, active_llm = {} } = settings;

  // Active provider summary string computation
  const activeProviderName = PROVIDER_NAMES[provider] || provider;
  const isProviderConfigured = Boolean(
    (isSubscription && auth_tokens[provider]) ||
    (!isSubscription && (apiKey || endpoint))
  );

  return (
    <div className="space-y-10 pb-16">
      {/* 1. Page Header */}
      <header className="border-b border-neutral-200/80 pb-5">
        <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
          Settings
        </h1>
        <p className="text-sm text-neutral-500 mt-1">
          Configure integrations, AI provider defaults, and job-search preferences.
        </p>
      </header>

      {/* 2. Primary Section: AI Provider */}
      <section aria-labelledby="ai-provider-heading" className="space-y-4">
        <div>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-neutral-800" aria-hidden="true" />
              <h2 id="ai-provider-heading" className="text-lg font-semibold text-neutral-900 tracking-tight">
                AI provider
              </h2>
            </div>

            {saveStatus?.section === "llm" && (
              <Badge variant={saveStatus.error ? "danger" : "apply"}>
                {saveStatus.message}
              </Badge>
            )}
          </div>

          {/* Compact active provider summary */}
          <div className="mt-3 p-3.5 bg-neutral-50/80 rounded-xl border border-neutral-200/80 flex items-start gap-3">
            <ProviderIcon provider={provider} className="w-5 h-5 mt-0.5 text-neutral-800 shrink-0" />
            <div className="text-xs leading-relaxed">
              {isProviderConfigured ? (
                <>
                  <div className="font-semibold text-neutral-900">
                    {activeProviderName} is active
                  </div>
                  <div className="text-neutral-500 font-mono text-[11px] mt-0.5">
                    Using <span className="font-semibold text-neutral-800">{model}</span> through{" "}
                    {isSubscription ? "authenticated subscription session" : endpoint || "default endpoint"}.
                  </div>
                </>
              ) : (
                <>
                  <div className="font-semibold text-neutral-900">
                    No AI provider configured
                  </div>
                  <div className="text-neutral-500 text-[11px] mt-0.5">
                    Connect a provider or configure an OpenAI-compatible endpoint to continue.
                  </div>
                </>
              )}
            </div>
          </div>
        </div>

        {/* 3. Provider Configuration Form */}
        <Card className="p-6 border-neutral-200/90 shadow-2xs">
          <form onSubmit={handleSaveLlm} className="space-y-6">
            {/* Group A: Provider and model */}
            <div className="space-y-3.5">
              <div className="text-xs font-semibold uppercase tracking-wider text-neutral-500">
                Provider and model
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {/* Active Provider */}
                <div>
                  <label
                    htmlFor={providerSelectId}
                    className="block text-xs font-medium text-neutral-700 mb-1.5"
                  >
                    Active provider <span className="text-red-500" aria-hidden="true">*</span>
                  </label>
                  <select
                    id={providerSelectId}
                    value={provider}
                    onChange={(e) => {
                      const next = e.target.value;
                      setProvider(next);
                      // Default sensible model if switching
                      if (next === "claude") setModel("claude-3-5-sonnet-20241022");
                      else if (next === "codex") setModel("gpt-5.4-mini");
                      else if (next === "copilot") setModel("gpt-4o");
                      else if (next === "gemini") setModel("gemini-2.5-flash");
                      else if (next === "openai") setModel("gpt-4o-mini");
                    }}
                    className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3.5 py-2 text-neutral-900 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-900 transition-colors"
                  >
                    <option value="openai">OpenAI Compatible (BYOK)</option>
                    <option value="claude">Claude Code (Anthropic Subscription)</option>
                    <option value="codex">ChatGPT / Codex (OpenAI Subscription)</option>
                    <option value="copilot">GitHub Copilot (Subscription)</option>
                    <option value="gemini">Google Antigravity (Subscription)</option>
                  </select>
                </div>

                {/* Model Selection */}
                <div>
                  <div className="flex items-center justify-between mb-1.5">
                    <label
                      htmlFor={modelSelectId}
                      className="block text-xs font-medium text-neutral-700"
                    >
                      Model selection <span className="text-red-500" aria-hidden="true">*</span>
                    </label>
                    <button
                      type="button"
                      onClick={() => refetchModels()}
                      aria-label="Refresh model catalog from provider"
                      className="text-xs text-neutral-600 hover:text-neutral-900 inline-flex items-center gap-1.5 cursor-pointer rounded-xl px-1.5 py-0.5 hover:bg-neutral-100 transition-colors"
                    >
                      <RefreshCw
                        className={cn("w-3 h-3 text-neutral-500", modelsLoading && "animate-spin text-neutral-900")}
                        aria-hidden="true"
                      />
                      <span>{modelsLoading ? "Refreshing..." : "Refresh models"}</span>
                    </button>
                  </div>

                  {modelsData?.models && modelsData.models.length > 0 ? (
                    <select
                      id={modelSelectId}
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      className="w-full text-sm font-mono bg-neutral-50 border border-neutral-200 rounded-xl px-3.5 py-2 text-neutral-900 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-900 transition-colors"
                    >
                      {modelsData.models.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.name && m.name !== m.id ? `${m.name} (${m.id})` : m.id}
                        </option>
                      ))}
                      {!modelsData.models.some((m) => m.id === model) && (
                        <option value={model}>Custom: {model}</option>
                      )}
                    </select>
                  ) : (
                    <input
                      id={modelSelectId}
                      type="text"
                      value={model}
                      onChange={(e) => setModel(e.target.value)}
                      placeholder="e.g. gpt-4o-mini, claude-3-5-sonnet"
                      className="w-full text-sm font-mono bg-neutral-50 border border-neutral-200 rounded-xl px-3.5 py-2 text-neutral-900 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-900 transition-colors"
                    />
                  )}
                </div>
              </div>
            </div>

            {/* If OpenAI Compatible (BYOK), show Connection and Credentials */}
            {!isSubscription && (
              <>
                <div className="border-t border-neutral-100" />

                {/* Group B: Connection */}
                <div className="space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wider text-neutral-500">
                    Connection
                  </div>
                  <div>
                    <label
                      htmlFor={endpointInputId}
                      className="block text-xs font-medium text-neutral-700 mb-1.5"
                    >
                      API endpoint / Base URL
                    </label>
                    <div className="relative flex items-center">
                      <input
                        id={endpointInputId}
                        type="text"
                        value={endpoint}
                        onChange={(e) => setEndpoint(e.target.value)}
                        placeholder="https://api.openai.com/v1"
                        className="w-full text-sm font-mono bg-neutral-50 border border-neutral-200 rounded-xl pl-3.5 pr-10 py-2 text-neutral-900 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-900 transition-colors"
                      />
                      <div className="absolute right-2.5 flex items-center">
                        <button
                          type="button"
                          onClick={handleCopyEndpoint}
                          aria-label="Copy API endpoint URL to clipboard"
                          title="Copy endpoint"
                          className="text-neutral-400 hover:text-neutral-800 transition-colors cursor-pointer p-1"
                        >
                          {copiedEndpoint ? (
                            <Check className="w-4 h-4 text-emerald-600" aria-hidden="true" />
                          ) : (
                            <Copy className="w-4 h-4" aria-hidden="true" />
                          )}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="border-t border-neutral-100" />

                {/* Group C: Credentials */}
                <div className="space-y-2">
                  <div className="text-xs font-semibold uppercase tracking-wider text-neutral-500">
                    Credentials
                  </div>
                  <div>
                    <label
                      htmlFor={apiKeyInputId}
                      className="block text-xs font-medium text-neutral-700 mb-1.5"
                    >
                      API key
                    </label>
                    <div className="relative flex items-center">
                      <input
                        id={apiKeyInputId}
                        type={showApiKey ? "text" : "password"}
                        value={apiKey}
                        onChange={(e) => setApiKey(e.target.value)}
                        placeholder="sk-..."
                        autoComplete="off"
                        spellCheck={false}
                        className="w-full text-sm font-mono bg-neutral-50 border border-neutral-200 rounded-xl pl-3.5 pr-10 py-2 text-neutral-900 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-900 transition-colors"
                      />
                      <div className="absolute right-2.5 flex items-center">
                        <button
                          type="button"
                          onClick={() => setShowApiKey((prev) => !prev)}
                          aria-label={showApiKey ? "Hide API key" : "Show API key"}
                          title={showApiKey ? "Hide API key" : "Show API key"}
                          className="text-neutral-400 hover:text-neutral-800 transition-colors cursor-pointer p-1"
                        >
                          {showApiKey ? (
                            <EyeOff className="w-4 h-4" aria-hidden="true" />
                          ) : (
                            <Eye className="w-4 h-4" aria-hidden="true" />
                          )}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </>
            )}

            <div className="border-t border-neutral-100" />

            {/* Group D: Advanced settings */}
            <div className="space-y-3">
              <button
                type="button"
                onClick={() => setIsAdvancedOpen((prev) => !prev)}
                aria-expanded={isAdvancedOpen}
                aria-controls="advanced-provider-settings"
                className="flex items-center justify-between w-full py-1 text-xs font-semibold text-neutral-700 hover:text-neutral-900 cursor-pointer select-none transition-colors"
              >
                <div className="flex items-center gap-2">
                  <Sliders className="w-3.5 h-3.5 text-neutral-500" aria-hidden="true" />
                  <span>Advanced settings</span>
                </div>
                {isAdvancedOpen ? (
                  <ChevronDown className="w-4 h-4 text-neutral-400" aria-hidden="true" />
                ) : (
                  <ChevronRight className="w-4 h-4 text-neutral-400" aria-hidden="true" />
                )}
              </button>

              {isAdvancedOpen && (
                <div
                  id="advanced-provider-settings"
                  className="space-y-3 pt-1 pl-1"
                >
                  <div>
                    <label
                      htmlFor={prefixInputId}
                      className="block text-xs font-medium text-neutral-700 mb-1"
                    >
                      Model prefix
                    </label>
                    <input
                      id={prefixInputId}
                      type="text"
                      value={prefix}
                      onChange={(e) => setPrefix(e.target.value)}
                      placeholder="e.g. openai/ or groq/"
                      aria-describedby={prefixHelpId}
                      className="w-full text-sm font-mono bg-neutral-50 border border-neutral-200 rounded-xl px-3.5 py-2 text-neutral-900 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-900 transition-colors"
                    />
                    <p
                      id={prefixHelpId}
                      className="text-xs text-neutral-500 mt-1.5 leading-relaxed"
                    >
                      Optional. Prefixes model IDs returned by this endpoint when required by a proxy or provider.
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Test result status feedback */}
            {testResult && (
              <div
                role="status"
                aria-live="polite"
                className={cn(
                  "p-3.5 rounded-xl text-xs font-mono flex items-start gap-2.5 border transition-all",
                  testResult.success
                    ? "bg-emerald-50 text-emerald-900 border-emerald-200/80"
                    : "bg-red-50 text-red-900 border-red-200/80"
                )}
              >
                {testResult.success ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" aria-hidden="true" />
                ) : (
                  <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" aria-hidden="true" />
                )}
                <div className="space-y-0.5">
                  <div className="font-sans font-semibold">
                    {testResult.success ? "Connection successful" : "Connection failed"}
                  </div>
                  <div className="text-[11px] leading-relaxed break-all">
                    {testResult.success ? testResult.response : testResult.error}
                  </div>
                </div>
              </div>
            )}

            {/* Actions: Sticky Action Bar */}
            <div className="pt-4 border-t border-neutral-100 flex flex-col-reverse sm:flex-row items-stretch sm:items-center justify-end gap-2.5">
              <Button
                type="button"
                variant="outline"
                size="md"
                onClick={handleTestConnection}
                disabled={testLlmMutation.isPending || saveMutation.isPending}
                aria-label="Test connection with current configuration"
              >
                <Zap
                  className={cn("w-3.5 h-3.5 text-neutral-600", testLlmMutation.isPending && "animate-spin")}
                  aria-hidden="true"
                />
                <span>{testLlmMutation.isPending ? "Testing connection..." : "Test connection"}</span>
              </Button>

              <Button
                type="submit"
                variant="primary"
                size="md"
                disabled={!isLlmDirty || saveMutation.isPending || testLlmMutation.isPending}
              >
                {saveMutation.isPending ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
                    <span>Saving changes...</span>
                  </>
                ) : (
                  <span>Save changes</span>
                )}
              </Button>
            </div>
          </form>
        </Card>
      </section>

      {/* 4. Secondary Section: Connected AI Services */}
      <section aria-labelledby="connected-services-heading" className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Key className="w-4 h-4 text-neutral-700" aria-hidden="true" />
            <h2 id="connected-services-heading" className="text-base font-semibold text-neutral-900 tracking-tight">
              Connected AI services
            </h2>
          </div>

          {saveStatus?.section === "oauth" && (
            <Badge variant={saveStatus.error ? "danger" : "apply"}>
              {saveStatus.message}
            </Badge>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          {/* Claude Code */}
          <ConnectedServiceCard
            icon={<ClaudeIcon className="w-5 h-5 shrink-0" />}
            name="Claude Code"
            description="Anthropic Claude Pro / Team / Enterprise"
            isConnected={Boolean(auth_tokens.claude)}
            onConnect={() => handleOAuthLogin("claude")}
            onManage={() => setManageProvider("claude")}
          />

          {/* ChatGPT / Codex */}
          <ConnectedServiceCard
            icon={<OpenAIIcon className="w-5 h-5 shrink-0 text-neutral-800" />}
            name="ChatGPT / Codex"
            description="OpenAI ChatGPT Plus / Pro OAuth session"
            isConnected={Boolean(auth_tokens.codex)}
            onConnect={() => handleOAuthLogin("codex")}
            onManage={() => setManageProvider("codex")}
          />

          {/* GitHub Copilot */}
          <ConnectedServiceCard
            icon={<CopilotIcon className="w-5 h-5 shrink-0 text-neutral-800" />}
            name="GitHub Copilot"
            description="GitHub Copilot via Device Code authorization"
            isConnected={Boolean(auth_tokens.copilot)}
            onConnect={startCopilotFlow}
            onManage={() => setManageProvider("copilot")}
          />

          {/* Google Antigravity */}
          <ConnectedServiceCard
            icon={<AntigravityIcon className="w-5 h-5 shrink-0" />}
            name="Google Antigravity"
            description="Google Code Assist / Gemini 2.5 & 3.7 access"
            isConnected={Boolean(auth_tokens.gemini)}
            onConnect={() => handleOAuthLogin("gemini")}
            onManage={() => setManageProvider("gemini")}
          />
        </div>

        {/* Copilot Device Code Dialog */}
        {copilotFlow && (
          <Card className="p-4 bg-sky-50/60 border-sky-200 text-xs space-y-2.5">
            <div className="font-semibold text-sky-950 flex items-center justify-between">
              <span>GitHub Copilot Device Authorization</span>
              <button
                type="button"
                onClick={() => setCopilotFlow(null)}
                aria-label="Cancel Copilot login"
                className="text-sky-800 hover:text-sky-950 cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            {copilotFlow.userCode && (
              <div className="space-y-1 text-sky-900 leading-relaxed">
                <div>
                  1. Open verification page:{" "}
                  <a
                    href={copilotFlow.verificationUri}
                    target="_blank"
                    rel="noreferrer"
                    className="font-bold underline text-sky-800 hover:text-sky-950 inline-flex items-center gap-1"
                  >
                    <span>{copilotFlow.verificationUri}</span>
                    <ExternalLink className="w-3 h-3" />
                  </a>
                </div>
                <div>
                  2. Enter device code:{" "}
                  <code className="font-mono bg-white px-2 py-0.5 rounded-xl border border-sky-200 font-bold text-sm text-neutral-900 select-all">
                    {copilotFlow.userCode}
                  </code>
                </div>
              </div>
            )}
            <div className="text-sky-800 font-mono text-[11px] pt-1">
              Status: {copilotFlow.status}
            </div>
          </Card>
        )}
      </section>

      {/* 5. Secondary Section: Jobstreet Connection */}
      <section aria-labelledby="jobstreet-heading" className="space-y-4">
        <div className="flex items-center gap-2">
          <JobstreetIcon
            className={cn(
              "w-4 h-4",
              has_auth ? "text-[#0d3880]" : "text-neutral-500"
            )}
            aria-hidden="true"
          />
          <h2 id="jobstreet-heading" className="text-base font-semibold text-neutral-900 tracking-tight">
            Jobstreet connection
          </h2>
        </div>

        <Card className="p-5 border-neutral-200/90 shadow-2xs">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-neutral-900">
                  Jobstreet session
                </span>
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border",
                    has_auth
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200/80"
                      : "bg-neutral-100 text-neutral-600 border-neutral-200/80"
                  )}
                >
                  <span
                    className={cn(
                      "w-1.5 h-1.5 rounded-full",
                      has_auth ? "bg-emerald-500" : "bg-neutral-400"
                    )}
                    aria-hidden="true"
                  />
                  <span>{has_auth ? "Active session" : "No saved session"}</span>
                </span>
              </div>
              <p className="text-xs text-neutral-500 mt-0.5">
                {has_auth
                  ? "Logged in · Authenticated browser state saved in data/storage_state.json"
                  : "No authenticated session found. Launch an external browser to log in."}
              </p>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <Button
                size="sm"
                variant="outline"
                onClick={async () => {
                  try {
                    await apiFetch("/api/settings/jobstreet/system-login", {
                      method: "POST",
                    });
                    showStatus("oauth", "External browser opened for Jobstreet login!");
                    // Poll settings query immediately after triggering login flow
                    setTimeout(() => refetch(), 2000);
                    setTimeout(() => refetch(), 5000);
                  } catch (e: any) {
                    showStatus("oauth", e.message, true);
                  }
                }}
                className="shrink-0"
                title="Launch external browser window to sign in to Jobstreet"
              >
                <Globe className="w-3.5 h-3.5" aria-hidden="true" />
                <span>{has_auth ? "Re-authenticate in browser" : "Log in in browser"}</span>
              </Button>

              {has_auth && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setIsJobstreetDeleteOpen(true)}
                  aria-label="Remove saved Jobstreet auth"
                  title="Remove saved Jobstreet authentication"
                  className="px-2 text-neutral-500 hover:text-red-600 hover:border-red-200 hover:bg-red-50 shrink-0"
                >
                  <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
                </Button>
              )}
            </div>
          </div>
        </Card>
      </section>

      {/* 6. Target Searches */}
      <section aria-labelledby="targets-heading" className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Target className="w-4 h-4 text-neutral-700" aria-hidden="true" />
            <h2 id="targets-heading" className="text-base font-semibold text-neutral-900 tracking-tight">
              Search targets
            </h2>
          </div>
          {saveStatus?.section === "targets" && (
            <Badge variant={saveStatus.error ? "danger" : "apply"}>
              {saveStatus.message}
            </Badge>
          )}
        </div>

        <Card className="p-5 border-neutral-200/90 shadow-2xs">
          <form onSubmit={handleSaveTargets} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1.5">
                  Roles (Name: url-slug, one per line)
                </label>
                <textarea
                  rows={5}
                  value={rolesText}
                  onChange={(e) => setRolesText(e.target.value)}
                  className="w-full text-xs font-mono bg-neutral-50 border border-neutral-200 rounded-xl p-3 text-neutral-900 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-900 transition-colors"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1.5">
                  Locations (Name: url-slug, one per line)
                </label>
                <textarea
                  rows={5}
                  value={locationsText}
                  onChange={(e) => setLocationsText(e.target.value)}
                  className="w-full text-xs font-mono bg-neutral-50 border border-neutral-200 rounded-xl p-3 text-neutral-900 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-900 transition-colors"
                />
              </div>
            </div>
            <div className="flex justify-end pt-3 border-t border-neutral-100">
              <Button type="submit" size="sm">
                Save search targets
              </Button>
            </div>
          </form>
        </Card>
      </section>

      {/* 7. Cover Letter Configuration */}
      <section aria-labelledby="cover-letter-heading" className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4 text-neutral-700" aria-hidden="true" />
            <h2 id="cover-letter-heading" className="text-base font-semibold text-neutral-900 tracking-tight">
              AI cover letter tailoring
            </h2>
          </div>
          {saveStatus?.section === "letter" && (
            <Badge variant={saveStatus.error ? "danger" : "apply"}>
              {saveStatus.message}
            </Badge>
          )}
        </div>

        <Card className="p-5 border-neutral-200/90 shadow-2xs">
          <form onSubmit={handleSaveLetter} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-neutral-700 mb-1.5">
                Professional pitch / Headline (1 Line summary)
              </label>
              <input
                type="text"
                value={pitch}
                onChange={(e) => setPitch(e.target.value)}
                placeholder="e.g. Senior Product Designer with 5+ years building fintech systems"
                className="w-full text-xs font-mono bg-neutral-50 border border-neutral-200 rounded-xl px-3.5 py-2 text-neutral-900 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-900 transition-colors"
              />
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="block text-xs font-medium text-neutral-700">
                  Custom prompt instructions (Optional)
                </label>
                <span className="text-[11px] text-neutral-400">
                  Leave empty to use standard prompt
                </span>
              </div>
              <textarea
                rows={3}
                value={customInstructions}
                onChange={(e) => setCustomInstructions(e.target.value)}
                placeholder="e.g. Write in Indonesian if the job description is in Indonesian. Keep under 120 words..."
                className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl p-3 text-neutral-900 focus:bg-white focus:outline-hidden focus:ring-2 focus:ring-neutral-900/10 focus:border-neutral-900 transition-colors leading-relaxed font-sans"
              />
            </div>

            <div className="flex justify-end pt-3 border-t border-neutral-100">
              <Button type="submit" size="sm">
                Save cover letter settings
              </Button>
            </div>
          </form>
        </Card>
      </section>

      {/* 8. Scoring & Salary Thresholds */}
      <section aria-labelledby="scoring-salary-heading" className="space-y-4">
        <div className="flex items-center gap-2">
          <Sliders className="w-4 h-4 text-neutral-700" aria-hidden="true" />
          <h2 id="scoring-salary-heading" className="text-base font-semibold text-neutral-900 tracking-tight">
            Scoring and salary expectations
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Scoring Threshold */}
          <Card className="p-5 border-neutral-200/90 shadow-2xs space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold uppercase tracking-wider text-neutral-500">
                Match threshold
              </div>
              {saveStatus?.section === "scoring" && (
                <Badge variant={saveStatus.error ? "danger" : "apply"}>
                  {saveStatus.message}
                </Badge>
              )}
            </div>

            <form onSubmit={handleSaveScoring} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1.5">
                  Apply match threshold (% requirements met)
                </label>
                <div className="flex items-center gap-2.5">
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={matchThreshold}
                    onChange={(e) => setMatchThreshold(parseInt(e.target.value, 10))}
                    className="w-24 text-sm font-bold bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-1.5 text-neutral-900 focus:bg-white"
                  />
                  <span className="text-xs font-medium text-neutral-500">%</span>
                </div>
              </div>
              <div className="flex justify-end pt-3 border-t border-neutral-100">
                <Button type="submit" size="sm">
                  Save threshold
                </Button>
              </div>
            </form>
          </Card>

          {/* Salary Preferences */}
          <Card className="p-5 border-neutral-200/90 shadow-2xs space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-xs font-semibold uppercase tracking-wider text-neutral-500">
                Salary range
              </div>
              {saveStatus?.section === "salary" && (
                <Badge variant={saveStatus.error ? "danger" : "apply"}>
                  {saveStatus.message}
                </Badge>
              )}
            </div>

            <form onSubmit={handleSaveSalary} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-medium text-neutral-700 mb-1.5">
                    Preferred (IDR)
                  </label>
                  <input
                    type="number"
                    step={100000}
                    value={preferredSalary}
                    onChange={(e) => setPreferredSalary(parseInt(e.target.value, 10))}
                    className="w-full text-xs font-mono bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-neutral-700 mb-1.5">
                    Min acceptable (IDR)
                  </label>
                  <input
                    type="number"
                    step={100000}
                    value={minAcceptableSalary}
                    onChange={(e) => setMinAcceptableSalary(parseInt(e.target.value, 10))}
                    className="w-full text-xs font-mono bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
                  />
                </div>
              </div>
              <div className="flex justify-end pt-3 border-t border-neutral-100">
                <Button type="submit" size="sm">
                  Save salary
                </Button>
              </div>
            </form>
          </Card>
        </div>
      </section>

      {/* 9. Application Rules & Filters */}
      <section aria-labelledby="filters-heading" className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-neutral-700" aria-hidden="true" />
            <h2 id="filters-heading" className="text-base font-semibold text-neutral-900 tracking-tight">
              Application rules and constraints
            </h2>
          </div>
          {saveStatus?.section === "filters" && (
            <Badge variant={saveStatus.error ? "danger" : "apply"}>
              {saveStatus.message}
            </Badge>
          )}
        </div>

        <Card className="p-5 border-neutral-200/90 shadow-2xs">
          <form onSubmit={handleSaveFilters} className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1.5">
                  Company cooldown (Days)
                </label>
                <input
                  type="number"
                  min={0}
                  value={cooldownDays}
                  onChange={(e) => setCooldownDays(parseInt(e.target.value, 10))}
                  className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3.5 py-2 text-neutral-900 focus:bg-white"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1.5">
                  Experience range required (Years)
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    min={0}
                    value={minYearsExp}
                    onChange={(e) => setMinYearsExp(parseInt(e.target.value, 10))}
                    className="w-20 text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
                  />
                  <span className="text-xs text-neutral-500">to</span>
                  <input
                    type="number"
                    min={0}
                    value={maxYearsExp}
                    onChange={(e) => setMaxYearsExp(parseInt(e.target.value, 10))}
                    className="w-20 text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
                  />
                  <span className="text-xs text-neutral-500">years</span>
                </div>
              </div>

              <div className="md:col-span-2">
                <label className="block text-xs font-medium text-neutral-700 mb-1.5">
                  Location whitelist (Comma-separated)
                </label>
                <input
                  type="text"
                  value={locationWhitelist}
                  onChange={(e) => setLocationWhitelist(e.target.value)}
                  className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3.5 py-2 text-neutral-900 focus:bg-white"
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-xs font-medium text-neutral-700 mb-1.5">
                  Role keywords required in title (Comma-separated)
                </label>
                <input
                  type="text"
                  value={roleKeywords}
                  onChange={(e) => setRoleKeywords(e.target.value)}
                  className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3.5 py-2 text-neutral-900 focus:bg-white"
                />
              </div>

              <div className="md:col-span-2">
                <label className="block text-xs font-medium text-neutral-700 mb-1.5">
                  Title blacklist keywords (Comma-separated)
                </label>
                <input
                  type="text"
                  value={titleBlacklist}
                  onChange={(e) => setTitleBlacklist(e.target.value)}
                  className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3.5 py-2 text-neutral-900 focus:bg-white"
                />
              </div>
            </div>

            <div className="flex justify-end pt-3 border-t border-neutral-100">
              <Button type="submit" size="sm">
                Save filter rules
              </Button>
            </div>
          </form>
        </Card>
      </section>

      {/* 10. Active Configuration Summary */}
      <section aria-labelledby="summary-heading" className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-neutral-700" aria-hidden="true" />
            <h2 id="summary-heading" className="text-base font-semibold text-neutral-900 tracking-tight">
              Active configuration summary
            </h2>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {/* Effective Provider */}
          <div className="p-3.5 rounded-xl border border-neutral-200/80 bg-neutral-50/50 flex flex-col justify-between space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-neutral-500">Effective AI Provider</span>
              <Badge variant="neutral" className="text-[10px] px-1.5 py-0">
                {settings?.env_overrides?.provider ? "env var" : "secrets.yaml"}
              </Badge>
            </div>
            <div className="flex items-center gap-2">
              <ProviderIcon provider={active_llm.provider || "openai"} className="w-4 h-4 text-neutral-800 shrink-0" />
              <span className="font-mono text-sm font-semibold text-neutral-900 capitalize">
                {active_llm.provider || "—"}
              </span>
            </div>
          </div>

          {/* Effective Model */}
          <div className="p-3.5 rounded-xl border border-neutral-200/80 bg-neutral-50/50 flex flex-col justify-between space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-neutral-500">Effective Model</span>
              <Badge variant="neutral" className="text-[10px] px-1.5 py-0">
                {settings?.env_overrides?.model ? "env var" : "config.yaml"}
              </Badge>
            </div>
            <div className="font-mono text-xs font-semibold text-neutral-900 truncate" title={active_llm.model}>
              {active_llm.model || "—"}
            </div>
          </div>

          {/* Company Cooldown */}
          <div className="p-3.5 rounded-xl border border-neutral-200/80 bg-neutral-50/50 flex flex-col justify-between space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-neutral-500">Company Cooldown</span>
              <Badge variant="neutral" className="text-[10px] px-1.5 py-0">
                secrets.yaml
              </Badge>
            </div>
            <div className="font-mono text-sm font-semibold text-neutral-900">
              {cooldownDays} <span className="text-xs font-normal font-sans text-neutral-500">day(s)</span>
            </div>
          </div>

          {/* Experience Range */}
          <div className="p-3.5 rounded-xl border border-neutral-200/80 bg-neutral-50/50 flex flex-col justify-between space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-neutral-500">Experience Range</span>
              <Badge variant="neutral" className="text-[10px] px-1.5 py-0">
                secrets.yaml
              </Badge>
            </div>
            <div className="font-mono text-sm font-semibold text-neutral-900">
              {minYearsExp} – {maxYearsExp} <span className="text-xs font-normal font-sans text-neutral-500">year(s)</span>
            </div>
          </div>
        </div>
      </section>

      {/* 11. Danger Zone: Reset Profile & Database */}
      <section aria-labelledby="danger-zone-heading" className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600" aria-hidden="true" />
            <h2 id="danger-zone-heading" className="text-base font-semibold text-red-600 tracking-tight">
              Danger zone
            </h2>
          </div>

          {saveStatus?.section === "danger" && (
            <Badge variant={saveStatus.error ? "danger" : "apply"}>
              {saveStatus.message}
            </Badge>
          )}
        </div>

        <Card className="p-5 border-red-200/80 bg-red-50/20 shadow-2xs">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="text-sm font-semibold text-neutral-900">
                Delete user profile and database
              </div>
              <p className="text-xs text-neutral-500 max-w-xl leading-relaxed">
                Permanently delete your profile and reset database history.
              </p>
            </div>

            <Button
              type="button"
              variant="danger"
              size="sm"
              onClick={() => {
                setDeleteConfirmationText("");
                setIsDeleteAllOpen(true);
              }}
              className="shrink-0"
              title="Delete all user profile data and database history"
            >
              <Trash2 className="w-3.5 h-3.5" aria-hidden="true" />
              <span>Delete profile and database</span>
            </Button>
          </div>
        </Card>
      </section>

      {/* Manage Service Modal / Dialog */}
      {manageProvider && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="manage-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs"
        >
          <div className="bg-white rounded-xl border border-neutral-200/90 shadow-xl max-w-md w-full p-6 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <ProviderIcon provider={manageProvider} className="w-6 h-6 text-neutral-800" />
                <div>
                  <h3 id="manage-modal-title" className="text-base font-semibold text-neutral-900">
                    Manage {PROVIDER_NAMES[manageProvider] || manageProvider}
                  </h3>
                  <p className="text-xs text-neutral-500">
                    Active subscription integration details.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setManageProvider(null)}
                aria-label="Close dialog"
                className="text-neutral-400 hover:text-neutral-700 p-1 rounded-xl hover:bg-neutral-100 transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-3.5 bg-neutral-50 rounded-xl border border-neutral-200/70 text-xs space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="text-neutral-500">Connection status</span>
                <Badge variant="apply">Connected</Badge>
              </div>
              <div className="flex items-center justify-between font-mono text-[11px]">
                <span className="text-neutral-500">Token storage</span>
                <span className="text-neutral-800">data/auth_tokens.json</span>
              </div>
            </div>

            <div className="pt-2 flex items-center justify-between gap-3 border-t border-neutral-100">
              <Button
                type="button"
                variant="danger"
                size="sm"
                onClick={() => {
                  setDisconnectCandidate(manageProvider);
                  setManageProvider(null);
                }}
              >
                <LogOut className="w-3.5 h-3.5" aria-hidden="true" />
                <span>Disconnect</span>
              </Button>

              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    handleOAuthLogin(manageProvider);
                    setManageProvider(null);
                  }}
                >
                  <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>Re-authenticate</span>
                </Button>
                <Button
                  type="button"
                  variant="primary"
                  size="sm"
                  onClick={() => setManageProvider(null)}
                >
                  Done
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Disconnect Confirmation Dialog */}
      {disconnectCandidate && (
        <div
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="disconnect-dialog-title"
          aria-describedby="disconnect-dialog-desc"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs"
        >
          <div className="bg-white rounded-xl border border-neutral-200/90 shadow-xl max-w-md w-full p-6 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" aria-hidden="true" />
              <div className="space-y-1">
                <h3 id="disconnect-dialog-title" className="text-base font-semibold text-neutral-900">
                  Disconnect {PROVIDER_NAMES[disconnectCandidate] || disconnectCandidate}?
                </h3>
                <p id="disconnect-dialog-desc" className="text-xs text-neutral-500 leading-relaxed">
                  Disconnecting will remove saved authorization tokens from local storage. You will need to re-authenticate with {PROVIDER_NAMES[disconnectCandidate] || disconnectCandidate} before running automated job pipelines that use this provider.
                </p>
              </div>
            </div>

            <div className="pt-2 flex items-center justify-end gap-2.5 border-t border-neutral-100">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setDisconnectCandidate(null)}
                disabled={disconnecting}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="danger"
                size="sm"
                onClick={handleConfirmDisconnect}
                disabled={disconnecting}
              >
                {disconnecting ? "Disconnecting..." : "Yes, disconnect"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Jobstreet Auth Dialog */}
      {isJobstreetDeleteOpen && (
        <div
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="delete-jobstreet-dialog-title"
          aria-describedby="delete-jobstreet-dialog-desc"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs"
        >
          <div className="bg-white rounded-xl border border-neutral-200/90 shadow-xl max-w-md w-full p-6 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-start gap-3">
              <AlertCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" aria-hidden="true" />
              <div className="space-y-1">
                <h3 id="delete-jobstreet-dialog-title" className="text-base font-semibold text-neutral-900">
                  Remove Jobstreet Session?
                </h3>
                <p id="delete-jobstreet-dialog-desc" className="text-xs text-neutral-500 leading-relaxed">
                  This will delete the saved Jobstreet authentication session file (<code className="font-mono text-[11px] bg-neutral-100 px-1 py-0.5 rounded">data/storage_state.json</code>). You will need to sign in again via browser to run automated job applications.
                </p>
              </div>
            </div>

            <div className="pt-2 flex items-center justify-end gap-2.5 border-t border-neutral-100">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setIsJobstreetDeleteOpen(false)}
                disabled={deletingJobstreetAuth}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="danger"
                size="sm"
                onClick={handleDeleteJobstreetAuth}
                disabled={deletingJobstreetAuth}
              >
                {deletingJobstreetAuth ? "Removing..." : "Yes, remove"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Delete All Data (Profile + Database) Confirmation Dialog */}
      {isDeleteAllOpen && (
        <div
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="delete-all-dialog-title"
          aria-describedby="delete-all-dialog-desc"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs"
        >
          <div className="bg-white rounded-xl border border-red-200/90 shadow-xl max-w-md w-full p-6 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-xl bg-red-50 text-red-600 shrink-0">
                <AlertCircle className="w-5 h-5" aria-hidden="true" />
              </div>
              <div className="space-y-1.5">
                <h3 id="delete-all-dialog-title" className="text-base font-semibold text-neutral-900">
                  Delete all profile and database data?
                </h3>
                <p id="delete-all-dialog-desc" className="text-xs text-neutral-500 leading-relaxed">
                  This action is permanent and cannot be undone. It will delete your saved candidate profile (<code className="font-mono text-[11px] bg-neutral-100 px-1 py-0.5 rounded">data/profile.yaml</code>) and clear all records from SQLite (<code className="font-mono text-[11px] bg-neutral-100 px-1 py-0.5 rounded">data/jobs.db</code>).
                </p>
              </div>
            </div>

            <div className="p-3 bg-neutral-50 border border-neutral-200/80 rounded-xl space-y-2 text-xs">
              <label htmlFor="delete-confirm-input" className="block text-neutral-700 font-medium">
                Type <span className="font-bold text-red-600 font-mono">DELETE</span> to confirm:
              </label>
              <input
                id="delete-confirm-input"
                type="text"
                value={deleteConfirmationText}
                onChange={(e) => setDeleteConfirmationText(e.target.value)}
                placeholder="DELETE"
                className="w-full text-xs font-mono bg-white border border-neutral-200 rounded-lg px-3 py-2 text-neutral-900 focus:outline-hidden focus:ring-2 focus:ring-red-500/20 focus:border-red-500"
                autoComplete="off"
                spellCheck={false}
              />
            </div>

            <div className="pt-2 flex items-center justify-end gap-2.5 border-t border-neutral-100">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setIsDeleteAllOpen(false);
                  setDeleteConfirmationText("");
                }}
                disabled={deleteAllDataMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="danger"
                size="sm"
                onClick={handleDeleteAllData}
                disabled={deleteConfirmationText !== "DELETE" || deleteAllDataMutation.isPending}
              >
                {deleteAllDataMutation.isPending ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" aria-hidden="true" />
                    <span>Deleting...</span>
                  </>
                ) : (
                  <span>Delete everything</span>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/**
 * Reusable Connected Service Item
 */
function ConnectedServiceCard({
  icon,
  name,
  description,
  isConnected,
  onConnect,
  onManage,
}: {
  icon: React.ReactNode;
  name: string;
  description: string;
  isConnected: boolean;
  onConnect: () => void;
  onManage: () => void;
}) {
  return (
    <Card className="p-4 border-neutral-200/90 shadow-2xs flex items-center justify-between gap-3">
      <div className="flex items-center gap-3 min-w-0">
        <div className="shrink-0">{icon}</div>
        <div className="min-w-0">
          <div className="font-semibold text-sm text-neutral-900 flex items-center gap-2">
            <span className="truncate">{name}</span>
            {isConnected ? (
              <Badge variant="apply">Connected</Badge>
            ) : (
              <Badge variant="neutral">Not connected</Badge>
            )}
          </div>
          <p className="text-xs text-neutral-500 mt-0.5 truncate">{description}</p>
        </div>
      </div>

      <div className="shrink-0">
        {isConnected ? (
          <Button
            size="sm"
            variant="outline"
            onClick={onManage}
            aria-label={`Manage ${name} connection`}
            className="flex items-center gap-1.5"
          >
            <span>Manage</span>
          </Button>
        ) : (
          <Button
            size="sm"
            variant="outline"
            onClick={onConnect}
            aria-label={`Connect ${name}`}
            className="flex items-center gap-1.5"
          >
            <LogIn className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Connect</span>
          </Button>
        )}
      </div>
    </Card>
  );
}
