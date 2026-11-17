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

    pdf.add_page()
    pdf.set_font(base_font, "B", 16)
    pdf.set_text_color(30, 58, 138)
    pdf.cell(0, 10, "ધોરણ 3 થી 8 - સ્માર્ટ AI સ્ટડી નોટ્સ", ln=True, align="C")
    pdf.set_font(base_font, "", 11)
    pdf.set_text_color(0, 0, 0)
    pdf.cell(0, 7, f"વિષય: {subject_name or 'સામાન્ય'}", ln=True, align="C")
    pdf.cell(0, 7, f"પ્રકરણ: {chapter_name or 'બધા પ્રકરણો'}", ln=True, align="C")
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

    return bytes(pdf.output(dest="S"))


def transcribe_audio_gujarati(audio_bytes, api_keys):
    """Convert recorded Gujarati speech audio into Gujarati text using Gemini."""
    if not HAS_GENAI or not api_keys:
        return ""
    prompt = (
        "આ ઓડિયોમાં વિદ્યાર્થી જે બોલ્યા છે તે ફક્ત ગુજરાતી લિપિમાં લખો. "
        "બીજું કોઈ વધારાનું લખાણ કે સમજૂતી લખશો નહીં, ફક્ત બોલાયેલા શબ્દો જ લખો."
    )
    for cur_key in api_keys:
        try:
            client = genai.Client(api_key=cur_key)
            resp = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
                    prompt
                ]
            )
            if resp and resp.text:
                return resp.text.strip()
        except Exception:
            continue
    return ""


st.set_page_config(
    page_title="ધોરણ 3 થી 8 ગુજરાતી માધ્યમ - સ્માર્ટ AI શિક્ષક",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="collapsed"
)


def load_syllabus():
    syllabus_path = "diksha_syllabus.json"
    if os.path.exists(syllabus_path):
        with open(syllabus_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


syllabus_data = load_syllabus()


def get_all_grades_reference_text(data):
    """Build compact reference of ALL Grades (3 to 8) GCERT chapters from diksha_syllabus.json."""
    if not data:
        return ""
    lines = ["GCERT ધોરણ 3 થી 8 નો સત્તાવાર અભ્યાસક્રમ (અનુક્રમણિકા):"]
    for grade_key, g_info in data.items():
        subjs = g_info.get("subjects", {})
        if not subjs:
            continue
        lines.append(f"\n[{grade_key}]")
        for subj, info in subjs.items():
            ch_names = [c["name"] for c in info.get("chapters", [])]
            if ch_names:
                lines.append(f"- {subj}: {', '.join(ch_names)}")
    return "\n".join(lines)


ALL_GRADES_REF = get_all_grades_reference_text(syllabus_data)

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
    padding: 1.25rem 1rem;
    border-radius: 16px;
    margin: 0.25rem 0 1rem 0;
    box-shadow: 0 8px 24px rgba(30, 58, 138, 0.25);
}
.app-banner h1 {
    margin: 0 0 0.25rem 0;
    font-size: 1.65rem;
    font-weight: 700;
}
.app-banner p {
    margin: 0;
    font-size: 0.95rem;
    opacity: 0.95;
}

.subject-pill {
    display: inline-flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 0.4rem;
    background: linear-gradient(135deg, #F59E0B, #D97706);
    color: #fff;
    padding: 0.45rem 0.9rem;
    border-radius: 999px;
    font-size: 0.9rem;
    font-weight: 600;
    margin-bottom: 0.85rem;
    box-shadow: 0 4px 12px rgba(245, 158, 11, 0.3);
}

.stChatMessage {
    border-radius: 18px !important;
    padding: 0.85rem 1rem !important;
    margin: 0.5rem 0 !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06) !important;
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

/* CHATGPT-STYLE SINGLE ROW BOTTOM PILL BAR (DESKTOP + MOBILE) */
[data-testid="stBottom"] {
    padding: 0.5rem 0.75rem !important;
    background: transparent !important;
    border-top: none !important;
    box-shadow: none !important;
    z-index: 99999 !important;
}

[data-testid="stBottom"] [data-testid="stHorizontalBlock"],
div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) {
    display: flex !important;
    flex-direction: row !important;
    flex-wrap: nowrap !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 6px !important;
    background-color: #2f2f2f !important;
    border: 1px solid #4a4a4a !important;
    border-radius: 999px !important;
    padding: 5px 8px !important;
    box-shadow: 0 4px 18px rgba(0, 0, 0, 0.28) !important;
    max-width: 820px !important;
    width: 100% !important;
    margin: 0 auto !important;
}

