"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchDocument } from "@/app/api";
import PdfViewer from "@/components/PdfViewer";
import SetList from "@/components/SetList";
import ComponentTable from "@/components/ComponentTable";
import ReextractButton from "@/components/ReextractButton";

export default function DocumentPage({ params }: { params: { id: string } }) {
  const { id } = params;
  const [selectedSetId, setSelectedSetId] = useState<number | null>(null);

  const { data: doc, isLoading, error } = useQuery({
    queryKey: ["document", id],
    queryFn: () => fetchDocument(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      // Poll while processing
      return status === "processing" || status === "uploaded" ? 3000 : false;
    },
  });

  if (isLoading) return <div className="p-8 text-gray-500">Loading document...</div>;
  if (error) return <div className="p-8 text-red-500">Error: {String(error)}</div>;
  if (!doc) return <div className="p-8 text-gray-500">Document not found</div>;

  const selectedSet = doc.sets.find((s) => s.id === selectedSetId) ?? null;

  // Jump PDF to the first page of the selected set
  const selectedLocations = selectedSet?.locations ?? [];

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="px-4 py-2 border-b bg-white flex items-center justify-between">
        <div>
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
          <PdfViewer docId={id} pageCount={doc.page_count} locations={selectedLocations} />
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
