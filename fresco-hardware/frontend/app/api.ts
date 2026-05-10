/**
 * API client for the Fresco backend.
 *
 * All endpoints proxy through Next.js rewrites to avoid CORS in production.
 * In dev, requests go directly to the FastAPI server.
 */

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ---------------------------------------------------------------------------
// Device ID — unique per browser, persisted in localStorage
// ---------------------------------------------------------------------------

const DEVICE_ID_KEY = "fresco_device_id";

export function getDeviceId(): string {
  if (typeof window === "undefined") return "";
  let id = localStorage.getItem(DEVICE_ID_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(DEVICE_ID_KEY, id);
  }
  return id;
}

export interface Component {
  idx: number;
  qty: number | null;
  description: string;
  catalog_number: string | null;
  mfr: string | null;
  finish: string | null;
  notes: string | null;
  confidences: Record<string, number>;
}

export interface Location {
  page_num: number;
  bbox: number[] | null;
  line_start: number | null;
  line_end: number | null;
}

export interface HardwareSet {
  id: number;
  set_number: string;
  description: string | null;
  is_not_used: boolean;
  overall_confidence: number;
  column_reasoning: string | null;
  components: Component[];
  locations: Location[];
}

export interface DocumentData {
  id: string;
  filename: string;
  page_count: number;
  status: string;
  error_message: string | null;
  legend: Record<string, unknown> | null;
  created_at: string | null;
  sets: HardwareSet[];
}

export interface RefCodes {
  codes: Record<string, string>;
  ambiguous: string[];
}

// ---- Fetch helpers ----

export interface DocumentSummary {
  id: string;
  filename: string;
  page_count: number;
  status: string;
  created_at: string | null;
  set_count: number;
}

export async function listDocuments(): Promise<DocumentSummary[]> {
  const deviceId = getDeviceId();
  const url = deviceId
    ? `${API_BASE}/api/documents?device_id=${encodeURIComponent(deviceId)}`
    : `${API_BASE}/api/documents`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`List documents failed: ${res.status}`);
  return res.json();
}

export async function uploadDocument(file: File): Promise<{ doc_id: string; status: string }> {
  const form = new FormData();
  form.append("file", file);
  const deviceId = getDeviceId();
  if (deviceId) form.append("device_id", deviceId);
  const res = await fetch(`${API_BASE}/api/documents`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
  return res.json();
}

export async function fetchDocument(docId: string): Promise<DocumentData> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}`);
  if (!res.ok) throw new Error(`Fetch document failed: ${res.status}`);
  return res.json();
}

export function pdfUrl(docId: string): string {
  return `${API_BASE}/api/documents/${docId}/pdf`;
}

export async function correctComponent(
  setId: number,
  compIdx: number,
  field: string,
  value: string,
): Promise<void> {
  const res = await fetch(`${API_BASE}/api/sets/${setId}/components/${compIdx}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ field, value }),
  });
  if (!res.ok) throw new Error(`Correction failed: ${res.status}`);
}

export async function cancelDocument(docId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/documents/${docId}/cancel`, { method: "POST" });
  if (!res.ok) throw new Error(`Cancel failed: ${res.status}`);
}

export async function reextractSet(setId: number, hint: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/sets/${setId}/reextract`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hint }),
  });
  if (!res.ok) throw new Error(`Re-extract failed: ${res.status}`);
}

export async function fetchMfrCodes(): Promise<RefCodes> {
  const res = await fetch(`${API_BASE}/api/reference/mfr_codes`);
  if (!res.ok) throw new Error(`Fetch mfr codes failed: ${res.status}`);
  return res.json();
}

export async function fetchFinishCodes(): Promise<RefCodes> {
  const res = await fetch(`${API_BASE}/api/reference/finish_codes`);
  if (!res.ok) throw new Error(`Fetch finish codes failed: ${res.status}`);
  return res.json();
}
