RUBRIC = [
    {
        "id": "compliance",
        "title": "Compliance & Safety",
        "subcriteria": [
            {
                "id": "identity",
                "title": "Identity & authority verification",
                "options": [
                    {
                        "value": "strong",
                        "label": "Strong",
                        "description": "Confirms identity and authority before discussing protected or account-specific information.",
                    },
                    {
                        "value": "adequate",
                        "label": "Adequate",
                        "description": "Identity is confirmed, but sequencing or phrasing is slightly delayed or imprecise.",
                    },
                    {
                        "value": "weak",
                        "label": "Weak",
                        "description": "Partial identity check or caller authority remains ambiguous while the workflow continues.",
                    },
                    {
                        "value": "fail",
                        "label": "Fail",
                        "description": "Protected information or action is handled with no meaningful verification.",
                    },
                ],
            },
            {
                "id": "safety_escalation",
                "title": "Safety, urgency, and escalation",
                "options": [
                    {"value": "strong", "label": "Strong", "description": "Recognizes urgent or out-of-scope needs and routes cleanly."},
                    {"value": "adequate", "label": "Adequate", "description": "Routes correctly with minor delay or unnecessary friction."},
                    {"value": "weak", "label": "Weak", "description": "Misses cues or gives confusing escalation guidance."},
                    {"value": "fail", "label": "Fail", "description": "Blocks or mishandles a safety-critical or human-only request."},
                ],
            },
        ],
    },
    {
        "id": "task",
        "title": "Task Completion",
        "subcriteria": [
            {
                "id": "intent",
                "title": "Intent capture and workflow fit",
                "options": [
                    {"value": "strong", "label": "Strong", "description": "Understands the caller's goal and selects the right workflow."},
                    {"value": "adequate", "label": "Adequate", "description": "Gets to the right workflow after minor clarification."},
                    {"value": "weak", "label": "Weak", "description": "Loses context or repeats questions that were already answered."},
                    {"value": "fail", "label": "Fail", "description": "Pursues the wrong workflow or refuses a supported request."},
                ],
            },
            {
                "id": "commit",
                "title": "Confirmation before irreversible action",
                "options": [
                    {"value": "strong", "label": "Strong", "description": "Reads the proposed action clearly and waits for explicit confirmation."},
                    {"value": "adequate", "label": "Adequate", "description": "Confirms the action, but wording or timing could be clearer."},
                    {"value": "weak", "label": "Weak", "description": "Confirmation is rushed, ambiguous, or interrupted."},
                    {"value": "fail", "label": "Fail", "description": "Commits the action without the required confirmation."},
                ],
            },
        ],
    },
    {
        "id": "communication",
        "title": "Caller Experience",
        "subcriteria": [
            {
                "id": "clarity",
                "title": "Clarity, empathy, and turn-taking",
                "options": [
                    {"value": "strong", "label": "Strong", "description": "Clear, calm, concise, and responsive to caller emotion."},
                    {"value": "adequate", "label": "Adequate", "description": "Generally clear with occasional awkwardness or over-talking."},
                    {"value": "weak", "label": "Weak", "description": "Frequent repetition, poor pacing, or missed caller cues."},
                    {"value": "fail", "label": "Fail", "description": "Confusing, dismissive, or materially damages caller trust."},
                ],
            }
        ],
    },
]
