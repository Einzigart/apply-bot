import { useEffect } from "react";
import { Outlet, useLocation, useNavigate, useParams } from "react-router";
import { Sidebar } from "./sidebar";
import { useProfile } from "../../api/hooks";
import { isMacElectron } from "../../lib/utils";

const ROUTE_TITLES: Record<string, string> = {
  "/": "Dashboard",
  "/setup": "Setup wizard",
  "/jobs": "Jobs",
  "/applications": "Applications",
  "/runs": "Runs",
  "/profile": "Profile",
  "/settings": "Settings",
};

export function AppLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const params = useParams();
  const { data: profileData, isLoading: profileLoading } = useProfile();

  useEffect(() => {
    // If profile is not set up and user is on root dashboard, redirect to setup
    if (!profileLoading && profileData && !profileData.has_profile && location.pathname === "/") {
      navigate("/setup", { replace: true });
    }
  }, [profileData, profileLoading, location.pathname, navigate]);

  const isSetupRoute = location.pathname === "/setup";
  const showSidebar = !isSetupRoute && (!profileData || profileData.has_profile || profileLoading);
  const isMac = isMacElectron();

  let title = ROUTE_TITLES[location.pathname];
  if (!title && location.pathname.startsWith("/runs/")) {
    title = `Run #${params.id || ""}`;
  }
  title = title ?? "Apply Bot";

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-white text-neutral-900 font-sans relative">
      {showSidebar && <Sidebar />}
      
      <div className="flex-1 flex flex-col h-screen min-w-0 bg-white">
        {/* Title Bar / Window Header */}
        <header className="h-10 shrink-0 border-b border-neutral-200/80 titlebar-drag flex items-center justify-between px-6 bg-white/80 backdrop-blur-xs select-none z-10">
          <div className="flex items-center gap-2">
            {!showSidebar && isMac && (
              <div className="w-14 shrink-0" />
            )}
            <h1 className="text-xs font-semibold text-neutral-800 tracking-tight">
              {title}
            </h1>
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


