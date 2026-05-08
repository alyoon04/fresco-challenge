"use client";

import type { HardwareSet } from "@/app/api";

interface Props {
  sets: HardwareSet[];
  selectedId: number | null;
  onSelect: (id: number) => void;
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
  if (sets.length === 0) {
    return <p className="p-4 text-gray-400 text-sm">No hardware sets extracted yet.</p>;
  }

  return (
    <ul className="divide-y overflow-auto">
      {sets.map((s) => (
        <li
          key={s.id}
          className={`px-3 py-2 cursor-pointer hover:bg-blue-50 transition-colors ${
            selectedId === s.id ? "bg-blue-100 border-l-4 border-blue-500" : ""
          }`}
          onClick={() => onSelect(s.id)}
        >
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-semibold">{s.set_number}</span>
            {s.is_not_used && (
              <span className="text-xs bg-gray-200 text-gray-600 px-1.5 py-0.5 rounded">NOT USED</span>
            )}
            {confidencePill(s.overall_confidence)}
          </div>
          {s.description && (
            <p className="text-xs text-gray-500 mt-0.5 truncate">{s.description}</p>
          )}
          <p className="text-xs text-gray-400 mt-0.5">
            {s.components.length} component{s.components.length !== 1 ? "s" : ""}
          </p>
        </li>
      ))}
    </ul>
  );
}
