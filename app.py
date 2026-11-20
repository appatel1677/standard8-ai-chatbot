import streamlit as st
import streamlit.components.v1 as components
import json, os, io, re, time
from PIL import Image
from fpdf import FPDF

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

st.set_page_config(
    page_title="Standard 3 to 8 Smart AI Palaj Teacher",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- PDF & MCQ HELPERS ---
def parse_mcq(text):
    questions = []
    for part in re.split(r'\n?પ્રશ્ન\s*\d+\s*[:.]', text)[1:]:
        lines = [l.strip() for l in part.strip().splitlines() if l.strip()]
        if not lines:
            continue
        q_text, options, answer, explanation = lines[0], {}, None, ""
        for l in lines[1:]:
            if m := re.match(r'([ABCD])[\).]\s*(.*)', l):
                options[m.group(1)] = m.group(2)
            elif re.search(r'સાચો જવાબ|જવાબ|Answer', l) and (ma := re.search(r'([ABCD])', l)):
                answer = ma.group(1)
            elif re.search(r'સમજૂતી|Explanation', l):
                explanation = re.sub(r'^(સમજૂતી|Explanation)[:.]?\s*', '', l)
        if q_text and options and answer:
            questions.append({"question": q_text, "options": options, "answer": answer, "explanation": explanation})
    return questions

@st.cache_resource
def get_pdf_font():
    for p in ["C:/Windows/Fonts/Nirmala.ttf", "C:/Windows/Fonts/Shruti.ttf", "NotoSansGujarati-Regular.ttf"]:
        if os.path.exists(p):
            return p
    try:
        import urllib.request
        urllib.request.urlretrieve(
            "https://github.com/google/fonts/raw/main/ofl/notosansgujarati/NotoSansGujarati%5Bwdth%2Cwght%5D.ttf",
            "NotoSansGujarati-Regular.ttf"
        )
        return "NotoSansGujarati-Regular.ttf"
    except Exception:
        return None

def build_pdf_bytes(messages):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_text_shaping(True)
    font_path = get_pdf_font()
    base_font = "Gujarati" if font_path else "helvetica"
    if font_path:
        pdf.add_font("Gujarati", "", font_path)
        pdf.add_font("Gujarati", "B", font_path)
    pdf.add_page()
    pdf.set_font(base_font, "B", 15)
    pdf.cell(0, 10, "Standard 3 to 8 Smart AI Palaj Teacher - Notes", ln=True, align="C")
    pdf.ln(4)
    for m in messages:
        pdf.set_font(base_font, "B", 11)
        pdf.cell(0, 7, ("વિદ્યાર્થી:" if m["role"] == "user" else "શિક્ષક:"), ln=True)
        pdf.set_font(base_font, "", 10)
        clean_txt = re.sub(r"<svg[\s\S]*?</svg>", "[આકૃતિ / નકશો સંલગ્ન છે]", m["content"])
        clean_txt = re.sub(r"```map_json[\s\S]*?```", "[ભારતનો નકશો સંલગ્ન છે]", clean_txt)
        clean_txt = re.sub(r"<[^>]+>", "", clean_txt)
        pdf.multi_cell(0, 6, clean_txt)
        pdf.ln(2)
    return bytes(pdf.output(dest="S"))

def transcribe_gujarati(audio_file, api_keys, preferred_model="gemini-2.5-flash-lite", lang_name="ગુજરાતી"):
    if not HAS_GENAI or not api_keys or not audio_file:
        return "", "API Key અથવા ઓડિયો ફાઈલ ઉપલબ્ધ નથી."

    audio_bytes = audio_file.getvalue()
    if len(audio_bytes) < 100:
        return "", "ઓડિયો રેકોર્ડ થયો નથી."

    detected_mime = getattr(audio_file, "type", None) or "audio/wav"
    mime_candidates = list(dict.fromkeys([detected_mime, "audio/wav", "audio/webm", "audio/mp4"]))
    model_candidates = list(dict.fromkeys([preferred_model, "gemini-2.5-flash-lite", "gemini-2.5-flash"]))

    script_hint = {
        "ગુજરાતી": "Gujarati script (ગુજરાતી લિપિ)",
        "English": "English text",
        "हिन्दी": "Hindi Devanagari script (हिन्दी लिपि)"
    }.get(lang_name, "Gujarati script (ગુજરાતી લિપિ)")

    prompt = (
        f"Listen to this audio carefully and transcribe ONLY the exact spoken words in {script_hint}. "
        "Do not add any explanation, translation, or extra text."
    )

    last_err = ""
    for key in api_keys:
        client = genai.Client(api_key=key)
        for mod in model_candidates:
            for mime in mime_candidates:
                try:
                    resp = client.models.generate_content(
                        model=mod,
                        contents=[types.Part.from_bytes(data=audio_bytes, mime_type=mime), prompt]
                    )
                    if resp and resp.text and resp.text.strip():
                        return resp.text.strip(), ""
                except Exception as e:
                    last_err = str(e)
                    if any(x in last_err for x in ("404", "429", "RESOURCE_EXHAUSTED")):
                        break
            if any(x in last_err for x in ("429", "RESOURCE_EXHAUSTED")):
                break

    return "", f"ઓડિયો ટ્રાન્સક્રાઈબ ન થઈ શક્યો: {last_err}"

@st.cache_data
def load_syllabus():
    if os.path.exists("diksha_syllabus.json"):
        with open("diksha_syllabus.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

# --- ACCURATE INDIA MAP COORDINATES & RENDERER ---
_INDIA_STATE_COORDS = {
    "jammu": (165, 52, "જમ્મુ-કાશ્મીર"),
    "ladakh": (195, 42, "લદ્દાખ"),
    "himachal": (182, 85, "હિમાચલ પ્રદેશ"),
    "punjab": (152, 102, "પંજાબ"),
    "haryana": (162, 122, "હરિયાણા"),
    "uttarakhand": (205, 112, "ઉત્તરાખંડ"),
    "rajasthan": (122, 165, "રાજસ્થાન"),
    "uttar pradesh": (225, 162, "ઉત્તર પ્રદેશ"),
    "bihar": (292, 178, "બિહાર"),
    "gujarat": (88, 222, "ગુજરાત"),
    "madhya pradesh": (185, 218, "મધ્ય પ્રદેશ"),
    "chhattisgarh": (245, 238, "છત્તીસગઢ"),
    "jharkhand": (285, 208, "ઝારખંડ"),
    "west bengal": (322, 222, "પશ્ચિમ બંગાળ"),
    "odisha": (282, 265, "ઓડિશા"),
    "maharashtra": (148, 275, "મહારાષ્ટ્ર"),
    "telangana": (202, 298, "તેલંગાણા"),
    "andhra pradesh": (212, 342, "આંધ્ર પ્રદેશ"),
    "karnataka": (152, 348, "કર્ણાટક"),
    "goa": (125, 332, "ગોવા"),
    "kerala": (158, 412, "કેરળ"),
    "tamil nadu": (192, 405, "તમિલનાડુ"),
    "assam": (382, 168, "આસામ"),
    "arunachal": (405, 142, "અરુણાચલ પ્રદેશ"),
    "meghalaya": (368, 185, "મેઘાલય"),
    "tripura": (375, 212, "ત્રિપુરા"),
    "mizoram": (388, 215, "મિઝોરમ"),
    "manipur": (398, 195, "મણિપુર"),
    "nagaland": (405, 175, "નાગાલેન્ડ"),
    "sikkim": (332, 152, "સિક્કિમ"),
}

_STATE_ALIASES = {
    "પંજાબ": "punjab", "punjab": "punjab",
    "ઉત્તર પ્રદેશ": "uttar pradesh", "uttar pradesh": "uttar pradesh", "up": "uttar pradesh",
    "પશ્ચિમ બંગાળ": "west bengal", "west bengal": "west bengal", "બંગાળ": "west bengal",
    "રાજસ્થાન": "rajasthan", "rajasthan": "rajasthan",
    "ગુજરાત": "gujarat", "gujarat": "gujarat",
    "મહારાષ્ટ્ર": "maharashtra", "maharashtra": "maharashtra",
    "મધ્ય પ્રદેશ": "madhya pradesh", "madhya pradesh": "madhya pradesh", "mp": "madhya pradesh",
    "બિહાર": "bihar", "bihar": "bihar",
    "ઓડિશા": "odisha", "odisha": "odisha", "orissa": "odisha",
    "કર્ણાટક": "karnataka", "karnataka": "karnataka",
    "તમિલનાડુ": "tamil nadu", "tamil nadu": "tamil nadu",
    "આંધ્ર પ્રદેશ": "andhra pradesh", "andhra pradesh": "andhra pradesh",
    "તેલંગાણા": "telangana", "telangana": "telangana",
    "કેરળ": "kerala", "kerala": "kerala",
    "આસામ": "assam", "assam": "assam",
    "ઝારખંડ": "jharkhand", "jharkhand": "jharkhand",
    "છત્તીસગઢ": "chhattisgarh", "chhattisgarh": "chhattisgarh",
    "હરિયાણા": "haryana", "haryana": "haryana",
    "હિમાચલ પ્રદેશ": "himachal", "himachal": "himachal",
    "ઉત્તરાખંડ": "uttarakhand", "uttarakhand": "uttarakhand",
    "જમ્મુ": "jammu", "jammu": "jammu", "kashmir": "jammu",
    "ગોવા": "goa", "goa": "goa",
    "સિક્કિમ": "sikkim", "sikkim": "sikkim",
}

def build_india_map_html(map_spec):
    """Build a crisp, accurate SVG India Map with symbols, state labels & legend."""
    title = map_spec.get("title", "ભારતનો નકશો - નકશા પૂર્તિ")
    items = map_spec.get("items", [])

    # Accurate India SVG outline path
    india_outline = (
        "M 162,25 L 185,22 L 210,36 L 222,55 L 205,72 L 198,92 L 222,108 L 245,132 "
        "L 285,148 L 325,152 L 334,138 L 342,152 L 365,152 L 395,132 L 422,142 L 414,168 "
        "L 404,195 L 392,226 L 378,224 L 372,202 L 352,196 L 342,216 L 332,242 L 308,262 "
        "L 282,292 L 245,326 L 218,365 L 204,405 L 182,438 L 166,435 L 152,398 L 134,355 "
        "L 118,308 L 112,262 L 82,252 L 58,236 L 74,218 L 62,204 L 88,196 L 102,182 "
        "L 92,155 L 122,126 L 142,96 L 152,68 L 146,44 Z"
    )

    state_offset_count = {}
    markers_svg = []
    legend_svg = []

    for idx, item in enumerate(items[:8]):
        label = str(item.get("label", ""))
        symbol = str(item.get("symbol", "●"))
        color = str(item.get("color", "#DC2626"))
        states = item.get("states", [])

        # Legend entry
        ly = 56 + idx * 36
        legend_svg.append(
            f'<rect x="448" y="{ly-14}" width="22" height="22" rx="5" fill="{color}" fill-opacity="0.18" stroke="{color}" stroke-width="1.5"/>'
            f'<text x="459" y="{ly+2}" text-anchor="middle" font-size="14" font-weight="bold" fill="{color}">{symbol}</text>'
            f'<text x="478" y="{ly-2}" font-size="13" font-weight="bold" fill="#0F172A">{label}</text>'
            f'<text x="478" y="{ly+13}" font-size="11" fill="#334155">({", ".join(states)})</text>'
        )

        for st_name in states:
            key = _STATE_ALIASES.get(st_name.strip().lower()) or _STATE_ALIASES.get(st_name.strip())
            if not key or key not in _INDIA_STATE_COORDS:
                continue
            bx, by, guj_st = _INDIA_STATE_COORDS[key]
            cnt = state_offset_count.get(key, 0)
            state_offset_count[key] = cnt + 1

            # Offset multiple symbols in the same state so they never overlap
            dx = (cnt % 2) * 20 - (10 if cnt > 0 else 0)
            dy = (cnt // 2) * 18
            px, py = bx + dx, by + dy

            markers_svg.append(
                f'<circle cx="{px}" cy="{py}" r="11" fill="#FFFFFF" stroke="{color}" stroke-width="2"/>'
                f'<text x="{px}" y="{py+4}" text-anchor="middle" font-size="13" font-weight="bold" fill="{color}">{symbol}</text>'
            )
            if cnt == 0:
                markers_svg.append(
                    f'<text x="{bx}" y="{by+22}" text-anchor="middle" font-size="10.5" font-weight="bold" fill="#1E293B">{guj_st}</text>'
                )

    legend_height = max(140, 50 + len(items[:8]) * 36)
    html = f"""
    <div style="background:#FFFFFF; border:2px solid #93C5FD; border-radius:14px; padding:10px; font-family:'Noto Sans Gujarati', sans-serif;">
      <svg width="100%" viewBox="0 0 680 460" xmlns="http://www.w3.org/2000/svg" style="max-height:450px; display:block; margin:auto;">
        <rect x="0" y="0" width="680" height="460" rx="12" fill="#F8FAFC"/>
        <text x="340" y="26" text-anchor="middle" font-size="17" font-weight="bold" fill="#1E3A8A">{title}</text>
        <!-- Compass -->
        <g transform="translate(55, 65)">
          <circle cx="0" cy="0" r="18" fill="#EFF6FF" stroke="#3B82F6" stroke-width="1.5"/>
          <line x1="0" y1="-13" x2="0" y2="13" stroke="#1E3A8A" stroke-width="1.5"/>
          <line x1="-13" y1="0" x2="13" y2="0" stroke="#1E3A8A" stroke-width="1.5"/>
          <text x="0" y="-21" text-anchor="middle" font-size="10" font-weight="bold" fill="#1E3A8A">ઉત્તર</text>
        </g>
        <!-- India Outline -->
        <path d="{india_outline}" fill="#FEF9C3" stroke="#92400E" stroke-width="2.2" stroke-linejoin="round"/>
        <!-- State Markers -->
        {''.join(markers_svg)}
        <!-- Legend Box -->
        <rect x="438" y="34" width="232" height="{legend_height}" rx="10" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="1.5"/>
        <text x="554" y="50" text-anchor="middle" font-size="13.5" font-weight="bold" fill="#1E3A8A">📌 સંજ્ઞા સૂચિ (Legend)</text>
        <line x1="448" y1="55" x2="660" y2="55" stroke="#E2E8F0" stroke-width="1"/>
        {''.join(legend_svg)}
      </svg>
    </div>
    """
    return html

# --- SMART GRADE, SUBJECT, DIAGRAM, MAP & GK DETECTION ---
_GUJ_DIGIT_MAP = str.maketrans("૦૧૨૩૪૫૬૭૮૯", "0123456789")

_SUBJECT_LABELS = {
    "gujarati": "ગુજરાતી",
    "sanskrit": "સંસ્કૃત",
    "math": "ગણિત",
    "science": "વિજ્ઞાન",
    "social_science": "સામાજિક વિજ્ઞાન",
    "environment": "પર્યાવરણ (આસપાસ)",
    "english": "અંગ્રેજી",
    "hindi": "હિન્દી",
    "vedic_math": "વૈદિક ગણિત",
    "allround": "સર્વાંગી શિક્ષણ",
}

_EXPLICIT_SUBJECTS = {
    "social_science": [
        "સામાજિક વિજ્ઞાન", "સામાજિક", "સમાજિક", "social science", "social", "samajik", "samaj",
        "ઇતિહાસ", "ભૂગોળ", "નાગરિક", "ઉદ્યોગ", "ટિસ્કો", "tisco", "જમશેદપુર", "બંધારણ", "સંસદ",
        "નકશો", "નક્શો", "નકશા", "નક્શા", "નકશાપૂર્તિ", "પાક ઉત્પાદન"
    ],
    "vedic_math": ["વૈદિક ગણિત", "vedic math", "vedic"],
    "math": ["ગણિત", "ગણીત", "math", "maths", "ganit", "ગણિત ગમ્મત", "ગણિત મેળો", "ભૂમિતિ", "બીજગણિત", "સમીકરણ", "અપૂર્ણાંક"],
    "science": ["વિજ્ઞાન", "science", "vigyan", "vignan", "પ્રકાશસંશ્લેષણ", "કોષ", "વિદ્યુત", "ચુંબક", "બળ", "દબાણ", "અણુ", "પરમાણુ", "મીણબત્તી", "જ્યોત"],
    "environment": ["પર્યાવરણ", "આસપાસ", "environment", "paryavaran", "aaspas", "aaspaas", "evs"],
    "gujarati": ["ગુજરાતી", "gujarati", "કલશોર", "kalshor", "કેકારવ", "kekarav", "કુહૂ", "કહુ", "kuhu", "પલાશ", "પળાશ", "palash", "કાવ્ય", "વ્યાકરણ", "સમાસ", "અલંકાર", "રૂઢિપ્રયોગ"],
    "sanskrit": ["સંસ્કૃત", "sanskrit", "sanskrut", "સુભાષિતાનિ", "શ્લોક"],
    "english": ["અંગ્રેજી", "english", "grammar", "tense"],
    "hindi": ["હિન્દી", "hindi", "हिन्दी", "તિતલી", "titali"],
    "allround": ["સર્વાંગી", "sarvangi", "ગીતા", "gita"],
}

_GK_OR_CA_KEYWORDS = [
    "current affair", "current affairs", "કરંટ અફેર્સ", "કરંટ", "વર્તમાન પ્રવાહ", "વર્તમાન પ્રવાહો",
    "તાજેતરના", "તાજેતરમાં", "આજના સમાચાર", "general knowledge", "સામાન્ય જ્ઞાન", "gk", "જી.કે", "જીકે",
    "વડાપ્રધાન", "રાષ્ટ્રપતિ", "મુખ્યમંત્રી", "રાજધાની", "ઓલિમ્પિક", "વર્લ્ડ કપ", "ઈસરો", "isro", "ચંદ્રયાન"
]

_DIAGRAM_KEYWORDS = [
    "આકૃતિ", "નામનિર્દેશ", "નામ નિર્દેશ", "ચિત્ર દોરી", "આકૃતિ દોરી", "આકૃતિ દોરો",
    "diagram", "labeled diagram", "draw", "sketch"
]

_MAP_KEYWORDS = [
    "નકશો", "નક્શો", "નકશા", "નક્શા", "નકશાપૂર્તિ", "નક્શાપૂર્તિ", "map", "સંજ્ઞા વડે", "સંગ્ના વદે"
]

def wants_diagram(text):
    t = (text or "").lower()
    return any(kw in t for kw in _DIAGRAM_KEYWORDS)

def wants_map(text):
    t = (text or "").lower()
    return any(kw in t for kw in _MAP_KEYWORDS)

def is_gk_or_current_affairs(text):
    t = (text or "").lower()
    return any(kw in t for kw in _GK_OR_CA_KEYWORDS)

def extract_grade(text):
    t = (text or "").translate(_GUJ_DIGIT_MAP).lower()
    patterns = [
        r"ધોરણ\s*[-:.]?\s*([3-8])",
        r"ધો\.?\s*[-:.]?\s*([3-8])",
        r"std\.?\s*[-:.]?\s*([3-8])",
        r"dhoran\s*[-:.]?\s*([3-8])",
        r"grade\s*[-:.]?\s*([3-8])",
        r"class\s*[-:.]?\s*([3-8])",
        r"\b([3-8])\s*મુ\b",
        r"\b([3-8])\s*માં\b",
    ]
    for p in patterns:
        if m := re.search(p, t):
            return int(m.group(1))
    return None

def extract_subject(text):
    t = (text or "").lower()
    for code, keywords in _EXPLICIT_SUBJECTS.items():
        for kw in keywords:
            if re.search(rf"(?<![a-zA-Z]){re.escape(kw.lower())}(?![a-zA-Z])", t):
                return code
    return None

def resolve_grade_subject_and_pdfs(current_query, past_user_queries, syllabus):
    explicit_grade = extract_grade(current_query)
    explicit_subject = extract_subject(current_query)

    if explicit_grade is None and is_gk_or_current_affairs(current_query):
        return None, None, []

    grade = explicit_grade
    subject = explicit_subject

    if grade is None or subject is None:
        is_followup = any(w in current_query.lower() for w in ("આ પાઠ", "આ પ્રકરણ", "આનો", "તેનો", "સારાંશ", "સ્વાધ્યાય", "mcq", "ઉદાહરણ", "વધુ સમજાવો"))
        if is_followup:
            for prev_q in reversed(past_user_queries[-3:]):
                if grade is None:
                    grade = extract_grade(prev_q)
                if subject is None:
                    subject = extract_subject(prev_q)
                if grade is not None and subject is not None:
                    break

    if not grade or not subject:
        return grade, subject, []

    matched = []
    grade_key = f"ધોરણ {grade}"
    subjects_dict = (syllabus.get(grade_key) or {}).get("subjects", {})
    for _label, info in subjects_dict.items():
        if info.get("code") == subject:
            for p in info.get("local_pdfs") or []:
                path = p.replace("\\", "/")
                if os.path.exists(path) and path not in matched:
                    matched.append(path)
            break

    if not matched:
        folder = f"textbook/std{grade}"
        if os.path.isdir(folder):
            for fname in sorted(os.listdir(folder)):
                if not fname.lower().endswith(".pdf"):
                    continue
                low = fname.lower()
                if subject == "gujarati" and any(k in low for k in ("gujarati", "kalshor", "kekarav", "kuhu", "palash")) and not any(x in low for x in ("sanskrit", "sanskrut", "gita", "ગીતા")):
                    matched.append(f"{folder}/{fname}")
                elif subject == "sanskrit" and any(k in low for k in ("sanskrit", "sanskrut", "સંસ્કૃત")):
                    matched.append(f"{folder}/{fname}")
                elif subject == "math" and any(k in low for k in ("math", "ganit", "ગણિત")) and "vedic" not in low and "વૈદિક" not in low:
                    matched.append(f"{folder}/{fname}")
                elif subject == "science" and any(k in low for k in ("science", "vigyan", "વિજ્ઞાન")):
                    matched.append(f"{folder}/{fname}")
                elif subject == "social_science" and any(k in low for k in ("social", "samajik", "સામાજિક")):
                    matched.append(f"{folder}/{fname}")
                elif subject == "environment" and any(k in low for k in ("environment", "evs", "paryavaran", "પર્યાવરણ")):
                    matched.append(f"{folder}/{fname}")
                elif subject == "english" and "english" in low:
                    matched.append(f"{folder}/{fname}")
                elif subject == "hindi" and any(k in low for k in ("hindi", "titali")):
                    matched.append(f"{folder}/{fname}")

    return grade, subject, matched[:2]

# --- VISION PAGE RENDERER ---
def _pick_target_page_indices(total_pages, query_text, full_query_context):
    selected = set(range(min(22, total_pages)))

    q_norm = f"{query_text} {full_query_context}".translate(_GUJ_DIGIT_MAP).lower()
    chap_nums = [int(n) for n in re.findall(r"(?:પાઠ|પ્રકરણ|કવિતા|એકમ|chapter|unit|lesson)\s*[-:.]?\s*(\d{1,2})", q_norm)]
    if not chap_nums:
        cleaned = re.sub(r"(?:ધોરણ|ધો\.?|std\.?|dhoran|grade|class)\s*[-:.]?\s*[3-8]", " ", q_norm)
        chap_nums = [int(n) for n in re.findall(r"\b(\d{1,2})\b", cleaned) if 1 <= int(n) <= 25]

    for ch in chap_nums[:2]:
        est_start = max(16, 14 + (ch - 1) * 8)
        for p in range(est_start - 2, min(total_pages, est_start + 10)):
            selected.add(p)

    for p_str in re.findall(r"(?:પાના|પાનું|પેજ|page)\s*(?:નંબર|નં\.?|no\.?)?\s*[-:.]?\s*(\d{1,3})", q_norm):
        p_idx = int(p_str) - 1
        for neighbor in range(max(0, p_idx - 1), min(total_pages, p_idx + 3)):
            selected.add(neighbor)

    return sorted(selected)[:28]

@st.cache_data(show_spinner=False)
def render_pdf_pages_as_jpeg_bytes(abspath, mtime, page_indices):
    images = []
    try:
        import fitz
        with fitz.open(abspath) as doc:
            for idx in page_indices:
                if 0 <= idx < len(doc):
                    pix = doc[idx].get_pixmap(dpi=130, alpha=False)
                    images.append((idx + 1, pix.tobytes("jpeg", jpg_quality=82)))
    except Exception:
        pass
    return images

def build_vision_pdf_parts(pdf_path, query_text, history_text):
    try:
        abspath = os.path.abspath(pdf_path)
        mtime = os.path.getmtime(abspath)
        import fitz
        with fitz.open(abspath) as doc:
            total_pages = len(doc)
    except Exception:
        return []

    target_indices = _pick_target_page_indices(total_pages, query_text, history_text)
    rendered = render_pdf_pages_as_jpeg_bytes(abspath, mtime, tuple(target_indices))
    parts = []
    for _pno, jpg_bytes in rendered:
        parts.append(types.Part.from_bytes(data=jpg_bytes, mime_type="image/jpeg"))
    return parts

def render_message_with_visuals(content):
    """Render both India Map JSON blocks and SVG Diagrams cleanly using components.html so nothing gets stripped."""
    # 1. Handle ```map_json ... ``` blocks
    if "```map_json" in content:
        segments = re.split(r"(```map_json[\s\S]*?```)", content)
        for seg in segments:
            if seg.startswith("```map_json"):
                raw_json = re.sub(r"^```map_json\s*|\s*```$", "", seg).strip()
                try:
                    spec = json.loads(raw_json)
                    components.html(build_india_map_html(spec), height=475, scrolling=False)
                except Exception:
                    st.code(raw_json)
            elif seg.strip():
                st.markdown(seg)
        return

    # 2. Handle inline <svg>...</svg> diagrams using components.html so Streamlit never strips SVG tags
    clean = re.sub(r"```(?:svg|xml|html)?\s*(<svg[\s\S]*?</svg>)\s*```", r"\1", content, flags=re.IGNORECASE)
    if "<svg" in clean.lower() and "</svg>" in clean.lower():
        parts = re.split(r"(<svg[\s\S]*?</svg>)", clean, flags=re.IGNORECASE)
        for part in parts:
            if part.strip().lower().startswith("<svg"):
                html_box = (
                    '<div style="background:#FFFFFF; border-radius:12px; padding:8px; '
                    'text-align:center; border:2px solid #93C5FD; font-family:\'Noto Sans Gujarati\', sans-serif;">'
                    f'{part}</div>'
                )
                components.html(html_box, height=355, scrolling=False)
            elif part.strip():
                st.markdown(part)
    else:
        st.markdown(clean)

syllabus_data = load_syllabus()

# --- POLISHED UI & BOTTOM INPUT BAR STYLING ---
st.markdown("""
<style>
:root {
    --app-bg: #F4F7FB;
    --app-text: #0F172A;
    --surface: #FFFFFF;
    --surface-border: #CBD5E1;
    --sidebar-bg: #FFFFFF;
    --sidebar-text: #0F172A;
    --accent: #2563EB;
    --bubble-user: #1E3A8A;
    --bubble-assistant: #111827;
    --bubble-text: #FFFFFF;
    --bottom-bar: #1E293B;
    --bottom-bar-border: #475569;
    --bottom-input: #0F172A;
    --bottom-input-border: #64748B;
}

html, body, [data-testid="stAppViewContainer"], .stApp, .main {
    max-width: 100vw !important;
    overflow-x: hidden !important;
    font-family: system-ui, -apple-system, 'Noto Sans Gujarati', 'Shruti', sans-serif !important;
    background-color: var(--app-bg) !important;
    color: var(--app-text) !important;
}

[data-testid="stHeader"] { background: transparent !important; }

.block-container {
    padding-top: 2.6rem !important;
    padding-bottom: 6.5rem !important;
    padding-left: 0.75rem !important;
    padding-right: 0.75rem !important;
    max-width: 820px !important;
    margin: 0 auto !important;
}

.slim-header {
    background: linear-gradient(90deg, #1E3A8A 0%, #2563EB 50%, #0284C7 100%);
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
    padding: 10px 18px;
    border-radius: 50px;
    text-align: center;
    font-size: 1.05rem;
    font-weight: 700;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25);
    margin-bottom: 12px;
}

.book-badge {
    display: inline-block;
    background: #DBEAFE;
    color: #1E3A8A !important;
    -webkit-text-fill-color: #1E3A8A !important;
    border: 1px solid #93C5FD;
    padding: 4px 12px;
    border-radius: 999px;
    font-size: 0.85rem;
    font-weight: 600;
    margin-bottom: 8px;
}

/* Sidebar */
section[data-testid="stSidebar"], [data-testid="stSidebar"] > div {
    background-color: var(--sidebar-bg) !important;
    color: var(--sidebar-text) !important;
    border-right: 1px solid var(--surface-border) !important;
}
section[data-testid="stSidebar"] p, section[data-testid="stSidebar"] span, section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] h1, section[data-testid="stSidebar"] h2, section[data-testid="stSidebar"] h3 {
    color: var(--sidebar-text) !important;
    -webkit-text-fill-color: var(--sidebar-text) !important;
}

/* Buttons */
.stButton > button, [data-testid="stDownloadButton"] > button {
    background-color: var(--surface) !important;
    color: var(--app-text) !important;
    -webkit-text-fill-color: var(--app-text) !important;
    border: 1px solid var(--surface-border) !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
}

/* Chat bubbles */
[data-testid="stChatMessage"] {
    border-radius: 14px !important;
    padding: 0.75rem 0.95rem !important;
    margin-bottom: 0.65rem !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.14) !important;
    background-color: var(--bubble-assistant) !important;
    border-left: 5px solid #34D399 !important;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]),
[data-testid="stChatMessage"][aria-label*="user" i] {
    background-color: var(--bubble-user) !important;
    border-left: 5px solid #60A5FA !important;
}
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li, [data-testid="stChatMessage"] span,
[data-testid="stChatMessage"] strong, [data-testid="stChatMessage"] em {
    color: var(--bubble-text) !important;
    -webkit-text-fill-color: var(--bubble-text) !important;
}
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li { font-size: 16px !important; line-height: 1.6 !important; }
[data-testid="stChatMessage"] .book-badge {
    background: #DBEAFE !important;
    color: #1E3A8A !important;
    -webkit-text-fill-color: #1E3A8A !important;
}

/* Bottom input bar with wide Language Selector so "ગુજરાતી" fits completely */
[data-testid="stBottom"] {
    padding: 0.45rem 0.5rem !important;
    background: transparent !important;
    z-index: 99999 !important;
}
[data-testid="stBottom"] > div {
    max-width: 820px !important;
    margin: 0 auto !important;
    padding: 0 !important;
}
[data-testid="stBottom"] [data-testid="stHorizontalBlock"] {
    display: grid !important;
    grid-template-columns: 38px 114px minmax(0, 1fr) 38px 38px !important;
    align-items: center !important;
    gap: 6px !important;
    background-color: var(--bottom-bar) !important;
    border: 1px solid var(--bottom-bar-border) !important;
    border-radius: 999px !important;
    padding: 5px 8px !important;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25) !important;
    width: 100% !important;
    box-sizing: border-box !important;
}
[data-testid="stBottom"] [data-testid="stColumn"] {
    width: 100% !important; min-width: 0 !important; max-width: 100% !important;
    padding: 0 !important; margin: 0 !important;
    display: flex !important; align-items: center !important; justify-content: center !important;
}
[data-testid="stBottom"] [data-testid="stSelectbox"] { width: 100% !important; }
[data-testid="stBottom"] [data-testid="stSelectbox"] div[data-baseweb="select"] > div {
    background-color: #334155 !important;
    color: #FFFFFF !important;
    border-radius: 999px !important;
    border: 1px solid #64748B !important;
    min-height: 36px !important;
    height: 36px !important;
    font-size: 13px !important;
    padding: 0 8px !important;
}
[data-testid="stBottom"] [data-testid="stSelectbox"] span,
[data-testid="stBottom"] [data-testid="stSelectbox"] div,
[data-testid="stBottom"] [data-testid="stSelectbox"] svg {
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
    fill: #FFFFFF !important;
}
[data-testid="stBottom"] [data-testid="stTextInput"] { width: 100% !important; }
[data-testid="stBottom"] div[data-baseweb="input"],
[data-testid="stBottom"] div[data-baseweb="base-input"] {
    background-color: var(--bottom-input) !important;
    border-radius: 999px !important;
    border: 1px solid var(--bottom-input-border) !important;
    min-height: 38px !important;
    width: 100% !important;
}
[data-testid="stBottom"] input,
[data-testid="stBottom"] input[type="text"] {
    background-color: var(--bottom-input) !important;
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
    caret-color: #FFFFFF !important;
    border-radius: 999px !important;
    border: none !important;
    padding: 6px 12px !important;
    font-size: 15px !important;
    height: 38px !important;
    width: 100% !important;
}
[data-testid="stBottom"] input::placeholder {
    color: #CBD5E1 !important;
    -webkit-text-fill-color: #CBD5E1 !important;
    opacity: 1 !important;
}
[data-testid="stBottom"] [data-testid="InputInstructions"] { display: none !important; }
[data-testid="stBottom"] button {
    border-radius: 50% !important;
    width: 38px !important; height: 38px !important; min-height: 38px !important; min-width: 38px !important;
    padding: 0 !important; border: none !important;
    color: #FFFFFF !important; -webkit-text-fill-color: #FFFFFF !important;
    display: flex !important; align-items: center !important; justify-content: center !important;
    box-shadow: none !important;
}
[data-testid="stBottom"] [data-testid="stPopover"] > button {
    background-color: #334155 !important;
    font-size: 16px !important;
}
[data-testid="stBottom"] [data-testid="stPopover"] > button svg { display: none !important; }
[data-testid="stBottom"] button[kind="secondary"] {
    background-color: #10B981 !important;
    font-size: 16px !important;
}
[data-testid="stBottom"] button[kind="primary"] {
    background-color: #2563EB !important;
    font-size: 15px !important;
}

@media (max-width: 600px) {
    .slim-header { font-size: 0.92rem; padding: 8px 10px; }
    [data-testid="stBottom"] [data-testid="stHorizontalBlock"] {
        grid-template-columns: 34px 102px minmax(0, 1fr) 34px 34px !important;
        gap: 4px !important;
    }
    [data-testid="stBottom"] button {
        width: 34px !important; height: 34px !important; min-height: 34px !important; min-width: 34px !important;
    }
}
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE ---
defaults = {
    "messages": [], "mcq_questions": None, "mcq_user_answers": {}, "mcq_checked": False,
    "draft_text": "", "mic_open": False, "audio_counter": 0, "input_version": 0, "voice_error": "",
    "ui_lang": "ગુજરાતી"
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("### 🎓 સ્માર્ટ AI શિક્ષક")
    raw_keys = (st.secrets.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEYS") or
                st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or "")
    api_keys = [k.strip().strip('"\'') for k in str(raw_keys).split(",") if k.strip()]

    model_choice = st.selectbox("🤖 AI મોડેલ:", ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3.5-flash-lite"])

    st.markdown("### 🛠️ ક્વિક ટૂલ્સ")
    quick_action = None
    c1, c2 = st.columns(2)
    if c1.button("📖 સારાંશ"): quick_action = "summary"
    if c1.button("📝 MCQ ટેસ્ટ"): quick_action = "mcq"
    if c2.button("📝 સ્વાધ્યાય"): quick_action = "exercise"
    if c2.button("💡 ઉદાહરણ"): quick_action = "easy_example"

    st.divider()
    if st.button("🗑️ નવી ચેટ", use_container_width=True):
        st.session_state.update({
            "messages": [], "mcq_questions": None, "mcq_user_answers": {},
            "mcq_checked": False, "draft_text": "", "voice_error": "",
            "input_version": st.session_state.input_version + 1
        })
        st.rerun()

    u1, u2 = st.columns([1, 2])
    dl_fmt = u1.selectbox("ફોર્મેટ", [".pdf", ".txt", ".md"], label_visibility="collapsed")
    if u2.button("📥 નોટ્સ", use_container_width=True) and st.session_state.messages:
        if dl_fmt == ".pdf":
            data, mime = build_pdf_bytes(st.session_state.messages), "application/pdf"
        else:
            data = "\n\n".join(f"{'વિદ્યાર્થી' if m['role']=='user' else 'શિક્ષક'}: {m['content']}" for m in st.session_state.messages)
            mime = "text/plain"
        st.download_button("⬇️ ડાઉનલોડ", data=data, file_name=f"notes{dl_fmt}", mime=mime, use_container_width=True)

# --- HEADER ---
st.markdown('<div class="slim-header">📚 Standard 3 to 8 Smart AI Palaj Teacher</div>', unsafe_allow_html=True)

if quick_action:
    prompts = {
        "summary": "છેલ્લી ચર્ચા મુજબના પાઠનો સરળ ગુજરાતીમાં મુદ્દાસર સારાંશ આપો.",
        "exercise": "છેલ્લી ચર્ચા મુજબના પાઠના સ્વાધ્યાયના પ્રશ્નો અને જવાબો સમજૂતી સાથે આપો.",
        "mcq": "છેલ્લી ચર્ચા મુજબના પાઠ આધારિત ૫ MCQ બનાવો. ફોર્મેટ:\nપ્રશ્ન 1: પ્રશ્ન?\nA. ...\nB. ...\nC. ...\nD. ...\nસાચો જવાબ: B\nસમજૂતી: ...",
        "easy_example": "છેલ્લી ચર્ચા મુજબના વિષયનું વાસ્તવિક જીવનના સરળ ઉદાહરણો દ્વારા સમજાવો."
    }
    if quick_action == "mcq":
        st.session_state.update({"mcq_questions": None, "mcq_user_answers": {}, "mcq_checked": False})
    st.session_state.messages.append({"role": "user", "content": prompts[quick_action]})

# --- CHAT HISTORY ---
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        render_message_with_visuals(m["content"])

# --- INTERACTIVE MCQ ---
if st.session_state.mcq_questions:
    st.divider()
    st.markdown("### 📝 MCQ ટેસ્ટ - ૫ પ્રશ્નો")
    for i, q in enumerate(st.session_state.mcq_questions):
        st.markdown(f"**પ્રશ્ન {i+1}:** {q['question']}")
        keys = list(q["options"].keys())
        labels = [f"{k}. {q['options'][k]}" for k in keys]
        cur = st.session_state.mcq_user_answers.get(i)
        choice = st.radio("વિકલ્પ પસંદ કરો:", labels, index=(keys.index(cur) if cur in keys else None), key=f"mcq_{i}")
        st.session_state.mcq_user_answers[i] = choice[0] if choice else None

    c1, c2 = st.columns(2)
    if c1.button("🏆 સ્કોર તપાસો"):
        st.session_state.mcq_checked = True
    if c2.button("🔄 નવો ટેસ્ટ"):
        st.session_state.update({"mcq_questions": None, "mcq_user_answers": {}, "mcq_checked": False})
        st.rerun()

    if st.session_state.mcq_checked:
        score = sum(1 for i, q in enumerate(st.session_state.mcq_questions) if st.session_state.mcq_user_answers.get(i) == q["answer"])
        st.success(f"🎯 તમારો સ્કોર: **{score} / {len(st.session_state.mcq_questions)}**")
        for i, q in enumerate(st.session_state.mcq_questions):
            ua, ca = st.session_state.mcq_user_answers.get(i), q["answer"]
            correct_opt = q["options"].get(ca, "")
            with st.container(border=True):
                status_text = "✅ સાચો!" if ua == ca else f"❌ ખોટો! સાચો જવાબ: **{ca}. {correct_opt}**"
                st.markdown(f"**પ્રશ્ન {i+1}:** {status_text}")
                if q.get("explanation"):
                    st.caption(f"💡 સમજૂતી: {q['explanation']}")

if st.session_state.voice_error:
    st.error(f"⚠️ {st.session_state.voice_error}")

# --- VOICE INPUT ---
if st.session_state.mic_open:
    with st.container(border=True):
        st.markdown(f"🎙️ **માઈક પર દબાવી {st.session_state.ui_lang} માં બોલો, પૂરું થાય એટલે ⏹ દબાવો:**")
        audio_val = st.audio_input("રેકોર્ડ", key=f"mob_rec_{st.session_state.audio_counter}", label_visibility="collapsed")
        if st.button("❌ બંધ કરો", key="close_rec_btn"):
            st.session_state.mic_open = False
            st.rerun()
        if audio_val is not None:
            with st.spinner("🎧 લખાઈ રહ્યું છે..."):
                spoken, err = transcribe_gujarati(audio_val, api_keys, preferred_model=model_choice, lang_name=st.session_state.ui_lang)
            st.session_state.audio_counter += 1
            st.session_state.mic_open = False
            if spoken:
                st.session_state.voice_error = ""
                existing = st.session_state.draft_text.strip()
                st.session_state.draft_text = f"{existing} {spoken}".strip() if existing else spoken
                st.session_state.input_version += 1
            else:
                st.session_state.voice_error = err or "અવાજ સ્પષ્ટ સંભળાયો નથી, ફરીથી બોલો."
            st.rerun()

# --- ATTACHMENT PREVIEW ---
attached = st.session_state.get("bottom_uploader") or st.session_state.get("bottom_camera")
if attached:
    with st.container(border=True):
        t1, t2, t3 = st.columns([1, 6, 1])
        try:
            t1.image(Image.open(io.BytesIO(attached.getvalue())), width=45)
        except Exception:
            t1.markdown("📎")
        t2.caption(f"📎 જોડાયેલ: {getattr(attached, 'name', 'ફોટો')}")
        if t3.button("❌", key="rm_att"):
            st.session_state.pop("bottom_uploader", None)
            st.session_state.pop("bottom_camera", None)
            st.rerun()

# --- BOTTOM INPUT BAR (WITH FULL "ગુજરાતી" LANGUAGE SELECTOR) ---
with getattr(st, "bottom", st.container()):
    col_plus, col_lang, col_in, col_mic, col_send = st.columns([1, 2.6, 7.2, 1, 1], vertical_alignment="center")
    with col_plus:
        with st.popover("➕"):
            st.file_uploader("📁 ગેલેરી / PDF પસંદ કરો", key="bottom_uploader")
            st.camera_input("📸 કેમેરાથી ફોટો પાડો", key="bottom_camera")
    with col_lang:
        selected_lang = st.selectbox(
            "ભાષા",
            ["ગુજરાતી", "English", "हिन्दी"],
            index=["ગુજરાતી", "English", "हिन्दी"].index(st.session_state.ui_lang),
            key="bottom_lang_select",
            label_visibility="collapsed"
        )
        st.session_state.ui_lang = selected_lang
    with col_in:
        placeholders = {
            "ગુજરાતી": "પ્રશ્ન, આકૃતિ, નકશો, ઉદાહરણ, GK કે Current Affairs પૂછો...",
            "English": "Ask any question, diagram, map, example, GK or Current Affairs...",
            "हिन्दी": "प्रश्न, चित्र, मानचित्र, उदाहरण, GK या Current Affairs पूछें..."
        }
        user_text = st.text_input(
            "પ્રશ્ન...",
            value=st.session_state.draft_text,
            key=f"chat_box_{st.session_state.input_version}",
            placeholder=placeholders.get(selected_lang, placeholders["ગુજરાતી"]),
            label_visibility="collapsed"
        )
        st.session_state.draft_text = user_text
    with col_mic:
        if st.button("🎤", key="real_mic_btn", help="બોલીને લખો"):
            st.session_state.voice_error = ""
            st.session_state.mic_open = not st.session_state.mic_open
            st.rerun()
    with col_send:
        send_clicked = st.button("➤", type="primary", key="real_send_btn", help="મોકલો")

if send_clicked and (user_text.strip() or attached):
    st.session_state.messages.append({"role": "user", "content": user_text.strip() or "[ફાઈલ સંલગ્ન છે]"})
    st.session_state.draft_text = ""
    st.session_state.voice_error = ""
    st.session_state.input_version += 1
    st.session_state.mic_open = False
    st.rerun()

# --- AI RESPONSE ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    clean_q = st.session_state.messages[-1]["content"].strip()
    reply_lang = st.session_state.ui_lang
    with st.chat_message("assistant"):
        if not HAS_GENAI or not api_keys:
            st.error("⚠️ Secrets માં GEMINI_API_KEY દાખલ કરો.")
        else:
            past_user_msgs = [m["content"] for m in st.session_state.messages[:-1] if m["role"] == "user"]
            grade, subject, local_pdf_paths = resolve_grade_subject_and_pdfs(clean_q, past_user_msgs, syllabus_data)

            user_att_parts = []
            att = st.session_state.get("bottom_uploader") or st.session_state.get("bottom_camera")
            if att:
                fb = att.getvalue()
                if getattr(att, "type", "") == "application/pdf":
                    user_att_parts.append(types.Part.from_bytes(data=fb, mime_type="application/pdf"))
                else:
                    user_att_parts.append(Image.open(io.BytesIO(fb)))
            st.session_state.pop("bottom_uploader", None)
            st.session_state.pop("bottom_camera", None)

            sub_label = _SUBJECT_LABELS.get(subject, subject or "")
            if grade and sub_label and local_pdf_paths:
                pdf_names = ", ".join(os.path.basename(p) for p in local_pdf_paths)
                st.markdown(f'<div class="book-badge">📖 ધોરણ {grade} | {sub_label} — {pdf_names}</div>', unsafe_allow_html=True)
            elif is_gk_or_current_affairs(clean_q):
                st.markdown('<div class="book-badge">🌍 સામાન્ય જ્ઞાન (GK) & વર્તમાન પ્રવાહો (Current Affairs)</div>', unsafe_allow_html=True)

            recent_hist = "\n".join(
                f"{'વિદ્યાર્થી' if m['role']=='user' else 'શિક્ષક'}: {m['content']}"
                for m in st.session_state.messages[:-1][-4:]
            )

            book_page_parts = []
            for pdf_path in local_pdf_paths:
                book_page_parts.extend(build_vision_pdf_parts(pdf_path, clean_q, recent_hist))

            visual_instruction = ""
            if wants_map(clean_q):
                visual_instruction = (
                    "\n6. **ભારતનો નકશો (Map JSON Format):** વિદ્યાર્થીએ નકશા પૂર્તિ પૂછી છે! "
                    "તમારા જવાબમાં સૌથી પહેલા નીચે મુજબનો એક ચોક્કસ ```map_json બ્લોક આપો, જેનાથી સ્ક્રીન પર ભારતનો અસલી નકશો, સંજ્ઞાઓ અને સંજ્ઞા સૂચિ (Legend) આપમેળે દોરાઈ જશે:\n"
                    "```map_json\n"
                    "{\n"
                    "  \"title\": \"ભારતનો નકશો - મુખ્ય પાક ઉત્પાદક રાજ્યો\",\n"
                    "  \"items\": [\n"
                    "    {\"label\": \"ઘઉં\", \"symbol\": \"▲\", \"color\": \"#D97706\", \"states\": [\"પંજાબ\", \"ઉત્તર પ્રદેશ\"]},\n"
                    "    {\"label\": \"ડાંગર\", \"symbol\": \"●\", \"color\": \"#16A34A\", \"states\": [\"પશ્ચિમ બંગાળ\", \"પંજાબ\"]}\n"
                    "  ]\n"
                    "}\n"
                    "```\n"
                    "   - દરેક આઇટમ માટે અલગ સંજ્ઞા (`▲`, `●`, `■`, `★`, `◆`, `✚`) અને અલગ ઘાટો રંગ (`#D97706`, `#16A34A`, `#2563EB`, `#DC2626`, `#7C3AED`, `#0D9488`) વાપરો.\n"
                    "   - `states` માં ભારતના સાચા રાજ્યોના નામ ગુજરાતીમાં લખો (જેમ કે: પંજાબ, ઉત્તર પ્રદેશ, પશ્ચિમ બંગાળ, રાજસ્થાન, ગુજરાત, મહારાષ્ટ્ર, મધ્ય પ્રદેશ, બિહાર, ઓડિશા, કર્ણાટક, તમિલનાડુ, આંધ્ર પ્રદેશ, તેલંગાણા, કેરળ, આસામ, ઝારખંડ, છત્તીસગઢ, હરિયાણા).\n"
                    "   - `map_json` બ્લોકની નીચે દરેક પાક અને તેના ઉત્પાદક રાજ્યોની મુદ્દાસર સમજૂતી આપો."
                )
            elif wants_diagram(clean_q):
                visual_instruction = (
                    "\n6. **નામનિર્દેશવાળી આકૃતિ (SVG Diagram):** વિદ્યાર્થીએ આકૃતિ દોરવાનું કહ્યું છે! "
                    "તમારા જવાબમાં એકદમ સ્પષ્ટ, રંગીન અને સ્વચ્છ **inline `<svg width=\"420\" height=\"320\" viewBox=\"0 0 420 320\" xmlns=\"[http://www.w3.org/2000/svg](http://www.w3.org/2000/svg)\">...</svg>`** કોડ મૂકો.\n"
                    "   - SVG ની અંદર સફેદ બેકગ્રાઉન્ડ (`<rect width=\"420\" height=\"320\" fill=\"#FFFFFF\"/>`) રાખો.\n"
                    "   - આકૃતિના દરેક ભાગને રંગીન આકારોથી દોરો, તીર/રેખા (`<line>`) વડે જમણી કે ડાબી બાજુ સ્પષ્ટ નામનિર્દેશન (`<text font-size=\"13\" font-weight=\"bold\" fill=\"#0F172A\">...</text>`) લખો.\n"
                    "   - આકૃતિની નીચે દરેક ભાગની મુદ્દાસર સમજૂતી આપો."
                )

            book_context_instruction = (
                f"સંદર્ભ પાઠ્યપુસ્તક: GCERT ધોરણ {grade} - {sub_label} (ગુજરાતી માધ્યમ). "
                "જો પ્રશ્ન પાઠ્યપુસ્તકના પાઠ કે અનુક્રમણિકાનો હોય, તો સંલગ્ન પાનાઓની ઈમેજ પરથી ૧૦૦% શુદ્ધ જોડણીમાં જવાબ આપો. "
                "જો વિદ્યાર્થીએ કોઈ બીજા વિષય કે સામાન્ય જ્ઞાનનો પ્રશ્ન પૂછ્યો હોય, તો પણ કોઈ ઠપકો આપ્યા વગર સીધો અને સચોટ જવાબ આપો."
                if local_pdf_paths else
                "વિદ્યાર્થીએ ધોરણ 3 થી 8 અભ્યાસક્રમ, General Knowledge (સામાન્ય જ્ઞાન), અથવા Current Affairs (વર્તમાન પ્રવાહો) નો પ્રશ્ન પૂછ્યો છે. ત્વરિત અને સચોટ જવાબ આપો."
            )

            sys_prompt = (
                "તમે ધોરણ 3 થી 8 ના વિદ્યાર્થીઓ માટેના અત્યંત પ્રેમાળ, ઉત્સાહી અને નિષ્ણાત AI શિક્ષક છો.\n"
                "મહત્વના નિયમો (કડકાઈથી પાલન કરો):\n"
                f"1. **જવાબની ભાષા:** વિદ્યાર્થીએ પસંદ કરેલી ભાષા **{reply_lang}** છે — આખો જવાબ, આકૃતિ અને નકશાના નામનિર્દેશન **{reply_lang}** ભાષામાં જ આપો (જ્યાં સુધી પ્રશ્નમાં અન્ય ભાષા ન માંગી હોય).\n"
                "2. **ઉષ્માભર્યો આવકાર:** દરેક જવાબની શરૂઆત ટૂંકા, પ્રેમાળ આવકારથી કરો (દા.ત., 'નમસ્તે વિદ્યાર્થી મિત્ર! 🙏' અથવા 'ખૂબ સરસ પ્રશ્ન છે! 🌟').\n"
                "3. **ક્યારેય વિષય બાબતે ઠપકો ન આપો:** ક્યારેય એવું ન લખો કે 'તમે આ વિષયનો જ પ્રશ્ન પૂછો' — વિદ્યાર્થી જે ધોરણ, જે વિષય, General Knowledge કે Current Affairs પૂછે તેનો તરત જ સીધો જવાબ આપો.\n"
                "4. **વિદ્યાર્થીની માંગ મુજબ શૈલી:** ટૂંકમાં માંગે તો ટૂંકમાં, વિગતવાર માંગે તો મુદ્દાસર વિગતથી, અને ઉદાહરણ માંગે તો સરળ ઉદાહરણો સાથે જવાબ આપો.\n"
                "5. **શુદ્ધ જોડણી:** ૧૦૦% શુદ્ધ લિપિ વાપરો અને ગણિત/વિજ્ઞાનના સૂત્રો $...$ માં લખો."
                f"{visual_instruction}\n\n"
                f"{book_context_instruction}"
            )
            prompt_text = f"{sys_prompt}\n\n{recent_hist}\nવિદ્યાર્થીનો પ્રશ્ન: {clean_q}"

            models = [model_choice] + [m for m in ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3.5-flash-lite"] if m != model_choice]
            placeholder = st.empty()
            placeholder.markdown("⚡ *તમારા પ્રશ્નનો જવાબ તૈયાર થઈ રહ્યો છે...*")
            answer_text, success, last_err = "", False, None

            for key in api_keys:
                client = genai.Client(api_key=key)
                contents = []
                contents.extend(book_page_parts)
                contents.extend(user_att_parts)
                contents.append(prompt_text)

                for mod in models:
                    try:
                        temp = ""
                        for chunk in client.models.generate_content_stream(model=mod, contents=contents):
                            if chunk.text:
                                temp += chunk.text
                                if "<svg" not in temp.lower() and "```map_json" not in temp:
                                    placeholder.markdown(temp + "▌")
                                else:
                                    placeholder.markdown("🗺️ *નકશો / આકૃતિ તૈયાર થઈ રહી છે...* ▌")
                        if temp.strip():
                            placeholder.empty()
                            render_message_with_visuals(temp)
                            answer_text, success = temp, True
                            break
                    except Exception as e:
                        last_err = e
                        if any(x in str(e) for x in ("429", "RESOURCE_EXHAUSTED")):
                            break
                if success:
                    break

            if success:
                st.session_state.messages.append({"role": "assistant", "content": answer_text})
                if quick_action == "mcq" and st.session_state.mcq_questions is None:
                    if parsed := parse_mcq(answer_text):
                        st.session_state.mcq_questions = parsed
                    st.rerun()
            else:
                placeholder.empty()
                err_msg = f"❌ જવાબ મેળવી શકાયો નથી. ({last_err})"
                st.error(err_msg)
                st.session_state.messages.append({"role": "assistant", "content": err_msg})