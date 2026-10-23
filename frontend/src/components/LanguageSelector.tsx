"use client";

import React from "react";
import { ArrowLeftRight, ChevronDown } from "lucide-react";

// Names must match what the backend accepts (see backend/config.py INDIC_LANGUAGES)
const LANGUAGES = [
  { name: "English", native: "English" },
  { name: "Hindi", native: "हिन्दी" },
  { name: "Bengali", native: "বাংলা" },
  { name: "Tamil", native: "தமிழ்" },
  { name: "Telugu", native: "తెలుగు" },
  { name: "Marathi", native: "मराठी" },
  { name: "Gujarati", native: "ગુજરાતી" },
  { name: "Kannada", native: "ಕನ್ನಡ" },
  { name: "Malayalam", native: "മലയാളം" },
  { name: "Punjabi", native: "ਪੰਜਾਬੀ" },
  { name: "Odia", native: "ଓଡ଼ିଆ" },
  { name: "Urdu", native: "اردو" },
  { name: "Assamese", native: "অসমীয়া" },
  { name: "Sanskrit", native: "संस्कृतम्" },
  { name: "Maithili", native: "मैथिली" },
  { name: "Nepali", native: "नेपाली" },
  { name: "Konkani", native: "कोंकणी" },
  { name: "Sindhi", native: "سنڌي" },
  { name: "Kashmiri", native: "كٲشُر" },
  { name: "Dogri", native: "डोगरी" },
  { name: "Bodo", native: "बड़ो" },
  { name: "Santali", native: "ᱥᱟᱱᱛᱟᱲᱤ" },
];

interface LanguageSelectorProps {
  sourceLang: string;
  targetLang: string;
  onSourceChange: (lang: string) => void;
  onTargetChange: (lang: string) => void;
  onSwap: () => void;
  disabled?: boolean;
}

function LanguageSelect({ id, label, value, onChange, disabled }: {
  id: string; label: string; value: string; onChange: (v: string) => void; disabled?: boolean;
}) {
  return (
    <div className="flex-1 space-y-1.5">
      <label htmlFor={id} className="block text-sm font-medium text-neutral-700">
        {label}
      </label>
      <div className="relative">
        <select
          id={id}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          className="w-full h-12 pl-4 pr-10 rounded-lg border border-neutral-300 bg-white text-base text-neutral-900 appearance-none cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 disabled:opacity-60"
        >
          {LANGUAGES.map((lang) => (
            <option key={lang.name} value={lang.name}>
              {lang.name === lang.native ? lang.name : `${lang.name} — ${lang.native}`}
            </option>
          ))}
        </select>
        <ChevronDown className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 w-5 h-5 text-neutral-500" aria-hidden="true" />
      </div>
    </div>
  );
}

export function LanguageSelector({
  sourceLang,
  targetLang,
  onSourceChange,
  onTargetChange,
  onSwap,
  disabled,
}: LanguageSelectorProps) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-end gap-3">
      <LanguageSelect id="source-lang" label="From (the document's language)" value={sourceLang} onChange={onSourceChange} disabled={disabled} />
      <button
        type="button"
        onClick={onSwap}
        disabled={disabled}
        className="self-center sm:self-auto h-12 px-3 rounded-lg border border-neutral-300 bg-white text-neutral-700 hover:bg-neutral-100 flex items-center justify-center gap-2 text-sm cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 disabled:opacity-50"
        aria-label="Swap the two languages"
        title="Swap the two languages"
      >
        <ArrowLeftRight className="w-5 h-5 rotate-90 sm:rotate-0" aria-hidden="true" />
        <span className="sm:hidden">Swap</span>
      </button>
      <LanguageSelect id="target-lang" label="To (the language you want)" value={targetLang} onChange={onTargetChange} disabled={disabled} />
    </div>
  );
}
