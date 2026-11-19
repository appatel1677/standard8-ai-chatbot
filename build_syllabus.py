import json
import os
import glob

SUBJECT_KEYWORDS = {
    "social_science": [
        "social", "samajik", "samaj", "સામાજિક", "સમાજિક",
    ],
    "math": [
        "math", "maths", "ganit", "ગણિત", "ગણીત",
    ],
    "science": [
        "science", "vigyan", "vignan", "વિજ્ઞાન",
    ],
    "environment": [
        "environment", "paryavaran", "aaspas", "aaspaas", "evs",
        "પર્યાવરણ", "આસપાસ", "our wonderful world",
    ],
    "gujarati": [
        "gujarati", "kalshor", "kekarav", "kuhu", "palash",
        "ગુજરાતી", "કલશોર", "કેકારવ", "પલાશ", "કહુ",
    ],
    "english": [
        "english", "અંગ્રેજી",
    ],
    "hindi": [
        "hindi", "હિન્દી", "हिन्दी", "titali", "તિતલી",
    ],
    "sanskrit": [
        "sanskrit", "સંસ્કૃત",
    ],
}


def detect_subject_code_from_filename(filename):
    name = filename.lower()
    # Check social science before science to avoid false matches.
    for code in ("social_science", "math", "science", "environment", "gujarati", "english", "hindi", "sanskrit"):
        for kw in SUBJECT_KEYWORDS[code]:
            if kw.lower() in name:
                return code
    return None


def _grade_dirs(grade_num):
    base_dirs = ["textbook", "textbooks"]
    suffixes = [f"std{grade_num}", f"std_{grade_num}", f"std {grade_num}"]
    dirs = []
    for base in base_dirs:
        if not os.path.isdir(base):
            continue
        # direct expected dirs
        for suf in suffixes:
            p = os.path.join(base, suf)
            if os.path.isdir(p):
                dirs.append(p)
        # also scan for any matching subdir names (case-insensitive)
        try:
            for entry in os.listdir(base):
                full = os.path.join(base, entry)
                if not os.path.isdir(full):
                    continue
                low = entry.lower().replace("-", "_").replace(" ", "")
                if low in {f"std{grade_num}", f"std_{grade_num}"}:
                    dirs.append(full)
        except Exception:
            pass
    # de-duplicate preserving order
    seen = set()
    out = []
    for d in dirs:
        nd = os.path.normpath(d)
        if nd not in seen:
            seen.add(nd)
            out.append(nd)
    return out


def find_local_pdfs(grade_num):
    """Scan textbook dirs for grade and return {subject_code: [relative_pdf_paths]}."""
    found = {}
    for folder in _grade_dirs(grade_num):
        for pdf_path in glob.glob(os.path.join(folder, "*.pdf")):
            rel = os.path.relpath(pdf_path, ".").replace("\\", "/")
            code = detect_subject_code_from_filename(os.path.basename(pdf_path))
            if not code:
                continue
            found.setdefault(code, []).append(rel)
    for code in list(found.keys()):
        found[code] = sorted(set(found[code]))
    return found


def update_syllabus_with_local_pdfs(syllabus):
    for grade in range(3, 9):
        grade_key = f"ધોરણ {grade}"
        grade_data = syllabus.get(grade_key)
        if not grade_data:
            continue
        subjects = grade_data.get("subjects", {})
        local_by_code = find_local_pdfs(grade)

        for _sub_name, sub_info in subjects.items():
            code = sub_info.get("code")
            pdfs = local_by_code.get(code, []) if code else []
            sub_info["local_pdfs"] = pdfs
            for ch in sub_info.get("chapters", []) or []:
                if isinstance(ch, dict):
                    ch["local_pdfs"] = pdfs

        total_pdfs = sum(len(v) for v in local_by_code.values())
        print(f"Grade {grade}: {len(subjects)} subjects | {total_pdfs} local PDFs matched")
    return syllabus


def main():
    path = "diksha_syllabus.json"
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            syllabus = json.load(f)
    else:
        syllabus = {}

    syllabus = update_syllabus_with_local_pdfs(syllabus)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(syllabus, f, ensure_ascii=False, indent=2)

    print("diksha_syllabus.json updated with local PDF paths.")


if __name__ == "__main__":
    main()
