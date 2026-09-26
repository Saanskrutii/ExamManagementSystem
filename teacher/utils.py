import re
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


def extract_syllabus_from_pdf(pdf_file):
    """
    High-Precision Syllabus Parser.
    Re-assembles PDF text tokens and extracts Units, Chapters, and Sections cleanly.
    """
    reader = PdfReader(pdf_file)
    full_text = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            full_text += text + "\n"

    # Re-assemble single-word newlines into clean lines
    lines = reassemble_pdf_tokens(full_text)

    units = []
    current_unit = None
    unit_counter = 1

    chapter_re = re.compile(r"^Chapter\s*(\d+)\s*(.*)$", re.IGNORECASE)
    section_re = re.compile(r"^Section\s*(\d+)\s*(.*)$", re.IGNORECASE)
    essential_re = re.compile(r"^Essential\s+Learnings?[\:\-\s]*(.*)$", re.IGNORECASE)

    for line_str in lines:
        line_lower = line_str.lower()

        # Skip main PDF document title/header
        if line_lower.startswith("general science:") or line_lower.startswith("instructor:") or line_lower == "• second semester":
            continue

        # Check for Unit header e.g. "Unit – Matter (State Standard 12.2.1)"
        if line_lower.startswith("unit"):
            title = re.sub(r"^unit\s*[\-\–\:\s]*", "", line_str, flags=re.IGNORECASE).strip()
            title = re.sub(r"\(State Standard.*?\)", "", title, flags=re.IGNORECASE).strip(" -–:")

            if not title or len(title) < 2:
                title = f"Unit {unit_counter}"

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

            c_match = chapter_re.match(line_str)
            s_match = section_re.match(line_str)

            if c_match:
                c_num = c_match.group(1)
                c_title = c_match.group(2).strip()
                item_text = f"\n• Chapter {c_num}: {c_title}" if c_title else f"\n• Chapter {c_num}"
                current_unit["items"].append(item_text)
            elif s_match:
                s_num = s_match.group(1)
                s_title = s_match.group(2).strip()
                item_text = f"  - Section {s_num}: {s_title}" if s_title else f"  - Section {s_num}"
                current_unit["items"].append(item_text)
            else:
                if len(line_str) > 1:
                    current_unit["items"].append(f"  {line_str}")

    if current_unit:
        units.append(current_unit)

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