[data-testid="stBottom"] [data-testid="stColumn"],
div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) > [data-testid="stColumn"] {
    width: auto !important;
    min-width: unset !important;
    max-width: unset !important;
    flex: 0 0 auto !important;
    padding: 0 !important;
    margin: 0 !important;
}

[data-testid="stBottom"] [data-testid="stColumn"]:nth-child(2),
div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) > [data-testid="stColumn"]:nth-child(2) {
    flex: 1 1 auto !important;
    min-width: 0 !important;
}

[data-testid="stBottom"] [data-testid="stPopover"] > button,
div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) [data-testid="stPopover"] > button {
    border-radius: 50% !important;
    width: 36px !important;
    height: 36px !important;
    min-height: 36px !important;
    padding: 0 !important;
    background-color: transparent !important;
    color: #ffffff !important;
    border: none !important;
    font-size: 20px !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
[data-testid="stBottom"] [data-testid="stPopover"] > button:hover {
    background-color: #424242 !important;
}
[data-testid="stBottom"] [data-testid="stPopover"] > button svg {
    display: none !important;
}

[data-testid="stBottom"] [data-testid="stTextInput"],
div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) [data-testid="stTextInput"] {
    margin: 0 !important;
    width: 100% !important;
}
[data-testid="stBottom"] [data-testid="stTextInput"] div[data-baseweb="input"],
div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) div[data-baseweb="input"] {
    background-color: #2f2f2f !important;
    border: none !important;
    box-shadow: none !important;
}
[data-testid="stBottom"] [data-testid="stTextInput"] input,
div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) input[type="text"] {
    background-color: #2f2f2f !important;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    caret-color: #ffffff !important;
    border: none !important;
    padding: 6px 8px !important;
    font-size: 0.95rem !important;
    box-shadow: none !important;
}
[data-testid="stBottom"] [data-testid="stTextInput"] input::placeholder,
div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) input[type="text"]::placeholder {
    color: #a3a3a3 !important;
    -webkit-text-fill-color: #a3a3a3 !important;
}
[data-testid="stBottom"] [data-testid="InputInstructions"],
div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) [data-testid="InputInstructions"] {
    display: none !important;
}

[data-testid="stBottom"] button[kind="secondary"],
div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) button[kind="secondary"] {
    border-radius: 50% !important;
    width: 36px !important;
    height: 36px !important;
    min-height: 36px !important;
    padding: 0 !important;
    background-color: transparent !important;
    color: #ffffff !important;
    border: none !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    font-size: 18px !important;
}
[data-testid="stBottom"] button[kind="secondary"]:hover {
    background-color: #424242 !important;
}

[data-testid="stBottom"] button[kind="primary"],
div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) button[kind="primary"] {
    border-radius: 50% !important;
    width: 36px !important;
    height: 36px !important;
    min-height: 36px !important;
    padding: 0 !important;
    background-color: #2563EB !important;
    color: #ffffff !important;
    border: none !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    font-size: 16px !important;
}
[data-testid="stBottom"] button[kind="primary"]:hover {
    background-color: #1D4ED8 !important;
}

