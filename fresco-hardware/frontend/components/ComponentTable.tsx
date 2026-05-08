"use client";

import { useCallback, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  correctComponent,
  fetchMfrCodes,
  fetchFinishCodes,
  type HardwareSet,
  type Component,
} from "@/app/api";

interface Props {
  set: HardwareSet;
  docId: string;
}

function cellConfidenceClass(confidence?: number): string {
  if (confidence === undefined || confidence === null) return "";
  if (confidence >= 0.8) return "bg-green-50";
  if (confidence >= 0.5) return "bg-yellow-50";
  return "bg-red-50";
}

function EditableCell({
  value,
  confidence,
  onSave,
  options,
}: {
  value: string;
  confidence?: number;
  onSave: (val: string) => void;
  options?: Record<string, string>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);

  const commit = useCallback(() => {
    setEditing(false);
    if (draft !== value) onSave(draft);
  }, [draft, value, onSave]);

  if (editing) {
    if (options) {
      return (
        <select
          className="w-full text-sm border rounded px-1 py-0.5"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          autoFocus
        >
          <option value="">--</option>
          {Object.entries(options).map(([code, name]) => (
            <option key={code} value={code}>
              {code} - {name}
            </option>
          ))}
        </select>
      );
    }
    return (
      <input
        className="w-full text-sm border rounded px-1 py-0.5"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && commit()}
        autoFocus
      />
    );
  }

  return (
    <span
      className={`block px-1 py-0.5 cursor-pointer rounded hover:ring-1 hover:ring-blue-300 ${cellConfidenceClass(confidence)}`}
      onClick={() => {
        setDraft(value);
        setEditing(true);
      }}
    >
      {value || <span className="text-gray-300">-</span>}
    </span>
  );
}

export default function ComponentTable({ set, docId }: Props) {
  const queryClient = useQueryClient();

  const { data: mfrRef } = useQuery({
    queryKey: ["ref", "mfr"],
    queryFn: fetchMfrCodes,
    staleTime: Infinity,
  });
  const { data: finishRef } = useQuery({
    queryKey: ["ref", "finish"],
    queryFn: fetchFinishCodes,
    staleTime: Infinity,
  });

  const handleSave = useCallback(
    async (comp: Component, field: string, value: string) => {
      await correctComponent(set.id, comp.idx, field, value);
      queryClient.invalidateQueries({ queryKey: ["document", docId] });
    },
    [set.id, docId, queryClient],
  );

  return (
    <div className="overflow-auto">
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="bg-gray-100 text-left text-xs text-gray-600">
            <th className="px-2 py-1.5 w-10">#</th>
            <th className="px-2 py-1.5 w-10">Qty</th>
            <th className="px-2 py-1.5">Description</th>
            <th className="px-2 py-1.5 w-28">Catalog #</th>
            <th className="px-2 py-1.5 w-16">Mfr</th>
            <th className="px-2 py-1.5 w-16">Finish</th>
            <th className="px-2 py-1.5 w-24">Notes</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {set.components.map((c) => (
            <tr key={c.idx} className="hover:bg-gray-50">
              <td className="px-2 py-1 text-gray-400">{c.idx}</td>
              <td className="px-2 py-1">{c.qty ?? "-"}</td>
              <td className="px-2 py-1">
                <EditableCell
                  value={c.description}
                  confidence={c.confidences?.description}
                  onSave={(v) => handleSave(c, "description", v)}
                />
              </td>
              <td className="px-2 py-1">
                <EditableCell
                  value={c.catalog_number || ""}
                  confidence={c.confidences?.catalog_number}
                  onSave={(v) => handleSave(c, "catalog_number", v)}
                />
              </td>
              <td className="px-2 py-1">
                <EditableCell
                  value={c.mfr || ""}
                  confidence={c.confidences?.mfr}
                  onSave={(v) => handleSave(c, "mfr", v)}
                  options={mfrRef?.codes}
                />
              </td>
              <td className="px-2 py-1">
                <EditableCell
                  value={c.finish || ""}
                  confidence={c.confidences?.finish}
                  onSave={(v) => handleSave(c, "finish", v)}
                  options={finishRef?.codes}
                />
              </td>
              <td className="px-2 py-1">
                <EditableCell
                  value={c.notes || ""}
                  confidence={c.confidences?.notes}
                  onSave={(v) => handleSave(c, "notes", v)}
                />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
