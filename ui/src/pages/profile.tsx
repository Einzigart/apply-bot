import { useState, useEffect } from "react";
import { Link } from "react-router";
import {
  Save,
  Check,
  User,
  GraduationCap,
  Briefcase,
  Wrench,
  FolderGit2,
  FileText,
  Eye,
  Edit3,
  FileCode,
  ChevronDown,
  ChevronRight,
  Sparkles,
  RefreshCw,
  AlertCircle,
  X,
} from "lucide-react";
import { useProfile, useSaveProfile, useImportCV } from "../api/hooks";
import { Card, Button, Badge } from "../components/ui/core";
import { cn, formatCurrency } from "../lib/utils";

export function ProfilePage() {
  const { data, isLoading } = useProfile();
  const saveMutation = useSaveProfile();
  const importCvMutation = useImportCV();

  const [mode, setMode] = useState<"view" | "edit">("view");
  const [formData, setFormData] = useState<any>({});
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [openRaw, setOpenRaw] = useState<Record<string, boolean>>({});

  // CV import state
  const [showImport, setShowImport] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  // Multiline strings for form inputs
  const [languagesText, setLanguagesText] = useState("");
  const [locationsOkText, setLocationsOkText] = useState("");
  const [certificationsText, setCertificationsText] = useState("");
  const [experienceText, setExperienceText] = useState("");
  const [skillsText, setSkillsText] = useState("");
  const [projectsText, setProjectsText] = useState("");

  const populateFromProfile = (p: any) => {
    setFormData(p || {});

    setLanguagesText((p?.languages || []).join("\n"));
    setLocationsOkText((p?.locations_ok || []).join("\n"));
    setCertificationsText((p?.education?.certifications || []).join("\n"));

    const expLines = (p?.experience || [])
      .map((e: any) =>
        typeof e === "object"
          ? `${e.role || ""} | ${e.org || ""} | ${e.period || ""} | ${e.summary || ""}`
          : e
      )
      .join("\n");
    setExperienceText(expLines);

    const skillLines = (p?.skills || [])
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

    setProjectsText((p?.projects || []).join("\n"));
  };

  useEffect(() => {
    if (data?.profile) {
      populateFromProfile(data.profile);
    }
  }, [data]);

  const handleImportCv = () => {
    if (!importFile) return;
    setImportError(null);
    importCvMutation.mutate(importFile, {
      onSuccess: (res) => {
        populateFromProfile(res.profile);
        setMode("edit");
        setShowImport(false);
        setImportFile(null);
      },
      onError: (err) => {
        setImportError(err.message || "Failed to parse CV with AI.");
      },
    });
  };

  const handleChange = (key: string, value: any) => {
    setFormData((prev: any) => ({ ...prev, [key]: value }));
  };

  const handleNestedChange = (parent: string, key: string, value: any) => {
    setFormData((prev: any) => ({
      ...prev,
      [parent]: { ...(prev[parent] || {}), [key]: value },
    }));
  };

  const handleSubmit = (e: React.FormEvent) => {
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

    saveMutation.mutate(payload, {
      onSuccess: () => {
        setSaveSuccess(true);
        setMode("view");
        setTimeout(() => setSaveSuccess(false), 2500);
      },
    });
  };

  if (isLoading || !data) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-8 bg-neutral-200 rounded-xl w-48" />
        <div className="h-96 bg-neutral-200 rounded-xl" />
      </div>
    );
  }

  const prof = data.profile || {};
  const edu = prof.education || {};
  const rawFiles = data.raw || {};

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-neutral-900">
            Candidate Profile
          </h1>
          <p className="text-sm text-neutral-500 mt-0.5">
            Structured candidate context used for matching, scoring, and auto-applying
          </p>
        </div>

        <div className="flex items-center gap-3">
          {saveSuccess && (
            <Badge variant="apply" className="flex items-center gap-1">
              <Check className="w-3 h-3" />
              <span>Profile Saved</span>
            </Badge>
          )}

          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setShowImport(!showImport)}
          >
            <Sparkles className="w-3.5 h-3.5 text-neutral-800" />
            <span>Import CV (PDF)</span>
          </Button>

          <div className="flex items-center bg-neutral-200/70 p-1 rounded-xl">
            <button
              type="button"
              onClick={() => setMode("view")}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl transition-all cursor-pointer",
                mode === "view"
                  ? "bg-white text-neutral-900 shadow-2xs font-semibold"
                  : "text-neutral-600 hover:text-neutral-900"
              )}
            >
              <Eye className="w-3.5 h-3.5" />
              <span>View Mode</span>
            </button>
            <button
              type="button"
              onClick={() => setMode("edit")}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-xl transition-all cursor-pointer",
                mode === "edit"
                  ? "bg-white text-neutral-900 shadow-2xs font-semibold"
                  : "text-neutral-600 hover:text-neutral-900"
              )}
            >
              <Edit3 className="w-3.5 h-3.5" />
              <span>Edit Mode</span>
            </button>
          </div>
        </div>
      </div>

      {/* CV Import Panel */}
      {showImport && (
        <Card className="p-5 border-neutral-300 shadow-xs bg-neutral-50/50 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-neutral-800" />
              <h3 className="text-sm font-semibold text-neutral-900">
                Extract Profile from CV (PDF)
              </h3>
            </div>
            <button
              type="button"
              onClick={() => setShowImport(false)}
              className="text-neutral-400 hover:text-neutral-700 p-1 cursor-pointer"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <p className="text-xs text-neutral-500">
            Upload your CV PDF. Apply Bot will extract your experience, skills, and background using your configured AI model, and populate the edit form for your review.
          </p>

          <div className="flex flex-col sm:flex-row items-center gap-3">
            <input
              type="file"
              accept=".pdf,application/pdf"
              id="profile-cv-input"
              className="text-xs file:mr-3 file:py-1.5 file:px-3 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-neutral-900 file:text-white hover:file:bg-neutral-800 cursor-pointer w-full text-neutral-700"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  setImportFile(e.target.files[0]);
                  setImportError(null);
                }
              }}
            />

            <Button
              type="button"
              variant="primary"
              size="sm"
              onClick={handleImportCv}
              disabled={!importFile || importCvMutation.isPending}
              className="shrink-0"
            >
              {importCvMutation.isPending ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Extracting with AI...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Parse with AI</span>
                </>
              )}
            </Button>
          </div>

          {importError && (
            <div className="p-2.5 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 text-red-500" />
              <span>{importError}</span>
            </div>
          )}
        </Card>
      )}

      {/* Empty Profile Banner for new user */}
      {!data.has_profile && (
        <Card className="p-4 bg-amber-50/50 border-amber-200/80 flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-amber-600 shrink-0" />
            <div>
              <p className="text-xs font-semibold text-amber-900">
                Your profile is not configured yet
              </p>
              <p className="text-[11px] text-amber-700">
                Use the setup wizard to configure your AI provider and import your CV automatically.
              </p>
            </div>
          </div>
          <Link to="/setup">
            <Button size="sm" variant="primary">
              <Sparkles className="w-3.5 h-3.5" />
              <span>Launch Setup Wizard</span>
            </Button>
          </Link>
        </Card>
      )}

      {/* VIEW MODE */}
      {mode === "view" && (
        <div className="space-y-6">
          <Card className="p-6 space-y-6">
            {/* Header / Intro */}
            <div className="border-b border-neutral-100 pb-5">
              <h2 className="text-xl font-bold text-neutral-900">
                {prof.name || "(No name configured)"}
              </h2>
              <p className="text-sm text-neutral-600 mt-1">
                {[prof.location, prof.work_rights].filter(Boolean).join(" · ")}
              </p>
              <p className="text-xs text-neutral-500 mt-1 font-mono">
                {prof.years_experience ?? 0} years experience
                {prof.languages && prof.languages.length > 0
                  ? ` · ${prof.languages.join(", ")}`
                  : ""}
              </p>
            </div>

            {/* Education */}
            {edu && (edu.degree || edu.university) && (
              <div className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
                  Education
                </h3>
                <div className="text-sm text-neutral-900 font-medium">
                  {edu.degree} — {edu.university}
                  {(edu.period || edu.gpa) && (
                    <span className="text-neutral-500 font-normal ml-2">
                      ({[edu.period, edu.gpa ? `GPA ${edu.gpa}` : ""].filter(Boolean).join(", ")})
                    </span>
                  )}
                </div>
                {edu.certifications && edu.certifications.length > 0 && (
                  <p className="text-xs text-neutral-500">
                    Certifications: {edu.certifications.join(", ")}
                  </p>
                )}
              </div>
            )}

            {/* Experience */}
            {prof.experience && prof.experience.length > 0 && (
              <div className="space-y-3">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
                  Work Experience
                </h3>
                <div className="space-y-3">
                  {prof.experience.map((e: any, idx: number) => (
                    <div key={idx} className="text-sm border-l-2 border-neutral-200 pl-3 space-y-0.5">
                      <div className="font-semibold text-neutral-900">
                        {e.role} — <span className="text-neutral-600 font-normal">{e.org}</span>
                        {e.period && <span className="text-xs text-neutral-400 font-mono ml-2">({e.period})</span>}
                      </div>
                      {e.summary && <p className="text-xs text-neutral-600 leading-relaxed">{e.summary}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Skills */}
            {prof.skills && prof.skills.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
                  Skills ({prof.skills.length})
                </h3>
                <div className="flex flex-wrap gap-1.5">
                  {prof.skills.map((s: any, idx: number) => {
                    const name = typeof s === "object" ? s.name : s;
                    const aliases = typeof s === "object" && s.aliases?.length ? s.aliases.join(", ") : "";
                    return (
                      <span
                        key={idx}
                        className="inline-flex items-center px-2.5 py-1 bg-neutral-100 text-neutral-800 text-xs font-mono rounded-xl"
                        title={aliases ? `Aliases: ${aliases}` : undefined}
                      >
                        {name}
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Projects */}
            {prof.projects && prof.projects.length > 0 && (
              <div className="space-y-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
                  Projects
                </h3>
                <ul className="list-disc list-inside space-y-1 text-xs text-neutral-700 leading-relaxed">
                  {prof.projects.map((p: string, idx: number) => (
                    <li key={idx}>{p}</li>
                  ))}
                </ul>
              </div>
            )}

            {/* Footer Summary Grid */}
            <div className="pt-4 border-t border-neutral-100 grid grid-cols-1 md:grid-cols-3 gap-4 text-xs">
              <div>
                <span className="text-neutral-400 block font-medium">CV File:</span>
                <code className="text-neutral-800 font-mono">{prof.cv_file || "CV.pdf"}</code>
              </div>
              <div>
                <span className="text-neutral-400 block font-medium">Salary Range:</span>
                <span className="text-neutral-800 font-mono">
                  {formatCurrency(prof.salary?.min_acceptable || 6000000)} - {formatCurrency(prof.salary?.preferred || 7000000)}
                </span>
                {prof.salary_expectation && (
                  <span className="text-neutral-400 block text-[11px] mt-0.5 font-mono">
                    ({prof.salary_expectation})
                  </span>
                )}
              </div>
              <div>
                <span className="text-neutral-400 block font-medium">Locations:</span>
                <span className="text-neutral-800">
                  {(prof.locations_ok || []).join(", ") || "—"}
                </span>
              </div>
            </div>
          </Card>

          {/* Raw YAML Files Accordion */}
          <div className="space-y-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-neutral-400">
              Raw Configuration Files
            </h3>
            {Object.entries(rawFiles).map(([filename, content]) => {
              const isOpen = !!openRaw[filename];
              return (
                <Card key={filename} className="overflow-hidden">
                  <button
                    type="button"
                    onClick={() =>
                      setOpenRaw((prev) => ({ ...prev, [filename]: !isOpen }))
                    }
                    className="w-full px-4 py-2.5 flex items-center justify-between text-xs font-mono text-neutral-700 bg-neutral-50/70 hover:bg-neutral-100/70 transition-colors cursor-pointer"
                  >
                    <div className="flex items-center gap-2">
                      <FileCode className="w-3.5 h-3.5 text-neutral-500" />
                      <span className="font-semibold">data/{filename}</span>
                    </div>
                    {isOpen ? (
                      <ChevronDown className="w-3.5 h-3.5 text-neutral-400" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5 text-neutral-400" />
                    )}
                  </button>
                  {isOpen && (
                    <pre className="p-4 bg-neutral-950 text-neutral-200 text-xs font-mono overflow-x-auto max-h-96 leading-relaxed select-text">
                      {content}
                    </pre>
                  )}
                </Card>
              );
            })}
          </div>
        </div>
      )}

      {/* EDIT MODE */}
      {mode === "edit" && (
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* 1. Basic Information */}
          <Card className="p-5 space-y-4">
            <div className="flex items-center gap-2">
              <User className="w-4 h-4 text-neutral-700" />
              <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-700">
                Basic Information
              </h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  Full Name
                </label>
                <input
                  type="text"
                  value={formData.name || ""}
                  onChange={(e) => handleChange("name", e.target.value)}
                  className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 focus:bg-white"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  Location
                </label>
                <input
                  type="text"
                  value={formData.location || ""}
                  onChange={(e) => handleChange("location", e.target.value)}
                  className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 focus:bg-white"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  Work Rights / Nationality
                </label>
                <input
                  type="text"
                  value={formData.work_rights || ""}
                  onChange={(e) => handleChange("work_rights", e.target.value)}
                  className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 focus:bg-white"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  Years of Experience
                </label>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  value={formData.years_experience ?? 0}
                  onChange={(e) =>
                    handleChange("years_experience", parseFloat(e.target.value) || 0)
                  }
                  className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 focus:bg-white"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  Languages (One per line)
                </label>
                <textarea
                  rows={3}
                  value={languagesText}
                  onChange={(e) => setLanguagesText(e.target.value)}
                  className="w-full text-xs font-mono bg-neutral-50 border border-neutral-200 rounded-xl p-3 focus:bg-white"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  Acceptable Locations (One per line)
                </label>
                <textarea
                  rows={3}
                  value={locationsOkText}
                  onChange={(e) => setLocationsOkText(e.target.value)}
                  className="w-full text-xs font-mono bg-neutral-50 border border-neutral-200 rounded-xl p-3 focus:bg-white"
                />
              </div>
            </div>
          </Card>

          {/* 2. Education */}
          <Card className="p-5 space-y-4">
            <div className="flex items-center gap-2">
              <GraduationCap className="w-4 h-4 text-neutral-700" />
              <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-700">
                Education
              </h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  Degree
                </label>
                <input
                  type="text"
                  value={edu.degree || ""}
                  onChange={(e) =>
                    handleNestedChange("education", "degree", e.target.value)
                  }
                  placeholder="e.g. B.Sc. Computer Science"
                  className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 focus:bg-white"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  University / Institution
                </label>
                <input
                  type="text"
                  value={edu.university || ""}
                  onChange={(e) =>
                    handleNestedChange("education", "university", e.target.value)
                  }
                  placeholder="e.g. Universitas Indonesia"
                  className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 focus:bg-white"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  Period
                </label>
                <input
                  type="text"
                  value={edu.period || ""}
                  onChange={(e) =>
                    handleNestedChange("education", "period", e.target.value)
                  }
                  placeholder="e.g. 2021-08 to 2025-07"
                  className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 focus:bg-white"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  GPA
                </label>
                <input
                  type="text"
                  value={edu.gpa || ""}
                  onChange={(e) =>
                    handleNestedChange("education", "gpa", e.target.value)
                  }
                  placeholder="e.g. 3.55/4.00"
                  className="w-full text-sm bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 focus:bg-white"
                />
              </div>
              <div className="md:col-span-2">
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  Certifications (One per line)
                </label>
                <textarea
                  rows={3}
                  value={certificationsText}
                  onChange={(e) => setCertificationsText(e.target.value)}
                  placeholder="AWS Certified Solutions Architect"
                  className="w-full text-xs font-mono bg-neutral-50 border border-neutral-200 rounded-xl p-3 focus:bg-white"
                />
              </div>
            </div>
          </Card>

          {/* 3. Work Experience */}
          <Card className="p-5 space-y-4">
            <div className="flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-neutral-700" />
              <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-700">
                Work Experience
              </h2>
            </div>
            <p className="text-xs text-neutral-500">
              Format: <code>Role | Organization | Period | Summary</code> (one per line)
            </p>
            <textarea
              rows={5}
              value={experienceText}
              onChange={(e) => setExperienceText(e.target.value)}
              placeholder="Software Engineer Intern | Acme Corp | 2024-01 to 2024-06 | Built backend REST APIs with Python."
              className="w-full text-xs font-mono bg-neutral-50 border border-neutral-200 rounded-xl p-3 focus:bg-white leading-relaxed"
            />
          </Card>

          {/* 4. Skills & Aliases */}
          <Card className="p-5 space-y-4">
            <div className="flex items-center gap-2">
              <Wrench className="w-4 h-4 text-neutral-700" />
              <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-700">
                Skills & Aliases
              </h2>
            </div>
            <p className="text-xs text-neutral-500">
              Format: <code>skill_name: alias1, alias2</code> or just <code>skill_name</code> (one per line)
            </p>
            <textarea
              rows={6}
              value={skillsText}
              onChange={(e) => setSkillsText(e.target.value)}
              placeholder="python: python3, py&#10;sql: postgresql, mysql, sqlite&#10;react: react.js"
              className="w-full text-xs font-mono bg-neutral-50 border border-neutral-200 rounded-xl p-3 focus:bg-white leading-relaxed"
            />
          </Card>

          {/* 5. Projects */}
          <Card className="p-5 space-y-4">
            <div className="flex items-center gap-2">
              <FolderGit2 className="w-4 h-4 text-neutral-700" />
              <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-700">
                Projects
              </h2>
            </div>
            <p className="text-xs text-neutral-500">
              One project highlight per line. Passed into the scorer context.
            </p>
            <textarea
              rows={4}
              value={projectsText}
              onChange={(e) => setProjectsText(e.target.value)}
              placeholder="AI Chatbot — RAG application built with Python, LangChain, and FastAPI."
              className="w-full text-xs font-mono bg-neutral-50 border border-neutral-200 rounded-xl p-3 focus:bg-white leading-relaxed"
            />
          </Card>

          {/* 6. CV & Salary Expectations */}
          <Card className="p-5 space-y-4">
            <div className="flex items-center gap-2">
              <FileText className="w-4 h-4 text-neutral-700" />
              <h2 className="text-sm font-semibold uppercase tracking-wider text-neutral-700">
                Application Details & Salary
              </h2>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  CV File Name
                </label>
                <input
                  type="text"
                  value={formData.cv_file || "CV.pdf"}
                  onChange={(e) => handleChange("cv_file", e.target.value)}
                  className="w-full text-sm font-mono bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 focus:bg-white"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  Preferred Salary (IDR)
                </label>
                <input
                  type="number"
                  step="100000"
                  value={formData.salary?.preferred || 7000000}
                  onChange={(e) =>
                    handleNestedChange(
                      "salary",
                      "preferred",
                      parseInt(e.target.value, 10) || 0
                    )
                  }
                  className="w-full text-sm font-mono bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 focus:bg-white"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-neutral-700 mb-1">
                  Min Acceptable Salary (IDR)
                </label>
                <input
                  type="number"
                  step="100000"
                  value={formData.salary?.min_acceptable || 6000000}
                  onChange={(e) =>
                    handleNestedChange(
                      "salary",
                      "min_acceptable",
                      parseInt(e.target.value, 10) || 0
                    )
                  }
                  className="w-full text-sm font-mono bg-neutral-50 border border-neutral-200 rounded-xl px-3 py-2 focus:bg-white"
                />
              </div>
            </div>
          </Card>

          {/* Action Bar */}
          <div className="flex items-center justify-between pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setMode("view")}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={saveMutation.isPending}>
              <Save className="w-3.5 h-3.5" />
              <span>{saveMutation.isPending ? "Saving..." : "Save Profile"}</span>
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
