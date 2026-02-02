from fpdf import FPDF
import json
from typing import Dict, Any, Optional
from langchain_core.messages import HumanMessage
from agent.utils import get_llm, extract_json
from prompts.templates import HR_RECOMMENDATION_PROMPT
import config

class PDFReport(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'AI Interview Result Report', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def generate_pdf_report(candidate_name, interview_data, avg_score, resume_score, recommendation: Optional[dict] = None):
    pdf = PDFReport()
    pdf.add_page()
    
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="Interview Report", ln=True, align='C')
    pdf.ln(10)
    
    # Calculate Skips
    if interview_data is None:
        interview_data = []

    if isinstance(interview_data, str):
        try:
            interview_data = json.loads(interview_data)
        except:
            interview_data = []
        
    skipped_count = sum(1 for item in interview_data if item.get('score') == 0 and "skipped" in item.get('feedback', '').lower())
    answered_count = len(interview_data) - skipped_count
    
    # Candidate Info
    pdf.set_font("Arial", size=12)
    pdf.cell(200, 10, txt=f"Candidate Name: {candidate_name.title()}", ln=True)
    pdf.cell(200, 10, txt=f"Resume Score: {resume_score}%", ln=True)
    pdf.cell(200, 10, txt=f"Interview Score: {avg_score:.1f} / 10", ln=True)
    pdf.cell(200, 10, txt=f"Answered: {answered_count} | Skipped: {skipped_count}", ln=True)
    pdf.ln(10)

    # HR Recommendation Summary
    if recommendation:
        pdf.set_font("Arial", 'B', 13)
        pdf.cell(200, 8, txt="Recommendation", ln=True)
        pdf.set_font("Arial", size=11)
        pdf.cell(200, 6, txt=f"Decision: {recommendation.get('decision', 'N/A')}", ln=True)
        pdf.cell(200, 6, txt=f"Performance: {recommendation.get('performance', 'N/A')}", ln=True)
        pdf.multi_cell(0, 6, f"Score-Based Summary: {recommendation.get('score_based_summary', 'N/A')}")
        pdf.cell(200, 6, txt=f"Knowledge Level: {recommendation.get('knowledge_level', 'N/A')}", ln=True)
        pdf.cell(200, 6, txt=f"Role Fit: {recommendation.get('role_fit', 'N/A')}", ln=True)
        pdf.cell(200, 6, txt=f"Readiness: {recommendation.get('readiness', 'N/A')}", ln=True)
        summary = recommendation.get("summary", "")
        if summary:
            pdf.multi_cell(0, 6, f"Summary: {summary}")
        concerns = recommendation.get("concerns", [])
        if concerns:
            pdf.multi_cell(0, 6, "Concerns: " + "; ".join(concerns))
        pdf.ln(8)
    
    # Detailed Breakdown
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(200, 10, txt="Interview Details", ln=True)
    pdf.ln(5)
    
    if not interview_data:
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt="No interview data available.", ln=True)
        return pdf.output(dest='S').encode('latin-1')

    for i, eval_item in enumerate(interview_data, 1):
        pdf.set_font("Arial", 'B', 11)
        # Handle unicode roughly by replacing or encoding
        q = eval_item.get('question', '').encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 10, f"Q{i}: {q}")
        
        pdf.set_font("Arial", size=10)
        pdf.cell(0, 6, f"Score: {eval_item.get('score', 0)}/10", ln=True)
        
        ans = eval_item.get('user_answer', '').encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 6, f"Answer: {ans}")
        
        feed = eval_item.get('feedback', '').encode('latin-1', 'replace').decode('latin-1')
        pdf.multi_cell(0, 6, f"Feedback: {feed}")
        
        # Metrics
        duration = eval_item.get('duration', 0)
        pdf.set_font("Arial", 'I', 9)
        pdf.cell(0, 6, f"Time Taken: {duration}s", ln=True)
        
        pdf.ln(5)
        
    return pdf.output(dest='S').encode('latin-1', 'replace') # Return bytes

def generate_hr_recommendation(interview_data, avg_score: float, resume_score: float) -> Dict[str, Any]:
    """
    Generate an HR recommendation summary and decision based on interview data.
    """
    try:
        prompt = HR_RECOMMENDATION_PROMPT.format(
            avg_score=avg_score,
            resume_score=resume_score,
            interview_data=json.dumps(interview_data)
        )
        llm = get_llm(temperature=config.TEMPERATURE_RECOMMEND, max_tokens=config.MAX_TOKENS_RECOMMEND)
        response = llm.invoke([HumanMessage(content=prompt)])
        rec = extract_json(response.content)
    except Exception:
        rec = {}

    # Enforce threshold-based decision so not everyone moves forward
    if resume_score < config.MIN_ELIGIBLE_RESUME_SCORE:
        decision = "Reject"
        performance = "Not Eligible"
    elif avg_score >= 6:
        decision = "Move Forward"
        performance = "Strong"
    elif avg_score >= 3.5:
        decision = "Hold"
        performance = "Average"
    else:
        decision = "Reject"
        performance = "Weak"

    if performance == "Strong":
        score_summary = "Strong performance based on scores; recommended to move forward."
    elif performance == "Average":
        score_summary = "Average performance; consider for hold or follow-up evaluation."
    elif performance == "Weak":
        score_summary = "Weak performance based on scores; not recommended to move forward."
    else:
        score_summary = "Not eligible based on resume threshold."

    return {
        "decision": decision,
        "performance": performance,
        "score_based_summary": score_summary,
        "knowledge_level": rec.get("knowledge_level", "Unknown"),
        "role_fit": rec.get("role_fit", "Unknown"),
        "readiness": rec.get("readiness", "Unknown"),
        "summary": rec.get("summary", "No summary available."),
        "concerns": rec.get("concerns", [])
    }
