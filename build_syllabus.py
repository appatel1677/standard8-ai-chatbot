import json
import os
import glob

SUBJECT_KEYWORDS = {
    "social_science": ["social", "samajik", "samaj", "સામાજિક", "સમાજિક"],
    "vedic_math": ["vedic", "વૈદિક"],
    "math": ["math", "maths", "ganit", "ગણિત", "ગણીત"],
    "science": ["science", "vigyan", "vignan", "વિજ્ઞાન"],
    "environment": ["environment", "paryavaran", "aaspas", "aaspaas", "evs", "પર્યાવરણ", "આસપાસ", "our wonderful world"],
    "sanskrit": ["sanskrit", "sanskrut", "સંસ્કૃત"],
    "gujarati": ["gujarati", "kalshor", "kekarav", "kuhu", "palash", "ગુજરાતી", "કલશોર", "કેકારવ", "કુહૂ", "પલાશ", "કહુ", "પળાશ"],
    "english": ["english", "અંગ્રેજી"],
    "hindi": ["hindi", "હિન્દી", "हिन्दी", "titali", "તિતલી"],
    "allround": ["sarvangi", "સર્વાંગી", "allround"],
}

PRIMARY_SUBJECTS = {
    "📐 ગણિત (Mathematics)": ("📐", "math"),
    "🌿 પર્યાવરણ (આસપાસ)": ("🌿", "environment"),
    "📖 ગુજરાતી (Gujarati)": ("📖", "gujarati"),
    "🔤 અંગ્રેજી (English)": ("🔤", "english"),
    "🇮🇳 હિન્દી (Hindi)": ("🇮🇳", "hindi"),
}

UPPER_PRIMARY_SUBJECTS = {
    "📐 ગણિત (Mathematics)": ("📐", "math"),
    "🔬 વિજ્ઞાન (Science)": ("🔬", "science"),
    "🌍 સામાજિક વિજ્ઞાન (Social Science)": ("🌍", "social_science"),
    "📖 ગુજરાતી (Gujarati)": ("📖", "gujarati"),
    "🔤 અંગ્રેજી (English)": ("🔤", "english"),
    "🇮🇳 હિન્દી (Hindi)": ("🇮🇳", "hindi"),
    "🕉️ સંસ્કૃત (Sanskrit)": ("🕉️", "sanskrit"),
    "🧮 વૈદિક ગણિત (Vedic Maths)": ("🧮", "vedic_math"),
    "🎨 સર્વાંગી શિક્ષણ (Allround Education)": ("🎨", "allround"),
}


def detect_subject_code(filename):
    name = filename.lower()
    if "gita" in name or "ગીતા" in name:
        return "allround"

    normalized = name
    for marker in (
        "gujarati medium", "gujarati_medium", "gujaratimedium",
        "english medium", "english_medium", "englishmedium",
        "hindi medium", "hindi_medium", "hindimedium",
        "ગુજરાતી માધ્યમ", "અંગ્રેજી માધ્યમ", "હિન્દી માધ્યમ",
        "med gujarati", "med-gujarati", "med_gujarati",
        "med-english", "med_english",
    ):
        normalized = normalized.replace(marker, " ")

    # Sanskrit checked BEFORE Gujarati so Sanskrut_Med-Gujarati maps strictly to sanskrit
    order = ("social_science", "vedic_math", "math", "science", "environment", "sanskrit", "gujarati", "english", "hindi", "allround")
    for code in order:
        if any(kw.lower() in normalized for kw in SUBJECT_KEYWORDS[code]):
            return code
    for code in order:
        if any(kw.lower() in name for kw in SUBJECT_KEYWORDS[code]):
            return code
    return None


def find_local_pdfs(grade_num):
    found = {}
    base_dir = os.path.join("textbook", f"std{grade_num}")
    if not os.path.isdir(base_dir):
        return found

    for pdf_path in glob.glob(os.path.join(base_dir, "*.pdf")):
        rel = os.path.relpath(pdf_path, ".").replace("\\", "/")
        code = detect_subject_code(os.path.basename(pdf_path))
        if code:
            found.setdefault(code, []).append(rel)

    for code in found:
        found[code] = sorted(set(found[code]))
    return found


def main():
    syllabus = {}
    for grade in range(8, 2, -1):
        grade_key = f"ધોરણ {grade}"
        local_by_code = find_local_pdfs(grade)
        sub_map = PRIMARY_SUBJECTS if grade in (3, 4, 5) else UPPER_PRIMARY_SUBJECTS

        subjects = {}
        for sub_name, (icon, code) in sub_map.items():
            pdfs = local_by_code.get(code, [])
            subjects[sub_name] = {
                "icon": icon,
                "code": code,
                "local_pdfs": pdfs,
            }
        syllabus[grade_key] = {"subjects": subjects}
        print(f"Std {grade} -> Gujarati: {local_by_code.get('gujarati', [])} | Sanskrit: {local_by_code.get('sanskrit', [])}")

    with open("diksha_syllabus.json", "w", encoding="utf-8") as f:
        json.dump(syllabus, f, ensure_ascii=False, indent=2)
    print("✅ diksha_syllabus.json સફળતાપૂર્વક અપડેટ થઈ ગઈ છે!")


if __name__ == "__main__":
    main()