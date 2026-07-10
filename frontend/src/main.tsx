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
  Pause,
  Play,
  Save,
  Search,
  ShieldCheck,
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
  const [evidence, setEvidence] = useState("");
  const [isPlaying, setIsPlaying] = useState(false);
  const [query, setQuery] = useState("");
  const [notice, setNotice] = useState("");

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
  const filteredCalls = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return calls;
    return calls.filter((call) => {
      const haystack = `${call.id} ${call.expectedRating} ${call.reasoning} ${call.summary.issueTags.join(" ")}`.toLowerCase();
      return haystack.includes(needle);
    });
  }, [calls, query]);

  async function selectCall(callId: string) {
    const next = await loadCall(callId);
    setActiveCall(next);
    setCriterionIndex(0);
    setSubIndex(0);
    setRatings({});
    setEvidence("");
    setNotice("");
  }

  function stepRubric(direction: 1 | -1) {
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
    }
  }

  async function submit(status: "draft" | "submitted") {
    if (!activeCall || !activeSubcriterion) return;
    if (status === "submitted" && (!ratings[activeSubcriterion.id] || !evidence.trim())) {
      setNotice("Select a rating and add evidence before submitting.");
      return;
    }
    await saveRating({
      call_id: activeCall.id,
      ratings,
      evidence,
      status
    });
    setNotice(status === "draft" ? "Draft saved on this device." : "Rating submitted.");
  }

  if (!activeCall || !activeCriterion || !activeSubcriterion) {
    return <main className="loading">Loading call review workspace...</main>;
  }

  return (
    <main className="app-shell">
      <aside className="queue-panel" aria-label="Call queue">
        <div className="queue-header">
          <div>
            <p className="eyebrow">Review queue</p>
            <h1>Call ratings</h1>
          </div>
          <div className="queue-count">{calls.length}</div>
        </div>
        <label className="search-box">
          <Search size={16} aria-hidden="true" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search calls" />
        </label>
        <div className="call-list">
          {filteredCalls.map((call) => (
            <button
              className={`call-row ${call.id === activeCall.id ? "is-active" : ""}`}
              key={call.id}
              onClick={() => selectCall(call.id)}
            >
              <span className={`rating-pill ${call.expectedRating.toLowerCase()}`}>{call.expectedRating}</span>
              <span className="call-row-main">
                <strong>{shortId(call.id)}</strong>
                <span>{call.summary.issueTags.join(" / ") || "general review"}</span>
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
            <button className="play-button" onClick={() => setIsPlaying((value) => !value)} aria-label="Toggle playback">
              {isPlaying ? <Pause size={28} /> : <Play size={28} />}
            </button>
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
              Criterion {criterionIndex + 1} of {rubric.length}
            </span>
            <div className="dots" aria-hidden="true">
              {rubric.map((item) => (
                <span key={item.id} className={item.id === activeCriterion.id ? "is-active" : ""} />
              ))}
            </div>
          </div>
          <div className="criterion-title">
            <ShieldCheck size={19} aria-hidden="true" />
            <h2>{activeCriterion.title}</h2>
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
                  <strong>
                    {option.label}
                    {option.value === "strong" ? " ✓" : option.value === "fail" ? " ×" : ""}
                  </strong>
                  <small>{option.description}</small>
                </span>
              </label>
            ))}
          </fieldset>

          <label className="notes-label">
            Evidence / notes *
            <textarea value={evidence} onChange={(event) => setEvidence(event.target.value)} rows={4} />
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

      <aside className="context-panel" aria-label="Call context">
        <p className="eyebrow">Known label</p>
        <div className={`large-badge ${activeCall.expectedRating.toLowerCase()}`}>{activeCall.expectedRating}</div>
        <h2>Why this sample matters</h2>
        <p>{activeCall.reasoning}</p>
        <div className="metric-grid">
          <span>
            <strong>{activeCall.summary.turnCount}</strong>
            turns
          </span>
          <span>
            <strong>{activeCall.summary.toolCount}</strong>
            tools
          </span>
        </div>
        <div className="tag-stack">
          {activeCall.summary.issueTags.map((tag) => (
            <span key={tag}>{tag}</span>
          ))}
        </div>
      </aside>
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
