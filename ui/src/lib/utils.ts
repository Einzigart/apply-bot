import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatCurrency(amount: number | string | undefined | null) {
  if (!amount) return "—";
  const num = typeof amount === "string" ? parseInt(amount.replace(/[^0-9]/g, ""), 10) : amount;
  if (isNaN(num)) return String(amount);
  return new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
  }).format(num);
}
