"use client";

import { useMemo, useState } from "react";
import type { HardwareSet } from "@/app/api";

interface Props {
  sets: HardwareSet[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}

/**
 * Extract a display title and subtitle from a hardware set.
 * Adaptively picks the most identifying text from the description.
 */
function getSetDisplay(s: HardwareSet): { title: string; subtitle: string | null } {
  const desc = s.description || "";
  if (!desc) return { title: s.set_number, subtitle: null };
  if (desc.length <= 80) return { title: desc, subtitle: null };
  return { title: desc.slice(0, 75) + "…", subtitle: null };
}

function confidencePill(confidence: number) {
  let bg = "bg-green-100 text-green-800";
  if (confidence < 0.5) bg = "bg-red-100 text-red-800";
  else if (confidence < 0.8) bg = "bg-yellow-100 text-yellow-800";

  return (
    <span className={`text-xs px-1.5 py-0.5 rounded-full ${bg}`}>
      {Math.round(confidence * 100)}%
    </span>
  );
}

export default function SetList({ sets, selectedId, onSelect }: Props) {
  const [query, setQuery] = useState("");

  // Deduplicate by set_number (keep first by id, i.e. earliest extraction)
  // then sort by PDF order (page, then vertical position)
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
  }, [sets, query]);

  if (sets.length === 0) {
    return <p className="p-4 text-gray-400 text-sm">No hardware sets extracted yet.</p>;
  }

  return (
    <div className="flex flex-col h-full">
      <div className="px-3 py-2 border-b">
        <input
          type="text"
          placeholder="Search doors, components, mfr..."
          className="w-full text-sm border rounded px-2 py-1.5"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      {filtered.length === 0 ? (
        <p className="p-4 text-gray-400 text-sm">No matches for &ldquo;{query}&rdquo;</p>
      ) : (
    <ul className="divide-y overflow-auto flex-1">
      {filtered.map((s) => (
        <li
          key={s.id}
          className={`px-3 py-2 cursor-pointer hover:bg-blue-50 transition-colors ${
            selectedId === s.id ? "bg-blue-100 border-l-4 border-blue-500" : ""
          }`}
          onClick={() => onSelect(s.id)}
        >
          {(() => {
            const { title, subtitle } = getSetDisplay(s);
            return (
              <>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-gray-800">{title}</span>
                  {s.is_not_used && (
                    <span className="text-xs bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded shrink-0">NOT USED</span>
                  )}
                </div>
                {subtitle && (
                  <p className="text-xs text-gray-500 mt-0.5 truncate">{subtitle}</p>
                )}
                <div className="flex items-center gap-2 mt-0.5">
                  <span className="text-xs text-gray-400">
                    {s.components.length} component{s.components.length !== 1 ? "s" : ""}
                  </span>
                  {confidencePill(s.overall_confidence)}
                </div>
              </>
            );
          })()}
        </li>
      ))}
    </ul>
      )}
    </div>
  );
}
