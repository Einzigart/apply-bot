import { ReactNode, useState, useRef, useEffect } from "react";
import { CircleHelp } from "lucide-react";
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
    "inline-flex items-center justify-center font-medium squircle whitespace-nowrap transition-all duration-140 active:scale-[0.97] cursor-pointer disabled:opacity-50 disabled:pointer-events-none disabled:active:scale-100";

  const variants = {
    primary: "bg-neutral-900 hover:bg-neutral-800 text-white shadow-2xs",
    secondary: "bg-neutral-100 hover:bg-neutral-200 text-neutral-900",
    danger: "bg-red-50 hover:bg-red-100 text-red-700 border border-red-200/80",
    ghost: "hover:bg-neutral-100 text-neutral-600 hover:text-neutral-900",
    outline: "border border-neutral-200 hover:bg-neutral-50 text-neutral-700 shadow-2xs",
  };

  const sizes = {
    sm: "text-xs px-3 py-1.5 gap-1.5 rounded-xl",
    md: "text-sm px-3.5 py-2 gap-2 rounded-xl",
    lg: "text-base px-4 py-2.5 gap-2.5 rounded-xl",
    icon: "p-2 rounded-xl",
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
        "inline-flex items-center px-2.5 py-0.5 rounded-xl text-xs font-medium border",
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
        "bg-white rounded-xl border border-neutral-200/80 shadow-2xs",
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
      <rect width="16" height="12" x="4" y="8" rx="3" />
      <path d="M2 14h2" />
      <path d="M20 14h2" />
      <path d="M15 13v2" />
      <path d="M9 13v2" />
    </svg>
  );
}

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  side?: "top" | "bottom" | "left" | "right" | "auto";
  align?: "center" | "start" | "end";
  className?: string;
}

export function Tooltip({
  content,
  children,
  side = "top",
  align = "center",
  className,
}: TooltipProps) {
  const [isOpen, setIsOpen] = useState(false);
  const triggerRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [actualSide, setActualSide] = useState<"top" | "bottom">(side === "bottom" ? "bottom" : "top");
  const [actualAlign, setActualAlign] = useState<"center" | "start" | "end">(align);

  useEffect(() => {
    if (isOpen && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      // If close to top of viewport or card container, flip to bottom
      if (rect.top < 110) {
        setActualSide("bottom");
      } else {
        setActualSide("top");
      }

      // Check horizontal edges to prevent clipping on right/left boundaries
      if (rect.left + 220 > window.innerWidth) {
        setActualAlign("end");
      } else if (rect.left < 100) {
        setActualAlign("start");
      } else {
        setActualAlign(align);
      }
    }
  }, [isOpen, side, align]);

  const sideClasses = actualSide === "top"
    ? "bottom-full mb-2"
    : "top-full mt-2";

  const alignClasses = actualAlign === "center"
    ? "left-1/2 -translate-x-1/2"
    : actualAlign === "end"
    ? "right-0 translate-x-1"
    : "left-0 -translate-x-1";

  return (
    <div
      ref={triggerRef}
      className="relative inline-flex items-center"
      onMouseEnter={() => setIsOpen(true)}
      onMouseLeave={() => setIsOpen(false)}
      onFocus={() => setIsOpen(true)}
      onBlur={() => setIsOpen(false)}
    >
      {children}
      {isOpen && (
        <div
          ref={tooltipRef}
          role="tooltip"
          className={cn(
            "absolute z-50 px-2.5 py-1.5 text-xs text-neutral-100 bg-neutral-900 border border-neutral-700/80 rounded-xl shadow-xl pointer-events-none whitespace-normal w-60 max-w-[280px] transition-all duration-140 font-normal leading-relaxed text-left squircle",
            sideClasses,
            alignClasses,
            className
          )}
        >
          {content}
        </div>
      )}
    </div>
  );
}

export function InfoTooltip({
  text,
  side = "top",
  align = "center",
  className,
}: {
  text: ReactNode;
  side?: "top" | "bottom" | "left" | "right";
  align?: "center" | "start" | "end";
  className?: string;
}) {
  return (
    <Tooltip content={text} side={side} align={align} className={className}>
      <button
        type="button"
        aria-label="More information"
        className="inline-flex items-center justify-center p-0.5 rounded-full text-neutral-400 hover:text-neutral-700 hover:bg-neutral-100 transition-colors cursor-help focus:outline-hidden focus:ring-1 focus:ring-neutral-400"
      >
        <CircleHelp className="w-3.5 h-3.5 stroke-[1.75]" />
      </button>
    </Tooltip>
  );
}




