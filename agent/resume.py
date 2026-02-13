from pypdf import PdfReader
from io import BytesIO
from langchain_core.messages import HumanMessage
from agent.utils import get_llm, extract_json
from prompts.templates import RESUME_SCREENING_PROMPT
import config
from agent.logger import get_logger

logger = get_logger(__name__)

def extract_text_from_pdf(file_obj) -> str:
    """
    Extracts text from a PDF file object (bytes).
    """
    try:
        reader = PdfReader(file_obj)
        text = ""
        for page in reader.pages:
            text += page.extract_text() or ""
        return text
    except Exception as e:
        return f"Error reading PDF: {str(e)}"

def screen_resume(resume_text: str, jd_text: str):
    """
    Screens the resume against the JD using the LLM.
    Returns a dictionary with name, score, and reasoning.
    """
    try:
        logger.info("Screening resume against JD")
        from datetime import datetime
        prompt = RESUME_SCREENING_PROMPT.format(
            resume_text=resume_text[:4000],
            jd_text=jd_text[:2000],
            current_date=datetime.now().strftime("%B %Y")
        )
        
        llm = get_llm(temperature=config.TEMPERATURE_EVAL, max_tokens=config.MAX_TOKENS_EVAL)
        response = llm.invoke([HumanMessage(content=prompt)])
        
        return extract_json(response.content)
    except Exception as e:
        logger.error(f"Error screening resume: {e}")
        return {"score": 0, "reasoning": f"Error: {str(e)}", "name": "Unknown"}
