import { useState, useEffect } from "react";
import {
  Key,
  Sliders,
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
} from "lucide-react";
import {
  useSettings,
  useSaveSettings,
  useTestLlm,
  useProviderModels,
} from "../api/hooks";
import { Card, Button, Badge } from "../components/ui/core";
import { apiFetch } from "../api/client";
import { cn } from "../lib/utils";

export function SettingsPage() {
  const { data: settings, isLoading, refetch } = useSettings();
  const saveMutation = useSaveSettings();
  const testLlmMutation = useTestLlm();

  // LLM state
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("gpt-4o-mini");
  const [endpoint, setEndpoint] = useState("https://api.openai.com/v1");
  const [apiKey, setApiKey] = useState("");
  const [prefix, setPrefix] = useState("");

  // Targets state
  const [rolesText, setRolesText] = useState("");
  const [locationsText, setLocationsText] = useState("");

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

  // Models query
  const { data: modelsData, isLoading: modelsLoading, refetch: refetchModels } =
    useProviderModels(provider);

  useEffect(() => {
    if (settings) {
      // LLM
      const llm = settings.llm_cfg || {};
      const active = settings.active_llm || {};
      setProvider(active.provider || llm.provider || "openai");
      setModel(active.raw_model || llm.model || "gpt-4o-mini");
      setEndpoint(llm.endpoint || "https://api.openai.com/v1");
      setApiKey(llm.api_key || "");
      setPrefix(llm.prefix || "");

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

  const showStatus = (section: string, message: string, error = false) => {
    setSaveStatus({ section, message, error });
    setTimeout(() => setSaveStatus(null), 3000);
  };

  const handleSaveLlm = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate(
      {
        section: "llm",
        data: { provider, endpoint, model, prefix, api_key: apiKey },
      },
      {
        onSuccess: (res) => showStatus("llm", res.message || "Saved"),
        onError: (err) => showStatus("llm", err.message, true),
      }
    );
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
      showStatus("oauth", res.message || `Connected to ${prov}`);
      refetch();
    } catch (err: any) {
      showStatus("oauth", err.message, true);
    }
  };

  const handleOAuthLogout = async (prov: string) => {
    try {
      await apiFetch(`/api/settings/oauth/${prov}/logout`, { method: "POST" });
      showStatus("oauth", `Logged out from ${prov}`);
      refetch();
    } catch (err: any) {
      showStatus("oauth", err.message, true);
    }
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

      // Poll
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
      <div className="space-y-4 animate-pulse">
        <div className="h-8 bg-slate-200 rounded w-32" />
        <div className="h-64 bg-slate-200 rounded-xl" />
      </div>
    );
  }

  const { has_auth, auth_tokens = {}, active_llm = {} } = settings;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Settings
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Jobstreet session, AI subscriptions, targeting filters, and salary configuration
        </p>
      </div>

      {/* 1. Jobstreet Auth Section */}
      <Card className="p-5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck
              className={cn(
                "w-5 h-5",
                has_auth ? "text-emerald-600" : "text-amber-500"
              )}
            />
            <div>
              <h2 className="text-sm font-semibold text-slate-900">
                Jobstreet Authentication
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                {has_auth
                  ? "Logged in · Session saved in data/storage_state.json"
                  : "No saved session found"}
              </p>
            </div>
          </div>
          <Button
            size="sm"
            variant="outline"
            onClick={async () => {
              try {
                await apiFetch("/api/settings/jobstreet/system-login", { method: "POST" });
                showStatus("oauth", "Opened Chrome for Jobstreet Google Login!");
              } catch (e: any) {
                showStatus("oauth", e.message, true);
              }
            }}
            className="flex items-center gap-1.5"
            title="Launch external browser window to sign in to Jobstreet"
          >
            <Globe size={13} />
            <span>{has_auth ? "Re-authenticate with Browser" : "Log in with Browser"}</span>
          </Button>
        </div>
      </Card>

      {/* 2. AI Subscriptions & OAuth */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Key className="w-4 h-4 text-blue-600" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-700">
              AI Subscriptions & OAuth
            </h2>
          </div>
          {saveStatus?.section === "oauth" && (
            <Badge variant={saveStatus.error ? "danger" : "apply"}>
              {saveStatus.message}
            </Badge>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          {/* Claude */}
          <Card className="p-4 flex items-center justify-between">
            <div>
              <div className="font-semibold text-sm text-slate-900 flex items-center gap-2">
                <span>Claude Code</span>
                {auth_tokens.claude ? (
                  <Badge variant="apply">Connected</Badge>
                ) : (
                  <Badge variant="default">Not Connected</Badge>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Anthropic Claude Pro / Team / Enterprise
              </p>
            </div>
            {auth_tokens.claude ? (
              <Button
                size="sm"
                variant="danger"
                onClick={() => handleOAuthLogout("claude")}
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Disconnect</span>
              </Button>
            ) : (
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleOAuthLogin("claude")}
              >
                <LogIn className="w-3.5 h-3.5" />
                <span>Connect</span>
              </Button>
            )}
          </Card>

          {/* ChatGPT / Codex */}
          <Card className="p-4 flex items-center justify-between">
            <div>
              <div className="font-semibold text-sm text-slate-900 flex items-center gap-2">
                <span>ChatGPT / Codex</span>
                {auth_tokens.codex ? (
                  <Badge variant="apply">Connected</Badge>
                ) : (
                  <Badge variant="default">Not Connected</Badge>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-1">
                OpenAI ChatGPT Plus / Pro OAuth
              </p>
            </div>
            {auth_tokens.codex ? (
              <Button
                size="sm"
                variant="danger"
                onClick={() => handleOAuthLogout("codex")}
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Disconnect</span>
              </Button>
            ) : (
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleOAuthLogin("codex")}
              >
                <LogIn className="w-3.5 h-3.5" />
                <span>Connect</span>
              </Button>
            )}
          </Card>

          {/* GitHub Copilot */}
          <Card className="p-4 flex items-center justify-between">
            <div>
              <div className="font-semibold text-sm text-slate-900 flex items-center gap-2">
                <span>GitHub Copilot</span>
                {auth_tokens.copilot ? (
                  <Badge variant="apply">Connected</Badge>
                ) : (
                  <Badge variant="default">Not Connected</Badge>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-1">
                GitHub Copilot via Device Code
              </p>
            </div>
            {auth_tokens.copilot ? (
              <Button
                size="sm"
                variant="danger"
                onClick={() => handleOAuthLogout("copilot")}
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Disconnect</span>
              </Button>
            ) : (
              <Button size="sm" variant="outline" onClick={startCopilotFlow}>
                <LogIn className="w-3.5 h-3.5" />
                <span>Connect</span>
              </Button>
            )}
          </Card>

          {/* Google Antigravity */}
          <Card className="p-4 flex items-center justify-between">
            <div>
              <div className="font-semibold text-sm text-slate-900 flex items-center gap-2">
                <span>Google Antigravity</span>
                {auth_tokens.gemini ? (
                  <Badge variant="apply">Connected</Badge>
                ) : (
                  <Badge variant="default">Not Connected</Badge>
                )}
              </div>
              <p className="text-xs text-slate-500 mt-1">
                Google Code Assist / Gemini 2.5/3.7
              </p>
            </div>
            {auth_tokens.gemini ? (
              <Button
                size="sm"
                variant="danger"
                onClick={() => handleOAuthLogout("gemini")}
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Disconnect</span>
              </Button>
            ) : (
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleOAuthLogin("gemini")}
              >
                <LogIn className="w-3.5 h-3.5" />
                <span>Connect</span>
              </Button>
            )}
          </Card>
        </div>

        {copilotFlow && (
          <Card className="p-4 bg-blue-50/50 border-blue-200 text-xs space-y-2">
            <div className="font-semibold text-blue-900">
              GitHub Copilot Device Login
            </div>
            {copilotFlow.userCode && (
              <div>
                1. Visit:{" "}
                <a
                  href={copilotFlow.verificationUri}
                  target="_blank"
                  rel="noreferrer"
                  className="font-bold underline text-blue-700 inline-flex items-center gap-1"
                >
                  <span>{copilotFlow.verificationUri}</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
                <br />
                2. Enter code:{" "}
                <code className="font-mono bg-white px-2 py-0.5 rounded border font-bold text-sm">
                  {copilotFlow.userCode}
                </code>
              </div>
            )}
            <div className="text-slate-600 font-mono">
              Status: {copilotFlow.status}
            </div>
          </Card>
        )}
      </div>

      {/* 3. Active AI Provider & Model Selection */}
      <Card className="p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="w-4 h-4 text-blue-600" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-700">
              Model & Provider Selector
            </h2>
          </div>
          {saveStatus?.section === "llm" && (
            <Badge variant={saveStatus.error ? "danger" : "apply"}>
              {saveStatus.message}
            </Badge>
          )}
        </div>

        <form onSubmit={handleSaveLlm} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Active Provider
              </label>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 focus:bg-white"
              >
                <option value="openai">OpenAI Compatible (BYOK)</option>
                <option value="claude">Claude Code (Anthropic Subscription)</option>
                <option value="codex">ChatGPT / Codex (OpenAI Subscription)</option>
                <option value="copilot">GitHub Copilot (Subscription)</option>
                <option value="gemini">Google Antigravity (Subscription)</option>
              </select>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-medium text-slate-700">
                  Model Selection
                </label>
                <button
                  type="button"
                  onClick={() => refetchModels()}
                  className="text-xs text-blue-600 hover:text-blue-700 flex items-center gap-1 cursor-pointer"
                >
                  <RefreshCw className={cn("w-3 h-3", modelsLoading && "animate-spin")} />
                  <span>Refresh</span>
                </button>
              </div>

              {modelsData?.models && modelsData.models.length > 0 ? (
                <select
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 font-mono"
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
                  type="text"
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="gpt-4o-mini"
                  className="w-full text-sm font-mono bg-slate-50 border border-slate-200 rounded-lg px-3 py-2"
                />
              )}
            </div>

            {!isSubscription && (
              <>
                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    API Endpoint / Base URL
                  </label>
                  <input
                    type="text"
                    value={endpoint}
                    onChange={(e) => setEndpoint(e.target.value)}
                    placeholder="https://api.openai.com/v1"
                    className="w-full text-sm font-mono bg-slate-50 border border-slate-200 rounded-lg px-3 py-2"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    API Key
                  </label>
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="sk-..."
                    className="w-full text-sm font-mono bg-slate-50 border border-slate-200 rounded-lg px-3 py-2"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-slate-700 mb-1">
                    Model Prefix (Optional)
                  </label>
                  <input
                    type="text"
                    value={prefix}
                    onChange={(e) => setPrefix(e.target.value)}
                    placeholder="e.g. openai/ or groq/"
                    className="w-full text-sm font-mono bg-slate-50 border border-slate-200 rounded-lg px-3 py-2"
                  />
                </div>
              </>
            )}
          </div>

          <div className="flex items-center justify-between pt-3 border-t border-slate-100">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => testLlmMutation.mutate()}
              disabled={testLlmMutation.isPending}
            >
              <Zap className="w-3.5 h-3.5" />
              <span>{testLlmMutation.isPending ? "Testing..." : "Test Connection"}</span>
            </Button>
            <Button type="submit" size="sm">
              Save Provider Settings
            </Button>
          </div>

          {testLlmMutation.data && (
            <div
              className={cn(
                "p-3 rounded-lg text-xs font-mono flex items-start gap-2",
                testLlmMutation.data.success
                  ? "bg-emerald-50 text-emerald-800 border border-emerald-200"
                  : "bg-red-50 text-red-800 border border-red-200"
              )}
            >
              {testLlmMutation.data.success ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              ) : (
                <AlertCircle className="w-4 h-4 text-red-600 shrink-0 mt-0.5" />
              )}
              <span>
                {testLlmMutation.data.success
                  ? `Response: ${testLlmMutation.data.response}`
                  : `Error: ${testLlmMutation.data.error}`}
              </span>
            </div>
          )}
        </form>
      </Card>

      {/* 4. Target Searches */}
      <Card className="p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Target className="w-4 h-4 text-blue-600" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-700">
              Target Roles & Locations to Search
            </h2>
          </div>
          {saveStatus?.section === "targets" && (
            <Badge variant={saveStatus.error ? "danger" : "apply"}>
              {saveStatus.message}
            </Badge>
          )}
        </div>

        <form onSubmit={handleSaveTargets} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Roles (Name: url-slug, one per line)
              </label>
              <textarea
                rows={5}
                value={rolesText}
                onChange={(e) => setRolesText(e.target.value)}
                className="w-full text-xs font-mono bg-slate-50 border border-slate-200 rounded-lg p-2.5"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Locations (Name: url-slug, one per line)
              </label>
              <textarea
                rows={5}
                value={locationsText}
                onChange={(e) => setLocationsText(e.target.value)}
                className="w-full text-xs font-mono bg-slate-50 border border-slate-200 rounded-lg p-2.5"
              />
            </div>
          </div>
          <div className="flex justify-end pt-2 border-t border-slate-100">
            <Button type="submit" size="sm">
              Save Targets
            </Button>
          </div>
        </form>
      </Card>

      {/* 5. Scoring & Salary Thresholds */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Scoring Threshold */}
        <Card className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-700">
              Scoring Threshold
            </h2>
            {saveStatus?.section === "scoring" && (
              <Badge variant={saveStatus.error ? "danger" : "apply"}>
                {saveStatus.message}
              </Badge>
            )}
          </div>
          <form onSubmit={handleSaveScoring} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Apply Match Threshold (% Requirements Met)
              </label>
              <div className="flex items-center gap-3">
                <input
                  type="number"
                  min={1}
                  max={100}
                  value={matchThreshold}
                  onChange={(e) => setMatchThreshold(parseInt(e.target.value, 10))}
                  className="w-24 text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5 font-bold"
                />
                <span className="text-sm font-medium text-slate-600">%</span>
              </div>
            </div>
            <div className="flex justify-end pt-2 border-t border-slate-100">
              <Button type="submit" size="sm">
                Save Threshold
              </Button>
            </div>
          </form>
        </Card>

        {/* Salary Preferences */}
        <Card className="p-5 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-700">
              Salary Expectations
            </h2>
            {saveStatus?.section === "salary" && (
              <Badge variant={saveStatus.error ? "danger" : "apply"}>
                {saveStatus.message}
              </Badge>
            )}
          </div>
          <form onSubmit={handleSaveSalary} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Preferred (IDR)
                </label>
                <input
                  type="number"
                  step={100000}
                  value={preferredSalary}
                  onChange={(e) =>
                    setPreferredSalary(parseInt(e.target.value, 10))
                  }
                  className="w-full text-xs font-mono bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">
                  Min Acceptable (IDR)
                </label>
                <input
                  type="number"
                  step={100000}
                  value={minAcceptableSalary}
                  onChange={(e) =>
                    setMinAcceptableSalary(parseInt(e.target.value, 10))
                  }
                  className="w-full text-xs font-mono bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5"
                />
              </div>
            </div>
            <div className="flex justify-end pt-2 border-t border-slate-100">
              <Button type="submit" size="sm">
                Save Salary
              </Button>
            </div>
          </form>
        </Card>
      </div>

      {/* 6. Application Rules & Filters */}
      <Card className="p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Sliders className="w-4 h-4 text-blue-600" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-700">
              Application Rules & Constraints
            </h2>
          </div>
          {saveStatus?.section === "filters" && (
            <Badge variant={saveStatus.error ? "danger" : "apply"}>
              {saveStatus.message}
            </Badge>
          )}
        </div>

        <form onSubmit={handleSaveFilters} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Company Cooldown (Days)
              </label>
              <input
                type="number"
                min={0}
                value={cooldownDays}
                onChange={(e) => setCooldownDays(parseInt(e.target.value, 10))}
                className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Experience Range Required (Years)
              </label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min={0}
                  value={minYearsExp}
                  onChange={(e) => setMinYearsExp(parseInt(e.target.value, 10))}
                  className="w-20 text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5"
                />
                <span className="text-xs text-slate-500">to</span>
                <input
                  type="number"
                  min={0}
                  value={maxYearsExp}
                  onChange={(e) => setMaxYearsExp(parseInt(e.target.value, 10))}
                  className="w-20 text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5"
                />
                <span className="text-xs text-slate-500">years</span>
              </div>
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Location Whitelist (Comma-separated)
              </label>
              <input
                type="text"
                value={locationWhitelist}
                onChange={(e) => setLocationWhitelist(e.target.value)}
                className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Role Keywords Required in Job Title (Comma-separated)
              </label>
              <input
                type="text"
                value={roleKeywords}
                onChange={(e) => setRoleKeywords(e.target.value)}
                className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5"
              />
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-medium text-slate-700 mb-1">
                Title Blacklist Keywords (Comma-separated)
              </label>
              <input
                type="text"
                value={titleBlacklist}
                onChange={(e) => setTitleBlacklist(e.target.value)}
                className="w-full text-sm bg-slate-50 border border-slate-200 rounded-lg px-3 py-1.5"
              />
            </div>
          </div>

          <div className="flex justify-end pt-2 border-t border-slate-100">
            <Button type="submit" size="sm">
              Save Filter Rules
            </Button>
          </div>
        </form>
      </Card>

      {/* 7. Active Configuration Summary Table */}
      <Card className="p-5 space-y-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-700">
          Active Configuration Summary
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-slate-50 text-slate-500 border-b border-slate-200 font-medium">
              <tr>
                <th className="py-2 px-3">Setting</th>
                <th className="py-2 px-3">Resolved Value</th>
                <th className="py-2 px-3">Source</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 font-mono">
              <tr>
                <td className="py-2 px-3 text-slate-900 font-sans font-medium">
                  Effective AI Provider
                </td>
                <td className="py-2 px-3 text-blue-600">
                  {active_llm.provider || "—"}
                </td>
                <td className="py-2 px-3 text-slate-400 font-sans">
                  {settings.env_overrides?.provider ? "env var" : "secrets.yaml"}
                </td>
              </tr>
              <tr>
                <td className="py-2 px-3 text-slate-900 font-sans font-medium">
                  Effective Model ID
                </td>
                <td className="py-2 px-3 text-slate-700">
                  {active_llm.model || "—"}
                </td>
                <td className="py-2 px-3 text-slate-400 font-sans">
                  {settings.env_overrides?.model ? "env var" : "config.yaml"}
                </td>
              </tr>
              <tr>
                <td className="py-2 px-3 text-slate-900 font-sans font-medium">
                  Company Cooldown
                </td>
                <td className="py-2 px-3 text-slate-700">
                  {cooldownDays} day(s)
                </td>
                <td className="py-2 px-3 text-slate-400 font-sans">
                  secrets.yaml
                </td>
              </tr>
              <tr>
                <td className="py-2 px-3 text-slate-900 font-sans font-medium">
                  Experience Range
                </td>
                <td className="py-2 px-3 text-slate-700">
                  {minYearsExp} - {maxYearsExp} year(s)
                </td>
                <td className="py-2 px-3 text-slate-400 font-sans">
                  secrets.yaml
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
