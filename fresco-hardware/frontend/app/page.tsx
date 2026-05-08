"use client";

import { useCallback, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { uploadDocument } from "./api";

export default function Home() {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);

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
    <main className="flex items-center justify-center min-h-screen">
      <div className="text-center space-y-6 max-w-md w-full px-4">
        <h1 className="text-2xl font-bold text-gray-800">Fresco Hardware Sets</h1>
        <p className="text-gray-500 text-sm">Upload a Division 08 specbook PDF to extract hardware sets.</p>

        <div
          className={`border-2 border-dashed rounded-lg p-10 transition-colors cursor-pointer ${
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
      </div>
    </main>
  );
}
