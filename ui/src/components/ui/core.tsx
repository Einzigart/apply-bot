import { ReactNode } from "react";
import { cn } from "../../lib/utils";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "danger" | "ghost" | "outline";
  size?: "sm" | "md" | "lg" | "icon";
  children: ReactNode;
}

export function Button({
  variant = "primary",
  size = "md",
  className,
  children,
  ...props
}: ButtonProps) {
  const base =
    "inline-flex items-center justify-center font-medium rounded-md transition-all duration-140 active:scale-[0.97] cursor-pointer disabled:opacity-50 disabled:pointer-events-none disabled:active:scale-100";

  const variants = {
    primary: "bg-neutral-900 hover:bg-neutral-800 text-white shadow-2xs",
    secondary: "bg-neutral-100 hover:bg-neutral-200 text-neutral-900",
    danger: "bg-red-50 hover:bg-red-100 text-red-700 border border-red-200/80",
    ghost: "hover:bg-neutral-100 text-neutral-600 hover:text-neutral-900",
    outline: "border border-neutral-200 hover:bg-neutral-50 text-neutral-700 shadow-2xs",
  };

  const sizes = {
    sm: "text-xs px-2.5 py-1.5 gap-1.5",
    md: "text-sm px-3.5 py-1.5 gap-2",
    lg: "text-base px-4 py-2 gap-2.5",
    icon: "p-1.5",
  };

  return (
    <button
      className={cn(base, variants[variant], sizes[size], className)}
      {...props}
    >
      {children}
    </button>
  );
}

export function Badge({
  children,
  variant = "default",
  className,
}: {
  children: ReactNode;
  variant?:
    | "default"
    | "apply"
    | "review"
    | "skip"
    | "running"
    | "danger"
    | "purple"
    | "blue"
    | "amber"
    | "emerald"
    | "neutral";
  className?: string;
}) {
  const variants = {
    default: "bg-neutral-100 text-neutral-600 border-neutral-200/80",
    neutral: "bg-neutral-100 text-neutral-700 border-neutral-200/80",
    apply: "bg-emerald-50 text-emerald-700 border-emerald-200/80",
    review: "bg-amber-50 text-amber-700 border-amber-200/80",
    skip: "bg-neutral-100 text-neutral-500 border-neutral-200/80",
    running: "bg-blue-50 text-blue-700 border-blue-200/80 animate-pulse",
    danger: "bg-red-50 text-red-700 border-red-200/80",
    purple: "bg-purple-50 text-purple-700 border-purple-200/80",
    blue: "bg-sky-50 text-sky-700 border-sky-200/80",
    amber: "bg-amber-50 text-amber-700 border-amber-200/80",
    emerald: "bg-emerald-50 text-emerald-700 border-emerald-200/80",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border",
        variants[variant],
        className
      )}
    >
      {children}
    </span>
  );
}

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "bg-white rounded-lg border border-neutral-200/80 shadow-2xs overflow-hidden",
        className
      )}
    >
      {children}
    </div>
  );
}

export function ApplyBotIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
    >
      <path d="M16 8V6a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v2" />
      <rect width="16" height="12" x="4" y="8" rx="2" />
      <path d="M2 14h2" />
      <path d="M20 14h2" />
      <path d="M15 13v2" />
      <path d="M9 13v2" />
    </svg>
  );
}


