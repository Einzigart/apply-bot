import { NavLink } from "react-router";
import {
  LayoutDashboard,
  Briefcase,
  Send,
  Terminal,
  User,
  Sliders,
  Bot,
} from "lucide-react";
import { cn } from "../../lib/utils";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/jobs", label: "Jobs", icon: Briefcase },
  { to: "/applications", label: "Applications", icon: Send },
  { to: "/runs", label: "Runs", icon: Terminal },
  { to: "/profile", label: "Profile", icon: User },
  { to: "/settings", label: "Settings", icon: Sliders },
];

export function Sidebar() {
  return (
    <aside className="w-56 shrink-0 bg-[#fbfbfa] text-neutral-600 flex flex-col h-screen border-r border-neutral-200/80 select-none">
      {/* Window Drag Header / Traffic Light Area (Codex / macOS style) */}
      <div className="h-10 shrink-0 titlebar-drag flex items-center justify-end px-3" />

      {/* Brand Header */}
      <div className="px-3.5 pt-1 pb-3 flex items-center gap-2">
        <div className="w-6 h-6 rounded-md bg-neutral-900 text-white flex items-center justify-center shadow-xs">
          <Bot className="w-3.5 h-3.5 stroke-[2]" />
        </div>
        <span className="font-semibold text-sm tracking-tight text-neutral-900">
          Apply Bot
        </span>
      </div>

      {/* Nav items */}
      <nav className="flex-1 px-2.5 py-1 space-y-0.5 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 px-2.5 py-1.5 rounded-md text-sm font-medium transition-colors duration-120",
                  isActive
                    ? "bg-neutral-200/70 text-neutral-900 shadow-2xs font-semibold"
                    : "text-neutral-600 hover:text-neutral-900 hover:bg-neutral-200/40"
                )
              }
            >
              <Icon className="w-4 h-4 shrink-0 stroke-[1.75]" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      {/* Footer Info */}
      <div className="p-3 border-t border-neutral-200/80 text-xs text-neutral-400 flex items-center justify-between">
        <span>v0.1.0</span>
        <span className="text-[11px] font-mono text-neutral-400">localhost</span>
      </div>
    </aside>
  );
}


