import { createClient } from "@supabase/supabase-js";

import type {
  AiPartnerTurn,
  SessionCapability,
  SessionStatus,
  StudentReport,
  Task,
  UploadGrant,
} from "./types";
import type { RecordingResult } from "@/features/recording/mediaRecorder";

const API_URL = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

export const SAMPLE_TASK_ID = "99999999-9999-4999-8999-999999999999";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
  sessionToken?: string,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body && !headers.has("Content-Type"))
    headers.set("Content-Type", "application/json");
  if (sessionToken) headers.set("Authorization", `Bearer ${sessionToken}`);

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    cache: "no-store",
  });
  if (!response.ok) {
    const fallback = `La solicitud no se ha podido completar (${response.status}).`;
    let message = fallback;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail && response.status < 500) message = body.detail;
    } catch {
      // The fallback intentionally avoids exposing an untrusted upstream body.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function fetchTask(taskId = SAMPLE_TASK_ID): Promise<Task> {
  return request<Task>(`/v1/tasks/${encodeURIComponent(taskId)}`);
}

export function createSession(taskId: string): Promise<SessionCapability> {
  return request<SessionCapability>("/v1/practice-sessions", {
    method: "POST",
    body: JSON.stringify({
      task_id: taskId,
      recording_consent: true,
      consent_policy_version: "mvp-v1",
    }),
  });
}

export function fetchAiPartnerTurn(
  session: SessionCapability,
): Promise<AiPartnerTurn> {
  return request<AiPartnerTurn>(
    `/v1/practice-sessions/${session.session_id}/ai-partner-turn`,
    { method: "POST" },
    session.session_token,
  );
}

export function authorizeUpload(
  session: SessionCapability,
  mimeType: string,
  extension: string,
  recordingKind:
    | "candidate_response"
    | "candidate_a_reference"
    | "candidate_b_reference"
    | "pair_response" = "candidate_response",
): Promise<UploadGrant> {
  return request<UploadGrant>(
    `/v1/practice-sessions/${session.session_id}/upload-url`,
    {
      method: "POST",
      body: JSON.stringify({
        mime_type: mimeType,
        extension,
        recording_kind: recordingKind,
      }),
    },
    session.session_token,
  );
}

export async function uploadRecording(
  grant: UploadGrant,
  blob: Blob,
  mimeType: string,
  onProgress: (percentage: number) => void,
): Promise<void> {
  if (grant.provider === "local") {
    if (!grant.upload_url)
      throw new Error("No se ha recibido una URL de subida.");
    await uploadWithProgress(
      grant.upload_url,
      blob,
      mimeType,
      grant.upload_token,
      onProgress,
    );
    return;
  }

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!supabaseUrl || !supabaseAnonKey || !grant.bucket) {
    throw new Error("La subida privada no está configurada en este entorno.");
  }
  onProgress(15);
  const client = createClient(supabaseUrl, supabaseAnonKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { error } = await client.storage
    .from(grant.bucket)
    .uploadToSignedUrl(grant.storage_path, grant.upload_token, blob, {
      contentType: mimeType,
    });
  if (error) throw new Error("No se ha podido subir la grabación privada.");
  onProgress(100);
}

function uploadWithProgress(
  url: string,
  blob: Blob,
  mimeType: string,
  uploadToken: string,
  onProgress: (percentage: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.setRequestHeader("Content-Type", mimeType);
    xhr.setRequestHeader("X-Upload-Token", uploadToken);
    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable)
        onProgress(Math.round((event.loaded / event.total) * 100));
    });
    xhr.addEventListener("load", () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else reject(new Error("La grabación no ha podido subirse."));
    });
    xhr.addEventListener("error", () =>
      reject(new Error("Se ha interrumpido la subida.")),
    );
    xhr.addEventListener("abort", () =>
      reject(new Error("Se ha cancelado la subida.")),
    );
    xhr.send(blob);
  });
}

export function completeRecording(
  session: SessionCapability,
  grant: UploadGrant,
  recording: RecordingResult,
  hash: string,
): Promise<SessionStatus> {
  return request<SessionStatus>(
    `/v1/practice-sessions/${session.session_id}/recording-complete`,
    {
      method: "POST",
      body: JSON.stringify({
        recording_id: grant.recording_id,
        mime_type: recording.mimeType,
        size_bytes: recording.blob.size,
        duration_ms: recording.durationMs,
        sha256: hash,
        response_started_at: recording.responseStartedAt,
        response_ended_at: recording.responseEndedAt,
      }),
    },
    session.session_token,
  );
}

export function fetchSessionStatus(
  session: SessionCapability,
): Promise<SessionStatus> {
  return request<SessionStatus>(
    `/v1/practice-sessions/${session.session_id}`,
    undefined,
    session.session_token,
  );
}

export function retrySession(
  session: SessionCapability,
): Promise<{ status: string }> {
  return request(
    `/v1/practice-sessions/${session.session_id}/retry`,
    { method: "POST" },
    session.session_token,
  );
}

export function fetchReport(
  session: SessionCapability,
  candidate?: "A" | "B",
): Promise<StudentReport> {
  const query = candidate ? `?candidate=${candidate}` : "";
  return request<StudentReport>(
    `/v1/practice-sessions/${session.session_id}/report${query}`,
    undefined,
    session.session_token,
  );
}

export type Part3Event = {
  sequence: number;
  phase: "discussion" | "decision";
  speaker: "student" | "ai_partner" | "examiner";
  started_at_ms: number;
  ended_at_ms: number;
  text: string;
  move?: string;
  prompt_reference?: string;
  latency_ms?: number;
};

export function savePart3Events(
  session: SessionCapability,
  events: Part3Event[],
): Promise<SessionStatus> {
  return request<SessionStatus>(
    `/v1/practice-sessions/${session.session_id}/part3-events`,
    { method: "POST", body: JSON.stringify({ events }) },
    session.session_token,
  );
}

export function deleteSession(
  session: SessionCapability,
): Promise<{ deleted: boolean }> {
  return request(
    `/v1/practice-sessions/${session.session_id}`,
    { method: "DELETE" },
    session.session_token,
  );
}