@media (max-width: 768px) {
    .block-container {
        padding-top: 0.5rem !important;
        padding-left: 0.6rem !important;
        padding-right: 0.6rem !important;
        padding-bottom: 5.5rem !important;
        max-width: 100% !important;
    }
    .app-banner {
        padding: 0.85rem 0.75rem;
        margin-bottom: 0.6rem;
        border-radius: 14px;
    }
    .app-banner h1 { font-size: 1.2rem; }
    .app-banner p { font-size: 0.82rem; }
    .subject-pill { font-size: 0.78rem; padding: 0.35rem 0.75rem; }
    .stChatMessage {
        margin: 0.35rem 0 !important;
        padding: 0.65rem 0.85rem !important;
        border-radius: 14px !important;
    }
    .stChatMessage[data-testid="stChatMessage"][data-message-role="user"] {
        margin-left: 1rem !important;
    }
    .stChatMessage[data-testid="stChatMessage"][data-message-role="assistant"] {
        margin-right: 0.5rem !important;
    }
    [data-testid="stBottom"] {
        padding: 0.4rem 0.45rem !important;
    }
    [data-testid="stBottom"] [data-testid="stHorizontalBlock"],
    div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) {
        padding: 4px 6px !important;
        gap: 3px !important;
    }
    [data-testid="stBottom"] [data-testid="stTextInput"] input,
    div[data-testid="stHorizontalBlock"]:has([data-testid="stPopover"]) input[type="text"] {
        font-size: 0.9rem !important;
        padding: 4px 4px !important;
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
        ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3.5-flash-lite"],
        index=0,
        key="model_choice_select"
    )

    st.divider()

    grade_options = ["🎯 આપમેળે ઓળખો (Auto)", "ધોરણ 3", "ધોરણ 4", "ધોરણ 5", "ધોરણ 6", "ધોરણ 7", "ધોરણ 8"]
    grade_choice = st.selectbox(
        "🎓 ધોરણ પસંદ કરો (વૈકલ્પિક):",
        grade_options,
        index=0,
        key="grade_select"
    )

    st.divider()

    is_auto_mode = (grade_choice == "🎯 આપમેળે ઓળખો (Auto)")
    selected_subject_name = None
    selected_chapter_obj = None
    chapters = []

    if not is_auto_mode:
        grade_num = int(grade_choice.split()[-1])
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

            chapter_display = []
            for idx, ch in enumerate(chapters, 1):
                name = ch.get("name", "").strip()
                clean_title = re.sub(r'^(?:પ્રકરણ\s*\d+\s*[:\-\.]\s*|\d+[\.\)]\s*)', '', name).strip()
                chapter_display.append(f"પ્રકરણ {idx}: {clean_title}" if clean_title else f"પ્રકરણ {idx}")

            options_list = ["બધા પ્રકરણો / સામાન્ય પ્રશ્ન"] + chapter_display
            selected_chapter_idx = st.selectbox(
                "📑 પ્રકરણ પસંદ કરો:",
                range(len(options_list)),
                format_func=lambda i: options_list[i],
                index=0,
                key=f"chapter_select_{grade_num}_{selected_subject_name}"
            )

            if selected_chapter_idx > 0:
                selected_chapter_obj = chapters[selected_chapter_idx - 1]
    else:
        st.info("💡 **સ્માર્ટ મોડ ચાલુ છે:** તમે ડ્રોપડાઉન પસંદ કર્યા વગર પણ સીધો કોઈ પણ ધોરણ કે વિષયનો પ્રશ્ન પૂછી શકો છો!")

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
        st.session_state.show_voice_recorder = False
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
            f"પ્રકરણ: {selected_chapter_obj['name'] if selected_chapter_obj else 'બધા પ્રકરણો'}",
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
            chapter_name = selected_chapter_obj['name'] if selected_chapter_obj else 'બધા પ્રકરણો'
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
    <p>ગુજરાતી માધ્યમના બધા જ વિષયો માટે — સીધો પ્રશ્ન પૂછો, બોલીને પૂછો અથવા ફોટો અપલોડ કરો!</p>
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
if "show_voice_recorder" not in st.session_state:
    st.session_state.show_voice_recorder = False
if "audio_counter" not in st.session_state:
    st.session_state.audio_counter = 0

if not is_auto_mode and selected_subject_name:
    ch_text = selected_chapter_obj['name'] if selected_chapter_obj else 'બધા પ્રકરણો'
    st.markdown(f'''
    <div class="subject-pill">
        <span>🎓 {grade_choice} | 📌 {selected_subject_name} | {ch_text}</span>
    </div>
    ''', unsafe_allow_html=True)
else:
    st.markdown('''
    <div class="subject-pill">
        <span>✨ સ્માર્ટ મોડ (ધોરણ 3 થી 8) — સીધો તમારો પ્રશ્ન નીચે લખો કે બોલો!</span>
    </div>
    ''', unsafe_allow_html=True)

target_grade = "ધોરણ 3 થી 8" if is_auto_mode else grade_choice
target_subject = selected_subject_name if selected_subject_name else "સંબંધિત વિષય"
chapter_label = selected_chapter_obj['name'] if selected_chapter_obj else "છેલ્લી ચર્ચા મુજબના પ્રકરણ"

