"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchDocument, cancelDocument, type HardwareSet } from "@/app/api";
import PdfViewer from "@/components/PdfViewer";
import SetList from "@/components/SetList";
import ComponentTable from "@/components/ComponentTable";
import ReextractButton from "@/components/ReextractButton";

function StatusDot({ status }: { status: string }) {
  if (status === "done") return <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />;
  if (status === "failed") return <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />;
  if (status === "cancelled") return <span className="w-2 h-2 rounded-full bg-gray-400 inline-block" />;
  return <span className="w-2 h-2 rounded-full bg-amber-500 inline-block animate-pulse-soft" />;
}

export default function DocumentPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const [selectedSetId, setSelectedSetId] = useState<number | null>(null);
  const [targetPage, setTargetPage] = useState<number | null>(null);
  const scrollKeyRef = useRef(0);
  const [scrollKey, setScrollKey] = useState(0);
  const [cancelling, setCancelling] = useState(false);
  const queryClient = useQueryClient();

  const { data: doc, isLoading, error } = useQuery({
    queryKey: ["document", id],
    queryFn: () => fetchDocument(id),
  });

  useEffect(() => {
    const status = doc?.status;
    if (status === "done" || status === "failed" || status === "cancelled") return;

    const wsBase = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000")
      .replace(/^http/, "ws");
    const ws = new WebSocket(`${wsBase}/ws/documents/${id}`);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      queryClient.invalidateQueries({ queryKey: ["document", id] });
      if (data.status === "done" || data.status === "failed" || data.status === "cancelled") {
        ws.close();
      }
    };

    ws.onerror = () => ws.close();

    return () => {
      if (ws.readyState <= WebSocket.OPEN) ws.close();
    };
  }, [id, doc?.status, queryClient]);

  const handleCancel = useCallback(async () => {
    setCancelling(true);
    try {
      await cancelDocument(id);
      queryClient.invalidateQueries({ queryKey: ["document", id] });
    } catch (e) {
      console.error("Cancel failed:", e);
    } finally {
      setCancelling(false);
    }
  }, [id, queryClient]);

  const handleSelectSet = useCallback((setId: number) => {
    setSelectedSetId(setId);
    const sets = doc?.sets ?? [];
    const set = sets.find((s) => s.id === setId);
    if (set && set.locations.length > 0) {
      // page_num is 1-indexed from backend, matches PDF viewer
      const firstPage = Math.min(...set.locations.map((l) => l.page_num));
      console.log(`[DocPage] Set ${set.set_number}: locations=${JSON.stringify(set.locations.map(l => l.page_num))}, scrolling to page ${firstPage}`);
      scrollKeyRef.current += 1;
      setTargetPage(firstPage);
      setScrollKey(scrollKeyRef.current);
    }
  }, [doc?.sets]);

  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center bg-cream-100">
        <p className="text-cream-500 text-sm">Loading document...</p>
      </div>
    );
  }
  if (error) {
    return (
      <div className="h-screen flex items-center justify-center bg-cream-100">
        <p className="text-red-600 text-sm">Error: {String(error)}</p>
      </div>
    );
  }
  if (!doc) {
    return (
      <div className="h-screen flex items-center justify-center bg-cream-100">
        <p className="text-cream-500 text-sm">Document not found</p>
      </div>
    );
  }

  const selectedSet = doc.sets.find((s) => s.id === selectedSetId) ?? null;

  return (
    <div className="h-screen flex flex-col bg-cream-100">
      {/* Header */}
      <header className="px-5 py-3 border-b border-cream-200 bg-cream-50 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <a
            href="/"
            className="text-sm text-cream-600 border border-cream-300 rounded-lg px-3 py-1.5
                       transition-all duration-150
                       hover:border-cream-400 hover:text-cream-800 hover:bg-cream-100
                       active:scale-[0.97]"
          >
            &larr; Back
          </a>
          <div>
            <h1 className="text-base font-semibold text-cream-900 leading-tight">
              {doc.filename}
            </h1>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-xs text-cream-500">{doc.page_count} pages</span>
              <span className="text-cream-300">&middot;</span>
              <div className="flex items-center gap-1.5">
                <StatusDot status={doc.status} />
                <span className="text-xs text-cream-600">{doc.status}</span>
              </div>
              {doc.sets.length > 0 && (
                <>
                  <span className="text-cream-300">&middot;</span>
                  <span className="text-xs text-cream-500">{doc.sets.length} sets</span>
                </>
              )}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {(doc.status === "processing" || doc.status === "uploaded") && (
            <button
              onClick={handleCancel}
              disabled={cancelling}
              className="text-sm text-red-600 border border-red-300 rounded-lg px-3 py-1.5
                         transition-all duration-150
                         hover:bg-red-50 hover:border-red-400
                         active:scale-[0.97]
                         disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {cancelling ? "Stopping..." : "Stop Processing"}
            </button>
          )}
          {doc.error_message && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-1.5 max-w-md truncate">
              {doc.error_message}
            </p>
          )}
        </div>
      </header>

      {/* Three-pane layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: PDF viewer */}
        <div className="w-1/2 border-r border-cream-200">
          <PdfViewer
            docId={id}
            pageCount={doc.page_count}
            targetPage={targetPage}
            scrollKey={scrollKey}
          />
        </div>

        {/* Center: Set list */}
        <div className="w-1/4 border-r border-cream-200 bg-cream-50 overflow-auto flex flex-col">
          <div className="px-4 py-3 border-b border-cream-200">
            <h2 className="text-xs font-medium uppercase tracking-wider text-cream-500">
              Hardware Sets
            </h2>
          </div>
          <SetList sets={doc.sets} selectedId={selectedSetId} onSelect={handleSelectSet} />
        </div>

        {/* Right: Component table + re-extract */}
        <div className="w-1/4 bg-cream-50 overflow-auto flex flex-col">
          {selectedSet ? (
            <>
              <div className="px-4 py-3 border-b border-cream-200 flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <h2 className="text-sm font-semibold text-cream-900 leading-snug">
                    {selectedSet.description || selectedSet.set_number}
                  </h2>
                </div>
                <ReextractButton setId={selectedSet.id} docId={id} />
              </div>
              {selectedSet.column_reasoning && (
                <p className="px-4 py-2 text-xs text-cream-500 bg-cream-100 border-b border-cream-200 leading-relaxed">
                  {selectedSet.column_reasoning}
                </p>
              )}
              <div className="flex-1 overflow-auto">
                <ComponentTable set={selectedSet} docId={id} />
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-full">
              <p className="text-sm text-cream-400">Select a set to view components</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
