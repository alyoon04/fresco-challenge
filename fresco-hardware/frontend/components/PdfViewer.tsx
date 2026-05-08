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
  searchTerms: string[];
  searchKey: number;
}

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

export default function PdfViewer({ docId, pageCount, searchTerms, searchKey }: Props) {
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

  useEffect(() => {
    if (searchTerms.length === 0 || !containerRef.current) return;

    if (highlightRef.current) {
      highlightRef.current.remove();
      highlightRef.current = null;
    }

    let cancelled = false;

    async function doSearch() {
      const container = containerRef.current;
      if (!container || !pdfDocRef.current) return;

      let targetPage: number | null = null;
      let matchedTerm: string | null = null;
      for (const term of searchTerms) {
        targetPage = await findPageWithText(pdfDocRef.current!, term);
        if (cancelled) return;
        if (targetPage) {
          matchedTerm = term;
          break;
        }
      }

      if (!targetPage || !matchedTerm) return;
      const query = matchedTerm.toLowerCase();

      const pageElements = container.querySelectorAll(".react-pdf__Page");
      const targetEl = pageElements[targetPage - 1];
      if (!targetEl) return;

      targetEl.scrollIntoView({ behavior: "smooth", block: "start" });

      await new Promise((r) => setTimeout(r, 600));
      if (cancelled) return;

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
          highlight.style.backgroundColor = "rgba(217, 119, 87, 0.2)";
          highlight.style.border = "2px solid rgba(217, 119, 87, 0.6)";
          highlight.style.borderRadius = "3px";
          highlight.style.pointerEvents = "none";
          highlight.style.zIndex = "10";

          const wrapper = page.parentElement;
          if (wrapper) {
            wrapper.style.position = "relative";
            wrapper.appendChild(highlight);
            highlightRef.current = highlight;
          }

          span.scrollIntoView({ behavior: "smooth", block: "center" });
          return;
        }
      }
    }

    doSearch();
    return () => { cancelled = true; };
  }, [searchTerms, searchKey, docId]);

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
                const pages = containerRef.current?.querySelectorAll(".react-pdf__Page");
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
          {Array.from({ length: numPages }, (_, i) => (
            <div key={i} className="relative mx-auto mb-3 mt-1" style={{ width: pageWidth }}>
              <div className="text-xs text-cream-400 text-center py-1">Page {i + 1}</div>
              <div className="relative shadow-sm rounded overflow-hidden">
                <Page pageNumber={i + 1} width={pageWidth} />
              </div>
            </div>
          ))}
        </Document>
      </div>
    </div>
  );
}
