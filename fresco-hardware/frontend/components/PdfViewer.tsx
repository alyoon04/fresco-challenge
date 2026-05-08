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

/**
 * Search the actual PDF text content (not DOM) to find which page contains
 * the query. This works regardless of which pages are currently rendered.
 */
async function findPageWithText(
  pdfDocProxy: pdfjs.PDFDocumentProxy,
  query: string,
): Promise<number | null> {
  const q = query.toLowerCase();
  for (let i = 1; i <= pdfDocProxy.numPages; i++) {
    const page = await pdfDocProxy.getPage(i);
    const textContent = await page.getTextContent();
    const pageText = textContent.items
      .map((item) => ("str" in item ? item.str : ""))
      .join(" ")
      .toLowerCase();
    if (pageText.includes(q)) {
      return i;
    }
  }
  return null;
}

export default function PdfViewer({ docId, pageCount, searchQuery, searchKey }: Props) {
  const [numPages, setNumPages] = useState<number>(pageCount);
  const containerRef = useRef<HTMLDivElement>(null);
  const [pageWidth, setPageWidth] = useState(700);
  const highlightRef = useRef<HTMLDivElement | null>(null);
  const pdfDocRef = useRef<pdfjs.PDFDocumentProxy | null>(null);

  const onDocumentLoadSuccess = useCallback(
    (pdf: pdfjs.PDFDocumentProxy) => {
      pdfDocRef.current = pdf;
      setNumPages(pdf.numPages);
      if (containerRef.current) {
        setPageWidth(Math.min(containerRef.current.clientWidth - 32, 900));
      }
    },
    [],
  );

  // Search PDF text content to find correct page, scroll there, then highlight
  useEffect(() => {
    if (!searchQuery || !containerRef.current) return;

    // Clear previous highlight
    if (highlightRef.current) {
      highlightRef.current.remove();
      highlightRef.current = null;
    }

    const query = searchQuery.toLowerCase();
    let cancelled = false;

    async function doSearch() {
      const container = containerRef.current;
      if (!container || !pdfDocRef.current) return;

      // Search actual PDF text content for the correct page
      const targetPage = await findPageWithText(pdfDocRef.current, query);
      if (cancelled || !targetPage) return;

      // Scroll to the target page element
      const pageElements = container.querySelectorAll(".react-pdf__Page");
      const targetEl = pageElements[targetPage - 1];
      if (!targetEl) return;

      targetEl.scrollIntoView({ behavior: "smooth", block: "start" });

      // Wait for the page to scroll into view and text layer to render
      await new Promise((r) => setTimeout(r, 600));
      if (cancelled) return;

      // Now search the rendered text layer spans on that page for highlighting
      const spans = targetEl.querySelectorAll<HTMLSpanElement>(
        ".react-pdf__Page__textContent span",
      );
      for (const span of spans) {
        if (span.textContent && span.textContent.toLowerCase().includes(query)) {
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

          const wrapper = page.parentElement;
          if (wrapper) {
            wrapper.style.position = "relative";
            wrapper.appendChild(highlight);
            highlightRef.current = highlight;
          }

          // Fine-tune scroll to center on the match
          span.scrollIntoView({ behavior: "smooth", block: "center" });
          return;
        }
      }
    }

    doSearch();
    return () => { cancelled = true; };
  }, [searchQuery, searchKey, docId]);

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
