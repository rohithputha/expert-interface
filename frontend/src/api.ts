import sampleCalls from "./data/sampleCalls.json";
import { fallbackRubric } from "./data/rubric";
import type { CallDetail, CallSummary, RatingRecord, RubricCriterion } from "./types";

const rawApiUrl = (import.meta.env.VITE_API_URL as string | undefined)?.trim().replace(/\/$/, "");
const configuredApiUrl = rawApiUrl && /^https?:\/\//i.test(rawApiUrl) ? rawApiUrl : rawApiUrl ? `https://${rawApiUrl}` : undefined;
const API_URL = configuredApiUrl ?? "";
const USE_API = Boolean(configuredApiUrl) || import.meta.env.DEV;

type RatingPayload = {
  user_id: string;
  call_id: string;
  ratings: Record<string, string>;
  evidence: string;
  timing: RatingRecord["timing"];
  status: "draft" | "submitted";
  complete?: boolean;
  reviewer?: string;
};

export type LoginPayload = {
  email: string;
  password: string;
};

export type Reviewer = {
  id: string;
  name: string;
  email: string;
  displayName?: string;
};

export async function loadInitialData(reviewerId?: string): Promise<{
  calls: CallSummary[];
  activeCall: CallDetail | null;
  rubric: RubricCriterion[];
}> {
  if (USE_API) {
    const reviewerQuery = reviewerId ? `?user_id=${encodeURIComponent(reviewerId)}` : "";
    const [callsResponse, rubricResponse] = await Promise.all([
      fetch(apiPath(`/api/calls${reviewerQuery}`)),
      fetch(apiPath("/api/rubric"))
    ]);
    if (!callsResponse.ok) {
      throw new Error(`Could not load calls (${callsResponse.status})`);
    }
    if (!rubricResponse.ok) {
      throw new Error(`Could not load rubric (${rubricResponse.status})`);
    }
    const callsJson = await callsResponse.json();
    const rubricJson = await rubricResponse.json();
    const calls = callsJson.calls as CallSummary[];
    const activeCall = calls[0] ? await loadCall(calls[0].id, reviewerId) : null;
    return { calls, activeCall, rubric: rubricJson.rubric as RubricCriterion[] };
  }

  const calls = sampleCalls as CallDetail[];
  return {
    calls: calls.map(toSummary),
    activeCall: calls[0] ?? null,
    rubric: fallbackRubric
  };
}

export async function loadCall(callId: string, reviewerId?: string): Promise<CallDetail> {
  if (USE_API) {
    const reviewerQuery = reviewerId ? `?user_id=${encodeURIComponent(reviewerId)}` : "";
    const response = await fetch(apiPath(`/api/calls/${callId}${reviewerQuery}`));
    if (!response.ok) {
      throw new Error("Call not found");
    }
    const json = await response.json();
    return json.call as CallDetail;
  }
  const call = (sampleCalls as CallDetail[]).find((item) => item.id === callId);
  if (!call) {
    throw new Error("Call not found");
  }
  return call;
}

export async function saveRating(payload: RatingPayload): Promise<RatingRecord | null> {
  if (!USE_API) {
    const record: RatingRecord = {
      id: `local_${Date.now()}`,
      callId: payload.call_id,
      ratings: payload.ratings as RatingRecord["ratings"],
      evidence: payload.evidence,
      timing: payload.timing,
      status: payload.status,
      reviewer: payload.reviewer,
      createdAt: new Date().toISOString()
    };
    window.localStorage.setItem(`rating:${payload.call_id}`, JSON.stringify(record));
    return record;
  }
  const response = await fetch(apiPath("/api/ratings"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error("Rating save failed");
  }
  const json = await response.json();
  return json.rating as RatingRecord;
}

export async function loginReviewer(payload: LoginPayload): Promise<Reviewer> {
  const email = payload.email.trim().toLowerCase();
  if (!email) {
    throw new Error("Enter your email to continue.");
  }
  if (!USE_API) {
    return { id: "local-reviewer", name: email, email };
  }
  const response = await fetch(apiPath("/api/login"), {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
  const json = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(json.error || "Login failed");
  }
  return json.reviewer as Reviewer;
}

function apiPath(path: string) {
  return API_URL ? `${API_URL}${path}` : path;
}

export function mediaPath(path: string) {
  if (!path.startsWith("/")) return path;
  return apiPath(path);
}

function toSummary(call: CallDetail): CallSummary {
  return {
    id: call.id,
    expectedRating: call.expectedRating,
    reasoning: call.reasoning,
    recordingUrl: call.recordingUrl,
    summary: call.summary,
    reviewStatus: call.reviewStatus,
    reviewedAt: call.reviewedAt,
    reviewedBy: call.reviewedBy
  };
}
