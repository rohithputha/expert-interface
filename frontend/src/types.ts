export type RatingValue = "strong" | "adequate" | "weak" | "fail";

export type TranscriptTurn = {
  id: string;
  speaker: "agent" | "user";
  text: string;
  timestamp: string;
};

export type ToolEvent = {
  id: string;
  name: string;
  args: unknown;
  result: unknown;
  summary: string;
};

export type CallSummary = {
  id: string;
  expectedRating: "GOLDEN" | "BAD" | string;
  reasoning: string;
  recordingUrl: string;
  summary: {
    index: number;
    turnCount: number;
    toolCount: number;
    toolNames: string[];
    durationLabel: string;
    issueTags: string[];
  };
  reviewStatus: string;
  reviewedAt?: string | null;
};

export type CallDetail = CallSummary & {
  transcript: TranscriptTurn[];
  toolEvents: ToolEvent[];
  ratingsHistory: unknown[];
};

export type RubricOption = {
  value: RatingValue;
  label: string;
  description: string;
};

export type RubricSubcriterion = {
  id: string;
  title: string;
  options: RubricOption[];
};

export type RubricCriterion = {
  id: string;
  title: string;
  subcriteria: RubricSubcriterion[];
};
