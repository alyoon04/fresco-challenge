"use client";

import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchDocument } from "@/app/api";
import PdfViewer from "@/components/PdfViewer";
import SetList from "@/components/SetList";
import ComponentTable from "@/components/ComponentTable";
import ReextractButton from "@/components/ReextractButton";

export default function DocumentPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const [selectedSetId, setSelectedSetId] = useState<number | null>(null);
  const queryClient = useQueryClient();

  const { data: doc, isLoading, error } = useQuery({
    queryKey: ["document", id],
    queryFn: () => fetchDocument(id),
  });

  // WebSocket: listen for status changes, refetch when notified
  useEffect(() => {
    const status = doc?.status;
    if (status === "done" || status === "failed") return;

    const wsBase = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000")
      .replace(/^http/, "ws");
    const ws = new WebSocket(`${wsBase}/ws/documents/${id}`);

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      queryClient.invalidateQueries({ queryKey: ["document", id] });
      if (data.status === "done" || data.status === "failed") {
        ws.close();
      }
    };

    ws.onerror = () => ws.close();

    return () => {
      if (ws.readyState <= WebSocket.OPEN) ws.close();
    };
  }, [id, doc?.status, queryClient]);

  if (isLoading) return <div className="p-8 text-gray-500">Loading document...</div>;
  if (error) return <div className="p-8 text-red-500">Error: {String(error)}</div>;
  if (!doc) return <div className="p-8 text-gray-500">Document not found</div>;

  const selectedSet = doc.sets.find((s) => s.id === selectedSetId) ?? null;

  const selectedLocations = selectedSet?.locations ?? [];
  const scrollToPage = selectedLocations.length > 0 ? selectedLocations[0].page_num : null;

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="px-4 py-2 border-b bg-white flex items-center justify-between">
        <div className="flex items-center gap-3">
          <a href="/" className="text-sm text-blue-600 hover:text-blue-800">&larr; Home</a>
          <h1 className="text-lg font-semibold">{doc.filename}</h1>
          <span className="text-xs text-gray-400">
            {doc.page_count} pages &middot;{" "}
            <span
              className={
                doc.status === "done"
                  ? "text-green-600"
                  : doc.status === "failed"
                    ? "text-red-600"
                    : "text-yellow-600"
              }
            >
              {doc.status}
            </span>
            {doc.sets.length > 0 && ` \u00b7 ${doc.sets.length} sets`}
          </span>
        </div>
        {doc.error_message && (
          <p className="text-sm text-red-500 max-w-md truncate">{doc.error_message}</p>
        )}
      </header>

      {/* Three-pane layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: PDF viewer */}
        <div className="w-1/2 border-r">
          <PdfViewer docId={id} pageCount={doc.page_count} locations={selectedLocations} scrollToPage={scrollToPage} />
        </div>

        {/* Center: Set list */}
        <div className="w-1/4 border-r bg-white overflow-auto">
          <div className="px-3 py-2 border-b bg-gray-50">
            <h2 className="text-sm font-semibold text-gray-600">Hardware Sets</h2>
          </div>
          <SetList sets={doc.sets} selectedId={selectedSetId} onSelect={setSelectedSetId} />
        </div>

        {/* Right: Component table + re-extract */}
        <div className="w-1/4 bg-white overflow-auto flex flex-col">
          {selectedSet ? (
            <>
              <div className="px-3 py-2 border-b bg-gray-50 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold">
                    Set {selectedSet.set_number}
                  </h2>
                  {selectedSet.description && (
                    <p className="text-xs text-gray-500">{selectedSet.description}</p>
                  )}
                </div>
                <ReextractButton setId={selectedSet.id} docId={id} />
              </div>
              {selectedSet.column_reasoning && (
                <p className="px-3 py-1 text-xs text-gray-400 bg-gray-50 border-b">
                  {selectedSet.column_reasoning}
                </p>
              )}
              <div className="flex-1 overflow-auto">
                <ComponentTable set={selectedSet} docId={id} />
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-full text-gray-400 text-sm">
              Select a set to view components
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
