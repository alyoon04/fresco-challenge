"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { uploadDocument, listDocuments } from "./api";

export default function Home() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

  const { data: docs } = useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
  });

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
    <main className="min-h-screen py-12 px-4">
      <div className="max-w-2xl mx-auto space-y-8">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-gray-800">Fresco Hardware Sets</h1>
          <p className="text-gray-500 text-sm mt-1">Upload a Division 08 specbook PDF to extract hardware sets.</p>
        </div>

        <div
          className={`border-2 border-dashed rounded-lg p-10 transition-colors cursor-pointer text-center ${
            dragOver ? "border-blue-400 bg-blue-50" : "border-gray-300 hover:border-gray-400"
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
            <p className="text-gray-700 font-medium">{selectedFile.name}</p>
          ) : (
            <p className="text-gray-400">Drop PDF here or click to browse</p>
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
          className="w-full py-2.5 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          disabled={!selectedFile || uploading}
          onClick={() => selectedFile && handleUpload(selectedFile)}
        >
          {uploading ? "Uploading..." : "Upload & Extract"}
        </button>

        {error && <p className="text-red-500 text-sm">{error}</p>}

        {/* Previous documents */}
        {docs && docs.length > 0 && (
          <div>
            <h2 className="text-sm font-semibold text-gray-600 mb-3">Previous Documents</h2>
            <div className="border rounded-lg divide-y">
              {docs.map((doc) => (
                <a
                  key={doc.id}
                  href={`/doc/${doc.id}`}
                  className="flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors"
                >
                  <div>
                    <p className="text-sm font-medium text-gray-800">{doc.filename}</p>
                    <p className="text-xs text-gray-400">
                      {doc.page_count} pages
                      {doc.set_count > 0 && ` \u00b7 ${doc.set_count} sets`}
                      {doc.created_at && ` \u00b7 ${new Date(doc.created_at).toLocaleDateString()}`}
                    </p>
                  </div>
                  <span
                    className={`text-xs px-2 py-1 rounded-full ${
                      doc.status === "done"
                        ? "bg-green-100 text-green-700"
                        : doc.status === "failed"
                          ? "bg-red-100 text-red-700"
                          : "bg-yellow-100 text-yellow-700"
                    }`}
                  >
                    {doc.status}
                  </span>
                </a>
              ))}
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
