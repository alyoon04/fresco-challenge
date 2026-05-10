"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { uploadDocument, listDocuments } from "./api";

function StatusBadge({ status }: { status: string }) {
  const styles = {
    done: "bg-emerald-50 text-emerald-700 border-emerald-200",
    failed: "bg-red-50 text-red-700 border-red-200",
    processing: "bg-amber-50 text-amber-700 border-amber-200",
    uploaded: "bg-cream-200 text-cream-700 border-cream-300",
    cancelled: "bg-gray-50 text-gray-600 border-gray-200",
  }[status] ?? "bg-cream-200 text-cream-700 border-cream-300";

  return (
    <span className={`text-xs font-medium px-2.5 py-1 rounded-full border ${styles}`}>
      {status === "processing" && (
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-amber-500 mr-1.5 animate-pulse-soft" />
      )}
      {status}
    </span>
  );
}

export default function Home() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [search, setSearch] = useState("");

  const { data: docs } = useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
  });

  const filteredDocs = useMemo(() => {
    if (!docs) return [];
    if (!search.trim()) return docs;
    const q = search.toLowerCase();
    return docs.filter(
      (d) =>
        d.filename.toLowerCase().includes(q) ||
        d.status.toLowerCase().includes(q),
    );
  }, [docs, search]);

  const handleUpload = useCallback(
    async (file: File) => {
      setError(null);
      setUploading(true);
      try {
        const { doc_id } = await uploadDocument(file);
        router.push(`/doc/${doc_id}`);
      } catch (e) {
        setError(String(e));
      } finally {
        setUploading(false);
      }
    },
    [router],
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      const file = e.dataTransfer.files[0];
      if (file) setSelectedFile(file);
    },
    [],
  );

  return (
    <main className="h-screen flex">
      {/* Left — Upload */}
      <div className="w-1/2 flex flex-col justify-center px-16 xl:px-24 border-r border-cream-200">
        <div className="max-w-md w-full mx-auto space-y-10">
          {/* Title */}
          <div className="space-y-3">
            <h1 className="text-4xl font-semibold tracking-tight text-cream-900 border-b border-cream-300 pb-4">
              Fresco
            </h1>
            <p className="text-cream-600 text-sm leading-relaxed">
              Upload a Division 08 specbook PDF to extract hardware sets automatically.
            </p>
          </div>

          {/* Upload area */}
          <div className="space-y-4">
            <div
              className={`border-2 border-dashed rounded-xl p-14 transition-all duration-200 cursor-pointer text-center ${
                dragOver
                  ? "border-terra-400 bg-terra-50"
                  : selectedFile
                    ? "border-terra-300 bg-cream-50"
                    : "border-cream-300 hover:border-cream-400 bg-cream-50"
              }`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              onClick={() => fileRef.current?.click()}
            >
              {selectedFile ? (
                <div>
                  <p className="text-sm font-medium text-cream-900">{selectedFile.name}</p>
                  <p className="text-xs text-cream-500 mt-1">
                    {(selectedFile.size / 1024 / 1024).toFixed(1)} MB
                  </p>
                </div>
              ) : (
                <div>
                  <div className="text-cream-400 mb-3">
                    <svg className="w-10 h-10 mx-auto" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 16.5V9.75m0 0l3 3m-3-3l-3 3M6.75 19.5a4.5 4.5 0 01-1.41-8.775 5.25 5.25 0 0110.233-2.33 3 3 0 013.758 3.848A3.752 3.752 0 0118 19.5H6.75z" />
                    </svg>
                  </div>
                  <p className="text-sm text-cream-500">Drop PDF here or click to browse</p>
                  <p className="text-xs text-cream-400 mt-1">Supports .pdf files</p>
                </div>
              )}
            </div>

            <input
              ref={fileRef}
              type="file"
              accept=".pdf"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) setSelectedFile(file);
              }}
            />

            <button
              className="w-full py-3 rounded-lg border border-cream-900 bg-cream-900 text-cream-100 text-sm font-medium
                         transition-all duration-150
                         hover:bg-cream-800 hover:border-cream-800
                         active:scale-[0.98]
                         disabled:opacity-40 disabled:cursor-not-allowed disabled:active:scale-100"
              disabled={!selectedFile || uploading}
              onClick={() => selectedFile && handleUpload(selectedFile)}
            >
              {uploading ? "Uploading..." : "Upload & Extract"}
            </button>

            {error && (
              <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-2">
                {error}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Right — Documents */}
      <div className="w-1/2 flex flex-col bg-cream-50">
        {/* Header with search */}
        <div className="px-8 pt-8 pb-4 space-y-4">
          <h2 className="text-lg font-semibold text-cream-900 border-b border-cream-300 pb-3">
            Documents
          </h2>
          <div className="relative">
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-cream-400"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={2}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
            <input
              type="text"
              placeholder="Search documents..."
              className="w-full text-sm border border-cream-300 rounded-lg pl-10 pr-4 py-2.5 bg-white
                         placeholder-cream-400
                         focus:outline-none focus:ring-2 focus:ring-terra-300 focus:border-terra-400
                         transition-shadow duration-150"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
        </div>

        {/* Document list */}
        <div className="flex-1 overflow-auto px-8 pb-8">
          {!docs || docs.length === 0 ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-sm text-cream-400">No documents yet. Upload a PDF to get started.</p>
            </div>
          ) : filteredDocs.length === 0 ? (
            <div className="flex items-center justify-center h-64">
              <p className="text-sm text-cream-400">No documents matching &ldquo;{search}&rdquo;</p>
            </div>
          ) : (
            <div className="space-y-2">
              {filteredDocs.map((doc) => (
                <a
                  key={doc.id}
                  href={`/doc/${doc.id}`}
                  className="flex items-center justify-between px-5 py-4
                             bg-white border border-cream-200 rounded-xl
                             transition-all duration-150
                             hover:border-cream-300 hover:shadow-sm"
                >
                  <div className="min-w-0 mr-4">
                    <p className="text-sm font-medium text-cream-900 truncate">
                      {doc.filename}
                    </p>
                    <p className="text-xs text-cream-500 mt-1">
                      {doc.page_count} pages
                      {doc.set_count > 0 && (
                        <>
                          <span className="text-cream-300 mx-1">&middot;</span>
                          {doc.set_count} sets
                        </>
                      )}
                      {doc.created_at && (
                        <>
                          <span className="text-cream-300 mx-1">&middot;</span>
                          {new Date(doc.created_at).toLocaleDateString()}
                        </>
                      )}
                    </p>
                  </div>
                  <StatusBadge status={doc.status} />
                </a>
              ))}
            </div>
          )}
        </div>
      </div>
    </main>
  );
}
