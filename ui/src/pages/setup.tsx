import { useState, useEffect } from "react";
import { useNavigate } from "react-router";
import {
  Zap,
  Key,
  LogIn,
  LogOut,
  RefreshCw,
  Sparkles,
  Upload,
  FileText,
  CheckCircle2,
  AlertCircle,
  ArrowRight,
  ArrowLeft,
  Save,
  Check,
  User,
  GraduationCap,
  Briefcase,
  Wrench,
  FolderGit2,
  ExternalLink,
} from "lucide-react";
import {
  useSettings,
  useSaveSettings,
  useProviderModels,
  useTestLlm,
  useImportCV,
  useSaveProfile,
  useProfile,
} from "../api/hooks";
import { apiFetch } from "../api/client";
import { Card, Button, Badge } from "../components/ui/core";
import { cn } from "../lib/utils";

export function SetupPage() {
  const navigate = useNavigate();
  const { data: settings, isLoading: settingsLoading, refetch: refetchSettings } = useSettings();
  const { data: profileData, refetch: refetchProfile } = useProfile();
  const saveSettingsMutation = useSaveSettings();
  const testLlmMutation = useTestLlm();
  const importCvMutation = useImportCV();
  const saveProfileMutation = useSaveProfile();

  const [step, setStep] = useState<1 | 2>(1);

  // Step 1 - LLM state
  const [provider, setProvider] = useState("openai");
  const [endpoint, setEndpoint] = useState("https://api.openai.com/v1");
  const [model, setModel] = useState("gpt-4o-mini");
  const [apiKey, setApiKey] = useState("");
  const [prefix, setPrefix] = useState("");
  const [llmTestStatus, setLlmTestStatus] = useState<{
    success?: boolean;
    message?: string;
    loading?: boolean;
  }>({});
  const [step1Saved, setStep1Saved] = useState(false);
  const [copilotFlow, setCopilotFlow] = useState<{
    userCode?: string;
    verificationUri?: string;
    status: string;
  } | null>(null);

  // Step 2 - CV upload & Profile state
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [extractedData, setExtractedData] = useState<any>(null);
  const [extractError, setExtractError] = useState<string | null>(null);

  // Editable profile state after extraction
  const [formData, setFormData] = useState<any>({});
  const [languagesText, setLanguagesText] = useState("");
  const [locationsOkText, setLocationsOkText] = useState("");
  const [certificationsText, setCertificationsText] = useState("");
  const [experienceText, setExperienceText] = useState("");
  const [skillsText, setSkillsText] = useState("");
  const [projectsText, setProjectsText] = useState("");
  const [finishSuccess, setFinishSuccess] = useState(false);

  const {
    data: modelsData,
    isLoading: modelsLoading,
    refetch: refetchModels,
  } = useProviderModels(provider);

  useEffect(() => {
    if (settings) {
      const llm = settings.llm_cfg || {};
      const active = settings.active_llm || {};
      setProvider(active.provider || llm.provider || "openai");
      setModel(active.raw_model || llm.model || "gpt-4o-mini");
      setEndpoint(llm.endpoint || "https://api.openai.com/v1");
      setApiKey(llm.api_key || "");
      setPrefix(llm.prefix || "");
    }
  }, [settings]);

  const authTokens = settings?.auth_tokens || {};

  const handleOAuthLogin = async (prov: string) => {
    try {
      await apiFetch<{ success: boolean; message?: string }>(
        `/api/settings/oauth/${prov}/login`,
        { method: "POST" }
      );
      refetchSettings();
    } catch (err: any) {
      alert(`OAuth login failed: ${err.message}`);
    }
  };

  const handleOAuthLogout = async (prov: string) => {
    try {
      await apiFetch(`/api/settings/oauth/${prov}/logout`, { method: "POST" });
      refetchSettings();
    } catch (err: any) {
      alert(`OAuth logout failed: ${err.message}`);
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
          refetchSettings();
        }, 1500);
      }
    } catch (err: any) {
      setCopilotFlow({ status: `Failed: ${err.message}` });
    }
  };

  const handleTestLlm = () => {
    setLlmTestStatus({ loading: true });
    // First save the current LLM settings to ensure test uses current inputs
    saveSettingsMutation.mutate(
      {
        section: "llm",
        data: { provider, endpoint, model, prefix, api_key: apiKey },
      },
      {
        onSuccess: () => {
          testLlmMutation.mutate(undefined, {
            onSuccess: (res) => {
              if (res.success) {
                setLlmTestStatus({
                  success: true,
                  message: res.response || "Connection successful!",
                  loading: false,
                });
              } else {
                setLlmTestStatus({
                  success: false,
                  message: res.error || "Connection failed.",
                  loading: false,
                });
              }
            },
            onError: (err) => {
              setLlmTestStatus({
                success: false,
                message: err.message,
                loading: false,
              });
            },
          });
        },
        onError: (err) => {
          setLlmTestStatus({
            success: false,
            message: `Failed to save settings: ${err.message}`,
            loading: false,
          });
        },
      }
    );
  };

  const handleSaveStep1 = () => {
    saveSettingsMutation.mutate(
      {
        section: "llm",
        data: { provider, endpoint, model, prefix, api_key: apiKey },
      },
      {
        onSuccess: () => {
          setStep1Saved(true);
          setStep(2);
        },
        onError: (err) => {
          alert(`Failed to save AI settings: ${err.message}`);
        },
      }
    );
  };

  const handleFileDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (file.name.toLowerCase().endsWith(".pdf")) {
        setSelectedFile(file);
        setExtractError(null);
      } else {
        setExtractError("Please upload a PDF file (*.pdf).");
      }
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (file.name.toLowerCase().endsWith(".pdf")) {
        setSelectedFile(file);
        setExtractError(null);
      } else {
        setExtractError("Please upload a PDF file (*.pdf).");
      }
    }
  };

  const handleExtractCv = () => {
    if (!selectedFile) return;
    setExtractError(null);
    importCvMutation.mutate(selectedFile, {
      onSuccess: (data) => {
        const p = data.profile;
        setExtractedData(p);
        setFormData(p);

        setLanguagesText((p.languages || []).join("\n"));
        setLocationsOkText((p.locations_ok || []).join("\n"));
        setCertificationsText((p.education?.certifications || []).join("\n"));

        const expLines = (p.experience || [])
          .map((e: any) =>
            typeof e === "object"
              ? `${e.role || ""} | ${e.org || ""} | ${e.period || ""} | ${e.summary || ""}`
              : e
          )
          .join("\n");
        setExperienceText(expLines);

        const skillLines = (p.skills || [])
          .map((s: any) => {
            if (typeof s === "object" && s.name) {
              return s.aliases && s.aliases.length > 0
                ? `${s.name}: ${s.aliases.join(", ")}`
                : s.name;
            }
            return String(s);
          })
          .join("\n");
        setSkillsText(skillLines);

        setProjectsText((p.projects || []).join("\n"));
      },
      onError: (err) => {
        setExtractError(err.message || "Failed to extract CV with AI.");
      },
    });
  };

  const handleSaveProfile = (e: React.FormEvent) => {
    e.preventDefault();

    const languages = languagesText
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);

    const locations_ok = locationsOkText
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);

    const certifications = certificationsText
      .split("\n")
      .map((c) => c.trim())
      .filter(Boolean);

    const experience = experienceText
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => {
        const parts = l.split("|").map((p) => p.trim());
        return {
          role: parts[0] || "",
          org: parts[1] || "",
          period: parts[2] || "",
          summary: parts[3] || "",
        };
      });

    const skills = skillsText
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => {
        if (l.includes(":")) {
          const [name, aliasesPart] = l.split(":", 2);
          const aliases = aliasesPart
            .split(",")
            .map((a) => a.trim())
            .filter(Boolean);
          return { name: name.trim(), aliases };
        }
        return { name: l, aliases: [] };
      });

    const projects = projectsText
      .split("\n")
      .map((p) => p.trim())
      .filter(Boolean);

    const payload = {
      ...formData,
      languages,
      locations_ok,
      education: {
        ...(formData.education || {}),
        certifications,
      },
      experience,
      skills,
      projects,
    };

    saveProfileMutation.mutate(payload, {
      onSuccess: () => {
        setFinishSuccess(true);
        refetchProfile();
        setTimeout(() => {
          navigate("/");
        }, 1200);
      },
      onError: (err) => {
        alert(`Failed to save profile: ${err.message}`);
      },
    });
  };

  if (settingsLoading) {
    return (
      <div className="py-12 flex justify-center items-center">
        <div className="flex items-center gap-3 text-sm text-neutral-500">
          <RefreshCw className="w-4 h-4 animate-spin text-neutral-800" />
          <span>Loading setup wizard...</span>
        </div>
      </div>
    );
  }

  const isSubscription = [
    "claude",
    "codex",
    "chatgpt",
    "copilot",
    "gemini",
    "antigravity",
  ].includes(provider);

  return (
    <div className="max-w-3xl mx-auto py-4 space-y-8">
      {/* Onboarding Header */}
      <div className="text-center space-y-2">
        <div className="inline-flex items-center justify-center w-10 h-10 rounded-xl bg-neutral-900 text-white shadow-xs mb-1">
          <Sparkles className="w-5 h-5" />
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
          Welcome to Apply Bot
        </h1>
        <p className="text-sm text-neutral-500 max-w-md mx-auto">
          Get started in 2 quick steps: set up your AI model, then import your CV to automatically configure your profile.
        </p>
      </div>

      {/* Steps Indicator */}
      <div className="flex items-center justify-center gap-3 text-xs font-medium">
        <button
          onClick={() => setStep(1)}
          className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-full transition-colors cursor-pointer",
            step === 1
              ? "bg-neutral-900 text-white font-semibold"
              : "bg-neutral-100 text-neutral-600 hover:bg-neutral-200"
          )}
        >
          <span className="w-4 h-4 rounded-full bg-white/20 flex items-center justify-center text-[10px]">
            1
          </span>
          <span>1. Set up AI Provider</span>
        </button>

        <div className="w-6 h-px bg-neutral-200" />

        <button
          onClick={() => {
            if (step1Saved || authTokens[provider] || apiKey) {
              setStep(2);
            }
          }}
          className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-full transition-colors",
            step === 2
              ? "bg-neutral-900 text-white font-semibold"
              : "bg-neutral-100 text-neutral-600",
            !step1Saved && !authTokens[provider] && !apiKey
              ? "opacity-60 cursor-not-allowed"
              : "cursor-pointer hover:bg-neutral-200"
          )}
        >
          <span className="w-4 h-4 rounded-full bg-white/20 flex items-center justify-center text-[10px]">
            2
          </span>
          <span>2. Import CV & Profile</span>
        </button>
      </div>

      {/* STEP 1: AI Provider & Model */}
      {step === 1 && (
        <Card className="p-6 space-y-6 border-neutral-200 shadow-xs">
          <div className="border-b border-neutral-100 pb-4">
            <div className="flex items-center gap-2">
              <Zap className="w-4 h-4 text-neutral-800" />
              <h2 className="text-base font-semibold text-neutral-900">
                Step 1: Configure AI Model
              </h2>
            </div>
            <p className="text-xs text-neutral-500 mt-1">
              Apply Bot uses your chosen AI model to parse CVs, evaluate job descriptions, and tailor cover letters.
            </p>
          </div>

          {/* Subscription OAuth Cards */}
          <div className="space-y-2.5">
            <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-500">
              AI Subscriptions & Direct OAuth
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              {/* Claude */}
              <div className="p-3 border border-neutral-200 rounded-lg flex items-center justify-between bg-neutral-50/50">
                <div>
                  <div className="font-medium text-xs text-neutral-900 flex items-center gap-1.5">
                    <span>Claude Code</span>
                    {authTokens.claude ? (
                      <Badge variant="apply">Connected</Badge>
                    ) : (
                      <Badge variant="default">Not Connected</Badge>
                    )}
                  </div>
                  <p className="text-[11px] text-neutral-400">Anthropic Claude Pro / Max</p>
                </div>
                {authTokens.claude ? (
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => handleOAuthLogout("claude")}
                  >
                    <LogOut className="w-3 h-3" />
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleOAuthLogin("claude")}
                  >
                    <LogIn className="w-3 h-3" />
                    <span>Connect</span>
                  </Button>
                )}
              </div>

              {/* ChatGPT / Codex */}
              <div className="p-3 border border-neutral-200 rounded-lg flex items-center justify-between bg-neutral-50/50">
                <div>
                  <div className="font-medium text-xs text-neutral-900 flex items-center gap-1.5">
                    <span>ChatGPT / Codex</span>
                    {authTokens.codex ? (
                      <Badge variant="apply">Connected</Badge>
                    ) : (
                      <Badge variant="default">Not Connected</Badge>
                    )}
                  </div>
                  <p className="text-[11px] text-neutral-400">OpenAI Plus / Pro</p>
                </div>
                {authTokens.codex ? (
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => handleOAuthLogout("codex")}
                  >
                    <LogOut className="w-3 h-3" />
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleOAuthLogin("codex")}
                  >
                    <LogIn className="w-3 h-3" />
                    <span>Connect</span>
                  </Button>
                )}
              </div>

              {/* GitHub Copilot */}
              <div className="p-3 border border-neutral-200 rounded-lg flex items-center justify-between bg-neutral-50/50">
                <div>
                  <div className="font-medium text-xs text-neutral-900 flex items-center gap-1.5">
                    <span>GitHub Copilot</span>
                    {authTokens.copilot ? (
                      <Badge variant="apply">Connected</Badge>
                    ) : (
                      <Badge variant="default">Not Connected</Badge>
                    )}
                  </div>
                  <p className="text-[11px] text-neutral-400">Copilot Individual / Business</p>
                </div>
                {authTokens.copilot ? (
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => handleOAuthLogout("copilot")}
                  >
                    <LogOut className="w-3 h-3" />
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={startCopilotFlow}
                  >
                    <LogIn className="w-3 h-3" />
                    <span>Connect</span>
                  </Button>
                )}
              </div>

              {/* Google Gemini */}
              <div className="p-3 border border-neutral-200 rounded-lg flex items-center justify-between bg-neutral-50/50">
                <div>
                  <div className="font-medium text-xs text-neutral-900 flex items-center gap-1.5">
                    <span>Google Gemini</span>
                    {authTokens.gemini ? (
                      <Badge variant="apply">Connected</Badge>
                    ) : (
                      <Badge variant="default">Not Connected</Badge>
                    )}
                  </div>
                  <p className="text-[11px] text-neutral-400">Google Code Assist / Antigravity</p>
                </div>
                {authTokens.gemini ? (
                  <Button
                    size="sm"
                    variant="danger"
                    onClick={() => handleOAuthLogout("gemini")}
                  >
                    <LogOut className="w-3 h-3" />
                  </Button>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleOAuthLogin("gemini")}
                  >
                    <LogIn className="w-3 h-3" />
                    <span>Connect</span>
                  </Button>
                )}
              </div>
            </div>

            {copilotFlow && (
              <div className="p-3 bg-blue-50/60 border border-blue-200 rounded-lg text-xs space-y-1.5">
                <div className="font-semibold text-blue-900">
                  GitHub Copilot Device Login
                </div>
                {copilotFlow.userCode && (
                  <div>
                    1. Open:{" "}
                    <a
                      href={copilotFlow.verificationUri}
                      target="_blank"
                      rel="noreferrer"
                      className="font-semibold underline text-blue-700 inline-flex items-center gap-1"
                    >
                      <span>{copilotFlow.verificationUri}</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                    <br />
                    2. Enter code:{" "}
                    <code className="font-mono bg-white px-2 py-0.5 rounded border border-blue-200 font-bold">
                      {copilotFlow.userCode}
                    </code>
                  </div>
                )}
                <div className="text-blue-700 font-mono text-[11px]">
                  {copilotFlow.status}
                </div>
              </div>
            )}
          </div>

          {/* Active Model Selection */}
          <div className="space-y-4 pt-2">
            <label className="block text-xs font-semibold uppercase tracking-wider text-neutral-500">
              Active Provider & Model Choice
            </label>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  Active Provider
                </label>
                <select
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                  className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 focus:bg-white text-neutral-800"
                >
                  <option value="openai">OpenAI Compatible (BYOK / OpenRouter / Groq / Local)</option>
                  <option value="claude">Claude Code (Anthropic Subscription)</option>
                  <option value="codex">ChatGPT / Codex (OpenAI Subscription)</option>
                  <option value="copilot">GitHub Copilot (Subscription)</option>
                  <option value="gemini">Google Antigravity (Subscription)</option>
                </select>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="block text-xs font-medium text-neutral-700">
                    Model Selection
                  </label>
                  <button
                    type="button"
                    onClick={() => refetchModels()}
                    className="text-[11px] text-neutral-500 hover:text-neutral-900 flex items-center gap-1 cursor-pointer"
                  >
                    <RefreshCw className={cn("w-3 h-3", modelsLoading && "animate-spin")} />
                    <span>Refresh</span>
                  </button>
                </div>

                {modelsData?.models && modelsData.models.length > 0 ? (
                  <select
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 font-mono text-neutral-800"
                  >
                    {modelsData.models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.id}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    type="text"
                    value={model}
                    onChange={(e) => setModel(e.target.value)}
                    placeholder="e.g. gpt-4o-mini, claude-3-7-sonnet"
                    className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 font-mono text-neutral-800"
                  />
                )}
              </div>
            </div>

            {/* Custom BYOK settings if openai compatible */}
            {!isSubscription && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 p-3.5 bg-neutral-50/50 rounded-lg border border-neutral-200">
                <div className="sm:col-span-2">
                  <label className="block text-xs font-medium text-neutral-700 mb-1">
                    API Endpoint
                  </label>
                  <input
                    type="text"
                    value={endpoint}
                    onChange={(e) => setEndpoint(e.target.value)}
                    placeholder="https://api.openai.com/v1"
                    className="w-full text-xs bg-white border border-neutral-200 rounded-lg px-3 py-2 font-mono text-neutral-800"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-neutral-700 mb-1">
                    API Key
                  </label>
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    placeholder="sk-..."
                    className="w-full text-xs bg-white border border-neutral-200 rounded-lg px-3 py-2 font-mono text-neutral-800"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-neutral-700 mb-1">
                    Model Prefix (Optional)
                  </label>
                  <input
                    type="text"
                    value={prefix}
                    onChange={(e) => setPrefix(e.target.value)}
                    placeholder="e.g. openai or deepseek"
                    className="w-full text-xs bg-white border border-neutral-200 rounded-lg px-3 py-2 font-mono text-neutral-800"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Test connection & Feedback */}
          <div className="pt-2 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 border-t border-neutral-100">
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={handleTestLlm}
                disabled={llmTestStatus.loading}
              >
                {llmTestStatus.loading ? (
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Key className="w-3.5 h-3.5" />
                )}
                <span>Test Connection</span>
              </Button>

              {llmTestStatus.success === true && (
                <div className="flex items-center gap-1.5 text-xs text-emerald-600 font-medium">
                  <CheckCircle2 className="w-4 h-4" />
                  <span>{llmTestStatus.message}</span>
                </div>
              )}
              {llmTestStatus.success === false && (
                <div className="flex items-center gap-1.5 text-xs text-red-600 font-medium">
                  <AlertCircle className="w-4 h-4" />
                  <span className="truncate max-w-xs">{llmTestStatus.message}</span>
                </div>
              )}
            </div>

            <Button
              type="button"
              variant="primary"
              size="md"
              onClick={handleSaveStep1}
              disabled={saveSettingsMutation.isPending}
            >
              <span>Continue to Profile Import</span>
              <ArrowRight className="w-4 h-4" />
            </Button>
          </div>
        </Card>
      )}

      {/* STEP 2: CV Upload and Review */}
      {step === 2 && (
        <div className="space-y-6">
          {/* CV Upload Dropzone */}
          <Card className="p-6 space-y-4 border-neutral-200 shadow-xs">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-neutral-800" />
                <h2 className="text-base font-semibold text-neutral-900">
                  Step 2: Upload Your CV (PDF)
                </h2>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setStep(1)}
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Back to AI Setup</span>
              </Button>
            </div>

            <p className="text-xs text-neutral-500">
              Upload your resume or curriculum vitae in PDF format. Apply Bot will extract your experience, skills, and education to build your candidate profile.
            </p>

            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleFileDrop}
              className={cn(
                "border-2 border-dashed rounded-xl p-8 text-center transition-colors flex flex-col items-center justify-center gap-3 cursor-pointer",
                selectedFile
                  ? "border-neutral-900 bg-neutral-50/80"
                  : "border-neutral-200 hover:border-neutral-400 bg-neutral-50/40"
              )}
              onClick={() => document.getElementById("cv-file-input")?.click()}
            >
              <input
                id="cv-file-input"
                type="file"
                accept=".pdf,application/pdf"
                className="hidden"
                onChange={handleFileSelect}
              />
              <div className="w-12 h-12 rounded-full bg-white border border-neutral-200 flex items-center justify-center text-neutral-700 shadow-xs">
                <Upload className="w-5 h-5" />
              </div>
              <div>
                <p className="text-sm font-medium text-neutral-800">
                  {selectedFile ? selectedFile.name : "Click to select or drag and drop your CV PDF"}
                </p>
                <p className="text-xs text-neutral-400 mt-0.5">
                  {selectedFile
                    ? `${(selectedFile.size / 1024).toFixed(1)} KB · Ready for AI extraction`
                    : "Supports standard PDF documents"}
                </p>
              </div>
            </div>

            {extractError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 text-red-500" />
                <span>{extractError}</span>
              </div>
            )}

            <div className="flex justify-end pt-2">
              <Button
                variant="primary"
                size="md"
                onClick={handleExtractCv}
                disabled={!selectedFile || importCvMutation.isPending}
              >
                {importCvMutation.isPending ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Extracting Profile with AI...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    <span>Extract Profile with AI</span>
                  </>
                )}
              </Button>
            </div>
          </Card>

          {/* Extracted Profile Review Form */}
          {extractedData && (
            <Card className="p-6 space-y-6 border-neutral-200 shadow-xs">
              <div className="border-b border-neutral-100 pb-4 flex items-center justify-between">
                <div>
                  <h3 className="text-base font-semibold text-neutral-900 flex items-center gap-2">
                    <CheckCircle2 className="w-5 h-5 text-emerald-600" />
                    <span>Profile Extracted — Review & Confirm</span>
                  </h3>
                  <p className="text-xs text-neutral-500 mt-1">
                    Review and adjust the extracted information before saving to your profile.
                  </p>
                </div>
              </div>

              <form onSubmit={handleSaveProfile} className="space-y-6">
                {/* 1. Basic Information */}
                <div className="space-y-4">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 flex items-center gap-1.5">
                    <User className="w-3.5 h-3.5" />
                    <span>Candidate Information</span>
                  </h4>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Full Name
                      </label>
                      <input
                        type="text"
                        value={formData.name || ""}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        required
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 text-neutral-900 focus:bg-white"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Location
                      </label>
                      <input
                        type="text"
                        value={formData.location || ""}
                        onChange={(e) => setFormData({ ...formData, location: e.target.value })}
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 text-neutral-900 focus:bg-white"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Work Rights / Citizenship
                      </label>
                      <input
                        type="text"
                        value={formData.work_rights || ""}
                        onChange={(e) => setFormData({ ...formData, work_rights: e.target.value })}
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 text-neutral-900 focus:bg-white"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Total Years Experience (e.g. 2.5)
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        value={formData.years_experience ?? 0}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            years_experience: parseFloat(e.target.value) || 0,
                          })
                        }
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 text-neutral-900 focus:bg-white"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Languages (one per line)
                      </label>
                      <textarea
                        rows={2}
                        value={languagesText}
                        onChange={(e) => setLanguagesText(e.target.value)}
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 text-neutral-900 focus:bg-white"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Target Locations (one per line)
                      </label>
                      <textarea
                        rows={2}
                        value={locationsOkText}
                        onChange={(e) => setLocationsOkText(e.target.value)}
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 text-neutral-900 focus:bg-white"
                      />
                    </div>
                  </div>
                </div>

                {/* 2. Education */}
                <div className="space-y-4 pt-2 border-t border-neutral-100">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 flex items-center gap-1.5">
                    <GraduationCap className="w-3.5 h-3.5" />
                    <span>Education</span>
                  </h4>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Degree
                      </label>
                      <input
                        type="text"
                        value={formData.education?.degree || ""}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            education: { ...(formData.education || {}), degree: e.target.value },
                          })
                        }
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 text-neutral-900 focus:bg-white"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        University / Institution
                      </label>
                      <input
                        type="text"
                        value={formData.education?.university || ""}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            education: { ...(formData.education || {}), university: e.target.value },
                          })
                        }
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 text-neutral-900 focus:bg-white"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Period (e.g. 2020-2024)
                      </label>
                      <input
                        type="text"
                        value={formData.education?.period || ""}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            education: { ...(formData.education || {}), period: e.target.value },
                          })
                        }
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 text-neutral-900 focus:bg-white"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        GPA / Grade
                      </label>
                      <input
                        type="text"
                        value={formData.education?.gpa || ""}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            education: { ...(formData.education || {}), gpa: e.target.value },
                          })
                        }
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 text-neutral-900 focus:bg-white"
                      />
                    </div>

                    <div className="sm:col-span-2">
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Certifications (one per line)
                      </label>
                      <textarea
                        rows={2}
                        value={certificationsText}
                        onChange={(e) => setCertificationsText(e.target.value)}
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 text-neutral-900 focus:bg-white"
                      />
                    </div>
                  </div>
                </div>

                {/* 3. Work Experience */}
                <div className="space-y-3 pt-2 border-t border-neutral-100">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 flex items-center gap-1.5">
                    <Briefcase className="w-3.5 h-3.5" />
                    <span>Work Experience</span>
                  </h4>
                  <p className="text-[11px] text-neutral-400">
                    Format per line: <code className="font-mono bg-neutral-100 px-1 py-0.5 rounded">Role | Company | Period | Brief summary</code>
                  </p>
                  <textarea
                    rows={4}
                    value={experienceText}
                    onChange={(e) => setExperienceText(e.target.value)}
                    className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg p-3 font-mono text-neutral-900 focus:bg-white leading-relaxed"
                  />
                </div>

                {/* 4. Skills & Aliases */}
                <div className="space-y-3 pt-2 border-t border-neutral-100">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 flex items-center gap-1.5">
                    <Wrench className="w-3.5 h-3.5" />
                    <span>Skills & Aliases</span>
                  </h4>
                  <p className="text-[11px] text-neutral-400">
                    Format per line: <code className="font-mono bg-neutral-100 px-1 py-0.5 rounded">skill_name: alias1, alias2</code>
                  </p>
                  <textarea
                    rows={4}
                    value={skillsText}
                    onChange={(e) => setSkillsText(e.target.value)}
                    className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg p-3 font-mono text-neutral-900 focus:bg-white leading-relaxed"
                  />
                </div>

                {/* 5. Projects */}
                <div className="space-y-3 pt-2 border-t border-neutral-100">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 flex items-center gap-1.5">
                    <FolderGit2 className="w-3.5 h-3.5" />
                    <span>Projects</span>
                  </h4>
                  <p className="text-[11px] text-neutral-400">
                    One project per line (Title — Summary and stack)
                  </p>
                  <textarea
                    rows={3}
                    value={projectsText}
                    onChange={(e) => setProjectsText(e.target.value)}
                    className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg p-3 text-neutral-900 focus:bg-white leading-relaxed"
                  />
                </div>

                {/* 6. Salary & CV file */}
                <div className="space-y-4 pt-2 border-t border-neutral-100">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-500">
                    Salary & Jobstreet CV Settings
                  </h4>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Preferred Salary (IDR)
                      </label>
                      <input
                        type="number"
                        value={formData.salary?.preferred ?? 7000000}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            salary: {
                              ...(formData.salary || {}),
                              preferred: parseInt(e.target.value) || 0,
                            },
                          })
                        }
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 text-neutral-900 focus:bg-white"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Min Acceptable Salary (IDR)
                      </label>
                      <input
                        type="number"
                        value={formData.salary?.min_acceptable ?? 6000000}
                        onChange={(e) =>
                          setFormData({
                            ...formData,
                            salary: {
                              ...(formData.salary || {}),
                              min_acceptable: parseInt(e.target.value) || 0,
                            },
                          })
                        }
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 text-neutral-900 focus:bg-white"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        CV Filename on Jobstreet
                      </label>
                      <input
                        type="text"
                        value={formData.cv_file || selectedFile?.name || "CV.pdf"}
                        onChange={(e) => setFormData({ ...formData, cv_file: e.target.value })}
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-lg px-3 py-2 font-mono text-neutral-900 focus:bg-white"
                      />
                    </div>
                  </div>
                </div>

                {/* Save button */}
                <div className="flex items-center justify-end gap-3 pt-4 border-t border-neutral-100">
                  <Button
                    type="submit"
                    variant="primary"
                    size="md"
                    disabled={saveProfileMutation.isPending}
                  >
                    {finishSuccess ? (
                      <>
                        <Check className="w-4 h-4 text-emerald-400" />
                        <span>Profile Saved! Redirecting...</span>
                      </>
                    ) : saveProfileMutation.isPending ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        <span>Saving Profile...</span>
                      </>
                    ) : (
                      <>
                        <Save className="w-4 h-4" />
                        <span>Save Profile & Finish Setup</span>
                      </>
                    )}
                  </Button>
                </div>
              </form>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
