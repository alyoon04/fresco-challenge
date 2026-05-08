"use client";

import { useMemo, useState } from "react";
import type { HardwareSet } from "@/app/api";

interface Props {
  sets: HardwareSet[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

function getSetDisplay(s: HardwareSet): { title: string; subtitle: string | null } {
  const desc = s.description || "";
  if (!desc) return { title: s.set_number, subtitle: null };
  if (desc.length <= 80) return { title: desc, subtitle: null };
  return { title: desc.slice(0, 75) + "\u2026", subtitle: null };
}

function ConfidencePill({ confidence }: { confidence: number }) {
  const pct = Math.round(confidence * 100);
  let styles = "bg-emerald-50 text-emerald-700 border-emerald-200";
  if (confidence < 0.5) styles = "bg-red-50 text-red-700 border-red-200";
  else if (confidence < 0.8) styles = "bg-amber-50 text-amber-700 border-amber-200";

  return (
    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${styles}`}>
      {pct}%
    </span>
  );
}

export default function SetList({ sets, selectedId, onSelect }: Props) {
  const [query, setQuery] = useState("");

  const sorted = useMemo(() => {
    const seen = new Set<string>();
    const deduped = sets.filter((s) => {
      if (seen.has(s.set_number)) return false;
      seen.add(s.set_number);
      return true;
    });
    return deduped.sort((a, b) => {
      const aLoc = a.locations[0];
      const bLoc = b.locations[0];
      if (!aLoc && !bLoc) return 0;
      if (!aLoc) return 1;
      if (!bLoc) return -1;
      if (aLoc.page_num !== bLoc.page_num) return aLoc.page_num - bLoc.page_num;
      const aY = aLoc.bbox?.[1] ?? aLoc.line_start ?? 0;
      const bY = bLoc.bbox?.[1] ?? bLoc.line_start ?? 0;
      return aY - bY;
    });
  }, [sets]);

  const filtered = useMemo(() => {
    if (!query.trim()) return sorted;
    const q = query.toLowerCase();
    return sorted.filter(
      (s) =>
        s.set_number.toLowerCase().includes(q) ||
        s.description?.toLowerCase().includes(q) ||
        s.components.some(
          (c) =>
            c.description.toLowerCase().includes(q) ||
            c.catalog_number?.toLowerCase().includes(q) ||
            c.mfr?.toLowerCase().includes(q),
        ),
    );
  }, [sorted, query]);

  if (sets.length === 0) {
    return <p className="p-5 text-cream-400 text-sm">No hardware sets extracted yet.</p>;
  }

  return (
    <div className="flex flex-col flex-1 min-h-0">
      {/* Search */}
      <div className="px-4 py-2.5 border-b border-cream-200">
        <input
          type="text"
          placeholder="Search sets..."
          className="w-full text-xs border border-cream-300 rounded-lg px-3 py-2 bg-cream-50
                     placeholder-cream-400
                     focus:outline-none focus:ring-2 focus:ring-terra-300 focus:border-terra-400
                     transition-shadow duration-150"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {filtered.length === 0 ? (
        <p className="p-5 text-cream-400 text-sm">No matches for &ldquo;{query}&rdquo;</p>
      ) : (
        <ul className="overflow-auto flex-1">
          {filtered.map((s) => {
            const { title } = getSetDisplay(s);
            const isSelected = selectedId === s.id;
            return (
              <li
                key={s.id}
                className={`px-4 py-3 cursor-pointer border-b border-cream-200
                           transition-all duration-150
                           ${isSelected
                             ? "bg-terra-50 border-l-[3px] border-l-terra-500"
                             : "hover:bg-cream-100 border-l-[3px] border-l-transparent"
                           }`}
                onClick={() => onSelect(s.id)}
              >
                <div className="flex items-start gap-2">
                  <span className={`text-sm leading-snug ${isSelected ? "font-semibold text-cream-900" : "font-medium text-cream-800"}`}>
                    {title}
                  </span>
                  {s.is_not_used && (
                    <span className="text-[10px] font-medium bg-cream-200 text-cream-600 border border-cream-300 px-1.5 py-0.5 rounded shrink-0 mt-0.5">
                      NOT USED
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2 mt-1.5">
                  <span className="text-[11px] text-cream-500">
                    {s.components.length} component{s.components.length !== 1 ? "s" : ""}
                  </span>
                  <ConfidencePill confidence={s.overall_confidence} />
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
