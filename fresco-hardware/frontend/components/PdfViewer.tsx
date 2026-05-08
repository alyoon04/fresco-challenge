"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { pdfUrl, type Location } from "@/app/api";

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface Props {
  docId: string;
  pageCount: number;
  locations: Location[];
  scrollToPage?: number | null;
}

function confidenceColor(confidence?: number): string {
  if (confidence === undefined || confidence === null) return "rgba(59,130,246,0.25)";
  if (confidence >= 0.8) return "rgba(34,197,94,0.25)";
  if (confidence >= 0.5) return "rgba(234,179,8,0.3)";
  return "rgba(239,68,68,0.3)";
}

export default function PdfViewer({ docId, pageCount, locations, scrollToPage: scrollTarget }: Props) {
  const [numPages, setNumPages] = useState<number>(pageCount);
  const containerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<Map<number, HTMLDivElement>>(new Map());
  const [pageWidth, setPageWidth] = useState(700);

  const onDocumentLoadSuccess = useCallback(
    ({ numPages: n }: { numPages: number }) => {
      setNumPages(n);
      if (containerRef.current) {
        setPageWidth(Math.min(containerRef.current.clientWidth - 32, 900));
      }
    },
    [],
  );

  // Scroll to a specific page
  const scrollToPage = useCallback((pageNum: number) => {
    const el = pageRefs.current.get(pageNum);
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }, []);

  // Auto-scroll when a set is selected
  useEffect(() => {
    if (scrollTarget !== null && scrollTarget !== undefined) {
      const el = pageRefs.current.get(scrollTarget);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [scrollTarget]);

  const firstLocPage = locations.length > 0 ? locations[0].page_num : null;

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
              if (val >= 1 && val <= numPages) scrollToPage(val - 1);
            }
          }}
        />
        {firstLocPage !== null && (
          <button
            className="text-xs px-2 py-1 rounded bg-blue-100 text-blue-700 hover:bg-blue-200"
            onClick={() => scrollToPage(firstLocPage)}
          >
            Jump to set (p.{firstLocPage + 1})
          </button>
        )}
      </div>

      {/* Scrollable PDF */}
      <div ref={containerRef} className="flex-1 overflow-auto bg-gray-200">
        <Document
          file={pdfUrl(docId)}
          loading={<p className="p-4 text-gray-500">Loading PDF...</p>}
          onLoadSuccess={onDocumentLoadSuccess}
        >
          {Array.from({ length: numPages }, (_, i) => {
            const pageBboxes = locations.filter((loc) => loc.page_num === i && loc.bbox);
            return (
              <div
                key={i}
                ref={(el) => { if (el) pageRefs.current.set(i, el); }}
                className="relative mx-auto mb-2"
                style={{ width: pageWidth }}
              >
                {/* Page number label */}
                <div className="text-xs text-gray-400 text-center py-1">Page {i + 1}</div>
                <Page pageNumber={i + 1} width={pageWidth} />
                {/* Bbox overlays */}
                {pageBboxes.map((loc, j) => {
                  const [x0, y0, x1, y1] = loc.bbox!;
                  // react-pdf renders at 72 DPI by default, scale factor = width / 612
                  const scale = pageWidth / 612;
                  return (
                    <div
                      key={j}
                      className="absolute border-2 border-blue-400 pointer-events-none"
                      style={{
                        left: x0 * scale,
                        top: y0 * scale + 20, // offset for page label
                        width: (x1 - x0) * scale,
                        height: (y1 - y0) * scale,
                        backgroundColor: confidenceColor(),
                      }}
                    />
                  );
                })}
              </div>
            );
          })}
        </Document>
      </div>
    </div>
  );
}
