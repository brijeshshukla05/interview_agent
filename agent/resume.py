from io import BytesIO
import re
import time
from typing import Any, Dict, List, Optional, Set

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
MIN_PAGE_NATIVE_TEXT_LEN = 60
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


def _normalize_line(line: str) -> str:
    line = re.sub(r"[\u2022\u25cf\u25aa\u25ab\u25ba\u25c6\u2605\u2713\u2714\uf0b7]", " ", line)
    line = re.sub(r"\s+", " ", line).strip(" -|:;,")
    return line.strip()


def extract_candidate_name_from_text(resume_text: str) -> Optional[str]:
    """
    Best-effort deterministic fallback for candidate name extraction.
    """
    if not resume_text:
        return None

    banned_fragments = {
        "curriculum vitae",
        "resume",
        "professional summary",
        "work experience",
        "experience",
        "skills",
        "education",
        "summary",
        "profile",
        "code coverage",
    }
    company_words = {
        "technologies", "technology", "solutions", "systems", "services", "labs",
        "infotech", "consulting", "consultancy", "corp", "corporation", "inc",
        "llc", "ltd", "limited", "pvt", "private", "school", "institute", "university",
    }
    title_words = {
        "engineer", "developer", "architect", "manager", "consultant",
        "analyst", "specialist", "lead", "senior", "junior", "intern",
    }
    non_name_words = {
        "and", "or", "with", "for", "from", "into", "onto", "over", "under", "between",
        "identify", "optimization", "optimizations", "expression", "expressions",
        "coverage", "development", "technologies", "skills", "experience", "certifications",
        "programming", "languages", "services", "application", "applications", "project",
        "software", "management", "tools", "engineering", "front-end", "frontend",
        "other", "patterns",
    }
    lines = [_normalize_line(l) for l in resume_text.splitlines()]
    lines = [l for l in lines if l]

    def is_name_candidate(raw: str) -> bool:
        line = raw.lower()
        if any(x in line for x in banned_fragments):
            return False
        if "@" in raw or "http" in line or re.search(r"\d{7,}", raw):
            return False
        if " at " in line:
            return False
        if raw == raw.lower():
            return False
        words = raw.split()
        if not (2 <= len(words) <= 4):
            return False
        if any(w.lower() in title_words for w in words):
            return False
        if any(w.lower().strip(".,") in company_words for w in words):
            return False
        if any(w.lower().strip(".,") in non_name_words for w in words):
            return False
        if not re.fullmatch(r"[A-Za-z][A-Za-z'.-]+(?:\s+[A-Za-z][A-Za-z'.-]+){1,3}", raw):
            return False
        return True

    # Pass 1: prefer candidate line near contact lines.
    scan_limit = min(len(lines), 200)
    for i in range(scan_limit):
        raw = lines[i]
        if not is_name_candidate(raw):
            continue
        neighborhood = " ".join(lines[i + 1 : min(i + 4, scan_limit)]).lower()
        if ("@" in neighborhood) or ("linkedin" in neighborhood) or ("github" in neighborhood):
            return raw.title()

    return None


def _extract_native_text(pdf_bytes: bytes) -> str:
    """Extract embedded text from PDF (works for text-based PDFs)."""
    reader = PdfReader(BytesIO(pdf_bytes))
    text = ""
    for page in reader.pages:
        text += page.extract_text() or ""
    return text.strip()


def _extract_native_pages_text(pdf_bytes: bytes) -> List[str]:
    """Extract native text page-by-page."""
    reader = PdfReader(BytesIO(pdf_bytes))
    return [(page.extract_text() or "").strip() for page in reader.pages]


