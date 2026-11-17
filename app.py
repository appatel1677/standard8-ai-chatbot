import streamlit as st
import json
import os
import io
import re
from PIL import Image
from fpdf import FPDF

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False


def parse_mcq(text):
    """Parse AI-generated MCQ text into a list of question dicts."""
    questions = []
    parts = re.split(r'\n?પ્રશ્ન\s*\d+\s*[:.]', text)
    for part in parts[1:]:
        lines = [l.strip() for l in part.strip().splitlines() if l.strip()]
        if not lines:
            continue
        q_text = lines[0]
        options = {}
        answer = None
        explanation = ""
        for l in lines[1:]:
            m = re.match(r'([ABCD])[\).]\s*(.*)', l)
            if m:
                options[m.group(1)] = m.group(2)
            elif re.search(r'સાચો જવાબ|જવાબ|Answer', l):
                ma = re.search(r'([ABCD])', l)
                if ma:
                    answer = ma.group(1)
            elif re.search(r'સમજૂતી|Explanation', l):
                explanation = re.sub(r'^(સમજૂતી|Explanation)[:.]?\s*', '', l)
        if q_text and options and answer:
            questions.append({
                "question": q_text,
                "options": options,
                "answer": answer,
                "explanation": explanation
            })
    return questions


# ---------------------------------------------------------------------------
# PDF font loader (Gujarati / Devanagari support via fpdf2 + uharfbuzz)
# ---------------------------------------------------------------------------
@st.cache_resource
def get_pdf_font_path():
    """Return a TTF path supporting Gujarati & Devanagari, downloading if needed."""
    candidates = [
        "C:/Windows/Fonts/Nirmala.ttf",
        "C:/Windows/Fonts/Shruti.ttf",
        "C:/Windows/Fonts/NotoSansGujarati-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path

    font_path = os.path.join(os.getcwd(), "NotoSansGujarati-Regular.ttf")
    if not os.path.exists(font_path):
        try:
            import urllib.request
            url = ("https://github.com/google/fonts/raw/main/ofl/notosansgujarati/"
                   "NotoSansGujarati%5Bwdth%2Cwght%5D.ttf")
            urllib.request.urlretrieve(url, font_path)
        except Exception:
            pass
    if os.path.exists(font_path):
        return font_path
    return None


def build_pdf_bytes(messages, subject_name, chapter_name):
    """Build a printable PDF (bytes) of the chat notes with Gujarati-friendly font."""
    font_path = get_pdf_font_path()
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_text_shaping(True)

    if font_path:
        pdf.add_font("Gujarati", "", font_path)
        pdf.add_font("Gujarati", "B", font_path)
        base_font = "Gujarati"
    else:
        base_font = "helvetica"

    def footer():
        pdf.set_y(-12)
        pdf.set_font(base_font, "", 8)
        pdf.set_text_color(120, 120, 120)
        pdf.cell(0, 6, f"Page {pdf.page_no()}", align="C")

    pdf.add_page()
    pdf.set_font(base_font, "B", 16)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 10, "ધોરણ 3 થી 8 - સ્માર્ટ AI સ્ટડી નોટ્સ", ln=True, align="C")
    pdf.set_font(base_font, "", 11)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 7, f"વિષય: {subject_name or 'સામાન્ય'}", ln=True, align="C")
    pdf.cell(0, 7, f"પ્રકરણ: {chapter_name or 'કોઈપણ'}", ln=True, align="C")
    pdf.ln(4)

    for msg in messages:
        role = "વિદ્યાર્થી" if msg["role"] == "user" else "શિક્ષક"
        pdf.set_font(base_font, "B", 11)
        if msg["role"] == "user":
            pdf.set_text_color(30, 58, 138)
        else:
            pdf.set_text_color(16, 118, 44)
        pdf.cell(0, 7, role + ":", ln=True)
        pdf.set_font(base_font, "", 10)
        pdf.set_text_color(0, 0, 0)
        pdf.multi_cell(0, 6, msg["content"])
        pdf.ln(2)

    pdf_bytes = bytes(pdf.output(dest="S"))
    return pdf_bytes


