import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Headphones,
  ListChecks,
  Menu,
  Save,
  Search,
  ShieldCheck,
  X,
  Wrench
} from "lucide-react";
import { loadCall, loadInitialData, saveRating } from "./api";
import type { CallDetail, CallSummary, RatingValue, RubricCriterion } from "./types";
import "./styles.css";

type ViewMode = "conversation" | "tools";

function App() {
  const [calls, setCalls] = useState<CallSummary[]>([]);
  const [activeCall, setActiveCall] = useState<CallDetail | null>(null);
  const [rubric, setRubric] = useState<RubricCriterion[]>([]);
  const [criterionIndex, setCriterionIndex] = useState(0);
  const [subIndex, setSubIndex] = useState(0);
  const [mode, setMode] = useState<ViewMode>("conversation");
  const [ratings, setRatings] = useState<Record<string, RatingValue>>({});
  const [evidenceBySubcriterion, setEvidenceBySubcriterion] = useState<Record<string, string>>({});
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");
  const [queueOpen, setQueueOpen] = useState(false);
  const [completedIds, setCompletedIds] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    loadInitialData().then((data) => {
      setCalls(data.calls);
      setActiveCall(data.activeCall);
      setRubric(data.rubric);
    });
  }, []);

  const activeCriterion = rubric[criterionIndex];
  const activeSubcriterion = activeCriterion?.subcriteria[subIndex];
  const totalSubcriteria = rubric.reduce((sum, item) => sum + item.subcriteria.length, 0);
  const flatIndex =
    rubric.slice(0, criterionIndex).reduce((sum, item) => sum + item.subcriteria.length, 0) + subIndex + 1;
  const activePosition = Math.max(0, calls.findIndex((call) => call.id === activeCall?.id));
  const progress = totalSubcriteria ? Math.round((Object.keys(ratings).length / totalSubcriteria) * 100) : 0;
  const ungradedCalls = useMemo(
    () => calls.filter((call) => call.reviewStatus !== "submitted" && !completedIds.has(call.id)),
    [calls, completedIds]
  );
  const completedSubcriterionCount = useMemo(
    () =>
      rubric
        .flatMap((criterion) => criterion.subcriteria)
        .filter((subcriterion) => ratings[subcriterion.id] && evidenceBySubcriterion[subcriterion.id]?.trim()).length,
    [evidenceBySubcriterion, ratings, rubric]
  );
  const filteredCalls = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return ungradedCalls;
    return ungradedCalls.filter((call) => {
      const haystack = `${call.id} ${call.summary.turnCount} ${call.summary.toolCount}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [query, ungradedCalls]);

  function activeSubcriterionReady() {
    if (!activeSubcriterion) return false;
    return Boolean(ratings[activeSubcriterion.id] && evidenceBySubcriterion[activeSubcriterion.id]?.trim());
  }

  function firstIncompleteSubcriterion() {
    for (let nextCriterionIndex = 0; nextCriterionIndex < rubric.length; nextCriterionIndex += 1) {
      const criterion = rubric[nextCriterionIndex];
      for (let nextSubIndex = 0; nextSubIndex < criterion.subcriteria.length; nextSubIndex += 1) {
        const subcriterion = criterion.subcriteria[nextSubIndex];
        if (!ratings[subcriterion.id] || !evidenceBySubcriterion[subcriterion.id]?.trim()) {
          return { criterionIndex: nextCriterionIndex, subIndex: nextSubIndex, title: subcriterion.title };
        }
      }
    }
    return null;
  }

  async function selectCall(callId: string) {
    const next = await loadCall(callId);
    setActiveCall(next);
    setCriterionIndex(0);
    setSubIndex(0);
    setRatings({});
    setEvidenceBySubcriterion({});
    setNotice("");
    setQueueOpen(false);
  }

  function stepRubric(direction: 1 | -1) {
    if (direction === 1 && activeSubcriterion && !activeSubcriterionReady()) {
      setNotice("Select a rating and add evidence before moving to the next question.");
      return;
    }
    let nextCriterion = criterionIndex;
    let nextSub = subIndex + direction;
    if (nextSub >= (rubric[nextCriterion]?.subcriteria.length ?? 0)) {
      nextCriterion += 1;
      nextSub = 0;
    }
    if (nextSub < 0) {
      nextCriterion -= 1;
      nextSub = Math.max(0, (rubric[nextCriterion]?.subcriteria.length ?? 1) - 1);
    }
    if (nextCriterion >= 0 && nextCriterion < rubric.length) {
      setCriterionIndex(nextCriterion);
      setSubIndex(nextSub);
      setNotice("");
    }
  }

  async function submit(status: "draft" | "submitted") {
    if (!activeCall || !activeSubcriterion) return;
    if (status === "submitted") {
      const firstIncomplete = firstIncompleteSubcriterion();
      if (firstIncomplete) {
        setCriterionIndex(firstIncomplete.criterionIndex);
        setSubIndex(firstIncomplete.subIndex);
        setNotice(`Complete rating and evidence for "${firstIncomplete.title}" before submitting.`);
        return;
      }
    }
    await saveRating({
      call_id: activeCall.id,
      ratings,
      evidence: JSON.stringify(evidenceBySubcriterion),
      status
    });
    if (status === "submitted") {
      const nextCompleted = new Set(completedIds);
      nextCompleted.add(activeCall.id);
      setCompletedIds(nextCompleted);
      setCalls((current) =>
        current.map((call) => (call.id === activeCall.id ? { ...call, reviewStatus: "submitted" } : call))
      );
      const nextCall = ungradedCalls.find((call) => call.id !== activeCall.id);
      if (nextCall) {
        await selectCall(nextCall.id);
        setNotice("Rating submitted. Moved to the next ungraded call.");
      } else {
        setNotice("Rating submitted. Queue complete.");
      }
      return;
    }
    setNotice("Draft saved on this device.");
  }

  if (!activeCall || !activeCriterion || !activeSubcriterion) {
    return <main className="loading">Loading call review workspace...</main>;
  }

  return (
    <main className="app-shell">
      <button className="queue-toggle" onClick={() => setQueueOpen(true)} aria-label="Open ungraded calls queue">
        <Menu size={18} />
        <span>{ungradedCalls.length}</span>
      </button>
      {queueOpen ? <button className="queue-backdrop" onClick={() => setQueueOpen(false)} aria-label="Close queue" /> : null}

      <aside className={`queue-panel ${queueOpen ? "is-open" : ""}`} aria-label="Ungraded calls queue">
        <div className="queue-header">
          <div>
            <p className="eyebrow">Ungraded queue</p>
            <h1>Calls to rate</h1>
          </div>
          <button className="queue-close" onClick={() => setQueueOpen(false)} aria-label="Close queue">
            <X size={19} />
          </button>
          <div className="queue-count">{ungradedCalls.length}</div>
        </div>
        <label className="search-box">
          <Search size={16} aria-hidden="true" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search calls" />
        </label>
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
      </aside>

      <section className="phone-workspace" aria-label="Active call rating">
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
          <div className="criterion-topline">
            <span>
              Criterion {criterionIndex + 1} of {rubric.length} · {completedSubcriterionCount}/{totalSubcriteria} done
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

          <label className="notes-label">
            Evidence / notes *
            <textarea
              value={evidenceBySubcriterion[activeSubcriterion.id] ?? ""}
              onChange={(event) =>
                setEvidenceBySubcriterion((current) => ({
                  ...current,
                  [activeSubcriterion.id]: event.target.value
                }))
              }
              rows={3}
            />
          </label>

          {notice ? <p className="notice">{notice}</p> : null}

          <div className="action-bar">
            <button className="secondary-action" onClick={() => stepRubric(-1)} disabled={flatIndex === 1}>
              <ArrowLeft size={18} /> Back
            </button>
            <button className="secondary-action save-action" onClick={() => submit("draft")}>
              <Save size={18} /> Draft
            </button>
            {flatIndex === totalSubcriteria ? (
              <button className="primary-action" onClick={() => submit("submitted")}>
                Submit <Check size={18} />
              </button>
            ) : (
              <button className="primary-action" onClick={() => stepRubric(1)}>
                Next <ArrowRight size={18} />
              </button>
            )}
          </div>
        </section>
      </section>
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

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