def _ocr_with_pytesseract(
    pdf_bytes: bytes,
    max_pages: int = MAX_OCR_PAGES,
    timeout_s: float = OCR_TIMEOUT_SECONDS,
    page_numbers: Optional[Set[int]] = None,
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
        pages_done = 0
        for page_num, page in enumerate(doc):
            if page_numbers is not None and page_num not in page_numbers:
                continue
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
            pages_done += 1
            if pages_done >= max_pages:
                logger.info("Pytesseract OCR page limit reached (%s)", max_pages)
                break
    finally:
        doc.close()

    return "\n".join(p for p in text_parts if p).strip()


def _ocr_with_rapidocr(
    pdf_bytes: bytes,
    max_pages: int = MAX_OCR_PAGES,
    timeout_s: float = OCR_TIMEOUT_SECONDS,
    page_numbers: Optional[Set[int]] = None,
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
        pages_done = 0
        for page_num, page in enumerate(doc):
            if page_numbers is not None and page_num not in page_numbers:
                continue
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
            pages_done += 1
            if pages_done >= max_pages:
                logger.info("RapidOCR page limit reached (%s)", max_pages)
                break
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
        native_pages: List[str] = []
        native_error = None
        try:
            native_pages = _extract_native_pages_text(pdf_bytes)
            native_text = "\n".join([t for t in native_pages if t]).strip()
        except (PdfReadError, ValueError, OSError, fitz.FileDataError) as e:
            native_error = str(e)
            logger.warning(f"Native PDF extraction failed: {e}")
        except Exception as e:
            native_error = str(e)
            logger.warning(f"Unexpected native extraction failure: {e}")

        sparse_pages = {
            idx for idx, page_text in enumerate(native_pages)
            if len(page_text) < MIN_PAGE_NATIVE_TEXT_LEN
        }
        native_name = extract_candidate_name_from_text(native_text)
        ocr_pages = set(sparse_pages)
        if not native_name and native_pages:
            # Name often lives in image header; always OCR first pages when name is missing.
            for i in range(min(2, len(native_pages))):
                ocr_pages.add(i)

        # Fast path: native text is sufficient and no sparse pages need OCR recovery.
        if len(native_text) >= MIN_NATIVE_TEXT_LEN and not sparse_pages and native_name:
            result["text"] = native_text
            result["status"] = "ok"
            result["source"] = "native"
            return result

        logger.info(
            "Attempting OCR fallback (native_len=%s, sparse_pages=%s)",
            len(native_text),
            len(sparse_pages),
        )

        ocr_text = ""
        page_subset = ocr_pages if ocr_pages else None
        try:
            ocr_text = _ocr_with_rapidocr(
                pdf_bytes,
                max_pages=MAX_OCR_PAGES,
                timeout_s=OCR_TIMEOUT_SECONDS,
                page_numbers=page_subset,
            )
        except Exception as e:
            logger.warning(f"RapidOCR failed: {e}")
        if not ocr_text:
            try:
                ocr_text = _ocr_with_pytesseract(
                    pdf_bytes,
                    max_pages=MAX_OCR_PAGES,
                    timeout_s=OCR_TIMEOUT_SECONDS,
                    page_numbers=page_subset,
                )
            except Exception as e:
                logger.warning(f"Pytesseract OCR failed: {e}")

        if native_text and ocr_text and not native_name:
            # Prioritize OCR text first when native missed the header/name.
            combined = f"{ocr_text}\n{native_text}".strip()
        else:
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
        fallback_name = extract_candidate_name_from_text(resume_text) or "Unknown Candidate"
        from datetime import datetime
        prompt = RESUME_SCREENING_PROMPT.format(
            resume_text=resume_text[:4000],
            jd_text=jd_text[:2000],
            current_date=datetime.now().strftime("%B %Y")
        )
        
        llm = get_llm(temperature=config.TEMPERATURE_EVAL, max_tokens=config.MAX_TOKENS_EVAL)
        response = llm.invoke([HumanMessage(content=prompt)])
        parsed = extract_json(response.content)
        if not isinstance(parsed, dict):
            parsed = {}
        llm_name = str(parsed.get("name", "")).strip()
        if not llm_name or llm_name.lower() in {"unknown", "unknown candidate", "n/a", "na"}:
            parsed["name"] = fallback_name
        return parsed
    except Exception as e:
        logger.error(f"Error screening resume: {e}")
        fallback_name = extract_candidate_name_from_text(resume_text) or "Unknown Candidate"
        return {"score": 0, "reasoning": f"Error: {str(e)}", "name": fallback_name}