if quick_action:
    prompt_map = {
        "summary": f"{target_grade} ના {target_subject} ના '{chapter_label}' નો સરસ અને સરળ ગુજરાતીમાં મુદ્દાસર સારાંશ આપો.",
        "exercise": f"{target_grade} ના {target_subject} ના '{chapter_label}' ના સ્વાધ્યાયના પ્રશ્નો અને તેના સાચા જવાબો સમજૂતી સાથે આપો.",
        "mcq": f"{target_grade} ના {target_subject} ના '{chapter_label}' આધારિત ગુજરાતીમાં ૫ MCQ (બહુવિકલ્પી) પ્રશ્નો બનાવો. દરેક પ્રશ્નમાં ૪ વિકલ્પો (A, B, C, D) હોય. નીચેના ફોર્મેટમાં જ લખો:\n\nપ્રશ્ન 1: પ્રશ્ન લખો?\nA. વિકલ્પ 1\nB. વિકલ્પ 2\nC. વિકલ્પ 3\nD. વિકલ્પ 4\nસાચો જવાબ: B\nસમજૂતી: સરળ સમજૂતી.\n\nઆ પ્રકારે તમામ ૫ પ્રશ્નો લખો.",
        "easy_example": f"{target_grade} ના {target_subject} ના '{chapter_label}' નું સરળ ભાષામાં વાસ્તવિક જીવનના ઉદાહરણો દ્વારા સમજૂતી આપો. ગુજરાતીમાં લખો. ગણિત અથવા વિજ્ઞાન હોય તો સૂત્રો $...$ (LaTeX) નો ઉપયોગ કરો.",
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

if st.session_state.show_voice_recorder:
    with st.container(border=True):
        col_v1, col_v2 = st.columns([5, 1])
        with col_v1:
            st.markdown("🎙️ **ગુજરાતીમાં બોલો અને પૂરું થાય એટલે લાલ સ્ટોપ (⏹) બટન દબાવો:**")
        with col_v2:
            if st.button("✖", key="close_voice_btn"):
                st.session_state.show_voice_recorder = False
                st.rerun()

        audio_val = st.audio_input("અવાજ રેકોર્ડ કરો", key=f"voice_rec_{st.session_state.audio_counter}", label_visibility="collapsed")
        if audio_val is not None:
            audio_bytes = audio_val.getvalue()
            st.session_state.audio_counter += 1
            st.session_state.show_voice_recorder = False
            with st.spinner("🎧 તમારો અવાજ ગુજરાતીમાં લખાઈ રહ્યો છે..."):
                spoken_text = transcribe_audio_gujarati(audio_bytes, api_keys)
            if spoken_text:
                st.session_state.messages.append({"role": "user", "content": f"🎤 {spoken_text}"})
            else:
                st.warning("⚠️ અવાજ સ્પષ્ટ સંભળાયો નથી, કૃપા કરીને ફરીથી બોલો.")
            st.rerun()

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
            if st.button("❌", key="clear_attachment_btn"):
                st.session_state.pop("bottom_uploader", None)
                st.session_state.pop("bottom_camera", None)
                st.rerun()

if "input_counter" not in st.session_state:
    st.session_state.input_counter = 0

bottom_container = getattr(st, "bottom", st.container())
with bottom_container:
    col_plus, col_input, col_mic, col_send = st.columns([1, 10, 1, 1], vertical_alignment="center")
    with col_plus:
        with st.popover("➕"):
            st.file_uploader("📁 ગેલેરી / PDF / ફાઈલ પસંદ કરો", type=None, key="bottom_uploader")
            st.camera_input("📸 કેમેરાથી ફોટો પાડો", key="bottom_camera")
    with col_input:
        user_text = st.text_input(
            "પ્રશ્ન...",
            placeholder="પ્રશ્ન પૂછો (દા.ત. ધોરણ 8 સંસ્કૃત પાઠ 2, અથવા કોઈપણ સવાલ)...",
            label_visibility="collapsed",
            key=f"chat_text_input_{st.session_state.input_counter}"
        )
    with col_mic:
        if st.button("🎤", key=f"mic_toggle_{st.session_state.input_counter}", help="બોલીને પ્રશ્ન પૂછો"):
            st.session_state.show_voice_recorder = not st.session_state.show_voice_recorder
            st.rerun()
    with col_send:
        send_clicked = st.button("➤", type="primary", key=f"send_btn_{st.session_state.input_counter}")

if send_clicked and (user_text.strip() or attached_file):
    prompt_text = user_text.strip() if user_text.strip() else ("[ફાઈલ સંલગ્ન છે]" if attached_file else "")
    st.session_state.messages.append({"role": "user", "content": prompt_text})
    st.session_state.input_counter += 1
    st.rerun()

if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    last_user_msg = st.session_state.messages[-1]["content"]
    clean_user_msg = last_user_msg.lstrip("🎤 ").strip()
    with st.chat_message("assistant"):
        if not HAS_GENAI or not api_keys:
            st.error("⚠️ કૃપા કરીને Secrets માં તમારી Gemini API Key દાખલ કરો!")
        else:
            try:
                if is_auto_mode:
                    mode_instruction = (
                        "વિદ્યાર્થીએ કોઈ ડ્રોપડાઉન પસંદ કર્યું નથી.\n"
                        "૧) જો વિદ્યાર્થીના પ્રશ્ન, આગળની વાતચીત કે ફોટો પરથી ધોરણ (3 થી 8) અને વિષય સમજાઈ જાય, તો તરત જ સરળ ગુજરાતીમાં સંપૂર્ણ અને સચોટ જવાબ આપો.\n"
                        "૨) જો વિદ્યાર્થી ફક્ત અધૂરો પ્રશ્ન પૂછે (જેમ કે 'પાઠ 2 સમજાવો' જેમાં ધોરણ અને વિષય સ્પષ્ટ ન હોય), તો નમ્રતાથી એક નાનો ફોલો-અપ પ્રશ્ન પૂછો: 'તમે કયા ધોરણ (3 થી 8) અને કયા વિષયના પાઠ વિશે જાણવા માંગો છો?'\n"
                        "૩) મહત્વપૂર્ણ: તમારી પાસે ધોરણ 3 થી 8 ના બધા જ વિષયો (ગુજરાતી, હિન્દી, ગણિત, પર્યાવરણ/વિજ્ઞાન, સામાજિક વિજ્ઞાન, અંગ્રેજી, સંસ્કૃત) નું સંપૂર્ણ જ્ઞાન છે. ક્યારેય એમ ન કહેવું કે 'મારી પાસે ડેટા નથી'. નીચે આપેલી GCERT ની સત્તાવાર અનુક્રમણિકા મુજબ જ જવાબ આપો (જૂના પુસ્તકો જેમ કે 'Marigold' કે 'ગણિતગમ્મત' સાથે ગૂંચવાશો નહીં):\n"
                        f"{ALL_GRADES_REF}\n"
                    )
                else:
                    all_ch_list = "\n".join([f"- {c['name']}" for c in chapters]) if chapters else ""
                    mode_instruction = (
                        f"હાલ પસંદ કરેલ ધોરણ: {grade_choice} | વિષય: {selected_subject_name} | "
                        f"પ્રકરણ: {selected_chapter_obj['name'] if selected_chapter_obj else 'બધા પ્રકરણો'}.\n"
                        f"આ વિષયના GCERT નવા પ્રકરણોની સત્તાવાર યાદી:\n{all_ch_list}\n"
                        "મહત્વપૂર્ણ સૂચના: જૂના પુસ્તકો (જેમ કે અંગ્રેજીમાં 'Marigold' કે ગણિતમાં 'ગણિતગમ્મત') સાથે ક્યારેય ગૂંચવાશો નહીં. "
                        "ઉપર આપેલા પ્રકરણો/યુનિટ્સ જ આ વિષયના સાચા અને નવા પ્રકરણો છે, તેના આધારે જ જવાબ આપો."
                    )

                system_instruction = f"""તમે ગુજરાત રાજ્ય શાળા પાઠ્યપુસ્તક મંડળ (GCERT) ધોરણ 3 થી 8 (ગુજરાતી માધ્યમ) ના નિષ્ણાત AI શિક્ષક છો.
{mode_instruction}
સરળ, સ્પષ્ટ અને સચોટ ગુજરાતીમાં જવાબ આપો. ગણિત/વિજ્ઞાનના સૂત્રો $...$ (LaTeX) માં લખો.
MCQ માટે 'સાચો જવાબ: X' અને સમજૂતી આપો."""

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
                            contents.append(types.Part.from_bytes(data=file_bytes, mime_type="application/pdf"))
                        else:
                            try:
                                contents.append(Image.open(io.BytesIO(file_bytes)))
                            except Exception:
                                contents.append("[અપલોડ કરેલી ફાઈલ સંલગ્ન છે]")
                    except Exception as file_err:
                        contents.append(f"[ફાઈલ જોડવામાં ભૂલ: {file_err}]")

                st.session_state.pop("bottom_uploader", None)
                st.session_state.pop("bottom_camera", None)

                recent_msgs = st.session_state.messages[:-1][-6:]
                history_text = ""
                for msg in recent_msgs:
                    history_text += f"{'વિદ્યાર્થી' if msg['role'] == 'user' else 'શિક્ષક'}: {msg['content']}\n"

                full_prompt = f"{system_instruction}\n\n{history_text}વિદ્યાર્થીનો પ્રશ્ન: {clean_user_msg}"
                contents.append(full_prompt)

                all_models = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3.5-flash-lite"]
                available_models = [model_choice] + [m for m in all_models if m != model_choice]

                answer_text = ""
                success = False
                last_error = None
                placeholder = st.empty()
                placeholder.markdown("⚡ *જવાબ લખાઈ રહ્યો છે...*")

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
                            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                                break
                            elif "503" in err_str or "UNAVAILABLE" in err_str or "500" in err_str or "404" in err_str:
                                continue
                            else:
                                raise err
                    if success:
                        break

                if not success:
                    placeholder.empty()
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