import { Outlet, useLocation, useParams } from "react-router";
import { Sidebar } from "./sidebar";

const ROUTE_TITLES: Record<string, { title: string; subtitle?: string }> = {
  "/": { title: "Dashboard", subtitle: "Overview and recent runs" },
  "/jobs": { title: "Jobs", subtitle: "Discovered and evaluated positions" },
  "/applications": { title: "Applications", subtitle: "Application history" },
  "/runs": { title: "Runs", subtitle: "Execution pipeline runner and status" },
  "/profile": { title: "Profile", subtitle: "Job applicant background and preferences" },
  "/settings": { title: "Settings", subtitle: "LLM, filters, salary, and system preferences" },
};

export function AppLayout() {
  const location = useLocation();
  const params = useParams();

  let routeInfo = ROUTE_TITLES[location.pathname];
  if (!routeInfo && location.pathname.startsWith("/runs/")) {
    routeInfo = { title: `Run #${params.id || ""}`, subtitle: "Execution logs and details" };
  }
  const title = routeInfo?.title ?? "Apply Bot";

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-white text-neutral-900 font-sans">
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
        </header>

        {/* Main Scrollable Content */}
        <main className="flex-1 overflow-y-auto px-8 py-6">
          <div className="max-w-5xl mx-auto w-full">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}

