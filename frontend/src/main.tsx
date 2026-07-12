import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowLeft,
  ArrowRight,
  BarChart3,
  Check,
  ChevronsUpDown,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Headphones,
  ListChecks,
  LogOut,
  Menu,
  RotateCcw,
  Search,
  ShieldCheck,
  UserRound,
  X,
  Wrench
} from "lucide-react";
import { loginReviewer, loadCall, loadInitialData, saveRating } from "./api";
import type { CallDetail, CallSummary, RatingValue, RubricCriterion } from "./types";
import "./styles.css";

type ViewMode = "conversation" | "tools";
type LoadState = "loading" | "ready" | "empty" | "error";
type Reviewer = { name: string };

const REVIEWER_KEY = "expert-interface:reviewer";

function App() {
  const [reviewer, setReviewer] = useState<Reviewer | null>(() => readStoredReviewer());
  const [calls, setCalls] = useState<CallSummary[]>([]);
  const [activeCall, setActiveCall] = useState<CallDetail | null>(null);
  const [rubric, setRubric] = useState<RubricCriterion[]>([]);
  const [loadState, setLoadState] = useState<LoadState>("loading");
  const [loadError, setLoadError] = useState("");
  const [criterionIndex, setCriterionIndex] = useState(0);
  const [subIndex, setSubIndex] = useState(0);
  const [mode, setMode] = useState<ViewMode>("conversation");
  const [ratings, setRatings] = useState<Record<string, RatingValue>>({});
  const [evidenceByCriterion, setEvidenceByCriterion] = useState<Record<string, string>>({});
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");
  const [queueOpen, setQueueOpen] = useState(false);
  const [completedIds, setCompletedIds] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    if (!reviewer) return;
    setLoadState("loading");
    loadInitialData()
      .then((data) => {
        setCalls(data.calls);
        setActiveCall(data.activeCall);
        setRubric(data.rubric);
        hydrateRatingState(data.activeCall, data.rubric);
        setLoadState(data.activeCall ? "ready" : "empty");
      })
      .catch((error: unknown) => {
        setLoadError(error instanceof Error ? error.message : "Could not load call review data.");
        setLoadState("error");
      });
  }, [reviewer]);

  const activeCriterion = rubric[criterionIndex];
  const activeSubcriterion = activeCriterion?.subcriteria[subIndex];
  const isEvidencePage = Boolean(activeCriterion && subIndex === activeCriterion.subcriteria.length);
  const totalSubcriteria = rubric.reduce((sum, item) => sum + item.subcriteria.length, 0);
  const totalPages = totalSubcriteria + rubric.length;
  const flatIndex =
    rubric.slice(0, criterionIndex).reduce((sum, item) => sum + item.subcriteria.length + 1, 0) + subIndex + 1;
  const activePosition = Math.max(0, calls.findIndex((call) => call.id === activeCall?.id));
  const progress = totalSubcriteria ? Math.round((Object.keys(ratings).length / totalSubcriteria) * 100) : 0;
  const isEditingRatedCall = activeCall?.reviewStatus === "submitted";
  const ungradedCalls = useMemo(
    () => calls.filter((call) => call.reviewStatus !== "submitted" && !completedIds.has(call.id)),
    [calls, completedIds]
  );
  const ratedCalls = useMemo(() => calls.filter((call) => call.reviewStatus === "submitted"), [calls]);
  const myRatedCalls = useMemo(
    () => ratedCalls.filter((call) => !call.reviewedBy || call.reviewedBy === reviewer?.name),
    [ratedCalls, reviewer?.name]
  );
  const completedSubcriterionCount = useMemo(
    () =>
      rubric
        .flatMap((criterion) => criterion.subcriteria)
        .filter((subcriterion) => ratings[subcriterion.id]).length,
    [ratings, rubric]
  );
  const filteredCalls = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return ungradedCalls;
    return ungradedCalls.filter((call) => {
      const haystack = `${call.id} ${call.summary.turnCount} ${call.summary.toolCount}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [query, ungradedCalls]);
  const filteredRatedCalls = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return myRatedCalls;
    return myRatedCalls.filter((call) => {
      const haystack = `${call.id} ${call.summary.turnCount} ${call.summary.toolCount} ${call.reviewedBy ?? ""}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [myRatedCalls, query]);

  function activeSubcriterionReady() {
    if (!activeSubcriterion) return false;
    return Boolean(ratings[activeSubcriterion.id]);
  }

  function activeEvidenceReady() {
    if (!activeCriterion) return false;
    return Boolean(evidenceByCriterion[activeCriterion.id]?.trim());
  }

  function firstIncompletePage() {
    for (let nextCriterionIndex = 0; nextCriterionIndex < rubric.length; nextCriterionIndex += 1) {
      const criterion = rubric[nextCriterionIndex];
      for (let nextSubIndex = 0; nextSubIndex < criterion.subcriteria.length; nextSubIndex += 1) {
        const subcriterion = criterion.subcriteria[nextSubIndex];
        if (!ratings[subcriterion.id]) {
          return { criterionIndex: nextCriterionIndex, subIndex: nextSubIndex, title: subcriterion.title };
        }
      }
      if (!evidenceByCriterion[criterion.id]?.trim()) {
        return { criterionIndex: nextCriterionIndex, subIndex: criterion.subcriteria.length, title: `${criterion.title} evidence` };
      }
    }
    return null;
  }

  async function selectCall(callId: string) {
    const next = await loadCall(callId);
    setActiveCall(next);
    setCriterionIndex(0);
    setSubIndex(0);
    hydrateRatingState(next, rubric);
    setNotice("");
    setQueueOpen(false);
  }

  function stepRubric(direction: 1 | -1) {
    if (direction === 1 && activeSubcriterion && !activeSubcriterionReady()) {
      setNotice("Select a rating before moving to the next question.");
      return;
    }
    if (direction === 1 && isEvidencePage && !activeEvidenceReady()) {
      setNotice("Add evidence / notes before moving to the next criterion.");
      return;
    }
    let nextCriterion = criterionIndex;
    let nextSub = subIndex + direction;
    if (nextSub > (rubric[nextCriterion]?.subcriteria.length ?? 0)) {
      nextCriterion += 1;
      nextSub = 0;
    }
    if (nextSub < 0) {
      nextCriterion -= 1;
      nextSub = Math.max(0, rubric[nextCriterion]?.subcriteria.length ?? 0);
    }
    if (nextCriterion >= 0 && nextCriterion < rubric.length) {
      setCriterionIndex(nextCriterion);
      setSubIndex(nextSub);
      setNotice("");
    }
  }

  function selectSubcriterion(flatValue: string) {
    const targetFlatIndex = Number(flatValue);
    let cursor = 0;
    for (let nextCriterionIndex = 0; nextCriterionIndex < rubric.length; nextCriterionIndex += 1) {
      const criterion = rubric[nextCriterionIndex];
      for (let nextSubIndex = 0; nextSubIndex <= criterion.subcriteria.length; nextSubIndex += 1) {
        cursor += 1;
        if (cursor === targetFlatIndex) {
          setCriterionIndex(nextCriterionIndex);
          setSubIndex(nextSubIndex);
          setNotice("");
          return;
        }
      }
    }
  }

  async function submit(status: "submitted") {
    if (!activeCall || !activeCriterion || !reviewer) return;
    if (isEditingRatedCall) {
      if (isEvidencePage && !activeEvidenceReady()) {
        setNotice("Add evidence / notes for this criterion before updating.");
        return;
      }
      if (!isEvidencePage && !activeSubcriterionReady()) {
        setNotice("Select a rating for this item before updating.");
        return;
      }
    } else {
      const firstIncomplete = firstIncompletePage();
      if (firstIncomplete) {
        setCriterionIndex(firstIncomplete.criterionIndex);
        setSubIndex(firstIncomplete.subIndex);
        setNotice(`Complete "${firstIncomplete.title}" before submitting.`);
        return;
      }
    }
    const saved = await saveRating({
      call_id: activeCall.id,
      ratings,
      evidence: JSON.stringify(evidenceByCriterion),
      status,
      reviewer: reviewer.name
    });
    const nextCompleted = new Set(completedIds);
    nextCompleted.add(activeCall.id);
    setCompletedIds(nextCompleted);
    setCalls((current) =>
      current.map((call) =>
        call.id === activeCall.id
          ? { ...call, reviewStatus: "submitted", reviewedAt: saved?.createdAt ?? new Date().toISOString(), reviewedBy: reviewer.name }
          : call
      )
    );
    setActiveCall((current) =>
      current
        ? {
            ...current,
            reviewStatus: "submitted",
            reviewedAt: saved?.createdAt ?? new Date().toISOString(),
            reviewedBy: reviewer.name,
            ratingsHistory: saved ? [saved, ...current.ratingsHistory] : current.ratingsHistory
          }
        : current
    );
    if (isEditingRatedCall) {
      setNotice("Rating updated.");
      return;
    }
    const nextCall = ungradedCalls.find((call) => call.id !== activeCall.id);
    if (nextCall) {
      await selectCall(nextCall.id);
      setNotice("Rating submitted. Moved to the next ungraded call.");
    } else {
      setNotice("Rating submitted. Queue complete.");
    }
  }

  function hydrateRatingState(call: CallDetail | null, rubricItems: RubricCriterion[]) {
    const latest = call?.ratingsHistory?.[0];
    setRatings(latest?.ratings ?? {});
    setEvidenceByCriterion(parseCriterionEvidence(latest?.evidence, rubricItems));
  }

  function logout() {
    window.localStorage.removeItem(REVIEWER_KEY);
    setReviewer(null);
    setCalls([]);
    setActiveCall(null);
    setRatings({});
    setEvidenceByCriterion({});
    setQueueOpen(false);
  }

  if (!reviewer) {
    return (
      <LoginScreen
        onLogin={(nextReviewer) => {
          window.localStorage.setItem(REVIEWER_KEY, JSON.stringify(nextReviewer));
          setReviewer(nextReviewer);
        }}
      />
    );
  }

  if (loadState === "loading") {
    return <main className="loading">Loading call review workspace...</main>;
  }

  if (loadState === "error") {
    return (
      <main className="loading state-message">
        <strong>Could not load calls</strong>
        <span>{loadError}</span>
        <small>Check `VITE_API_URL`, CORS, and `/api/calls` on the backend.</small>
      </main>
    );
  }

  if (loadState === "empty" || !activeCall || !activeCriterion) {
    return (
      <main className="loading state-message">
        <strong>No calls loaded</strong>
        <span>The backend is reachable, but it returned an empty call queue.</span>
        <small>Import calls into the connected database, then refresh this page.</small>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <button className="queue-toggle" onClick={() => setQueueOpen(true)} aria-label="Open ungraded calls queue">
        <BarChart3 size={18} />
        <span>{ungradedCalls.length}</span>
      </button>
      {queueOpen ? <button className="queue-backdrop" onClick={() => setQueueOpen(false)} aria-label="Close queue" /> : null}

      <aside className={`queue-panel ${queueOpen ? "is-open" : ""}`} aria-label="Review dashboard and call lists">
        <div className="queue-header">
          <div>
            <p className="eyebrow">Dashboard</p>
            <h1>{reviewer.name}</h1>
          </div>
          <button className="queue-close" onClick={() => setQueueOpen(false)} aria-label="Close queue">
            <X size={19} />
          </button>
          <div className="queue-count">{ungradedCalls.length}</div>
        </div>
        <div className="dashboard-grid" aria-label="Reviewer progress">
          <div>
            <span>{myRatedCalls.length}</span>
            <small>Done</small>
          </div>
          <div>
            <span>{ungradedCalls.length}</span>
            <small>Queue</small>
          </div>
          <div>
            <span>{calls.length}</span>
            <small>Total</small>
          </div>
        </div>
        <button className="logout-button" onClick={logout}>
          <LogOut size={16} /> Sign out
        </button>
        <label className="search-box">
          <Search size={16} aria-hidden="true" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search calls" />
        </label>
        <p className="list-heading">Queue</p>
        <div className="call-list">
          {!filteredCalls.length ? <p className="empty-queue">No ungraded calls left.</p> : null}
          {filteredCalls.map((call) => (
            <button
              className={`call-row ${call.id === activeCall.id ? "is-active" : ""}`}
              key={call.id}
              onClick={() => selectCall(call.id)}
            >
              <span className="call-row-main">
                <strong>{shortId(call.id)}</strong>
                <span>
                  {call.summary.turnCount} turns / {call.summary.toolCount} tools
                </span>
              </span>
              <span>{call.summary.durationLabel}</span>
            </button>
          ))}
        </div>
        <p className="list-heading">Rated calls</p>
        <div className="call-list rated-list">
          {!filteredRatedCalls.length ? <p className="empty-queue">No rated calls yet.</p> : null}
          {filteredRatedCalls.map((call) => (
            <button
              className={`call-row ${call.id === activeCall.id ? "is-active" : ""}`}
              key={call.id}
              onClick={() => selectCall(call.id)}
            >
              <span className="call-row-main">
                <strong>{shortId(call.id)}</strong>
                <span>{call.reviewedAt ? formatDate(call.reviewedAt) : "Ready to edit"}</span>
              </span>
              <span className="edit-chip">
                <RotateCcw size={13} /> Edit
              </span>
            </button>
          ))}
        </div>
      </aside>

      <section className="phone-workspace" aria-label="Active call rating">
        <div className="mobile-dashboard" aria-label="Dashboard summary">
          <div>
            <strong>{myRatedCalls.length}</strong>
            <span>Done</span>
          </div>
          <div>
            <strong>{ungradedCalls.length}</strong>
            <span>Queue</span>
          </div>
          <button onClick={() => setQueueOpen(true)}>
            <Menu size={16} /> Calls
          </button>
        </div>
        <header className="player">
          <div className="status-strip">
            <Headphones size={16} aria-hidden="true" />
            <span>
              Call {activePosition + 1} of {calls.length}
            </span>
            <span>{progress}% scored</span>
          </div>
          <div className="audio-row">
            <audio src={activeCall.recordingUrl} controls preload="metadata" />
          </div>
          <div className="skip-row">
            <button>
              <ChevronLeft size={16} /> 15s
            </button>
            <button>
              15s <ChevronRight size={16} />
            </button>
          </div>
        </header>

        <div className="tabs" role="tablist">
          <button className={mode === "conversation" ? "is-active" : ""} onClick={() => setMode("conversation")}>
            <ClipboardCheck size={17} /> Conversation
          </button>
          <button className={mode === "tools" ? "is-active" : ""} onClick={() => setMode("tools")}>
            <Wrench size={17} /> Tool calls
          </button>
        </div>

        <section className="evidence-view">
          {mode === "conversation" ? <Conversation call={activeCall} /> : <ToolCalls call={activeCall} />}
        </section>

        <section className="rating-card">
          {isEditingRatedCall ? (
            <label className="edit-selector">
              <span>
                <RotateCcw size={15} /> Edit item
              </span>
              <div>
                <select value={flatIndex} onChange={(event) => selectSubcriterion(event.target.value)}>
                  {rubric.flatMap((criterion, outerIndex) =>
                    [...criterion.subcriteria, null].map((subcriterion, innerIndex) => {
                      const value =
                        rubric.slice(0, outerIndex).reduce((sum, item) => sum + item.subcriteria.length + 1, 0) +
                        innerIndex +
                        1;
                      return (
                        <option value={value} key={subcriterion?.id ?? `${criterion.id}-evidence`}>
                          {value}. {criterion.title} - {subcriterion?.title ?? "Evidence / notes"}
                        </option>
                      );
                    })
                  )}
                </select>
                <ChevronsUpDown size={15} aria-hidden="true" />
              </div>
            </label>
          ) : null}
          <div className="criterion-topline">
            <span>
              Criterion {criterionIndex + 1} of {rubric.length} · {completedSubcriterionCount}/{totalSubcriteria} rated
            </span>
            <div className="dots" aria-hidden="true">
              {rubric.map((item) => (
                <span key={item.id} className={item.id === activeCriterion.id ? "is-active" : ""} />
              ))}
            </div>
          </div>
          <div className="criterion-title">
            <ShieldCheck size={19} aria-hidden="true" />
            <div>
              <h2>{activeCriterion.title}</h2>
              <p>{activeCriterion.description}</p>
            </div>
          </div>
          {isEvidencePage ? (
            <section className="criterion-evidence-page">
              <div className="subcriterion-heading">
                <h3>Evidence / notes</h3>
                <span>Required</span>
              </div>
              <label className="notes-label criterion-notes">
                Evidence for {activeCriterion.title} *
                <textarea
                  value={evidenceByCriterion[activeCriterion.id] ?? ""}
                  onChange={(event) =>
                    setEvidenceByCriterion((current) => ({
                      ...current,
                      [activeCriterion.id]: event.target.value
                    }))
                  }
                  rows={5}
                />
              </label>
            </section>
          ) : activeSubcriterion ? (
            <>
              <div className="subcriterion-heading">
                <h3>{activeSubcriterion.title}</h3>
                <span>
                  Sub {subIndex + 1} of {activeCriterion.subcriteria.length}
                </span>
              </div>

              <fieldset className="rating-options">
                <legend className="sr-only">Rating options</legend>
                {activeSubcriterion.options.map((option) => (
                  <label className="rating-option" key={option.value}>
                    <input
                      type="radio"
                      name={activeSubcriterion.id}
                      checked={ratings[activeSubcriterion.id] === option.value}
                      onChange={() => setRatings((current) => ({ ...current, [activeSubcriterion.id]: option.value }))}
                    />
                    <span className="radio-dot" aria-hidden="true" />
                    <span>
                      <span className="option-head">
                        <strong>
                          {option.label}
                          {option.value === "strong" ? " ✓" : option.value === "fail" ? " ×" : ""}
                        </strong>
                        <em>{option.points} pts</em>
                      </span>
                      <small>{option.description}</small>
                    </span>
                  </label>
                ))}
              </fieldset>
            </>
          ) : null}

          {notice ? <p className="notice">{notice}</p> : null}

          <div className="action-bar">
            {isEditingRatedCall ? (
              <button className="primary-action full-action" onClick={() => submit("submitted")}>
                Update <Check size={18} />
              </button>
            ) : (
              <>
                <button className="secondary-action" onClick={() => stepRubric(-1)} disabled={flatIndex === 1}>
                  <ArrowLeft size={18} /> Back
                </button>
                {flatIndex === totalPages ? (
                  <button className="primary-action" onClick={() => submit("submitted")}>
                    Submit <Check size={18} />
                  </button>
                ) : (
                  <button className="primary-action" onClick={() => stepRubric(1)}>
                    Next <ArrowRight size={18} />
                  </button>
                )}
              </>
            )}
          </div>
        </section>
      </section>
    </main>
  );
}

function LoginScreen({ onLogin }: { onLogin: (reviewer: Reviewer) => void }) {
  const [name, setName] = useState("");
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function submitLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      const reviewer = await loginReviewer({ name, passcode });
      onLogin(reviewer);
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : "Login failed");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="login-shell">
      <form className="login-card" onSubmit={submitLogin}>
        <div className="login-icon">
          <UserRound size={24} />
        </div>
        <div>
          <p className="eyebrow">Expert review</p>
          <h1>Sign in</h1>
        </div>
        <label>
          Name
          <input value={name} onChange={(event) => setName(event.target.value)} autoComplete="name" />
        </label>
        <label>
          Passcode
          <input
            value={passcode}
            onChange={(event) => setPasscode(event.target.value)}
            type="password"
            inputMode="numeric"
            autoComplete="current-password"
          />
        </label>
        {error ? <p className="notice login-error">{error}</p> : null}
        <button className="primary-action" disabled={isSubmitting}>
          {isSubmitting ? "Signing in..." : "Continue"}
        </button>
      </form>
    </main>
  );
}

