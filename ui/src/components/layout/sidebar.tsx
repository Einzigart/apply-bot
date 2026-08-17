import { NavLink } from "react-router";
import {
  LayoutDashboard,
  Briefcase,
  Send,
  Terminal,
  User,
  Settings as SettingsIcon,
} from "lucide-react";
import { cn } from "../../lib/utils";
import { ApplyBotIcon } from "../ui/core";

const NAV_ITEMS = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/jobs", label: "Jobs", icon: Briefcase },
  { to: "/applications", label: "Applications", icon: Send },
  { to: "/runs", label: "Runs", icon: Terminal },
  { to: "/profile", label: "Profile", icon: User },
  { to: "/settings", label: "Settings", icon: SettingsIcon },
];

export function Sidebar() {
  return (
    <aside className="w-56 shrink-0 bg-[#fbfbfa] text-neutral-600 flex flex-col h-screen border-r border-neutral-200/80 select-none">
      {/* Window Drag Header / Traffic Light Area (Codex / macOS style) */}
      <div className="h-10 shrink-0 titlebar-drag flex items-center justify-end px-3" />

      {/* Brand Header */}
      <div className="px-3.5 pt-1 pb-3 flex items-center gap-2">
        <div className="w-7 h-7 rounded-xl bg-neutral-900 text-white flex items-center justify-center shadow-xs">
          <ApplyBotIcon className="w-4 h-4" />
        </div>
        <span className="font-semibold text-sm tracking-tight text-neutral-900">
          Apply Bot
        </span>
      </div>

      {/* Nav items */}
      <nav className="flex-1 px-2.5 py-1 space-y-1 overflow-y-auto">
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm font-medium transition-all duration-120",
                  isActive
                    ? "bg-neutral-200/80 text-neutral-900 shadow-2xs font-semibold"
                    : "text-neutral-600 hover:text-neutral-900 hover:bg-neutral-200/50"
                )
              }
            >
              <Icon className="w-4 h-4 shrink-0 stroke-[1.75]" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>
    </aside>
  );
}


