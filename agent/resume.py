from io import BytesIO
import time
from typing import Any, Dict

import fitz  # PyMuPDF
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from langchain_core.messages import HumanMessage
from agent.utils import get_llm, extract_json
from prompts.templates import RESUME_SCREENING_PROMPT
import config
from agent.logger import get_logger

logger = get_logger(__name__)
MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB guardrail for malformed huge uploads
MIN_NATIVE_TEXT_LEN = 120
MAX_OCR_PAGES = 8
OCR_TIMEOUT_SECONDS = 20.0


def _base_result() -> Dict[str, Any]:
    return {
        "text": "",
        "status": "unreadable",  # ok | partial | corrupt | unreadable
        "error_code": None,
        "error_message": None,
        "ocr_used": False,
        "source": None,  # native | ocr | native+ocr
    }


def _extract_native_text(pdf_bytes: bytes) -> str:
    """Extract embedded text from PDF (works for text-based PDFs)."""
    reader = PdfReader(BytesIO(pdf_bytes))
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text.strip()


def _ocr_with_pytesseract(
    pdf_bytes: bytes, max_pages: int = MAX_OCR_PAGES, timeout_s: float = OCR_TIMEOUT_SECONDS
) -> str:
    """
    OCR PDF pages by rendering with PyMuPDF and reading text with pytesseract.
    Returns empty string if pytesseract is unavailable.
    """
    try:
        import pytesseract
        from PIL import Image
    except Exception:
        return ""

    text_parts = []
    start_t = time.monotonic()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page_num, page in enumerate(doc):
            if page_num >= max_pages:
                logger.info("Pytesseract OCR page limit reached (%s)", max_pages)
                break
            if time.monotonic() - start_t > timeout_s:
                logger.warning("Pytesseract OCR timed out after %.2fs", timeout_s)
                break
            # Render at higher resolution for better OCR quality.
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            img_bytes = pix.tobytes("png")
            image = Image.open(BytesIO(img_bytes))
            page_text = pytesseract.image_to_string(image)
            if page_text:
                text_parts.append(page_text.strip())
    finally:
        doc.close()

    return "\n".join(p for p in text_parts if p).strip()


def _ocr_with_rapidocr(
    pdf_bytes: bytes, max_pages: int = MAX_OCR_PAGES, timeout_s: float = OCR_TIMEOUT_SECONDS
) -> str:
    """
    Optional OCR fallback without external tesseract binary.
    Returns empty string if rapidocr is unavailable.
    """
    try:
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        return ""

    ocr_engine = RapidOCR()
    text_parts = []
    start_t = time.monotonic()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        for page_num, page in enumerate(doc):
            if page_num >= max_pages:
                logger.info("RapidOCR page limit reached (%s)", max_pages)
                break
            if time.monotonic() - start_t > timeout_s:
                logger.warning("RapidOCR timed out after %.2fs", timeout_s)
                break
            pix = page.get_pixmap(matrix=fitz.Matrix(2.0, 2.0), alpha=False)
            channels = pix.n
            image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
                pix.height, pix.width, channels
            )
            page_result, _ = ocr_engine(image)
            if page_result:
                lines = [item[1] for item in page_result if len(item) > 1 and item[1]]
                if lines:
                    text_parts.append("\n".join(lines))
    finally:
        doc.close()

    return "\n".join(text_parts).strip()


def extract_resume_content(file_obj) -> Dict[str, Any]:
    """
    Robust PDF extraction with OCR fallback and structured error reporting.
    """
    result = _base_result()
    try:
        if hasattr(file_obj, "getvalue"):
            pdf_bytes = file_obj.getvalue()
        else:
            file_obj.seek(0)
            pdf_bytes = file_obj.read()

        if not pdf_bytes:
            result["status"] = "corrupt"
            result["error_code"] = "EMPTY_FILE"
            result["error_message"] = "Uploaded file is empty."
            return result

        if len(pdf_bytes) > MAX_PDF_SIZE_BYTES:
            result["status"] = "unreadable"
            result["error_code"] = "FILE_TOO_LARGE"
            result["error_message"] = f"PDF exceeds {MAX_PDF_SIZE_BYTES // (1024 * 1024)} MB limit."
            return result

        if not pdf_bytes.startswith(b"%PDF-"):
            result["status"] = "corrupt"
            result["error_code"] = "INVALID_HEADER"
            result["error_message"] = "File is not a valid PDF (missing %PDF header)."
            return result

        native_text = ""
        native_error = None
        try:
            native_text = _extract_native_text(pdf_bytes)
        except (PdfReadError, ValueError, OSError, fitz.FileDataError) as e:
            native_error = str(e)
            logger.warning(f"Native PDF extraction failed: {e}")
        except Exception as e:
            native_error = str(e)
            logger.warning(f"Unexpected native extraction failure: {e}")

        if len(native_text) >= MIN_NATIVE_TEXT_LEN:
            result["text"] = native_text
            result["status"] = "ok"
            result["source"] = "native"
            return result

        logger.info("Low native PDF text detected; attempting OCR fallback")

        ocr_text = ""
        try:
            ocr_text = _ocr_with_rapidocr(
                pdf_bytes, max_pages=MAX_OCR_PAGES, timeout_s=OCR_TIMEOUT_SECONDS
            )
        except Exception as e:
            logger.warning(f"RapidOCR failed: {e}")
        if not ocr_text:
            try:
                ocr_text = _ocr_with_pytesseract(
                    pdf_bytes, max_pages=MAX_OCR_PAGES, timeout_s=OCR_TIMEOUT_SECONDS
                )
            except Exception as e:
                logger.warning(f"Pytesseract OCR failed: {e}")

        combined = f"{native_text}\n{ocr_text}".strip()
        if combined:
            result["text"] = combined
            result["status"] = "partial" if native_error else "ok"
            result["ocr_used"] = bool(ocr_text)
            result["source"] = "native+ocr" if native_text and ocr_text else "ocr"
            if native_error:
                result["error_code"] = "NATIVE_PARSE_FAILED"
                result["error_message"] = native_error
            return result

        result["status"] = "unreadable"
        result["error_code"] = "NO_EXTRACTABLE_TEXT"
        result["error_message"] = native_error or "No text extracted from native parsing or OCR."
        return result
    except Exception as e:
        logger.error(f"Error reading PDF: {e}")
        result["status"] = "corrupt"
        result["error_code"] = "READ_EXCEPTION"
        result["error_message"] = str(e)
        return result


def extract_text_from_pdf(file_obj) -> str:
    """
    Extracts text from a PDF file object.
    Supports both text PDFs and scanned/image PDFs via OCR fallback.
    """
    extraction = extract_resume_content(file_obj)
    if extraction["text"]:
        return extraction["text"]
    if extraction.get("error_message"):
        return f"Error reading PDF: {extraction['error_message']}"
    return ""

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