function Conversation({ call }: { call: CallDetail }) {
  const [turnIndex, setTurnIndex] = useState(0);
  const visible = call.transcript.slice(turnIndex, turnIndex + 1);
  return (
    <div className="conversation">
      <button className="turn-nav" onClick={() => setTurnIndex((value) => Math.max(0, value - 1))} aria-label="Previous turn">
        <ChevronLeft size={18} />
      </button>
      <div className="turn-stack">
        {visible.map((turn) => (
          <article className={`turn ${turn.speaker}`} key={turn.id}>
            <span>
              {turn.speaker} · {turn.timestamp}
            </span>
            <p>{turn.text}</p>
          </article>
        ))}
        <div className="turn-count">
          {Math.min(turnIndex + 1, call.transcript.length)} / {call.transcript.length} turns
        </div>
      </div>
      <button
        className="turn-nav"
        onClick={() => setTurnIndex((value) => Math.min(call.transcript.length - 1, value + 1))}
        aria-label="Next turn"
      >
        <ChevronRight size={18} />
      </button>
    </div>
  );
}

function ToolCalls({ call }: { call: CallDetail }) {
  if (!call.toolEvents.length) {
    return (
      <div className="empty-tools">
        <ListChecks size={24} />
        <p>No tool calls were captured for this call.</p>
      </div>
    );
  }
  return (
    <div className="tool-list">
      {call.toolEvents.map((event) => (
        <details key={event.id} className="tool-event">
          <summary>
            <span>{event.name}</span>
            <small>{event.summary}</small>
          </summary>
          <pre>{JSON.stringify({ args: event.args, result: event.result }, null, 2)}</pre>
        </details>
      ))}
    </div>
  );
}

function shortId(callId: string) {
  return callId.replace("call_", "").slice(0, 8);
}

function parseCriterionEvidence(evidence: string | undefined, rubricItems: RubricCriterion[]) {
  if (!evidence) return {};
  try {
    const parsed = JSON.parse(evidence);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      const evidenceMap = parsed as Record<string, string>;
      const hasCriterionKeys = rubricItems.some((criterion) => evidenceMap[criterion.id]);
      if (hasCriterionKeys) {
        return evidenceMap;
      }
      return rubricItems.reduce<Record<string, string>>((current, criterion) => {
        const notes = criterion.subcriteria
          .map((subcriterion) => evidenceMap[subcriterion.id]?.trim())
          .filter(Boolean);
        if (notes.length) {
          current[criterion.id] = notes.join("\n\n");
        }
        return current;
      }, {});
    }
  } catch {
    return {};
  }
  return {};
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Rated";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function readStoredReviewer(): Reviewer | null {
  try {
    const stored = window.localStorage.getItem(REVIEWER_KEY);
    if (!stored) return null;
    const parsed = JSON.parse(stored);
    return parsed?.name ? { name: parsed.name } : null;
  } catch {
    return null;
  }
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