st.set_page_config(
    page_title="ધોરણ 3 થી 8 ગુજરાતી માધ્યમ - સ્માર્ટ AI શિક્ષક",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="auto"
)


def load_syllabus():
    syllabus_path = "diksha_syllabus.json"
    if os.path.exists(syllabus_path):
        with open(syllabus_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


syllabus_data = load_syllabus()

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Gujarati:wght@400;500;600;700&display=swap');

html, body, p, h1, h2, h3, h4, h5, h6, input, textarea, button,
.stMarkdown, .stTextInput input, .stSelectbox, .stButton button,
.stChatMessage, .stCaption, .stRadio label, .stDownloadButton button,
.stAlert, .stInfo, .stSuccess, .stError, .stWarning {
    font-family: 'Noto Sans Gujarati', 'Noto Sans', 'Arial Unicode MS', sans-serif !important;
}

[data-testid="stIconMaterial"], .material-symbols-rounded, span[translate="no"],
[data-testid="stMaterialIcon"] {
    font-family: 'Material Symbols Rounded' !important;
}

.app-banner {
    background: linear-gradient(135deg, #1E3A8A, #3B82F6);
    color: #ffffff;
    padding: 1.5rem 1rem;
    border-radius: 16px;
    margin: 0.5rem 0 1.25rem 0;
    box-shadow: 0 8px 24px rgba(30, 58, 138, 0.25);
}
.app-banner h1 {
    margin: 0 0 0.25rem 0;
    font-size: 1.75rem;
    font-weight: 700;
    letter-spacing: 0.2px;
    font-family: 'Noto Sans Gujarati', 'Noto Sans', sans-serif !important;
}
.app-banner p {
    margin: 0;
    font-size: 1rem;
    opacity: 0.95;
    font-family: 'Noto Sans Gujarati', 'Noto Sans', sans-serif !important;
}

.subject-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    background: linear-gradient(135deg, #F59E0B, #D97706);
    color: #fff;
    padding: 0.5rem 1rem;
    border-radius: 999px;
    font-size: 0.95rem;
    font-weight: 600;
    margin-bottom: 1rem;
    box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3);
    font-family: 'Noto Sans Gujarati', 'Noto Sans', sans-serif !important;
}
.subject-pill .label { font-weight: 500; opacity: 0.9; }

.stChatMessage {
    border-radius: 16px !important;
    padding: 0.85rem 1rem !important;
    margin: 0.6rem 0 !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important;
}
.stChatMessage [data-testid="stChatMessageContent"] {
    border-radius: 16px !important;
}
.stChatMessage[data-testid="stChatMessage"][data-message-role="user"] {
    background: #EFF6FF !important;
    border-left: 4px solid #3B82F6 !important;
    margin-left: 2rem !important;
}
.stChatMessage[data-testid="stChatMessage"][data-message-role="assistant"] {
    background: #F0FDF4 !important;
    border-left: 4px solid #10B981 !important;
    margin-right: 2rem !important;
}

.mjx-chtml, .mjx-math, .MathJax {
    font-family: 'Noto Sans Gujarati', 'Noto Sans', sans-serif !important;
}

[data-testid="stBottom"] {
    background-color: #ffffff !important;
    border-top: 1px solid #e2e8f0 !important;
    padding: 0.75rem 1rem !important;
    box-shadow: 0 -4px 6px -1px rgba(0, 0, 0, 0.05) !important;
    z-index: 99999 !important;
}
[data-testid="stBottom"] [data-testid="stPopover"] > button {
    border-radius: 50% !important;
    width: 42px !important;
    height: 42px !important;
    padding: 0 !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-shadow: 0 2px 4px rgba(0,0,0,0.05) !important;
    background-color: #ffffff !important;
    border: 1px solid #cbd5e1 !important;
}

@media (max-width: 768px) {
    .block-container {
        padding-top: 0.5rem !important;
        padding-left: 0.5rem !important;
        padding-right: 0.5rem !important;
        max-width: 100% !important;
    }
    .app-banner {
        padding: 0.9rem 0.75rem;
        margin-bottom: 0.5rem;
        border-radius: 12px;
    }
    .app-banner h1 { font-size: 1.25rem; }
    .app-banner p { font-size: 0.85rem; }
    .subject-pill { font-size: 0.8rem; padding: 0.4rem 0.75rem; }
    .stChatMessage {
        margin: 0.3rem 0 !important;
        padding: 0.6rem 0.8rem !important;
        border-radius: 12px !important;
    }
    .stChatMessage[data-testid="stChatMessage"][data-message-role="user"] {
        margin-left: 0.5rem !important;
    }
    .stChatMessage[data-testid="stChatMessage"][data-message-role="assistant"] {
        margin-right: 0.5rem !important;
    }
    [data-testid="stBottom"] {
        padding: 0.5rem 0.5rem !important;
    }
    [data-testid="stSidebar"] {
        width: 0 !important;
    }
    .stChatMessage .stMarkdown {
        font-size: 0.95rem !important;
        line-height: 1.6 !important;
    }
}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.image("https://img.icons8.com/color/96/school.png", width=70)
    st.markdown("### 🎓 સ્માર્ટ AI શિક્ષક")
    st.markdown("ગુજરાત રાજ્ય શાળા પાઠ્યપુસ્તક મંડળ (GCERT) અને **DIKSHA** આધારિત ધોરણ 3 થી 8.")
    st.divider()

    def _clean_keys(raw):
        if not raw:
            return []
        cleaned = []
        for k in str(raw).split(","):
            k = k.strip().strip('"').strip("'").strip()
            if k:
                cleaned.append(k)
        return cleaned

    api_keys_raw = st.secrets.get("GEMINI_API_KEYS", "") if hasattr(st, "secrets") else ""
    if not api_keys_raw:
        api_keys_raw = os.environ.get("GEMINI_API_KEYS", "")
    api_keys = _clean_keys(api_keys_raw)
    if not api_keys:
        single_raw = st.secrets.get("GEMINI_API_KEY", "") if hasattr(st, "secrets") else ""
        if not single_raw:
            single_raw = os.environ.get("GEMINI_API_KEY", "")
        api_keys = _clean_keys(single_raw)

    st.divider()
    model_choice = st.selectbox(
        "🤖 AI મોડેલ પસંદ કરો:",
        ["gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"],
        index=0,
        key="model_choice_select"
    )

    st.divider()

    # Grade selection
    grade_choice = st.selectbox(
        "🎓 ધોરણ પસંદ કરો:",
        ["ધોરણ 3", "ધોરણ 4", "ધોરણ 5", "ધોરણ 6", "ધોરણ 7", "ધોરણ 8"],
        index=5,
        key="grade_select"
    )
    grade_num = int(grade_choice.split()[-1])

    st.divider()

    # Load syllabus based on grade
    grade_data = syllabus_data.get(grade_choice, {})
    active_syllabus = grade_data.get("subjects", {}) if isinstance(grade_data, dict) else {}

    if active_syllabus:
        subject_names = list(active_syllabus.keys())
        selected_subject_name = st.selectbox(
            "📖 વિષય પસંદ કરો:",
            subject_names,
            key=f"subject_select_{grade_num}"
        )
        subject_info = active_syllabus[selected_subject_name]
        chapters = subject_info.get("chapters", [])
        chapter_names = [ch["name"] for ch in chapters]

        # Clean format: "પ્રકરણ X: <Chapter Name>"
        chapter_display = []
        for idx, ch in enumerate(chapters, 1):
            name = ch.get("name", "").strip()
            clean_title = re.sub(r'^(?:પ્રકરણ\s*\d+\s*[:\-\.]\s*|\d+[\.\)]\s*)', '', name).strip()
            if clean_title:
                chapter_display.append(f"પ્રકરણ {idx}: {clean_title}")
            else:
                chapter_display.append(f"પ્રકરણ {idx}")

        options_list = ["બધા પ્રકરણો / સામાન્ય પ્રશ્ન"] + chapter_display
        selected_chapter_idx = st.selectbox(
            "📑 પ્રકરણ પસંદ કરો:",
            range(len(options_list)),
            format_func=lambda i: options_list[i],
            index=0,
            key=f"chapter_select_{grade_num}_{selected_subject_name}"
        )

        if selected_chapter_idx == 0:
            selected_chapter_name = "બધા પ્રકરણો / સામાન્ય પ્રશ્ન"
            selected_chapter_obj = None
        else:
            selected_chapter_name = chapter_names[selected_chapter_idx - 1]
            selected_chapter_obj = chapters[selected_chapter_idx - 1]
    else:
        selected_subject_name = None
        selected_chapter_obj = None
        st.warning("⚠️ સિલેબસ મળી નથી. કૃપા કરીને પહેલા build_syllabus.py રન કરો.")

    st.divider()
    st.markdown("### 🛠️ ક્વિક સ્ટડી ટૂલ્સ")
    quick_action = None
    col_q1, col_q2 = st.columns(2)
    with col_q1:
        if st.button("📖 સારાંશ"):
            quick_action = "summary"
        if st.button("📝 MCQ ટેસ્ટ"):
            quick_action = "mcq"
    with col_q2:
        if st.button("📝 સ્વાધ્યાય"):
            quick_action = "exercise"
        if st.button("💡 સરળ ઉદાહરણ"):
            quick_action = "easy_example"

    st.divider()
    st.markdown("### 🔧 યુટિલિટી")
    if st.button("🗑️ નવી ચેટ", use_container_width=True):
        st.session_state.messages = []
        st.session_state.pop("mcq_questions", None)
        st.session_state.pop("mcq_user_answers", None)
        st.session_state.pop("mcq_checked", None)
        st.rerun()

    col_u1, col_u2 = st.columns([1, 2])
    with col_u1:
        dl_format = st.selectbox(
            "ફોર્મેટ",
            [".pdf", ".txt", ".md"],
            index=0,
            key="dl_format",
            label_visibility="collapsed"
        )
    with col_u2:
        dl_clicked = st.button("📥 નોટ્સ ડાઉનલોડ કરો", use_container_width=True)

    notes_text = ""
    if st.session_state.get("messages"):
        lines = [
            "# ધોરણ 3 થી 8 ગુજરાતી માધ્યમ - નોટ્સ",
            f"વિષય: {selected_subject_name or 'સામાન્ય'}",
            f"પ્રકરણ: {selected_chapter_obj['name'] if selected_chapter_obj else 'કોઈપણ'}",
            "",
            "## ચેટ ઇતિહાસ / નોટ્સ",
            ""
        ]
        for msg in st.session_state.messages:
            role = "વિદ્યાર્થી" if msg["role"] == "user" else "શિક્ષક"
            lines.append(f"### {role}")
            lines.append(msg["content"])
            lines.append("")
        notes_text = "\n".join(lines)

    if notes_text and dl_clicked:
        if dl_format == ".pdf":
            chapter_name = selected_chapter_obj['name'] if selected_chapter_obj else 'કોઈપણ'
            pdf_bytes = build_pdf_bytes(
                st.session_state.messages,
                selected_subject_name or 'સામાન્ય',
                chapter_name
            )
            st.download_button(
                "📥 નોટ્સ ડાઉનલોડ કરો",
                data=pdf_bytes,
                file_name=f"notes_{(selected_subject_name or 'general').replace(' ', '_')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        else:
            st.download_button(
                "📥 નોટ્સ ડાઉનલોડ કરો",
                data=notes_text,
                file_name=f"notes_{(selected_subject_name or 'general').replace(' ', '_')}{dl_format}",
                mime="text/markdown" if dl_format == ".md" else "text/plain",
                use_container_width=True
            )

st.markdown('''
<div class="app-banner">
    <h1>📚 ધોરણ 3 થી 8 સ્માર્ટ AI શિક્ષક</h1>
    <p>તમારા બધા જ વિષયોના પ્રશ્નો, સ્વાધ્યાય ઉકેલ, અને માર્ગદર્શન માટેનો ડિજિટલ સાથી.</p>
</div>
''', unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []

if "mcq_questions" not in st.session_state:
    st.session_state.mcq_questions = None
if "mcq_user_answers" not in st.session_state:
    st.session_state.mcq_user_answers = {}
if "mcq_checked" not in st.session_state:
    st.session_state.mcq_checked = False

if selected_subject_name:
    ch_text = selected_chapter_obj['name'] if selected_chapter_obj else 'કોઈપણ'
    st.markdown(f'''
    <div class="subject-pill">
        <span class="label">🎓 {grade_choice} | 📌 {selected_subject_name}</span>
        <span>|</span>
        <span>{ch_text}</span>
    </div>
    ''', unsafe_allow_html=True)

client = None
if HAS_GENAI and api_keys:
    try:
        client = genai.Client(api_key=api_keys[0])
    except Exception as e:
        st.error(f"❌ Gemini Client Error: {e}")

chapter_label = selected_chapter_obj['name'] if selected_chapter_obj else 'આખા અભ્યાસક્રમ'

if quick_action and selected_subject_name:
    prompt_map = {
        "summary": f"{grade_choice} ના વિષય '{selected_subject_name}' ના પ્રકરણ '{chapter_label}' નો સરસ અને સરળ ગુજરાતીમાં મુદ્દાસર સારાંશ આપો.",
        "exercise": f"{grade_choice} ના વિષય '{selected_subject_name}' ના પ્રકરણ '{chapter_label}' ના સ્વાધ્યાયના પ્રશ્નો અને તેના સાચા જવાબો સમજૂતી સાથે આપો.",
        "mcq": f"{grade_choice} ના વિષય '{selected_subject_name}' ના પ્રકરણ '{chapter_label}' આધારિત ગુજરાતીમાં ૫ MCQ (બહુવિકલ્પી) પ્રશ્નો બનાવો. દરેક પ્રશ્નમાં ૪ વિકલ્પો (A, B, C, D) હોય. નીચેના ફોર્મેટમાં જ લખો:\n\nપ્રશ્ન 1: પ્રશ્ન લખો?\nA. વિકલ્પ 1\nB. વિકલ્પ 2\nC. વિકલ્પ 3\nD. વિકલ્પ 4\nસાચો જવાબ: B\nસમજૂતી: સરળ સમજૂતી.\n\nઆ પ્રકારે તમામ ૫ પ્રશ્નો લખો.",
        "easy_example": f"{grade_choice} ના વિષય '{selected_subject_name}' ના પ્રકરણ '{chapter_label}' નું સરળ ભાષામાં વાસ્તવિક જીવનના ઉદાહરણો દ્વારા સમજૂતી આપો જેથી {grade_choice} નું વિદ્યાર્થી સરળતાથી સમજી શકે. ગુજરાતીમાં લખો. ગણિત અથવા વિજ્ઞાન હોય તો સૂત્રો $...$ (LaTeX) નો ઉપયોગ કરો.",
        "imp": f"{grade_choice} ના વિષય '{selected_subject_name}' ના પ્રકરણ '{chapter_label}' માંથી વાર્ષિક પરીક્ષા માટે અતિ મહત્વના (IMP) પ્રશ્નો અને ઉત્તરો જણાવો.",
        "formulas": f"{grade_choice} ના વિષય '{selected_subject_name}' ના પ્રકરણ '{chapter_label}' ના તમામ મહત્વના સૂત્રો, નિયમો અથવા વ્યાકરણના મુદ્દાઓની યાદી બનાવીને સમજાવો.",
        "nmms": f"{grade_choice} ના વિષય '{selected_subject_name}' માટે NMMS સ્કોલરશીપ પરીક્ષામાં પૂછાઈ શકે તેવા મહત્વના પ્રશ્નો અને શોર્ટકટ ટ્રીક્સ ગુજરાતીમાં સમજાવો."
    }
    action_prompt = prompt_map.get(quick_action, "")
    if action_prompt:
        if quick_action == "mcq":
            st.session_state.mcq_questions = None
            st.session_state.mcq_user_answers = {}
            st.session_state.mcq_checked = False
        st.session_state.messages.append({"role": "user", "content": action_prompt})

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if st.session_state.get("mcq_questions"):
    st.divider()
    st.markdown("### 📝 MCQ ટેસ્ટ - ૫ પ્રશ્નો")
    for i, q in enumerate(st.session_state.mcq_questions):
        st.markdown(f"**પ્રશ્ન {i+1}:** {q['question']}")
        option_keys = list(q["options"].keys())
        option_labels = [f"{k}. {q['options'][k]}" for k in option_keys]
        current = st.session_state.mcq_user_answers.get(i)
        idx = option_keys.index(current) if current in option_keys else None
        choice = st.radio("સાચો વિકલ્પ પસંદ કરો:", option_labels, index=idx, key=f"mcq_radio_{i}")
        st.session_state.mcq_user_answers[i] = choice[0] if choice else None

    col_c1, col_c2 = st.columns(2)
    with col_c1:
        if st.button("🏆 સ્કોર તપાસો", key="check_mcq_btn"):
            st.session_state.mcq_checked = True
    with col_c2:
        if st.button("🔄 નવો ટેસ્ટ", key="new_mcq_btn"):
            st.session_state.mcq_questions = None
            st.session_state.mcq_user_answers = {}
            st.session_state.mcq_checked = False
            st.rerun()

    if st.session_state.mcq_checked:
        score = sum(
            1 for i, q in enumerate(st.session_state.mcq_questions)
            if st.session_state.mcq_user_answers.get(i) == q["answer"]
        )
        st.success(f"🎯 તમારો સ્કોર: **{score} / {len(st.session_state.mcq_questions)}**")
        for i, q in enumerate(st.session_state.mcq_questions):
            user_ans = st.session_state.mcq_user_answers.get(i)
            correct = q["answer"]
            with st.container(border=True):
                st.markdown(f"**પ્રશ્ન {i+1}:** {q['question']}")
                if user_ans == correct:
                    st.markdown(f"✅ તમારો જવાબ ({user_ans}) સાચો છે!")
                else:
                    st.markdown(f"❌ તમારો જવાબ ({user_ans or 'પસંદ કર્યું નથી'}) ખોટો છે. સાચો જવાબ: **{correct}. {q['options'].get(correct, '')}**")
                if q.get("explanation"):
                    st.markdown(f"💡 સમજૂતી: {q['explanation']}")

attached_file = st.session_state.get("bottom_uploader") or st.session_state.get("bottom_camera")

if attached_file:
    with st.container(border=True):
        col_thumb, col_info, col_clear = st.columns([1, 6, 1])
        with col_thumb:
            try:
                fb = attached_file.getvalue() if hasattr(attached_file, "getvalue") else attached_file.read()
                if hasattr(attached_file, "seek"):
                    attached_file.seek(0)
                st.image(Image.open(io.BytesIO(fb)), width=50)
            except Exception:
                st.markdown("📎")
        with col_info:
            file_name = getattr(attached_file, "name", "કેમેરા ફોટો")
            st.caption(f"📎 ફાઈલ જોડાયેલ છે: {file_name}")
        with col_clear:
            if st.button("❌ હટાવો", key="clear_attachment_btn"):
                st.session_state.pop("bottom_uploader", None)
                st.session_state.pop("bottom_camera", None)
                st.rerun()

if "input_counter" not in st.session_state:
    st.session_state.input_counter = 0

bottom_container = getattr(st, "bottom", st.container())
with bottom_container:
    col_mic, col_plus, col_input, col_send = st.columns([1, 1, 10, 1.5], vertical_alignment="center")
    with col_mic:
        mic_html = '''
        <button id="micBtn" onclick="startMic()" style="border-radius:50%;width:42px;height:42px;border:1px solid #cbd5e1;background:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:18px;box-shadow:0 2px 4px rgba(0,0,0,0.05);">🎤</button>
        <script>
        function startMic() {
            if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
                alert('બ્રાઉઝર વૉઇસ ઇનપુટ સપોર્ટ કરતું નથી');
                return;
            }
            const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
            const recognition = new SpeechRecognition();
            recognition.lang = 'gu-IN';
            recognition.interimResults = false;
            recognition.maxAlternatives = 1;
            recognition.onresult = function(event) {
                const transcript = event.results[0][0].transcript;
                const inputs = document.querySelectorAll('input[type="text"]');
                if (inputs.length > 0) {
                    inputs[inputs.length-1].value = transcript;
                    inputs[inputs.length-1].dispatchEvent(new Event('input', { bubbles: true }));
                }
            };
            recognition.onerror = function(event) { console.log('Speech error:', event.error); };
            recognition.start();
            document.getElementById('micBtn').style.background = '#FEE2E2';
            recognition.onend = function() { document.getElementById('micBtn').style.background = '#fff'; };
        }
        </script>
        '''
        st.components.v1.html(mic_html, height=60)
    with col_plus:
        with st.popover("➕"):
            st.file_uploader("📁 ગેલેરી / PDF / ફાઈલ પસંદ કરો", type=None, key="bottom_uploader")
            st.camera_input("📸 કેમેરાથી ફોટો પાડો", key="bottom_camera")
    with col_input:
        user_text = st.text_input(
            "પ્રશ્ન...",
            placeholder="અહીં તમારો પ્રશ્ન પૂછો (દા.ત., 'પ્રકરણ ૧ નો સ્વાધ્યાય સમજાવો')...",
            label_visibility="collapsed",
            key=f"chat_text_input_{st.session_state.input_counter}"
        )
    with col_send:
        send_clicked = st.button("➤", use_container_width=True, type="primary", key=f"send_btn_{st.session_state.input_counter}")

if send_clicked and (user_text.strip() or attached_file):
    prompt_text = user_text.strip() if user_text.strip() else ("[ફાઈલ સંલગ્ન છે]" if attached_file else "")
    st.session_state.messages.append({"role": "user", "content": prompt_text})
    st.session_state.input_counter += 1
    st.rerun()

if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    last_user_msg = st.session_state.messages[-1]["content"]
    with st.chat_message("assistant"):
        with st.spinner("🤖 AI શિક્ષક જવાબ તૈયાર કરી રહ્યા છે..."):
            if not client:
                st.error("⚠️ કૃપા કરીને સાઈડબારમાં તમારી Gemini API Key દાખલ કરો!")
            else:
                try:
                    system_instruction = f"""
તમે ગુજરાત રાજ્ય શાળા પાઠ્યપુસ્તક મંડળ (GCERT) અભ્યાસક્રમ આધારિત {grade_choice} (ગુજરાતી માધ્યમ) ના નિષ્ણાત અને મૈત્રીપૂર્ણ AI શિક્ષક છો.
વિદ્યાર્થીઓને હંમેશા સરળ, સ્પષ્ટ અને સચોટ ગુજરાતી ભાષામાં સ્ટેપ-બાય-સ્ટેપ સમજૂતી આપો.
વર્તમાન પસંદ કરેલ ધોરણ: {grade_choice}
વર્તમાન પસંદ કરેલ વિષય: {selected_subject_name if selected_subject_name else 'સામાન્ય'}
પ્રકરણ: {selected_chapter_obj['name'] if selected_chapter_obj else 'કોઈપણ'}
MCQ જવાબ પાદતરમાં હોય તો 'સાચો જવાબ: X' ફોર્મેટ અને સમજૂતી આપો. ગણિત/વિજ્ઞાનના સૂત્રો $...$ (LaTeX) નો ઉપયોગ કરો.
"""
                    contents = []
                    current_attachment = st.session_state.get("bottom_uploader") or st.session_state.get("bottom_camera")
                    if current_attachment is not None:
                        try:
                            file_bytes = current_attachment.getvalue() if hasattr(current_attachment, "getvalue") else current_attachment.read()
                            if hasattr(current_attachment, "seek"):
                                current_attachment.seek(0)

                            ftype = getattr(current_attachment, "type", "")
                            if ftype and ftype.startswith("image/"):
                                contents.append(Image.open(io.BytesIO(file_bytes)))
                            elif ftype == "application/pdf":
                                contents.append(
                                    types.Part.from_bytes(
                                        data=file_bytes,
                                        mime_type="application/pdf"
                                    )
                                )
                            else:
                                try:
                                    contents.append(Image.open(io.BytesIO(file_bytes)))
                                except Exception:
                                    contents.append("[અપલોડ કરેલી ફાઈલ સંલગ્ન છે]")
                        except Exception as file_err:
                            contents.append(f"[ફાઈલ જોડવામાં ભૂલ: {file_err}]")

                    st.session_state.pop("bottom_uploader", None)
                    st.session_state.pop("bottom_camera", None)

                    history_text = ""
                    for msg in st.session_state.messages[:-1]:
                        history_text += f"{'વિદ્યાર્થી' if msg['role'] == 'user' else 'શિક્ષક'}: {msg['content']}\n"

                    full_prompt = f"{system_instruction}\n\nઇતિહાસ:\n{history_text}\nપ્રશ્ન: {last_user_msg}"
                    contents.append(full_prompt)

                    all_models = ["gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash"]
                    available_models = [model_choice] + [m for m in all_models if m != model_choice]

                    answer_text = ""
                    success = False
                    last_error = None
                    placeholder = st.empty()

                    for cur_key in api_keys:
                        key_client = genai.Client(api_key=cur_key)
                        for cur_model in available_models:
                            try:
                                stream_obj = key_client.models.generate_content_stream(
                                    model=cur_model,
                                    contents=contents
                                )
                                temp_text = ""
                                for chunk in stream_obj:
                                    if chunk.text:
                                        temp_text += chunk.text
                                        placeholder.markdown(temp_text + "▌")
                                placeholder.markdown(temp_text)
                                answer_text = temp_text
                                success = True
                                break
                            except Exception as err:
                                last_error = err
                                err_str = str(err)
                                placeholder.empty()
                                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                                    break
                                elif "503" in err_str or "UNAVAILABLE" in err_str or "500" in err_str or "404" in err_str:
                                    continue
                                else:
                                    raise err
                        if success:
                            break

                    if not success:
                        err_msg = f"❌ સર્વર પર અત્યારે વધુ ટ્રાફિક છે. કૃપા કરીને થોડી સેકન્ડ પછી ફરી પ્રયત્ન કરો. ({last_error})"
                        st.error(err_msg)
                        st.session_state.messages.append({"role": "assistant", "content": err_msg})
                        st.stop()

                    st.session_state.messages.append({"role": "assistant", "content": answer_text})

                    if quick_action == "mcq" and st.session_state.mcq_questions is None:
                        parsed = parse_mcq(answer_text)
                        if parsed:
                            st.session_state.mcq_questions = parsed
                            st.session_state.mcq_user_answers = {}
                            st.session_state.mcq_checked = False
                        st.rerun()
                except Exception as e:
                    err_msg = f"❌ AI જવાબ મેળવવામાં ભૂલ આવી: {e}"
                    st.error(err_msg)
                    st.session_state.messages.append({"role": "assistant", "content": err_msg})