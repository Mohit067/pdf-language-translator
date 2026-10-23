import * as React from "react";
import { cn } from "@/lib/utils";

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "default" | "secondary" | "outline" | "ghost" | "destructive" | "subtle";
  size?: "default" | "sm" | "lg" | "icon";
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", ...props }, ref) => {
    const baseStyles =
      "inline-flex items-center justify-center whitespace-nowrap rounded-lg text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 select-none cursor-pointer";

    // Dark mode is handled by the palette remap in globals.css, so no dark: variants here
    const variantStyles = {
      default: "bg-neutral-900 text-neutral-50 shadow-sm hover:bg-neutral-800",
      secondary: "bg-neutral-100 text-neutral-900 hover:bg-neutral-200",
      outline: "border border-neutral-300 bg-white text-neutral-800 hover:bg-neutral-50 hover:text-neutral-900",
      ghost: "hover:bg-neutral-100 hover:text-neutral-900",
      subtle: "bg-neutral-100/80 text-neutral-800 hover:bg-neutral-200/80",
      destructive: "bg-red-600 text-white shadow-sm hover:bg-red-700",
    };

    const sizeStyles = {
      default: "h-9 px-4 py-2",
      sm: "h-8 rounded-md px-3 text-xs",
      lg: "h-11 rounded-lg px-6 text-base",
      icon: "h-9 w-9 p-0",
    };

    return (
      <button
        ref={ref}
        className={cn(baseStyles, variantStyles[variant], sizeStyles[size], className)}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button };
