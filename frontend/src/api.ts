import sampleCalls from "./data/sampleCalls.json";
import { fallbackRubric } from "./data/rubric";
import type { CallDetail, CallSummary, RubricCriterion } from "./types";

const API_URL = import.meta.env.VITE_API_URL as string | undefined;

type RatingPayload = {
  call_id: string;
  ratings: Record<string, string>;
  evidence: string;
  status: "submitted";
};

export async function loadInitialData(): Promise<{
  calls: CallSummary[];
  activeCall: CallDetail | null;
  rubric: RubricCriterion[];
}> {
  if (API_URL) {
    const [callsResponse, rubricResponse] = await Promise.all([
      fetch(`${API_URL}/api/calls`),
      fetch(`${API_URL}/api/rubric`)
    ]);
    const callsJson = await callsResponse.json();
    const rubricJson = await rubricResponse.json();
    const calls = callsJson.calls as CallSummary[];
    const activeCall = calls[0] ? await loadCall(calls[0].id) : null;
    return { calls, activeCall, rubric: rubricJson.rubric as RubricCriterion[] };
  }

  const calls = sampleCalls as CallDetail[];
  return {
    calls: calls.map(toSummary),
    activeCall: calls[0] ?? null,
    rubric: fallbackRubric
  };
}

export async function loadCall(callId: string): Promise<CallDetail> {
  if (API_URL) {
    const response = await fetch(`${API_URL}/api/calls/${callId}`);
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

export async function saveRating(payload: RatingPayload): Promise<void> {
  if (!API_URL) {
    window.localStorage.setItem(`rating:${payload.call_id}`, JSON.stringify(payload));
    return;
  }
  const response = await fetch(`${API_URL}/api/ratings`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error("Rating save failed");
  }
}

function toSummary(call: CallDetail): CallSummary {
  return {
    id: call.id,
    expectedRating: call.expectedRating,
    reasoning: call.reasoning,
    recordingUrl: call.recordingUrl,
    summary: call.summary,
    reviewStatus: call.reviewStatus,
    reviewedAt: call.reviewedAt
  };
}
