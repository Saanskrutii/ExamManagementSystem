import re
import os
import json
import tempfile
from django.conf import settings
from pypdf import PdfReader


def reassemble_pdf_tokens(raw_text):
    """
    Re-assembles words broken into individual newlines by pypdf due to PDF text bounding boxes.
    Combines tokens into clean, logical lines and headings.
    """
    text = raw_text.replace("\xa0", " ").replace("\r", "\n")
    tokens = [t.strip() for t in text.split("\n") if t.strip()]

    reconstructed_lines = []
    current_words = []

    for token in tokens:
        lower = token.lower()

        # Keywords that start a new line / heading
        is_heading_start = (
            lower.startswith("unit")
            or lower.startswith("chapter")
            or lower.startswith("section")
            or lower.startswith("essential learnings")
            or lower == "• second semester"
           # or lower.startswith("general science:")
            or lower.startswith("instructor:")
        )

        if is_heading_start:
            if current_words:
                reconstructed_lines.append(" ".join(current_words))
                current_words = []
            current_words.append(token)
        else:
            current_words.append(token)

    if current_words:
        reconstructed_lines.append(" ".join(current_words))

    return reconstructed_lines


def extract_syllabus_with_ollama(raw_text: str) -> list:
    """
    Sends extracted PDF text to local Ollama / Qwen3 for structured syllabus extraction.
    No data leaves your machine.
    """
    import urllib.request
    import urllib.error

    OLLAMA_URL = "http://localhost:11434/api/generate"
    OLLAMA_MODEL = "qwen3:4b"

    prompt = f"""You are an academic syllabus parser.
Analyse the following syllabus text and extract all educational units/chapters/modules.
Return ONLY a JSON array. Each object MUST have exactly these keys:
- "unit_number": (integer)
- "title": (string) title of the unit
- "description": (string) bullet points or key contents of the unit

Return ONLY the JSON array, no explanation, no markdown fences.

SYLLABUS TEXT:
{raw_text[:6000]}
"""

    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": 2048},
    }).encode("utf-8")

    req = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            raw_response = body.get("response", "").strip()
    except urllib.error.URLError as e:
        print(f"[AI Service] Ollama unreachable: {e}")
        return []

    # Strip <think>...</think> blocks (Qwen3 thinking mode)
    raw_response = re.sub(r"<think>.*?</think>", "", raw_response, flags=re.DOTALL).strip()
    # Strip markdown fences
    if raw_response.startswith("```"):
        raw_response = re.sub(r"^```[a-zA-Z]*\n?", "", raw_response)
        raw_response = raw_response.rstrip("`").strip()

    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError as e:
        print(f"[AI Service Warning] Ollama returned invalid JSON: {e}")
        return []

    if isinstance(data, dict):
        data = data.get("units", data.get("modules", data.get("chapters", [data])))

    if not isinstance(data, list):
        return []

    result = []
    for i, item in enumerate(data):
        if isinstance(item, dict):
            result.append({
                "unit_number": int(item.get("unit_number", i + 1)),
                "title": str(item.get("title", f"Unit {i+1}")),
                "description": str(item.get("description", ""))
            })
    return result


def extract_syllabus_from_pdf(pdf_file):
    """
    High-Precision Syllabus Parser.
    First tries PyPDF2 text extraction. If it's a scanned PDF, falls back to Gemini AI OCR.
    """
    pdf_file.seek(0)
    reader = PdfReader(pdf_file)
    full_text = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text += text + "\n"

    # If it's a scanned PDF without an OCR text layer, pypdf returns almost nothing 
    # or just watermarks like "Scanned by PDF Scanner".
    # We send the little text we have to Ollama for best-effort parsing.
    if len(full_text.strip()) < 300 or "scanned by pdf scanner" in full_text.lower():
        ai_extracted = extract_syllabus_with_ollama(full_text or "(scanned PDF — no text layer found)")
        if ai_extracted:
            return ai_extracted
        else:
            return [{"unit_number": 999, "title": "Could Not Extract", "description": "Ollama could not extract syllabus units from this PDF. Please ensure Ollama is running (ollama serve) or upload a text-based PDF."}]

    # Re-assemble single-word newlines into clean lines
    lines = reassemble_pdf_tokens(full_text)

    units = []
    current_unit = None
    unit_counter = 1
    fallback_items = []

    chapter_re = re.compile(r"^Chapter\s*(\d+)\s*(.*)$", re.IGNORECASE)
    section_re = re.compile(r"^Section\s*(\d+)\s*(.*)$", re.IGNORECASE)
    essential_re = re.compile(r"^Essential\s+Learnings?[\:\-\s]*(.*)$", re.IGNORECASE)
    
    # Matches Unit, Module, Chapter, or Topic at the start of a line
    unit_header_re = re.compile(r"^(unit|module|chapter|topic)\s*(.*)", re.IGNORECASE)

    for line_str in lines:
        line_lower = line_str.lower()

        # Skip main PDF document title/header
        if line_lower.startswith("general science:") or line_lower.startswith("instructor:") or line_lower == "• second semester":
            continue

        # Check for Unit/Module/Topic header
        unit_match = unit_header_re.match(line_str)
        if unit_match:
            prefix = unit_match.group(1).capitalize()
            raw_title = unit_match.group(2)
            title = re.sub(r"^[\-\–\:\s]*", "", raw_title).strip()
            title = re.sub(r"\(State Standard.*?\)", "", title, flags=re.IGNORECASE).strip(" -–:")

            if not title or len(title) < 2:
                title = f"{prefix} {unit_counter}"

            if current_unit:
                units.append(current_unit)

            current_unit = {
                "unit_number": unit_counter,
                "title": title[:200],
                "items": [],
            }
            unit_counter += 1
            continue

        if current_unit:
            e_match = essential_pattern_check(line_str)
            if e_match:
                current_unit["items"].append(f"📌 Essential Learnings: {e_match}")
                continue

            # We don't need chapter_re match if we already treat "Chapter" as a unit boundary,
            # but we keep it for subsections if it appears inside a unit.
            c_match = chapter_re.match(line_str)
            s_match = section_re.match(line_str)

            if c_match and "chapter" not in line_lower: # avoid double processing if chapter was already a unit
                pass 
            elif s_match:
                s_num = s_match.group(1)
                s_title = s_match.group(2).strip()
                item_text = f"  - Section {s_num}: {s_title}" if s_title else f"  - Section {s_num}"
                current_unit["items"].append(item_text)
            else:
                if len(line_str) > 1:
                    current_unit["items"].append(f"  {line_str}")
        else:
            # Collect text that appears before any Unit header (fallback)
            if len(line_str) > 1:
                fallback_items.append(f"  {line_str}")

    if current_unit:
        units.append(current_unit)
        
    # Fallback: if no units/modules were found at all, wrap everything in Unit 1
    if not units and fallback_items:
        units.append({
            "unit_number": 1,
            "title": "General Syllabus Content",
            "items": fallback_items
        })

    # Format output
    result = []
    for u in units:
        desc = "\n".join(u["items"]).strip()
        result.append({
            "unit_number": u["unit_number"],
            "title": u["title"],
            "description": desc,
        })

    return result


def essential_pattern_check(text):
    match = re.search(r"Essential\s+Learnings?[\:\-\s]*(.*)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None
