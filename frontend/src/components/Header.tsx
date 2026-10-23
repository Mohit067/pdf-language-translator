"use client";

import React, { useSyncExternalStore } from "react";
import { Languages, Moon, Sun } from "lucide-react";

// Theme state lives on <html class="dark"> (set before paint by the layout script)
function subscribeToTheme(onChange: () => void) {
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => observer.disconnect();
}
const isDarkSnapshot = () => document.documentElement.classList.contains("dark");

export function Header({ onHome }: { onHome?: () => void }) {
  const isDark = useSyncExternalStore(subscribeToTheme, isDarkSnapshot, () => false);

  const toggleTheme = () => {
    const next = !isDark;
    document.documentElement.classList.toggle("dark", next);
    try {
      localStorage.setItem("theme", next ? "dark" : "light");
    } catch {
      // storage unavailable (private mode): theme still applies for this page view
    }
  };

  return (
    <header className="w-full border-b border-neutral-200 bg-white sticky top-0 z-30">
      <div className="max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-10 h-16 flex items-center justify-between">
        <button
          onClick={onHome}
          className="flex items-center gap-3 text-left rounded-lg cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
          aria-label="TransDoc, go to the home page"
        >
          <div className="w-9 h-9 rounded-lg bg-emerald-600 flex items-center justify-center text-white" aria-hidden="true">
            <Languages className="w-5 h-5" />
          </div>
          <div>
            <p className="font-semibold text-neutral-900 text-base leading-tight">TransDoc</p>
            <p className="text-sm text-neutral-500 leading-tight">Document translator</p>
          </div>
        </button>

        <button
          onClick={toggleTheme}
          className="flex items-center gap-2 h-10 px-3 rounded-lg border border-neutral-300 text-sm font-medium text-neutral-700 hover:bg-neutral-100 transition cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600"
          aria-label={isDark ? "Switch to light mode" : "Switch to dark mode"}
        >
          {isDark ? <Sun className="w-4 h-4" aria-hidden="true" /> : <Moon className="w-4 h-4" aria-hidden="true" />}
          <span className="hidden sm:inline">{isDark ? "Light mode" : "Dark mode"}</span>
        </button>
      </div>
    </header>
  );
}
