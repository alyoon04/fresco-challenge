"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/esm/Page/AnnotationLayer.css";
import "react-pdf/dist/esm/Page/TextLayer.css";
import { pdfUrl } from "@/app/api";

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface Props {
  docId: string;
  pageCount: number;
  /** Page number (1-indexed) to scroll to and highlight */
  targetPage: number | null;
  /** Incremented to re-trigger scroll even if targetPage is the same */
  scrollKey: number;
}

export default function PdfViewer({ docId, pageCount, targetPage, scrollKey }: Props) {
  const [numPages, setNumPages] = useState<number>(pageCount);
  const containerRef = useRef<HTMLDivElement>(null);
  const [pageWidth, setPageWidth] = useState(700);
  const [highlightedPage, setHighlightedPage] = useState<number | null>(null);

  const onDocumentLoadSuccess = useCallback(
    (pdf: pdfjs.PDFDocumentProxy) => {
      setNumPages(pdf.numPages);
      if (containerRef.current) {
        setPageWidth(Math.min(containerRef.current.clientWidth - 32, 900));
      }
    },
    [],
  );

  // Scroll to target page and highlight it
  useEffect(() => {
    if (!targetPage || !containerRef.current) return;

    setHighlightedPage(targetPage);

    const wrapper = containerRef.current.querySelector<HTMLDivElement>(
      `[data-page-number="${targetPage}"]`
    );
    if (wrapper) {
      wrapper.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [targetPage, scrollKey]);

  return (
    <div className="flex flex-col h-full bg-cream-50">
      {/* Toolbar */}
      <div className="flex items-center gap-3 px-4 py-2.5 border-b border-cream-200 bg-cream-50">
        <span className="text-xs text-cream-500">{numPages} pages</span>
        <input
          type="number"
          min={1}
          max={numPages}
          placeholder="Go to page"
          className="w-24 text-xs border border-cream-300 rounded-lg px-2.5 py-1.5 bg-cream-50
                     placeholder-cream-400
                     focus:outline-none focus:ring-2 focus:ring-terra-300 focus:border-terra-400
                     transition-shadow duration-150"
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              const val = parseInt((e.target as HTMLInputElement).value);
              if (val >= 1 && val <= numPages) {
                const pages = containerRef.current?.querySelectorAll("[data-page-number]");
                if (pages?.[val - 1]) {
                  pages[val - 1].scrollIntoView({ behavior: "smooth", block: "start" });
                }
              }
            }
          }}
        />
      </div>

      {/* PDF */}
      <div ref={containerRef} className="flex-1 overflow-auto bg-cream-200">
        <Document
          file={pdfUrl(docId)}
          loading={<p className="p-6 text-cream-500 text-sm">Loading PDF...</p>}
          onLoadSuccess={onDocumentLoadSuccess}
        >
          {Array.from({ length: numPages }, (_, i) => {
            const pageNum = i + 1;
            const isHighlighted = highlightedPage === pageNum;
            return (
              <div
                key={i}
                data-page-number={pageNum}
                className="relative mx-auto mb-3 mt-1"
                style={{ width: pageWidth }}
              >
                <div className="text-xs text-cream-400 text-center py-1">Page {pageNum}</div>
                <div className={`relative shadow-sm rounded ${
                  isHighlighted ? "ring-2 ring-terra-500 ring-offset-2 ring-offset-cream-200" : ""
                }`}>
                  <Page pageNumber={pageNum} width={pageWidth} />
                  {isHighlighted && (
                    <div className="absolute left-0 top-0 w-1 h-full bg-terra-500 rounded-l" />
                  )}
                </div>
              </div>
            );
          })}
        </Document>
      </div>
    </div>
  );
}
