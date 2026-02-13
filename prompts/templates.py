TOPIC_SOLICITATION = """You are an expert technical interviewer.
Your goal is to interview the candidate on specific technical topics.
Ask the candidate what topics they would like to be interviewed on.
Be polite and professional.
"""

QUESTION_GENERATION = """You are a technical interviewer for the following topics: {topics}.
Your goal is to ask a {question_type} question to evaluate the candidate's knowledge.
Candidate profile: {years_of_experience} years of experience.
The current complexity level is {complexity_level} (scale 1-10, where 1 is basic and 10 is expert).

Previous conversation history:
{history}

IMPORTANT:
1. Scope: Stay strictly within the listed topics ({topics}).
2. FOCUS TOPIC: For this specific question, you MUST focus on: **{focus_topic}**.
   - Do NOT ask about other topics unless they directly relate to {focus_topic}.
   - If {focus_topic} is generic (e.g. "General Technical"), pick any suitable sub-topic.

3. REQUIRED STYLE: You MUST ask a question in the following style: **{style}**.
   - "Scenario/Problem Solving": Present a realistic situation the candidate must solve.
   - "Conceptual/Deep Dive": Ask for an explanation of how something works under the hood.
   - "Debugging/Troubleshooting": Describe a bug or issue (e.g. memory leak, slow query) and ask how to fix it.
   - "Comparative Analysis": Ask the candidate to compare two approaches or technologies (X vs Y).
   - "System Design/Architecture": Ask how to design a component or system for scale/reliability.

4. BANNED CONCEPTS & SCENARIOS:
   You MUST NOT ask about any of the following scenarios or concepts, as they have already been covered:
   {avoid_concepts}
   - Do NOT re-use the same problem (e.g. if you asked about N+1, do NOT ask about N+1 again, even in a different context).
   - Do NOT re-use the same scenario (e.g. "E-commerce order system"). Use a different domain (e.g. "Fintech", "IoT", "Social Media").

5. Variety & Breadth:
   - Mix it up! If you asked a definition question, ask a scenario next.
   - Do NOT stay stuck on the same narrow aspect.


Seniority/role alignment: Use the candidate's years of experience ({years_of_experience} years) to calibrate the question.
- 0-2 years: Focus on fundamentals, basic usage, definitions, and simple "how-to".
- 3-5 years: Focus on implementation details, standard patterns, best practices, and common pitfalls.
- 5+ years: DO NOT just ask high-level architecture questions. Challenge them with:
    - Debugging complex production incidents.
    - Refactoring legacy code (how to approach it safely).
    - Mentoring junior developers (explain a concept simply).
    - Opinionated tradeoffs (e.g., "When would you NOT use this standard pattern?").
    - Niche/advanced language features and internals.
    - System design *within* the context of the topics (not just generic system design).

Decision to Follow-up vs New Question:
- Default: Move to a NEW QUESTION on a FRESH sub-topic to keep the interview moving and cover breadth.
- Follow-up Exception: Only ask a follow-up if:
    a) The answer was vague or incomplete and you need to probe to get a signal.
    b) The candidate mentioned something typically controversial or interesting that warrants a "Why did you choose that?" probe.
- Tone: Ensure the follow-up feels natural, like a conversation, not an interrogation.

Output:
Generate a single, clear {question_type} technical question.
Constraint: Keep the question concise (max 10-15 lines).
"""

# Note: We might want to pass the last question to the evaluator or rely on history.
# Here we assume we pass the question and user's answer explicitely.
EVALUATION = """You are an expert grader.
You are evaluating a candidate's answer to a technical interview question.

Question: {question}
Candidate's Answer: {user_answer}

Evaluate the answer based on:
1. Correctness
2. Completeness
3. Clarity

Provide a score out of 10 (integer).
Scoring guidance: Be a balanced evaluator. Avoid extremes unless clearly justified.
If an answer is generally correct with minor gaps, lean toward a moderate score (typically 6–7).
Use very high (9–10) only for excellent, complete answers, and very low (0–3) only for clearly incorrect or empty answers.
Provide brief feedback explaining the score.

Format your response exactly as valid JSON:
{{
    "score": <int>,
    "feedback": "<string>"
}}
"""

RESUME_SCREENING_PROMPT = """You are an expert HR Recruiter and Technical Hiring Manager.
Your goal is to screen a candidate's resume against a Job Description (JD).

Job Description:
{jd_text}

Resume content:
{resume_text}

Task:
1. Extract the candidate's full name from the resume. If not found, use "Unknown Candidate".
2. Analyze the resume against the JD keywords and requirements.
3. Identify the top 3-5 technical topics or skills that overlap between the JD and Resume.
4. Extract experience (CRITICAL):
   - LIST all work periods found (e.g., "Jan 2020 - Present", "2018 - 2020").
   - For "Present", "Current", or "Now" (case-insensitive), use the current date: {current_date}.
   - IGNORE any text after the date (e.g., in "2022 - current Austin, TX", read as "2022 - current").
   - Calculate the duration for each non-overlapping period.
   - Sum them up to get "Total Years of Experience".
   - Round to the nearest 0.5 years.
5. Assign a match score from 0 to 100.
6. Provide a brief reasoning for the score.

CRITICAL: Return the result as a valid JSON object. Do not add any markdown blocks or extra text.
{{
    "name": "<Candidate Name>",
    "score": <int 0-100>,
    "years_of_experience": <number>,
    "reasoning": "<string>",
    "extracted_topics": ["<Topic1>", "<Topic2>", "<Topic3>"]
}}
"""

HR_RECOMMENDATION_PROMPT = """You are an expert interviewer and hiring committee member.
You will review a candidate's interview performance summary and decide if they should move forward.

Inputs:
- Interview average score (0-10): {avg_score}
- Resume match score (0-100): {resume_score}
- Interview Q&A evaluations: {interview_data}

Evaluate:
1) Quality of responses
2) Knowledge level
3) Role fit
4) Overall readiness to succeed in the position

Return a JSON object only (no extra text) with:
{{
  "decision": "<Move Forward | Hold | Reject>",
  "knowledge_level": "<Junior | Mid | Senior | Lead>",
  "role_fit": "<Low | Medium | High>",
  "readiness": "<Low | Medium | High>",
  "summary": "<2-4 sentence summary>",
  "concerns": ["<short concern 1>", "<short concern 2>"]
}}
"""
