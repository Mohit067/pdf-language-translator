"use client";

import React from "react";
import { Briefcase, BookOpen, MessageSquare, GraduationCap, Feather, Check } from "lucide-react";

export interface ToneOption {
  id: string;
  name: string;
  nativeName: string;
  description: string;
  icon: React.ComponentType<{ className?: string }>;
}

export const TONE_OPTIONS: ToneOption[] = [
  {
    id: "Professional",
    name: "Professional",
    nativeName: "पेशेवर / औपचारिक",
    description: "Formal, dignified, and clear. Ideal for official papers, reports, legal and business documents.",
    icon: Briefcase,
  },
  {
    id: "Literary",
    name: "Literary",
    nativeName: "साहित्यिक / कथात्मक",
    description: "Poetic, narrative flow, and expressive phrasing. Ideal for books, novels, history, and philosophy.",
    icon: BookOpen,
  },
  {
    id: "Conversational",
    name: "Conversational",
    nativeName: "बातचीत / सहज",
    description: "Natural everyday spoken style. Ideal for emails, messages, dialogues, and modern articles.",
    icon: MessageSquare,
  },
  {
    id: "Academic",
    name: "Academic",
    nativeName: "शैक्षणिक / तकनीकी",
    description: "Intellectually precise terminology and exact definitions. Ideal for research papers and textbooks.",
    icon: GraduationCap,
  },
  {
    id: "Simple",
    name: "Simple",
    nativeName: "सरल भाषा / आसान",
    description: "Easy everyday words, short clean sentences, minimal jargon. Ideal for general audiences and fast reading.",
    icon: Feather,
  },
];

interface ToneSelectorProps {
  selectedTone: string;
  onSelectTone: (tone: string) => void;
  disabled?: boolean;
}

export function ToneSelector({ selectedTone, onSelectTone, disabled }: ToneSelectorProps) {
  return (
    <div className="space-y-3" role="radiogroup" aria-label="Translation tone">
      <p className="text-sm text-neutral-600">
        Choose how you want the translated text to sound (style & vocabulary):
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {TONE_OPTIONS.map((tone) => {
          const Icon = tone.icon;
          const isSelected = selectedTone === tone.id;
          return (
            <button
              key={tone.id}
              type="button"
              role="radio"
              aria-checked={isSelected}
              disabled={disabled}
              onClick={() => onSelectTone(tone.id)}
              className={`relative flex flex-col p-4 rounded-xl border text-left transition-all cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-600 ${
                isSelected
                  ? "border-emerald-600 bg-emerald-50/70 shadow-xs ring-1 ring-emerald-600"
                  : "border-neutral-200 bg-white hover:border-neutral-300 hover:bg-neutral-50/60"
              } ${disabled ? "opacity-60 cursor-not-allowed" : ""}`}
            >
              <div className="flex items-center justify-between w-full mb-1.5">
                <div className="flex items-center gap-2.5">
                  <span
                    className={`p-1.5 rounded-lg ${
                      isSelected ? "bg-emerald-600 text-white" : "bg-neutral-100 text-neutral-600"
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                  </span>
                  <span className="font-semibold text-neutral-900 text-sm">{tone.name}</span>
                </div>
                {isSelected && (
                  <span className="w-5 h-5 rounded-full bg-emerald-600 text-white flex items-center justify-center shrink-0">
                    <Check className="w-3.5 h-3.5" />
                  </span>
                )}
              </div>
              <span className="text-xs font-medium text-emerald-800 mb-1">{tone.nativeName}</span>
              <p className="text-xs text-neutral-500 leading-relaxed">{tone.description}</p>
            </button>
          );
        })}
      </div>
    </div>
  );
}

