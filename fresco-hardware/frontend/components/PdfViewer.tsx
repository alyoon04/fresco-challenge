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
  searchTerms: string[];
  searchKey: number;
}

function normalize(s: string): string {
  return s.toLowerCase().replace(/\s+/g, " ").trim();
}

/**
 * Find spans on a page that match the query.
 * Tries single-span first, then concatenates adjacent spans for multi-word.
 */
function findMatchingSpans(
  pageEl: Element,
  terms: string[],
): HTMLSpanElement[] {
  const allSpans = Array.from(
    pageEl.querySelectorAll<HTMLSpanElement>(".react-pdf__Page__textContent span"),
  ).filter((s) => s.textContent && s.textContent.trim().length > 0);

  for (const term of terms) {
    const q = normalize(term);

    // Single-span match
    for (const span of allSpans) {
      if (normalize(span.textContent || "").includes(q)) {
        return [span];
      }
    }

    // Multi-span: concatenate adjacent spans
    for (let start = 0; start < allSpans.length; start++) {
      let combined = "";
      for (let end = start; end < allSpans.length && end < start + 15; end++) {
        const txt = allSpans[end].textContent || "";
        combined += (end > start ? " " : "") + txt;
        if (normalize(combined).includes(q)) {
          const nc = normalize(combined);
          const matchStart = nc.indexOf(q);
          let charCount = 0;
          let realStart = start;
          for (let i = start; i <= end; i++) {
            const spanLen = normalize(allSpans[i].textContent || "").length + 1;
            if (charCount + spanLen > matchStart) {
              realStart = i;
              break;
            }
            charCount += spanLen;
          }
          return allSpans.slice(realStart, end + 1);
        }
      }
    }
  }
  return [];
}

export default function PdfViewer({ docId, pageCount, searchTerms, searchKey }: Props) {
  const [numPages, setNumPages] = useState<number>(pageCount);
  const containerRef = useRef<HTMLDivElement>(null);
  const [pageWidth, setPageWidth] = useState(700);
  const highlightRef = useRef<HTMLDivElement | null>(null);
  const pdfDocRef = useRef<pdfjs.PDFDocumentProxy | null>(null);
  // Pre-built index: normalized text for every page, stored as state so
  // the search effect re-runs when indexing completes
  const [pageTexts, setPageTexts] = useState<string[]>([]);

  const onDocumentLoadSuccess = useCallback(
    async (pdf: pdfjs.PDFDocumentProxy) => {
      pdfDocRef.current = pdf;
      setNumPages(pdf.numPages);
      if (containerRef.current) {
        setPageWidth(Math.min(containerRef.current.clientWidth - 32, 900));
      }

      // Build page text index
      const texts: string[] = [];
      for (let i = 1; i <= pdf.numPages; i++) {
        const page = await pdf.getPage(i);
        const tc = await page.getTextContent();
        texts.push(normalize(tc.items.map((it) => ("str" in it ? it.str : "")).join(" ")));
      }
      setPageTexts(texts);
      console.log("[PdfViewer] indexed", texts.length, "pages");
    },
    [],
  );

  useEffect(() => {
    if (searchTerms.length === 0 || !containerRef.current || pageTexts.length === 0) return;

    if (highlightRef.current) {
      highlightRef.current.remove();
      highlightRef.current = null;
    }

    // Find the page — instant, using pre-built index
    let pageNum: number | null = null;
    let matchedTerm: string | null = null;
    for (const term of searchTerms) {
      const q = normalize(term);
      for (let i = 0; i < pageTexts.length; i++) {
        if (pageTexts[i].includes(q)) {
          pageNum = i + 1;
          matchedTerm = term;
          break;
        }
      }
      if (pageNum) break;
    }

    if (!pageNum) {
      console.log("[PdfViewer] no page found for any term:", searchTerms);
      return;
    }

    console.log("[PdfViewer] going to page:", pageNum, "matched:", matchedTerm, "all terms:", searchTerms);

    const container = containerRef.current;
    const pageEls = container.querySelectorAll(".react-pdf__Page");
    const pageEl = pageEls[pageNum - 1];
    if (!pageEl) return;

    pageEl.scrollIntoView({ behavior: "smooth", block: "start" });

    // Poll until the text layer spans have rendered with actual dimensions
    let cancelled = false;
    let attempts = 0;
    const maxAttempts = 20; // 20 × 200ms = 4 seconds max

    const timer = setInterval(() => {
      if (cancelled) { clearInterval(timer); return; }
      attempts++;

      const matchedSpans = findMatchingSpans(pageEl, searchTerms);
      if (matchedSpans.length === 0) {
        if (attempts >= maxAttempts) clearInterval(timer);
        return;
      }

      // Check if spans have actual dimensions (text layer fully rendered)
      const firstRect = matchedSpans[0].getBoundingClientRect();
      if (firstRect.width === 0 && firstRect.height === 0) {
        if (attempts >= maxAttempts) clearInterval(timer);
        return;
      }

      // Spans are rendered — highlight them
      clearInterval(timer);

      const page = matchedSpans[0].closest(".react-pdf__Page") as HTMLElement;
      if (!page) return;

      // Append to the page element itself (not its parent) so coordinates match
      page.style.position = "relative";

      const pageRect = page.getBoundingClientRect();

      let minLeft = Infinity, minTop = Infinity, maxRight = -Infinity, maxBottom = -Infinity;
      for (const s of matchedSpans) {
        const r = s.getBoundingClientRect();
        minLeft = Math.min(minLeft, r.left);
        minTop = Math.min(minTop, r.top);
        maxRight = Math.max(maxRight, r.right);
        maxBottom = Math.max(maxBottom, r.bottom);
      }

      const highlight = document.createElement("div");
      highlight.style.position = "absolute";
      highlight.style.left = `${minLeft - pageRect.left - 4}px`;
      highlight.style.top = `${minTop - pageRect.top - 2}px`;
      highlight.style.width = `${maxRight - minLeft + 8}px`;
      highlight.style.height = `${maxBottom - minTop + 4}px`;
      highlight.style.backgroundColor = "rgba(255, 200, 0, 0.35)";
      highlight.style.border = "3px solid rgba(255, 150, 0, 0.9)";
      highlight.style.borderRadius = "3px";
      highlight.style.pointerEvents = "none";
      highlight.style.zIndex = "9999";

      page.appendChild(highlight);
      highlightRef.current = highlight;
      console.log("[PdfViewer] highlight appended, size:", highlight.style.width, "x", highlight.style.height, "at", highlight.style.left, highlight.style.top);

      matchedSpans[0].scrollIntoView({ behavior: "smooth", block: "center" });
    }, 200);

    return () => { cancelled = true; clearInterval(timer); };
  }, [searchTerms, searchKey, pageTexts]);

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
              <div className="relative shadow-sm rounded">
                <Page pageNumber={i + 1} width={pageWidth} />
              </div>
            </div>
          ))}
        </Document>
      </div>
    </div>
  );
}
