"use client";

import { useCallback, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { reextractSet } from "@/app/api";

interface Props {
  setId: number;
  docId: string;
}

export default function ReextractButton({ setId, docId }: Props) {
  const [open, setOpen] = useState(false);
  const [hint, setHint] = useState("");
  const [loading, setLoading] = useState(false);
  const queryClient = useQueryClient();

  const handleSubmit = useCallback(async () => {
    setLoading(true);
    try {
      await reextractSet(setId, hint);
      queryClient.invalidateQueries({ queryKey: ["document", docId] });
      setOpen(false);
      setHint("");
    } catch (e) {
      alert(`Re-extract failed: ${e}`);
    } finally {
      setLoading(false);
    }
  }, [setId, hint, docId, queryClient]);

  if (!open) {
    return (
      <button
        className="text-xs px-2 py-1 rounded border border-orange-300 text-orange-600 hover:bg-orange-50"
        onClick={() => setOpen(true)}
      >
        Re-extract
      </button>
    );
  }

  return (
    <div className="border rounded p-3 bg-orange-50 space-y-2">
      <p className="text-sm font-medium text-orange-800">Re-extract this set</p>
      <textarea
        className="w-full text-sm border rounded p-2 h-20"
        placeholder="Optional hint for the model (e.g. 'Format B with implicit columns')"
        value={hint}
        onChange={(e) => setHint(e.target.value)}
      />
      <div className="flex gap-2">
        <button
          className="text-sm px-3 py-1 rounded bg-orange-500 text-white hover:bg-orange-600 disabled:opacity-50"
          onClick={handleSubmit}
          disabled={loading}
        >
          {loading ? "Sending..." : "Submit"}
        </button>
        <button
          className="text-sm px-3 py-1 rounded border text-gray-600 hover:bg-gray-100"
          onClick={() => setOpen(false)}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
