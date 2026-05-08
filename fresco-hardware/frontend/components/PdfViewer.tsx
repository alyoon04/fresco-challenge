"use client";

import { useCallback, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { pageUrl, type Location } from "@/app/api";

// Use CDN worker for react-pdf
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface Props {
  docId: string;
  pageCount: number;
  locations: Location[];
}

function confidenceColor(confidence?: number): string {
  if (confidence === undefined || confidence === null) return "rgba(59,130,246,0.25)";
  if (confidence >= 0.8) return "rgba(34,197,94,0.25)";
  if (confidence >= 0.5) return "rgba(234,179,8,0.3)";
  return "rgba(239,68,68,0.3)";
}

export default function PdfViewer({ docId, pageCount, locations }: Props) {
  const [currentPage, setCurrentPage] = useState(0);
  const [pageSize, setPageSize] = useState<{ width: number; height: number } | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const onPageLoadSuccess = useCallback(
    (page: { width: number; height: number }) => {
      setPageSize({ width: page.width, height: page.height });
    },
    [],
  );

  // Bboxes for the current page
  const bboxes = locations.filter((loc) => loc.page_num === currentPage && loc.bbox);

  return (
    <div className="flex flex-col h-full">
      {/* Page navigation */}
      <div className="flex items-center justify-between px-3 py-2 border-b bg-white">
        <button
          className="px-2 py-1 text-sm rounded border disabled:opacity-30"
          disabled={currentPage <= 0}
          onClick={() => setCurrentPage((p) => p - 1)}
        >
          Prev
        </button>
        <span className="text-sm text-gray-600">
          Page {currentPage + 1} / {pageCount}
        </span>
        <button
          className="px-2 py-1 text-sm rounded border disabled:opacity-30"
          disabled={currentPage >= pageCount - 1}
          onClick={() => setCurrentPage((p) => p + 1)}
        >
          Next
        </button>
      </div>

      {/* PDF + overlay */}
      <div ref={containerRef} className="relative flex-1 overflow-auto bg-gray-200 flex justify-center">
        <Document file={pageUrl(docId, currentPage)} loading={<p className="p-4 text-gray-500">Loading...</p>}>
          <Page
            pageNumber={1}
            width={containerRef.current?.clientWidth ? Math.min(containerRef.current.clientWidth - 16, 900) : 700}
            onLoadSuccess={onPageLoadSuccess}
          />
        </Document>

        {/* Bbox overlays */}
        {pageSize &&
          bboxes.map((loc, i) => {
            const [x0, y0, x1, y1] = loc.bbox!;
            const containerWidth = containerRef.current?.clientWidth
              ? Math.min(containerRef.current.clientWidth - 16, 900)
              : 700;
            const scale = containerWidth / pageSize.width;
            return (
              <div
                key={i}
                className="absolute border-2 border-blue-400 pointer-events-none"
                style={{
                  left: x0 * scale,
                  top: y0 * scale + 41, // offset for nav bar
                  width: (x1 - x0) * scale,
                  height: (y1 - y0) * scale,
                  backgroundColor: confidenceColor(),
                }}
              />
            );
          })}
      </div>
    </div>
  );
}
