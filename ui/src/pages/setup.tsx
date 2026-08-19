import { useState, useEffect, useRef } from "react";
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
  Globe,
  Trash2,
  Target,
  Sliders,
  Database,
  X,
} from "lucide-react";
import {
  useSettings,
  useSaveSettings,
  useProviderModels,
  useTestLlm,
  useImportCV,
  useSaveProfile,
  useProfile,
  useImportBackup,
} from "../api/hooks";
import { apiFetch } from "../api/client";
import { Card, Button, Badge, ApplyBotIcon } from "../components/ui/core";
import {
  OpenAIIcon,
  ClaudeIcon,
  CopilotIcon,
  AntigravityIcon,
  JobstreetIcon,
} from "../components/ui/provider-icons";
import { cn } from "../lib/utils";

const PROVIDER_DEFAULT_MODELS: Record<string, string> = {
  claude: "claude-sonnet-5",
  codex: "gpt-5.6-luna",
  copilot: "gpt-5.6-luna",
  gemini: "gemini-3.6-flash",
  openai: "gpt-4o-mini",
};

export function SetupPage() {
  const navigate = useNavigate();
  const { data: settings, isLoading: settingsLoading, refetch: refetchSettings } = useSettings();
  const { refetch: refetchProfile } = useProfile();
  const saveSettingsMutation = useSaveSettings();
  const testLlmMutation = useTestLlm();
  const importCvMutation = useImportCV();
  const saveProfileMutation = useSaveProfile();
  const importBackupMutation = useImportBackup();

  // Backup restore state during onboarding
  const [backupFile, setBackupFile] = useState<File | null>(null);
  const [isBackupModalOpen, setIsBackupModalOpen] = useState(false);
  const [backupError, setBackupError] = useState<string | null>(null);
  const [backupRestoredSuccess, setBackupRestoredSuccess] = useState(false);

  const initializedRef = useRef(false);
  const previousTokensRef = useRef<Record<string, boolean>>({});
  const initialConnectedCountRef = useRef<number | null>(null);

  const [step, setStep] = useState<1 | 2 | 3>(1);

  // Step 1 - LLM state
  const [provider, setProvider] = useState("openai");
  const [endpoint, setEndpoint] = useState("https://api.openai.com/v1");
  const [model, setModel] = useState("gpt-4o-mini");
  const [apiKey, setApiKey] = useState("");
  const [prefix, setPrefix] = useState("");
  const [isVerified, setIsVerified] = useState(false);
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

  // Step 2 - Jobstreet state
  const [jobstreetLoginTriggered, setJobstreetLoginTriggered] = useState(false);
  const [jobstreetDeleteLoading, setJobstreetDeleteLoading] = useState(false);

  // Step 3 - CV upload & Profile state
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
  
  // Predicted Search & Strategy state
  const [pitch, setPitch] = useState("");
  const [customInstructions, setCustomInstructions] = useState("");
  const [targetRolesText, setTargetRolesText] = useState("");
  const [targetLocationsText, setTargetLocationsText] = useState("");
  const [roleKeywordsText, setRoleKeywordsText] = useState("");
  const [locationWhitelistText, setLocationWhitelistText] = useState("");
  const [minExp, setMinExp] = useState(0);
  const [maxExp, setMaxExp] = useState(3);
  const [finishSuccess, setFinishSuccess] = useState(false);

  const {
    data: modelsData,
    isLoading: modelsLoading,
    refetch: refetchModels,
  } = useProviderModels(provider);

  useEffect(() => {
    if (settings) {
      const authTokens = settings.auth_tokens || {};
      const connectedKeys = Object.keys(authTokens).filter((k) => authTokens[k]?.connected);
      const currentConnectedCount = connectedKeys.length;

      if (!initializedRef.current) {
        initializedRef.current = true;
        initialConnectedCountRef.current = currentConnectedCount;
        const llm = settings.llm_cfg || {};
        const active = settings.active_llm || {};
        setProvider(active.provider || llm.provider || "openai");
        setModel(active.raw_model || llm.model || "gpt-4o-mini");
        setEndpoint(llm.endpoint || "https://api.openai.com/v1");
        setApiKey("");
        setPrefix(llm.prefix || "");

        const tokenMap: Record<string, boolean> = {};
        for (const k of ["claude", "codex", "copilot", "gemini"]) {
          tokenMap[k] = Boolean(authTokens[k]?.connected);
        }
        previousTokensRef.current = tokenMap;
        return;
      }

      // Check if a new provider just got connected
      const prev = previousTokensRef.current;
      let newlyConnectedProvider: string | null = null;

      for (const k of ["claude", "codex", "copilot", "gemini"]) {
        const isNowConnected = Boolean(authTokens[k]?.connected);
        const wasConnected = Boolean(prev[k]);
        if (isNowConnected && !wasConnected) {
          newlyConnectedProvider = k;
        }
      }

      // Update previous tokens tracking
      const tokenMap: Record<string, boolean> = {};
      for (const k of ["claude", "codex", "copilot", "gemini"]) {
        tokenMap[k] = Boolean(authTokens[k]?.connected);
      }
      previousTokensRef.current = tokenMap;

      // Only auto-switch provider/model if this is the FIRST connected AI provider
      if (newlyConnectedProvider && initialConnectedCountRef.current === 0) {
        initialConnectedCountRef.current = 1;
        const defModel = PROVIDER_DEFAULT_MODELS[newlyConnectedProvider] || "gpt-4o-mini";
        setProvider(newlyConnectedProvider);
        setModel(defModel);
        setIsVerified(false);
        setLlmTestStatus({});
      }
    }
  }, [settings]);

  const authTokens = settings?.auth_tokens || {};
  const hasJobstreetAuth = Boolean(settings?.has_auth);

  const isChromeInstalled = settings?.chrome_installed ?? true;

  const handleJobstreetLogin = async () => {
    if (settings?.chrome_installed === false) {
      alert("Google Chrome is required to sign in to Jobstreet. Please install Google Chrome from https://www.google.com/chrome first.");
      window.open("https://www.google.com/chrome", "_blank");
      return;
    }
    try {
      await apiFetch("/api/settings/jobstreet/system-login", { method: "POST" });
      setJobstreetLoginTriggered(true);
      setTimeout(() => refetchSettings(), 2000);
      setTimeout(() => refetchSettings(), 5000);
      setTimeout(() => refetchSettings(), 9000);
    } catch (err: any) {
      alert(`Failed to launch browser: ${err.message}`);
    }
  };

  const handleDeleteJobstreetAuth = async () => {
    setJobstreetDeleteLoading(true);
    try {
      await apiFetch("/api/settings/jobstreet/auth", { method: "DELETE" });
      refetchSettings();
    } catch (err: any) {
      alert(`Failed to remove Jobstreet session: ${err.message}`);
    } finally {
      setJobstreetDeleteLoading(false);
    }
  };

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

  const handleTestLlm = (onSuccessCallback?: () => void) => {
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
                setIsVerified(true);
                setLlmTestStatus({
                  success: true,
                  message: res.response || "Connection successful!",
                  loading: false,
                });
                if (onSuccessCallback) {
                  onSuccessCallback();
                }
              } else {
                setIsVerified(false);
                setLlmTestStatus({
                  success: false,
                  message: res.error || "Connection failed.",
                  loading: false,
                });
              }
            },
            onError: (err) => {
              setIsVerified(false);
              setLlmTestStatus({
                success: false,
                message: err.message,
                loading: false,
              });
            },
          });
        },
        onError: (err) => {
          setIsVerified(false);
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
    // If already verified, allow direct continuation
    if (isVerified || step1Saved) {
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
      return;
    }

    // Must pass the connection test first before proceeding
    handleTestLlm(() => {
      setStep1Saved(true);
      setStep(2);
    });
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

        // Predicted Cover Letter & Strategy
        const letter = p.letter || {};
        setPitch(letter.pitch || "");
        setCustomInstructions(letter.custom_instructions || "");

        // Predicted Configuration
        const pred = p.predicted_config || {};
        const rolesLines = (pred.target_roles || [
          { name: "Software Engineer", slug: "software-engineer" },
        ])
          .map((r: any) => (r.name && r.slug ? `${r.name}: ${r.slug}` : String(r)))
          .join("\n");
        setTargetRolesText(rolesLines);

        const locLines = (pred.target_locations || [
          { name: "Jakarta", slug: "Jakarta" },
          { name: "Remote (Indonesia)", slug: "Indonesia" },
        ])
          .map((l: any) => (l.name && l.slug ? `${l.name}: ${l.slug}` : String(l)))
          .join("\n");
        setTargetLocationsText(locLines);

        setRoleKeywordsText((pred.role_keywords || []).join(", "));
        setLocationWhitelistText((pred.location_whitelist || []).join(", "));
        setMinExp(pred.min_years_experience ?? 0);
        setMaxExp(pred.max_years_experience ?? (Math.max(1, Math.ceil(p.years_experience || 0) + 2)));
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

    const parsedTargetRoles = targetRolesText
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

    const parsedTargetLocations = targetLocationsText
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

    const parsedRoleKeywords = roleKeywordsText
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);

    const parsedLocationWhitelist = locationWhitelistText
      .split(",")
      .map((s) => s.trim().toLowerCase())
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
      letter: {
        ...(formData.letter || {}),
        pitch: pitch.trim(),
        custom_instructions: customInstructions.trim(),
      },
      predicted_config: {
        target_roles: parsedTargetRoles,
        target_locations: parsedTargetLocations,
        role_keywords: parsedRoleKeywords,
        location_whitelist: parsedLocationWhitelist,
        min_years_experience: minExp,
        max_years_experience: maxExp,
      },
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
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-neutral-900 text-white shadow-xs mb-1">
          <ApplyBotIcon className="w-6 h-6" />
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
          Welcome to Apply Bot
        </h1>
        <p className="text-sm text-neutral-500 max-w-md mx-auto">
          Get started in 3 quick steps: set up your AI model, connect your Jobstreet account, then import your CV to build your candidate profile.
        </p>
      </div>

      {/* Restore from Backup Option Banner */}
      <div className="p-3.5 rounded-xl border border-neutral-200 bg-neutral-50 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs">
        <div className="flex items-center gap-2.5">
          <div className="p-1.5 rounded-lg bg-white border border-neutral-200 text-neutral-700 shrink-0">
            <Database className="w-4 h-4" />
          </div>
          <div>
            <span className="font-semibold text-neutral-900">Already have an Apply Bot backup?</span>
            <span className="text-neutral-500 block sm:inline sm:ml-1.5">
              Restore your profile, AI configurations, and database history from a JSON backup file.
            </span>
          </div>
        </div>

        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={() => {
            setBackupError(null);
            setBackupFile(null);
            setIsBackupModalOpen(true);
          }}
          className="shrink-0 bg-white"
        >
          <Upload className="w-3.5 h-3.5" />
          <span>Restore Backup</span>
        </Button>
      </div>

      {/* Steps Indicator */}
      <div className="flex items-center justify-center gap-2 text-xs font-medium flex-wrap sm:flex-nowrap">
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
          <span>AI Provider</span>
        </button>

        <div className="w-4 h-px bg-neutral-200" />

        <button
          onClick={() => {
            if (isVerified || step1Saved) {
              setStep(2);
            }
          }}
          className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-full transition-colors",
            step === 2
              ? "bg-neutral-900 text-white font-semibold"
              : "bg-neutral-100 text-neutral-600",
            !isVerified && !step1Saved
              ? "opacity-60 cursor-not-allowed"
              : "cursor-pointer hover:bg-neutral-200"
          )}
        >
          <span className="w-4 h-4 rounded-full bg-white/20 flex items-center justify-center text-[10px]">
            2
          </span>
          <span>Jobstreet Auth</span>
        </button>

        <div className="w-4 h-px bg-neutral-200" />

        <button
          onClick={() => {
            if (isVerified || step1Saved) {
              setStep(3);
            }
          }}
          className={cn(
            "flex items-center gap-2 px-3 py-1.5 rounded-full transition-colors",
            step === 3
              ? "bg-neutral-900 text-white font-semibold"
              : "bg-neutral-100 text-neutral-600",
            !isVerified && !step1Saved
              ? "opacity-60 cursor-not-allowed"
              : "cursor-pointer hover:bg-neutral-200"
          )}
        >
          <span className="w-4 h-4 rounded-full bg-white/20 flex items-center justify-center text-[10px]">
            3
          </span>
          <span>Import CV & Profile</span>
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
              <div className="p-3 border border-neutral-200 rounded-xl flex items-center justify-between bg-neutral-50/50">
                <div className="flex items-center gap-2.5">
                  <ClaudeIcon className="w-5 h-5 shrink-0" />
                  <div>
                    <div className="font-medium text-xs text-neutral-900 flex items-center gap-1.5">
                      <span>Claude Code</span>
                      {authTokens.claude?.connected && (
                        <Badge variant="apply">Connected</Badge>
                      )}
                    </div>
                    <p className="text-[11px] text-neutral-400">Anthropic Claude Pro / Max</p>
                  </div>
                </div>
                {authTokens.claude?.connected ? (
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
              <div className="p-3 border border-neutral-200 rounded-xl flex items-center justify-between bg-neutral-50/50">
                <div className="flex items-center gap-2.5">
                  <OpenAIIcon className="w-5 h-5 shrink-0 text-neutral-800" />
                  <div>
                    <div className="font-medium text-xs text-neutral-900 flex items-center gap-1.5">
                      <span>ChatGPT / Codex</span>
                      {authTokens.codex?.connected && (
                        <Badge variant="apply">Connected</Badge>
                      )}
                    </div>
                    <p className="text-[11px] text-neutral-400">OpenAI Plus / Pro</p>
                  </div>
                </div>
                {authTokens.codex?.connected ? (
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
              <div className="p-3 border border-neutral-200 rounded-xl flex items-center justify-between bg-neutral-50/50">
                <div className="flex items-center gap-2.5">
                  <CopilotIcon className="w-5 h-5 shrink-0 text-neutral-800" />
                  <div>
                    <div className="font-medium text-xs text-neutral-900 flex items-center gap-1.5">
                      <span>GitHub Copilot</span>
                      {authTokens.copilot?.connected && (
                        <Badge variant="apply">Connected</Badge>
                      )}
                    </div>
                    <p className="text-[11px] text-neutral-400">Copilot Individual / Business</p>
                  </div>
                </div>
                {authTokens.copilot?.connected ? (
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
              <div className="p-3 border border-neutral-200 rounded-xl flex items-center justify-between bg-neutral-50/50">
                <div className="flex items-center gap-2.5">
                  <AntigravityIcon className="w-5 h-5 shrink-0" />
                  <div>
                    <div className="font-medium text-xs text-neutral-900 flex items-center gap-1.5">
                      <span>Google Antigravity</span>
                      {authTokens.gemini?.connected && (
                        <Badge variant="apply">Connected</Badge>
                      )}
                    </div>
                    <p className="text-[11px] text-neutral-400">Google Code Assist / Antigravity</p>
                  </div>
                </div>
                {authTokens.gemini?.connected ? (
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
              <div className="p-3 bg-blue-50/60 border border-blue-200 rounded-xl text-xs space-y-1.5">
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
                    <code className="font-mono bg-white px-2 py-0.5 rounded-xl border border-blue-200 font-bold">
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
                  onChange={(e) => {
                    const next = e.target.value;
                    setProvider(next);
                    setIsVerified(false);
                    setLlmTestStatus({});
                    if (PROVIDER_DEFAULT_MODELS[next]) {
                      setModel(PROVIDER_DEFAULT_MODELS[next]);
                    }
                  }}
                  className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 focus:bg-white text-neutral-800"
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
                    onChange={(e) => {
                      setModel(e.target.value);
                      setIsVerified(false);
                      setLlmTestStatus({});
                    }}
                    className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 font-mono text-neutral-800"
                  >
                    {modelsData.models.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.id}
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
                    onChange={(e) => {
                      setModel(e.target.value);
                      setIsVerified(false);
                      setLlmTestStatus({});
                    }}
                    placeholder="e.g. gpt-5.6-luna, claude-sonnet-5"
                    className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 font-mono text-neutral-800"
                  />
                )}
              </div>
            </div>

            {/* Custom BYOK settings if openai compatible */}
            {!isSubscription && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 p-3.5 bg-neutral-50/50 rounded-xl border border-neutral-200">
                <div className="sm:col-span-2">
                  <label className="block text-xs font-medium text-neutral-700 mb-1">
                    API Endpoint
                  </label>
                  <input
                    type="text"
                    value={endpoint}
                    onChange={(e) => {
                      setEndpoint(e.target.value);
                      setIsVerified(false);
                      setLlmTestStatus({});
                    }}
                    placeholder="https://api.openai.com/v1"
                    className="w-full text-xs bg-white border border-neutral-200 rounded-xl px-3 py-2 font-mono text-neutral-800"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-neutral-700 mb-1">
                    API Key
                  </label>
                  <input
                    type="password"
                    value={apiKey}
                    onChange={(e) => {
                      setApiKey(e.target.value);
                      setIsVerified(false);
                      setLlmTestStatus({});
                    }}
                    placeholder={settings?.has_api_key ? (settings?.masked_suffix ? `••••••••${settings.masked_suffix}` : "Configured") : "sk-..."}
                    className="w-full text-xs bg-white border border-neutral-200 rounded-xl px-3 py-2 font-mono text-neutral-800"
                  />
                </div>

                <div>
                  <label className="block text-xs font-medium text-neutral-700 mb-1">
                    Model Prefix (Optional)
                  </label>
                  <input
                    type="text"
                    value={prefix}
                    onChange={(e) => {
                      setPrefix(e.target.value);
                      setIsVerified(false);
                      setLlmTestStatus({});
                    }}
                    placeholder="e.g. openai or deepseek"
                    className="w-full text-xs bg-white border border-neutral-200 rounded-xl px-3 py-2 font-mono text-neutral-800"
                  />
                </div>
              </div>
            )}
          </div>

          {/* Test connection & Feedback */}
          <div className="pt-2 space-y-3 border-t border-neutral-100">
            {llmTestStatus.success === false && (
              <div className="p-3.5 bg-red-50 border border-red-200 rounded-xl text-xs space-y-2">
                <div className="flex items-start gap-2 text-red-800 font-medium">
                  <AlertCircle className="w-4 h-4 shrink-0 text-red-600 mt-0.5" />
                  <div className="space-y-1">
                    <p className="font-semibold text-red-900">Connection test failed</p>
                    <p className="font-mono text-[11px] text-red-700 break-words">{llmTestStatus.message}</p>
                    <p className="text-neutral-600 text-xs mt-1">
                      Try retrying the connection, or change your selected model (e.g. <span className="font-mono font-semibold">gemini-3.7-flash-medium</span>, <span className="font-mono font-semibold">claude-sonnet-5</span>, or <span className="font-mono font-semibold">gpt-5.6-luna</span>) or AI provider.
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => handleTestLlm()}
                  disabled={llmTestStatus.loading}
                >
                  {llmTestStatus.loading ? (
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <Key className="w-3.5 h-3.5" />
                  )}
                  <span>{llmTestStatus.success === false ? "Retry Test Connection" : "Test Connection"}</span>
                </Button>

                {llmTestStatus.success === true && (
                  <div className="flex items-center gap-1.5 text-xs text-emerald-600 font-medium">
                    <CheckCircle2 className="w-4 h-4" />
                    <span>{llmTestStatus.message}</span>
                  </div>
                )}
              </div>

              <Button
                type="button"
                variant="primary"
                size="md"
                onClick={handleSaveStep1}
                disabled={saveSettingsMutation.isPending || llmTestStatus.loading}
              >
                <span>Continue to Jobstreet Login</span>
                <ArrowRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* STEP 2: Jobstreet Authentication */}
      {step === 2 && (
        <Card className="p-6 space-y-6 border-neutral-200 shadow-xs">
          <div className="border-b border-neutral-100 pb-4 flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <JobstreetIcon className={cn("w-4 h-4", hasJobstreetAuth ? "text-[#0d3880]" : "text-neutral-800")} />
                <h2 className="text-base font-semibold text-neutral-900">
                  Step 2: Connect Jobstreet Account
                </h2>
              </div>
              <p className="text-xs text-neutral-500 mt-1">
                Apply Bot needs an active Jobstreet session to search for matching jobs and submit applications on your behalf.
              </p>
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

          {/* Chrome Installation Check Banner */}
          {!isChromeInstalled && (
            <div className="p-4 border border-amber-300 rounded-xl bg-amber-50 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-amber-900">
              <div className="flex items-start gap-2.5">
                <AlertCircle className="w-5 h-5 text-amber-600 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <p className="font-semibold text-amber-950">Google Chrome is required</p>
                  <p className="text-amber-800 leading-relaxed">
                    Apply Bot uses your installed Google Chrome browser for Jobstreet authentication and automated form submissions. If installed in a custom location, ensure it is added to your system PATH or set <code className="font-mono bg-amber-100 px-1 py-0.5 rounded">CHROME_PATH</code>.
                  </p>
                </div>
              </div>
              <a
                href="https://www.google.com/chrome"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white font-medium shrink-0 transition-colors cursor-pointer"
              >
                <span>Download Chrome</span>
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>
          )}

          {/* Session Status Banner */}
          <div className="p-5 border border-neutral-200 rounded-xl bg-neutral-50/60 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-neutral-900">
                  Jobstreet Session Status
                </span>
                <span
                  className={cn(
                    "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border",
                    hasJobstreetAuth
                      ? "bg-emerald-50 text-emerald-700 border-emerald-200/80"
                      : "bg-amber-50 text-amber-700 border-amber-200/80"
                  )}
                >
                  <span
                    className={cn(
                      "w-1.5 h-1.5 rounded-full",
                      hasJobstreetAuth ? "bg-emerald-500" : "bg-amber-500"
                    )}
                  />
                  <span>{hasJobstreetAuth ? "Session Connected" : "Not Authenticated"}</span>
                </span>
              </div>
              <p className="text-xs text-neutral-500">
                {hasJobstreetAuth
                  ? "Your authenticated session is active and stored securely in local browser storage state."
                  : "Click below to open an authentic browser window and sign in using Google or email on Jobstreet."}
              </p>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <Button
                variant={hasJobstreetAuth ? "outline" : "primary"}
                size="md"
                onClick={handleJobstreetLogin}
              >
                <Globe className="w-4 h-4" />
                <span>{hasJobstreetAuth ? "Re-authenticate in Browser" : "Log in to Jobstreet"}</span>
              </Button>

              {hasJobstreetAuth && (
                <Button
                  size="md"
                  variant="danger"
                  onClick={handleDeleteJobstreetAuth}
                  disabled={jobstreetDeleteLoading}
                  title="Remove saved Jobstreet session"
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              )}
            </div>
          </div>

          {jobstreetLoginTriggered && !hasJobstreetAuth && (
            <div className="p-3.5 bg-blue-50 border border-blue-200 rounded-xl text-xs text-blue-800 space-y-1">
              <div className="font-semibold flex items-center gap-2">
                <RefreshCw className="w-3.5 h-3.5 animate-spin text-blue-600" />
                <span>Waiting for login completion in browser window...</span>
              </div>
              <p className="text-blue-700">
                Complete your login inside the opened browser window. This status will automatically update once authenticated.
              </p>
            </div>
          )}

          {/* Action navigation */}
          <div className="pt-2 flex items-center justify-between border-t border-neutral-100">
            <button
              type="button"
              onClick={() => refetchSettings()}
              className="text-xs text-neutral-500 hover:text-neutral-900 inline-flex items-center gap-1.5 cursor-pointer"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Check session status</span>
            </button>

            <Button
              type="button"
              variant="primary"
              size="md"
              onClick={() => setStep(3)}
            >
              <span>Continue to CV Import</span>
              <ArrowRight className="w-4 h-4" />
            </Button>
          </div>
        </Card>
      )}

      {/* STEP 3: CV Upload and Review */}
      {step === 3 && (
        <div className="space-y-6">
          {/* CV Upload Dropzone */}
          <Card className="p-6 space-y-4 border-neutral-200 shadow-xs">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-neutral-800" />
                <h2 className="text-base font-semibold text-neutral-900">
                  Step 3: Upload Your CV (PDF)
                </h2>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setStep(2)}
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                <span>Back to Jobstreet Login</span>
              </Button>
            </div>

            <p className="text-xs text-neutral-500">
              Upload your resume or curriculum vitae in PDF format. Apply Bot will extract your experience, skills, and education to build your candidate profile.
            </p>

            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={handleFileDrop}
              className={cn(
                "border-2 border-dashed rounded-xl p-8 text-center transition-all flex flex-col items-center justify-center gap-3 cursor-pointer",
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
              <div className="w-12 h-12 rounded-xl bg-white border border-neutral-200 flex items-center justify-center text-neutral-700 shadow-xs">
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
              <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center gap-2">
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
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
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
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
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
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
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
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
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
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
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
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
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
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
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
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
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
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
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
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
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
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
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
                    Format per line: <code className="font-mono bg-neutral-100 px-2 py-0.5 rounded-xl">Role | Company | Period | Brief summary</code>
                  </p>
                  <textarea
                    rows={4}
                    value={experienceText}
                    onChange={(e) => setExperienceText(e.target.value)}
                    className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl p-3 font-mono text-neutral-900 focus:bg-white leading-relaxed"
                  />
                </div>

                {/* 4. Skills & Aliases */}
                <div className="space-y-3 pt-2 border-t border-neutral-100">
                  <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 flex items-center gap-1.5">
                    <Wrench className="w-3.5 h-3.5" />
                    <span>Skills & Aliases</span>
                  </h4>
                  <p className="text-[11px] text-neutral-400">
                    Format per line: <code className="font-mono bg-neutral-100 px-2 py-0.5 rounded-xl">skill_name: alias1, alias2</code>
                  </p>
                  <textarea
                    rows={4}
                    value={skillsText}
                    onChange={(e) => setSkillsText(e.target.value)}
                    className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl p-3 font-mono text-neutral-900 focus:bg-white leading-relaxed"
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
                    className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl p-3 text-neutral-900 focus:bg-white leading-relaxed"
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
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
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
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
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
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 font-mono text-neutral-900 focus:bg-white"
                      />
                    </div>
                  </div>
                </div>

                {/* 7. AI Cover Letter Strategy */}
                <div className="space-y-4 pt-2 border-t border-neutral-100">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 flex items-center gap-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-blue-600" />
                      <span>AI Predicted Cover Letter Strategy</span>
                    </h4>
                    <Badge variant="apply">AI Predicted</Badge>
                  </div>

                  <div className="space-y-3">
                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Professional Pitch / Headline (1-line summary)
                      </label>
                      <input
                        type="text"
                        value={pitch}
                        onChange={(e) => setPitch(e.target.value)}
                        placeholder="e.g. Full stack engineer specializing in Python, FastAPI, and React"
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 font-mono text-neutral-900 focus:bg-white"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Custom AI Cover Letter Instructions
                      </label>
                      <textarea
                        rows={2}
                        value={customInstructions}
                        onChange={(e) => setCustomInstructions(e.target.value)}
                        placeholder="e.g. Keep under 120 words. Emphasize backend APIs and database optimization..."
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl p-3 text-neutral-900 focus:bg-white leading-relaxed"
                      />
                    </div>
                  </div>
                </div>

                {/* 8. AI Predicted Search Configuration */}
                <div className="space-y-4 pt-2 border-t border-neutral-100">
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-semibold uppercase tracking-wider text-neutral-500 flex items-center gap-1.5">
                      <Target className="w-3.5 h-3.5 text-emerald-600" />
                      <span>AI Predicted Jobstreet Search & Filters</span>
                    </h4>
                    <Badge variant="apply">AI Configured</Badge>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Target Search Roles (Name: slug, 1 per line)
                      </label>
                      <textarea
                        rows={4}
                        value={targetRolesText}
                        onChange={(e) => setTargetRolesText(e.target.value)}
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl p-3 font-mono text-neutral-900 focus:bg-white leading-relaxed"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Target Locations (Name: slug, 1 per line)
                      </label>
                      <textarea
                        rows={4}
                        value={targetLocationsText}
                        onChange={(e) => setTargetLocationsText(e.target.value)}
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl p-3 font-mono text-neutral-900 focus:bg-white leading-relaxed"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Role Matching Keywords (comma-separated)
                      </label>
                      <textarea
                        rows={2}
                        value={roleKeywordsText}
                        onChange={(e) => setRoleKeywordsText(e.target.value)}
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl p-3 font-mono text-neutral-900 focus:bg-white leading-relaxed"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Location Whitelist (comma-separated)
                      </label>
                      <textarea
                        rows={2}
                        value={locationWhitelistText}
                        onChange={(e) => setLocationWhitelistText(e.target.value)}
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl p-3 font-mono text-neutral-900 focus:bg-white leading-relaxed"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Min Years Experience
                      </label>
                      <input
                        type="number"
                        value={minExp}
                        onChange={(e) => setMinExp(parseInt(e.target.value, 10) || 0)}
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-neutral-700 mb-1">
                        Max Years Experience
                      </label>
                      <input
                        type="number"
                        value={maxExp}
                        onChange={(e) => setMaxExp(parseInt(e.target.value, 10) || 0)}
                        className="w-full text-xs bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 text-neutral-900 focus:bg-white"
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

      {/* Restore Backup Dialog during Onboarding */}
      {isBackupModalOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="restore-backup-modal-title"
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs"
        >
          <div className="bg-white rounded-xl border border-neutral-200/90 shadow-xl max-w-md w-full p-6 space-y-4 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-neutral-100 text-neutral-800">
                  <Database className="w-5 h-5" />
                </div>
                <div>
                  <h3 id="restore-backup-modal-title" className="text-base font-semibold text-neutral-900">
                    Restore from Backup
                  </h3>
                  <p className="text-xs text-neutral-500">
                    Restore your candidate profile, AI settings, and job history.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setIsBackupModalOpen(false);
                  setBackupFile(null);
                  setBackupError(null);
                }}
                className="text-neutral-400 hover:text-neutral-700 p-1 rounded-lg hover:bg-neutral-100 transition-colors cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Dropzone */}
            <div
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (e.dataTransfer.files && e.dataTransfer.files[0]) {
                  const f = e.dataTransfer.files[0];
                  if (f.name.toLowerCase().endsWith(".json")) {
                    setBackupFile(f);
                    setBackupError(null);
                  } else {
                    setBackupError("Please select a JSON backup file (*.json).");
                  }
                }
              }}
              className={cn(
                "border-2 border-dashed rounded-xl p-6 text-center transition-all flex flex-col items-center justify-center gap-2.5 cursor-pointer",
                backupFile
                  ? "border-neutral-900 bg-neutral-50/80"
                  : "border-neutral-200 hover:border-neutral-400 bg-neutral-50/40"
              )}
              onClick={() => document.getElementById("onboarding-backup-file-input")?.click()}
            >
              <input
                id="onboarding-backup-file-input"
                type="file"
                accept=".json,application/json"
                className="hidden"
                onChange={(e) => {
                  if (e.target.files && e.target.files[0]) {
                    const f = e.target.files[0];
                    if (f.name.toLowerCase().endsWith(".json")) {
                      setBackupFile(f);
                      setBackupError(null);
                    } else {
                      setBackupError("Please select a JSON backup file (*.json).");
                    }
                  }
                }}
              />
              <Upload className="w-6 h-6 text-neutral-600" />
              <div>
                <p className="text-xs font-semibold text-neutral-800">
                  {backupFile ? backupFile.name : "Click to choose or drop backup JSON"}
                </p>
                <p className="text-[11px] text-neutral-400 mt-0.5">
                  {backupFile
                    ? `${(backupFile.size / 1024).toFixed(1)} KB`
                    : "apply-bot-backup-*.json"}
                </p>
              </div>
            </div>

            {backupError && (
              <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0 text-red-500" />
                <span>{backupError}</span>
              </div>
            )}

            {backupRestoredSuccess && (
              <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-800 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
                <span>Backup restored! Redirecting to Dashboard...</span>
              </div>
            )}

            <div className="pt-2 flex items-center justify-end gap-2.5 border-t border-neutral-100">
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => {
                  setIsBackupModalOpen(false);
                  setBackupFile(null);
                  setBackupError(null);
                }}
                disabled={importBackupMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="primary"
                size="sm"
                onClick={() => {
                  if (!backupFile) return;
                  setBackupError(null);
                  importBackupMutation.mutate(backupFile, {
                    onSuccess: () => {
                      setBackupRestoredSuccess(true);
                      refetchSettings();
                      refetchProfile();
                      setTimeout(() => {
                        navigate("/", { replace: true });
                      }, 1000);
                    },
                    onError: (err: any) => {
                      setBackupError(err.message || "Failed to restore backup.");
                    },
                  });
                }}
                disabled={!backupFile || importBackupMutation.isPending || backupRestoredSuccess}
              >
                {importBackupMutation.isPending ? (
                  <>
                    <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                    <span>Restoring...</span>
                  </>
                ) : (
                  <span>Restore & Continue</span>
                )}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
