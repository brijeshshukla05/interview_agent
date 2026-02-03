import streamlit as st
import sys
import os
import pandas as pd
from agent.graph import create_graph
from agent.state import AgentState
from agent.resume import extract_text_from_pdf, screen_resume
import config
from agent.audio import text_to_speech_bytes, audio_bytes_to_text
from streamlit_mic_recorder import mic_recorder
from agent.db import init_db, add_candidate, get_candidate, get_all_candidates, update_interview_result, update_recommendation, clear_db
from agent.report import generate_pdf_report, generate_hr_recommendation
import base64
import time
import json
import streamlit.components.v1 as components

# Add current directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

st.set_page_config(page_title="AI Interview Agent", page_icon="📝")

st.title("🤖 AI Interview Agent Platform")

# Custom component for reliable tab-switch detection
tab_switch_tracker = components.declare_component(
    "tab_switch_tracker",
    path=os.path.join(os.path.dirname(__file__), "components", "tab_switch_tracker"),
)

def end_interview():
    if st.session_state.get("agent_state") is not None:
        evals = st.session_state.agent_state.get("evaluations", [])
        if not evals and "current_candidate_name" in st.session_state:
            avg_score = 0.0
            cand = get_candidate(st.session_state.current_candidate_name)
            resume_score = cand.get("resume_score", 0) if cand else 0
            rec = generate_hr_recommendation([], avg_score, resume_score)
            rec["auto_ended"] = bool(st.session_state.get("auto_ended", False))
            if rec["auto_ended"]:
                rec["auto_end_reason"] = "Tab switch limit reached"
            update_interview_result(
                st.session_state.current_candidate_name,
                [],
                avg_score,
                final_summary=json.dumps(rec),
                decision=rec.get("decision")
            )
    st.session_state.interview_active = False
    st.session_state.confirm_end = False

# Initialize DB
init_db()

# Initialize Session State
if "graph" not in st.session_state:
    st.session_state.graph = create_graph()
if "agent_state" not in st.session_state:
    st.session_state.agent_state = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "interview_active" not in st.session_state:
    st.session_state.interview_active = False
if "question_audio" not in st.session_state:
    st.session_state.question_audio = {}
if "pending_voice_text" not in st.session_state:
    st.session_state.pending_voice_text = ""
if "clear_answer_input" not in st.session_state:
    st.session_state.clear_answer_input = False
if "current_q_idx" not in st.session_state:
    st.session_state.current_q_idx = None

