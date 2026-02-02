# Interview Agent — Project Overview

Below is a complete, file-by-file and function-by-function explanation of how this project works, plus a full feature list.

## Project Overview
- AI interview platform with two modes:
  - HR Admin: upload JD + resumes, screen candidates, view dashboard, download reports.
  - Candidate Access: eligible candidates take the interview (text + voice), get evaluated, and results are saved.

---

## config.py
**Purpose:** Central configuration for model, thresholds, and performance.
- `MODEL_NAME`, `BASE_URL`, `API_KEY`: LLM connection settings.
- `TEMPERATURE_ASK`, `TEMPERATURE_EVAL`, `TEMPERATURE_RECOMMEND`: LLM creativity per task.
- `MAX_QUESTIONS_DEFAULT`: number of questions per interview.
- `MOVE_FORWARD_SCORE`, `HOLD_SCORE`, `MIN_ELIGIBLE_RESUME_SCORE`: HR decision thresholds.
- `MAX_TOKENS_QUESTION`, `MAX_TOKENS_EVAL`, `MAX_TOKENS_RECOMMEND`: LLM response limits.
- `LLM_TIMEOUT_SECONDS`: timeout for LLM calls.

---

## app.py
**Purpose:** Streamlit UI for HR and candidates, main app flow.

### Initialization
- Initializes DB (`init_db`) and session state (graph, messages, interview flags).
- Sidebar sets mode (HR Admin or Candidate).

### HR Admin tab — Resume Screening
- `extract_text_from_pdf` + `screen_resume` called per uploaded resume.
- LLM returns resume match score + extracted topics.
- Saved in DB via `add_candidate`.

### HR Admin tab — Dashboard
- Loads candidates with `get_all_candidates`.
- Computes:
  - Answered / skipped counts from `interview_data`.
  - “Fair score” = total score / `MAX_QUESTIONS_DEFAULT`.
- Displays:
  - Resume %, Interview score (or “Not Eligible”), A/S ratio, status, time.
- Recommendation details:
  - Only shown for completed candidates with stored `final_summary`.
  - Expandable detail: decision, performance, score-based summary, knowledge level, role fit, readiness, summary, concerns.

### PDF Report download
- Uses stored `final_summary` when available.
- Generates report with `generate_pdf_report`.

### Candidate Access
- Login by name:
  - Only `status == screened` and resume score ≥ 70 allowed.
  - `completed` status is blocked (single attempt).
- Interview loop:
  - Generates question → candidate answer → evaluates → repeats until max Q.
  - Supports voice input (via mic recorder + speech recognition).
  - Saves results to DB:
    - Fair average score
    - LLM HR recommendation
    - Decision stored in `can_hire`
- Final report displayed in UI + saved.

---

## main.py
**Purpose:** CLI interview runner (non-Streamlit).
- Asks topics from user.
- Uses LangGraph:
  - `generate_question` → get answer → `evaluate_answer` → loop.
- Prints report at end.

---

## prompts/templates.py
**Purpose:** All LLM prompts.
- `TOPIC_SOLICITATION`: ask user what topics.
- `QUESTION_GENERATION`:  
  - Only in-scope topics.
  - Avoid repeated topics.
  - Align to candidate seniority/role.
  - Conceptual-only questions.
- `EVALUATION`: score answer, output JSON.
- `RESUME_SCREENING_PROMPT`: JD + resume match scoring.
- `HR_RECOMMENDATION_PROMPT`: final hiring recommendation JSON.

---

## agent/graph.py
**Purpose:** LangGraph state machine.
- `route_start`: decides evaluate vs generate based on history.
- `route_next_step`: ends when max question count reached.
- `create_graph`: builds graph with nodes and routing.

---

## agent/nodes.py
**Purpose:** Interview logic.
- `generate_question(state)`
  - Builds prompt from topics, history, complexity.
  - Uses LLM to generate conceptual question only.
- `evaluate_answer(state)`
  - Uses LLM to score + feedback.
  - Handles skipped answers (score 0).
  - Increments complexity and question count.

---

## agent/state.py
**Purpose:** Typed structure for interview state.
- `Evaluation`: question, answer, score, feedback, topics, complexity.
- `AgentState`: topics, history, current question, evaluations, complexity level, question count, exit flag.

---

## agent/db.py
**Purpose:** SQLite database access.
- `init_db()`: creates candidates table + migration for `final_summary`, `can_hire`.
- `add_candidate()`: store screening results.
- `get_candidate()`: fetch candidate by name.
- `update_interview_result()`: save interview results + HR decision.
- `update_recommendation()`: update summary/decision.
- `get_all_candidates()`: list candidates.
- `clear_db()`: wipe data.

---

## agent/resume.py
**Purpose:** Resume screening.
- `extract_text_from_pdf(file_obj)`: text extraction via `pypdf`.
- `screen_resume(resume_text, jd_text)`: LLM match and scoring.

---

## agent/audio.py
**Purpose:** Voice features.
- `text_to_speech_bytes(text)`: gTTS → audio.
- `audio_bytes_to_text(bytes)`: SpeechRecognition → text.

---

## agent/code_executor.py
**Purpose:** External code execution via Piston API.
- `get_runtimes()`: supported languages.
- `execute_code(language, code, stdin)`: run code remotely.
- `run_test_cases(language, code, test_cases)`: run test suite & collect results.

---

## agent/report.py
**Purpose:** PDF reporting + HR recommendation.
- `PDFReport`: FPDF layout (header/footer).
- `generate_pdf_report(...)`:
  - candidate info, scores, Q&A, timing
  - includes HR recommendation block.
- `generate_hr_recommendation(...)`:
  - Calls LLM for qualitative summary.
  - Enforces thresholds to decide Move Forward / Hold / Reject.
  - Adds performance label + score-based summary.

---

## agent/utils.py
**Purpose:** Shared LLM + JSON helpers.
- `get_llm(temperature, max_tokens)`:
  - Uses `config` settings + timeout.
- `extract_json(text)`:
  - Robust JSON parsing from LLM output.

---

## Other Files
- `requirements.txt`: dependencies.
- `candidates.db`: SQLite DB.
- `JD for DS.txt`: sample JD.
- `__pycache__/`: compiled Python bytecode (not source).

---

# Full Feature List (current)
- Resume screening against JD (LLM scoring + topics).
- Candidate eligibility gate (resume score ≥ 70).
- Single-attempt interview (completed users blocked).
- Conceptual-only interview questions.
- Topic-bounded & role-aligned questions.
- Voice input (mic → transcript).
- LLM answer evaluation + feedback.
- Fair scoring (unanswered count as 0).
- HR dashboard with A/S ratio + eligibility display.
- HR recommendation & decision (stored + PDF).
- PDF report download with full summary.
- LLM performance controls (token caps + timeouts).
- CLI interview mode.

