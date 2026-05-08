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
        className="text-xs font-medium px-3 py-1.5 rounded-lg
                   border border-terra-300 text-terra-600 bg-white
                   transition-all duration-150
                   hover:bg-terra-50 hover:border-terra-400
                   active:scale-[0.97]
                   shrink-0"
        onClick={() => setOpen(true)}
      >
        Re-extract
      </button>
    );
  }

  return (
    <div className="border border-terra-200 rounded-xl p-4 bg-terra-50/50 space-y-3 animate-fade-in">
      <p className="text-sm font-medium text-cream-900">Re-extract this set</p>
      <textarea
        className="w-full text-xs border border-cream-300 rounded-lg p-2.5 h-20
                   bg-white placeholder-cream-400 resize-none
                   focus:outline-none focus:ring-2 focus:ring-terra-300 focus:border-terra-400
                   transition-shadow duration-150"
        placeholder="Optional hint (e.g. 'Format B with implicit columns')"
        value={hint}
        onChange={(e) => setHint(e.target.value)}
      />
      <div className="flex gap-2">
        <button
          className="text-xs font-medium px-4 py-2 rounded-lg
                     border border-cream-900 bg-cream-900 text-cream-100
                     transition-all duration-150
                     hover:bg-cream-800 hover:border-cream-800
                     active:scale-[0.97]
                     disabled:opacity-50 disabled:active:scale-100"
          onClick={handleSubmit}
          disabled={loading}
        >
          {loading ? "Sending..." : "Submit"}
        </button>
        <button
          className="text-xs font-medium px-4 py-2 rounded-lg
                     border border-cream-300 text-cream-600 bg-white
                     transition-all duration-150
                     hover:bg-cream-100 hover:border-cream-400
                     active:scale-[0.97]"
          onClick={() => setOpen(false)}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