# Sidebar Navigation
with st.sidebar:
    st.markdown(
        """
        <style>
          section[data-testid="stSidebar"] .block-container {
            padding-top: 0.5rem;
          }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.header("Access Portal")
    mode = st.radio("Select User Type:", ["Candidate Access", "HR Admin"])
    
    # End Interview Logic (Only visible if active in Candidate Mode)
    if st.session_state.get("interview_active", False) and mode == "Candidate Access":
        st.divider()
        if st.button("⏭️ Skip Question", help="Skip current question (Score: 0)"):
            st.session_state.skip_triggered = True

        if "confirm_end" not in st.session_state:
            st.session_state.confirm_end = False
            
        if not st.session_state.confirm_end:
            if st.button("End Interview", type="primary"):
                st.session_state.confirm_end = True
                st.rerun()
        else:
            st.warning("Really end the interview?")
            col_y, col_n = st.columns(2)
            with col_y:
                if st.button("Yes"):
                    st.session_state.auto_ended = False
                    end_interview()
                    st.rerun()
            with col_n:
                if st.button("No"):
                    st.session_state.confirm_end = False
                    st.rerun()

        # Voice controls in navigation panel
        st.write("🎙️ Answer via Voice:")
        current_q_idx = st.session_state.current_q_idx
        if current_q_idx is None:
            assistant_count = sum(1 for m in st.session_state.messages if m.get("role") == "assistant")
            current_q_idx = assistant_count - 1 if assistant_count > 0 else None
            st.session_state.current_q_idx = current_q_idx
        if current_q_idx is None:
            st.info("No active question yet.")
        else:
            st.write("Use Start/Stop Recording below.")
            audio_input = mic_recorder(
                start_prompt="Start Recording",
                stop_prompt="Stop Recording",
                key="recorder_sidebar",
                format="wav",
            )
            if audio_input:
                st.session_state.question_audio[current_q_idx] = audio_input["bytes"]
                voice_text = audio_bytes_to_text(audio_input["bytes"])
                if voice_text:
                    st.session_state.pending_voice_text = voice_text

# ---------------- HR ADMIN SECTION ----------------
if mode == "HR Admin":
    st.header("HR Admin Panel")
    
    tab1, tab2 = st.tabs(["📄 Resume Screening", "📊 Dashboard"])
    
    with tab1:
        st.subheader("Process New Candidates")
        jd_text = st.text_area("Job Description", height=200, placeholder="Paste the JD here...")
        uploaded_files = st.file_uploader("Upload Resumes (PDF)", type="pdf", accept_multiple_files=True)
        question_file = st.file_uploader("Upload Question Bank (TXT)", type=["txt", "csv"])

        def parse_question_bank(file_obj):
            if not file_obj:
                return []
            try:
                content = file_obj.read().decode("utf-8", errors="ignore")
                if file_obj.name.lower().endswith(".csv"):
                    lines = [line.strip() for line in content.splitlines() if line.strip()]
                    # Use first column as question text
                    questions = [line.split(",")[0].strip() for line in lines if line.split(",")[0].strip()]
                else:
                    questions = [line.strip() for line in content.splitlines() if line.strip()]
                # Deduplicate while preserving order
                seen = set()
                unique_questions = []
                for q in questions:
                    if q not in seen:
                        unique_questions.append(q)
                        seen.add(q)
                return unique_questions
            except Exception:
                return []
        
        if st.button("Analyze & Whitelist Resumes"):
            if not jd_text or not uploaded_files:
                st.error("Please provide JD and Resumes.")
            else:
                with st.spinner("Analyzing resumes..."):
                    results = []
                    question_bank = parse_question_bank(question_file)
                    for uploaded_file in uploaded_files:
                        resume_text = extract_text_from_pdf(uploaded_file)
                        analysis = screen_resume(resume_text, jd_text)
                        
                        name = analysis.get("name", "Unknown")
                        score = analysis.get("score", 0)
                        
                        # Save to Database
                        # We store extracting topics for later interview use
                        topics = analysis.get("extracted_topics", [])
                        add_candidate(name, score, analysis, topics, question_bank)
                        
                        results.append({
                            "Name": name,
                            "Score": score,
                            "Status": "Saved to DB"
                        })
                    st.success("Analysis Complete! Candidates saved to Database.")
                    st.dataframe(pd.DataFrame(results))
    
    with tab2:
        st.subheader("Candidate Database")
        
        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("Refresh Table"):
                st.rerun()
        with c2:
            if st.button("Empty Database", type="secondary"):
                st.session_state.confirm_clear = True

        if st.session_state.get("confirm_clear"):
            st.warning("⚠️ Are you sure? This will DELETE ALL DATA permanently.")
            col_yes, col_no = st.columns(2)
            with col_yes:
                if st.button("Yes, Delete All", type="primary"):
                    clear_db()
                    st.session_state.confirm_clear = False
                    st.success("Database Cleared!")
                    time.sleep(1)
                    st.rerun()
            with col_no:
                if st.button("Cancel"):
                    st.session_state.confirm_clear = False
                    st.rerun()
        
        candidates = get_all_candidates()
        if candidates:
            # Display Summary Table
            dashboard_data = []
            def parse_recommendation(rec_str):
                if not rec_str:
                    return {}
                try:
                    return json.loads(rec_str)
                except Exception:
                    return {"summary": rec_str}

            for c in candidates:
                # Calculate stats
                try:
                    interview_data = json.loads(c['interview_data']) if c['interview_data'] else []
                    skipped = 0
                    answered = 0
                    for item in interview_data:
                        if item.get("skipped"):
                            skipped += 1
                        else:
                            # Backward-compatible fallback for older entries
                            if item.get('score') == 0 and "skipped" in item.get('feedback', '').lower():
                                skipped += 1
                            else:
                                answered += 1
                except:
                    skipped = 0
                    answered = 0
                    interview_data = []
                
                # Recompute fair interview score from data (includes unanswered as 0)
                total_score = sum(item.get("score", 0) for item in interview_data)
                fair_score = (
                    total_score / config.MAX_QUESTIONS_DEFAULT
                    if config.MAX_QUESTIONS_DEFAULT else 0
                )
                # If interview was completed with zero attempts, show stored score (likely 0.0)
                if not interview_data and c.get("interview_score") is not None:
                    fair_score = c.get("interview_score", 0) or 0

                # Use stored recommendation on dashboard to avoid repeated LLM calls
                rec = parse_recommendation(c.get("final_summary"))

                summary_text = rec.get("summary") or ""
                short_summary = (summary_text[:120] + "...") if len(summary_text) > 120 else summary_text

                total_duration = 0
                if interview_data:
                    total_duration = sum(item.get("duration", 0) or 0 for item in interview_data)

                dashboard_data.append({
                    "Name": c['name'],
                    "Resume": f"{c['resume_score']}%",
                    "Interview": (
                        "Not Eligible"
                        if c['resume_score'] < 70
                        else (f"{fair_score:.1f}" if c.get("status") == "completed" else "N/A")
                    ),
                    "A/S": f"A/S ({config.MAX_QUESTIONS_DEFAULT}): {answered}/{skipped}",
                    "Status": c['status'],
                    "Duration": (
                        "Not Eligible"
                        if c['resume_score'] < 70
                        else (f"{round(total_duration, 1)}s" if total_duration else "N/A")
                    )
                })
            
            st.dataframe(pd.DataFrame(dashboard_data))

            # Detailed Recommendation View
            st.divider()
            st.write("### Recommendation Details")
            for c in candidates:
                if c.get("status") != "completed" or not c.get("final_summary"):
                    continue
                rec = parse_recommendation(c.get("final_summary"))
                with st.expander(f"{c['name']} — {rec.get('decision', 'Pending')}"):
                    st.write(f"**Decision:** {rec.get('decision', 'N/A')}")
                    if rec.get("auto_ended"):
                        reason = rec.get("auto_end_reason", "Auto-ended")
                        st.write(f"**Auto-Ended:** Yes ({reason})")
                    st.write(f"**Performance:** {rec.get('performance', 'N/A')}")
                    st.write(f"**Score-Based Summary:** {rec.get('score_based_summary', 'N/A')}")
                    st.write(f"**Knowledge Level:** {rec.get('knowledge_level', 'N/A')}")
                    st.write(f"**Role Fit:** {rec.get('role_fit', 'N/A')}")
                    st.write(f"**Readiness:** {rec.get('readiness', 'N/A')}")
                    if rec.get("summary"):
                        st.write(f"**Summary:** {rec.get('summary')}")
                    concerns = rec.get("concerns") or []
                    if concerns:
                        st.write("**Concerns:** " + "; ".join(concerns))
            
            # Report Download Section
            st.divider()
            st.write("### Download Reports")
            selected_candidate = st.selectbox("Select Candidate", [c['name'] for c in candidates])
            
            if st.button("Generate PDF Report"):
                cand_data = next((c for c in candidates if c['name'] == selected_candidate), None)
                if cand_data:
                    rec = None
                    try:
                        interview_data = json.loads(cand_data['interview_data']) if cand_data['interview_data'] else []
                    except Exception:
                        interview_data = []
                    total_score = sum(item.get("score", 0) for item in interview_data)
                    fair_score = (
                        total_score / config.MAX_QUESTIONS_DEFAULT
                        if config.MAX_QUESTIONS_DEFAULT else 0
                    )
                    if cand_data.get("final_summary"):
                        try:
                            rec = json.loads(cand_data["final_summary"])
                        except Exception:
                            rec = {"summary": cand_data.get("final_summary"), "decision": cand_data.get("can_hire")}
                    pdf_bytes = generate_pdf_report(
                        cand_data['name'], 
                        cand_data['interview_data'], 
                        fair_score,
                        cand_data['resume_score'],
                        rec
                    )
                    b64_pdf = base64.b64encode(pdf_bytes).decode('latin-1')
                    href = f'<a href="data:application/pdf;base64,{b64_pdf}" download="{cand_data["name"]}_report.pdf">Download PDF Report</a>'
                    st.markdown(href, unsafe_allow_html=True)
        else:
            st.info("No candidates found in database.")
            
    # Remove old indentations
    # No more password error


# ---------------- CANDIDATE SECTION ----------------
elif mode == "Candidate Access":
    # Gating Logic
    if not st.session_state.interview_active:
        st.header("Candidate Login")
        st.markdown("Please enter your name to verify eligibility.")
        
        candidate_name = st.text_input("Full Name")
        
        if st.button("Login"):
            if not candidate_name:
                st.error("Enter name.")
            else:
                # Check DB
                cand = get_candidate(candidate_name)
                
                if cand and cand['status'] == 'screened' and cand['resume_score'] >= 70:
                    st.session_state.current_candidate_name = cand['name'] # Store for saving later
                    st.success(f"Welcome, {cand['name']}! Starting Interview...")
                    st.session_state.interview_active = True
                    st.session_state.tab_switch_reset_token = str(time.time())
                    st.session_state.auto_ended = False
                    st.session_state.question_audio = {}
                    st.session_state.pending_voice_text = ""
                    
                    # Reset Proctoring Logic (Optional, JS persists but we can ignore previous counts if we wanted)
                    # For now, we count specific session anomalies.
                    
                    # Load Topics from DB
                    import json
                    topics = []
                    if cand.get('extracted_topics'):
                        try:
                            topics = json.loads(cand['extracted_topics'])
                        except:
                            topics = ["General Technical"]
                    if not topics: topics = ["General Technical"]

                    question_bank = []
                    if cand.get("question_bank"):
                        try:
                            question_bank = json.loads(cand["question_bank"])
                        except Exception:
                            question_bank = []

                    st.session_state.agent_state = {
                        "topics": topics,
                        "history": [],
                        "current_question": None,
                        "evaluations": [],
                        "complexity_level": 1,
                        "question_count": 0,
                        "exit_session": False,
                        "question_bank": question_bank,
                        "bank_index": 0
                    }
                    st.session_state.messages = []
                    
                    # Start graph
                    result = st.session_state.graph.invoke(st.session_state.agent_state)
                    st.session_state.agent_state = result
                    if result.get("current_question"):
                        q_text = result["current_question"]
                        c_audio = text_to_speech_bytes(q_text)
                        
                        st.session_state.current_q_start_time = time.time() # Start Timer
                        st.session_state.messages.append({"role": "assistant", "content": q_text, "audio": c_audio})
                        st.session_state.agent_state["history"].append({"role": "assistant", "content": q_text})
                        st.session_state.current_q_idx = len(
                            [m for m in st.session_state.messages if m.get("role") == "assistant"]
                        ) - 1
                    st.rerun()
                else:
                    if cand and cand.get("status") == "completed":
                        st.error("Access Denied. Interview already completed (single attempt only).")
                    else:
                        st.error("Access Denied. Name not found or resume score too low.")

    else:
        # Active Interview
        st.header("🎤 Interview Session")

        # Tab switch tracking (auto-end on second switch)
        if "current_candidate_name" in st.session_state:
            name = st.session_state.current_candidate_name
            auto_submit_event = tab_switch_tracker(
                local_key=f"tab_switch_local_{name}",
                auto_key=f"tab_switch_autosubmit_{name}",
                session_key=f"tab_switch_session_{name}",
                reset_token=st.session_state.get("tab_switch_reset_token", ""),
                default="",
            )
            if auto_submit_event == "auto_submit":
                st.session_state.auto_ended = True
                end_interview()
                st.rerun()

        # Question Cards (recording controls per question)
        qa_pairs = []
        for msg in st.session_state.messages:
            if msg["role"] == "assistant":
                qa_pairs.append({"question": msg, "answer": None})
            elif msg["role"] == "user" and qa_pairs and qa_pairs[-1]["answer"] is None:
                qa_pairs[-1]["answer"] = msg

        current_q_idx = len(qa_pairs) - 1 if qa_pairs else None
        st.session_state.current_q_idx = current_q_idx

        for i, pair in enumerate(qa_pairs):
            q_msg = pair["question"]
            st.markdown(f"**Q{i+1}:** {q_msg['content']}")
            if q_msg.get("audio"):
                st.audio(q_msg["audio"], format="audio/mp3")
            if pair.get("answer"):
                st.markdown(f"**Answer:** {pair['answer']['content']}")

            if i in st.session_state.question_audio:
                st.audio(st.session_state.question_audio[i], format="audio/wav")
            st.divider()

        # Static recording controls parallel to answer input
        # Static answer input (anchored to bottom by Streamlit)
        prompt = st.chat_input("Your answer...")

        # User Input
        final_answer = None
        
        if st.session_state.get("skip_triggered"):
            final_answer = "<SKIPPED>"
            st.session_state.skip_triggered = False # Reset
        elif prompt:
            final_answer = prompt
        elif st.session_state.pending_voice_text:
             final_answer = st.session_state.pending_voice_text
             st.session_state.pending_voice_text = ""

        if final_answer:
            # Calculate Duration
            duration = 0
            if "current_q_start_time" in st.session_state:
                duration = time.time() - st.session_state.current_q_start_time
            
            with st.chat_message("user"):
                st.markdown(final_answer)
            st.session_state.messages.append({"role": "user", "content": final_answer})
            st.session_state.agent_state["history"].append({"role": "user", "content": final_answer})
            
            with st.spinner("AI is evaluating..."):
                 result = st.session_state.graph.invoke(st.session_state.agent_state)
                 st.session_state.agent_state = result
                 
                 # UPDATE EVALUATION WITH METRICS
                 if st.session_state.agent_state["evaluations"]:
                     last_eval = st.session_state.agent_state["evaluations"][-1]
                     last_eval["duration"] = round(duration, 2)
            
            if result.get("current_question"):
                 q_text = result["current_question"]
                 c_audio = text_to_speech_bytes(q_text)
                 
                 st.session_state.current_q_start_time = time.time() # Reset Timer
                 with st.chat_message("assistant"):
                     st.markdown(q_text)
                     if c_audio: st.audio(c_audio, format="audio/mp3")
                 st.session_state.messages.append({"role": "assistant", "content": q_text, "audio": c_audio})
                 st.session_state.agent_state["history"].append({"role": "assistant", "content": q_text})
                 st.session_state.current_q_idx = len(
                     [m for m in st.session_state.messages if m.get("role") == "assistant"]
                 ) - 1
            else:
                st.session_state.auto_ended = False
                st.session_state.interview_active = False
                st.rerun()

        # Progress
        if st.session_state.agent_state and st.session_state.agent_state.get("evaluations"):
            evals = st.session_state.agent_state["evaluations"]
            st.divider()
            st.write(f"Progress: {len(evals)} / {config.MAX_QUESTIONS_DEFAULT}")
            st.progress(min(len(evals) / config.MAX_QUESTIONS_DEFAULT, 1.0))

# ---------------- FINAL REPORT ----------------
if not st.session_state.interview_active and st.session_state.agent_state and st.session_state.agent_state.get("evaluations"):
    st.header("📊 Final Evaluation Report")
    st.markdown("Here is the breakdown of your technical interview.")
    
    evals = st.session_state.agent_state["evaluations"]
    total_score = sum(e["score"] for e in evals)
    # Fair average: include unanswered questions as 0
    avg_score = total_score / config.MAX_QUESTIONS_DEFAULT if config.MAX_QUESTIONS_DEFAULT else 0
    
    skipped_count = sum(1 for e in evals if e.get("skipped") or (e.get('score') == 0 and "skipped" in e.get('feedback', '').lower()))
    answered_count = len(evals) - skipped_count

    
    # Save Results to DB
    if "current_candidate_name" in st.session_state:
        cand = get_candidate(st.session_state.current_candidate_name)
        resume_score = cand.get("resume_score", 0) if cand else 0

        if "hr_recommendation" not in st.session_state:
            st.session_state.hr_recommendation = generate_hr_recommendation(evals, avg_score, resume_score)

        rec = st.session_state.hr_recommendation
        rec["auto_ended"] = bool(st.session_state.get("auto_ended", False))
        if rec["auto_ended"]:
            rec["auto_end_reason"] = "Tab switch limit reached"
        update_interview_result(
            st.session_state.current_candidate_name,
            evals,
            avg_score,
            final_summary=json.dumps(rec),
            decision=rec.get("decision")
        )
        st.success("Results saved to HR Database!")
    
    col1, col2, col3 = st.columns(3)
    with col1: st.metric("Questions Answered", answered_count)
    with col2: st.metric("Skipped", skipped_count)
    with col3: st.metric("Average Score", f"{avg_score:.1f} / 10")
    
    st.divider()
    for i, e in enumerate(evals, 1):
        score_color = "🟢" if e['score'] >= 8 else "🟡" if e['score'] >= 5 else "🔴"
        with st.expander(f"{score_color} Q{i}: Score {e['score']}/10 - {e['question'][:50]}..."):
            st.markdown(f"**Question:** {e['question']}")
            st.markdown(f"**Answer:** {e['user_answer']}")
            st.markdown(f"**Feedback:** {e['feedback']}")
            st.caption(f"⏱️ Time Taken: {e.get('duration', 0)}s")
    
    if st.button("Return to Login"):
        st.session_state.clear()
        st.rerun()
