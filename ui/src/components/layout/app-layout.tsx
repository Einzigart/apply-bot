import { useEffect } from "react";
import { Outlet, useLocation, useNavigate, useParams } from "react-router";
import { Sidebar } from "./sidebar";
import { useProfile } from "../../api/hooks";
import { BrowserPanel } from "../browser/browser-panel";
import { useBrowser } from "../browser/browser-context";
import { Globe } from "lucide-react";

const ROUTE_TITLES: Record<string, { title: string; subtitle?: string }> = {
  "/": { title: "Dashboard", subtitle: "Overview and recent runs" },
  "/setup": { title: "Setup Wizard", subtitle: "AI model configuration and CV import" },
  "/jobs": { title: "Jobs", subtitle: "Discovered and evaluated positions" },
  "/applications": { title: "Applications", subtitle: "Application history" },
  "/runs": { title: "Runs", subtitle: "Execution pipeline runner and status" },
  "/profile": { title: "Profile", subtitle: "Job applicant background and preferences" },
  "/settings": { title: "Settings", subtitle: "LLM, filters, salary, and system preferences" },
};

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = useParams();
  const { data: profileData, isLoading: profileLoading } = useProfile();
  const { openBrowser, closePanel, isOpen, isActive } = useBrowser();
  const isElectron = typeof window !== "undefined" && !!(window as any).electronAPI?.isElectron;
  const electronAPI = (window as any)?.electronAPI;

  useEffect(() => {
    // If profile is not set up and user is on root dashboard, redirect to setup
    if (!profileLoading && profileData && !profileData.has_profile && location.pathname === "/") {
      navigate("/setup", { replace: true });
    }
  }, [profileData, profileLoading, location.pathname, navigate]);

  let routeInfo = ROUTE_TITLES[location.pathname];
  if (!routeInfo && location.pathname.startsWith("/runs/")) {
    routeInfo = { title: `Run #${params.id || ""}`, subtitle: "Execution logs and details" };
  }
  const title = routeInfo?.title ?? "Apply Bot";

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-white text-neutral-900 font-sans relative">
      <Sidebar />
      
      <div className="flex-1 flex flex-col h-screen min-w-0 bg-white">
        {/* macOS Style Title Bar / Window Header */}
        <header className="h-10 shrink-0 border-b border-neutral-200/80 titlebar-drag flex items-center justify-between px-6 bg-white/80 backdrop-blur-xs select-none z-10">
          <div className="flex items-center gap-2">
            <h1 className="text-xs font-semibold text-neutral-800 tracking-tight">
              {title}
            </h1>
            {routeInfo?.subtitle && (
              <span className="text-[11px] text-neutral-400 hidden sm:inline">
                — {routeInfo.subtitle}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 titlebar-no-drag">
            {isActive && (
              <button
                type="button"
                onClick={() => {
                  if (isOpen) {
                    if (isElectron && electronAPI) {
                      try {
                        electronAPI.closeBrowserView();
                      } catch {}
                    }
                    closePanel();
                  } else {
                    openBrowser();
                  }
                }}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs font-medium transition-colors cursor-pointer pointer-events-auto ${
                  isOpen
                    ? "bg-neutral-900 text-white"
                    : "bg-neutral-100 hover:bg-neutral-200 text-neutral-700"
                }`}
              >
                <Globe size={13} />
                <span>{isOpen ? "Hide Browser" : "Browser View"}</span>
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse ml-0.5" />
              </button>
            )}
          </div>
        </header>

        {/* Main Scrollable Content */}
        <main className="flex-1 overflow-y-auto px-8 py-6">
          <div className="max-w-5xl mx-auto w-full">
            <Outlet />
          </div>
        </main>
      </div>

      {/* Embedded Live Browser Panel (Artifact style) */}
      <BrowserPanel />
    </div>
  );
}


