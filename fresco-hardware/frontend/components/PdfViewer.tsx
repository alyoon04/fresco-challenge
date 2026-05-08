"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { pdfUrl } from "@/app/api";

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface Props {
  docId: string;
  pageCount: number;
  searchQuery: string | null;
  searchKey: number;
}

export default function PdfViewer({ docId, pageCount, searchQuery, searchKey }: Props) {
  const [numPages, setNumPages] = useState<number>(pageCount);
  const containerRef = useRef<HTMLDivElement>(null);
  const [pageWidth, setPageWidth] = useState(700);
  const highlightRef = useRef<HTMLDivElement | null>(null);

  const onDocumentLoadSuccess = useCallback(
    ({ numPages: n }: { numPages: number }) => {
      setNumPages(n);
      if (containerRef.current) {
        setPageWidth(Math.min(containerRef.current.clientWidth - 32, 900));
      }
    },
    [],
  );

  // Search the rendered text layer for the query and highlight + scroll to it
  useEffect(() => {
    if (!searchQuery || !containerRef.current) return;

    // Clear previous highlight
    if (highlightRef.current) {
      highlightRef.current.remove();
      highlightRef.current = null;
    }

    const query = searchQuery.toLowerCase();

    // Small delay to let text layers render
    const timer = setTimeout(() => {
      const container = containerRef.current;
      if (!container) return;

      // Search all text layer spans
      const spans = container.querySelectorAll<HTMLSpanElement>(".react-pdf__Page__textContent span");
      for (const span of spans) {
        if (span.textContent && span.textContent.toLowerCase().includes(query)) {
          // Create highlight overlay
          const page = span.closest(".react-pdf__Page") as HTMLElement;
          if (!page) continue;

          const pageRect = page.getBoundingClientRect();
          const spanRect = span.getBoundingClientRect();

          const highlight = document.createElement("div");
          highlight.style.position = "absolute";
          highlight.style.left = `${spanRect.left - pageRect.left - 4}px`;
          highlight.style.top = `${spanRect.top - pageRect.top - 2}px`;
          highlight.style.width = `${spanRect.width + 8}px`;
          highlight.style.height = `${spanRect.height + 4}px`;
          highlight.style.backgroundColor = "rgba(59, 130, 246, 0.25)";
          highlight.style.border = "2px solid rgb(59, 130, 246)";
          highlight.style.borderRadius = "3px";
          highlight.style.pointerEvents = "none";
          highlight.style.zIndex = "10";

          // The page wrapper with relative positioning
          const wrapper = page.parentElement;
          if (wrapper) {
            wrapper.style.position = "relative";
            wrapper.appendChild(highlight);
            highlightRef.current = highlight;
          }

          // Scroll to it
          span.scrollIntoView({ behavior: "smooth", block: "center" });
          return;
        }
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery, searchKey]);

  return (
    <div className="flex flex-col h-full">
      {/* Page jump bar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b bg-white">
        <span className="text-sm text-gray-600">{numPages} pages</span>
        <input
          type="number"
          min={1}
          max={numPages}
          placeholder="Go to page"
          className="w-24 text-sm border rounded px-2 py-1"
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              const val = parseInt((e.target as HTMLInputElement).value);
              if (val >= 1 && val <= numPages) {
                const pages = containerRef.current?.querySelectorAll(".react-pdf__Page");
                if (pages?.[val - 1]) {
                  pages[val - 1].scrollIntoView({ behavior: "smooth", block: "start" });
                }
              }
            }
          }}
        />
      </div>

      {/* Scrollable PDF */}
      <div ref={containerRef} className="flex-1 overflow-auto bg-gray-200">
        <Document
          file={pdfUrl(docId)}
          loading={<p className="p-4 text-gray-500">Loading PDF...</p>}
          onLoadSuccess={onDocumentLoadSuccess}
        >
          {Array.from({ length: numPages }, (_, i) => (
            <div key={i} className="relative mx-auto mb-2" style={{ width: pageWidth }}>
              <div className="text-xs text-gray-400 text-center py-1">Page {i + 1}</div>
              <div className="relative">
                <Page pageNumber={i + 1} width={pageWidth} />
              </div>
            </div>
          ))}
        </Document>
      </div>
    </div>
  );
}
