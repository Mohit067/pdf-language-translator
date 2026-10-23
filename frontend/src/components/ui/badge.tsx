import * as React from "react";
import { cn } from "@/lib/utils";

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "secondary" | "outline" | "success" | "warning";
}

function Badge({ className, variant = "default", ...props }: BadgeProps) {
  const variantStyles = {
    default: "bg-neutral-900 text-neutral-50 hover:bg-neutral-800 dark:bg-neutral-50 dark:text-neutral-900",
    secondary: "bg-neutral-100 text-neutral-800 dark:bg-neutral-800 dark:text-neutral-200",
    outline: "text-neutral-700 border border-neutral-200 dark:text-neutral-300 dark:border-neutral-800",
    success: "bg-emerald-50 text-emerald-700 border border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800/60",
    warning: "bg-amber-50 text-amber-800 border border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800/60",
  };

  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium tracking-tight transition-colors",
        variantStyles[variant],
        className
      )}
      {...props}
    />
  );
}

export { Badge };
