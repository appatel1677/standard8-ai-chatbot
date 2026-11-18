import streamlit as st
import streamlit.components.v1 as components
import json, os, io, re
from PIL import Image
from fpdf import FPDF

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

st.set_page_config(page_title="Standard 3 to 8 Smart AI Palaj Teacher", page_icon="📚", layout="wide", initial_sidebar_state="collapsed")

# --- HELPER FUNCTIONS ---
def parse_mcq(text):
    questions = []
    for part in re.split(r'\n?પ્રશ્ન\s*\d+\s*[:.]', text)[1:]:
        lines = [l.strip() for l in part.strip().splitlines() if l.strip()]
        if not lines: continue
        q_text, options, answer, explanation = lines[0], {}, None, ""
        for l in lines[1:]:
            if m := re.match(r'([ABCD])[\).]\s*(.*)', l): options[m.group(1)] = m.group(2)
            elif re.search(r'સાચો જવાબ|જવાબ|Answer', l) and (ma := re.search(r'([ABCD])', l)): answer = ma.group(1)
            elif re.search(r'સમજૂતી|Explanation', l): explanation = re.sub(r'^(સમજૂતી|Explanation)[:.]?\s*', '', l)
        if q_text and options and answer:
            questions.append({"question": q_text, "options": options, "answer": answer, "explanation": explanation})
    return questions

@st.cache_resource
def get_pdf_font():
    for p in ["C:/Windows/Fonts/Nirmala.ttf", "C:/Windows/Fonts/Shruti.ttf", "NotoSansGujarati-Regular.ttf"]:
        if os.path.exists(p): return p
    try:
        import urllib.request
        urllib.request.urlretrieve("https://github.com/google/fonts/raw/main/ofl/notosansgujarati/NotoSansGujarati%5Bwdth%2Cwght%5D.ttf", "NotoSansGujarati-Regular.ttf")
        return "NotoSansGujarati-Regular.ttf"
    except Exception:
        return None

def build_pdf_bytes(messages, subj, chap):
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
    pdf.cell(0, 10, f"Standard 3 to 8 Smart AI Palaj Teacher ({subj} | {chap})", ln=True, align="C")
    pdf.ln(4)
    for m in messages:
        pdf.set_font(base_font, "B", 11)
        pdf.cell(0, 7, ("વિદ્યાર્થી:" if m["role"] == "user" else "શિક્ષક:"), ln=True)
        pdf.set_font(base_font, "", 10)
        pdf.multi_cell(0, 6, m["content"])
        pdf.ln(2)
    return bytes(pdf.output(dest="S"))

def transcribe_gujarati(audio_file, api_keys):
    if not HAS_GENAI or not api_keys or not audio_file: return ""
    audio_bytes = audio_file.getvalue()
    mime = getattr(audio_file, "type", None) or "audio/webm"
    prompt = "આ ઓડિયોમાં જે બોલાયું છે તે ફક્ત ગુજરાતી લિપિમાં લખો. કોઈ વધારાનું લખાણ લખશો નહીં."
    for key in api_keys:
        try:
            client = genai.Client(api_key=key)
            resp = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=[types.Part.from_bytes(data=audio_bytes, mime_type=mime), prompt]
            )
            if resp and resp.text: return resp.text.strip()
        except Exception:
            continue
    return ""

@st.cache_data
def load_syllabus():
    if os.path.exists("diksha_syllabus.json"):
        with open("diksha_syllabus.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

syllabus_data = load_syllabus()
ALL_GRADES_REF = "\n".join(
    f"[{g}] " + " | ".join(f"{s}: {', '.join(c['name'] for c in info.get('chapters', []))}" for s, info in d.get("subjects", {}).items())
    for g, d in syllabus_data.items() if d.get("subjects")
)

# --- MOBILE-FIRST RESPONSIVE CSS (NO HORIZONTAL SCROLL) ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Gujarati:wght@400;600;700&display=swap');

html, body, .stApp {
    max-width: 100vw !important;
    overflow-x: hidden !important;
    font-family: 'Noto Sans Gujarati', sans-serif !important;
}
p, h1, h2, h3, input, textarea, button, .stMarkdown, .stChatMessage {
    font-family: 'Noto Sans Gujarati', sans-serif !important;
}
[data-testid="stIconMaterial"], .material-symbols-rounded, span[translate="no"] {
    font-family: 'Material Symbols Rounded' !important;
}

/* ATTRACTIVE ROUNDED BLUE BANNER */
.app-banner {
    background: linear-gradient(135deg, #1E3A8A 0%, #2563EB 50%, #0EA5E9 100%);
    color: #ffffff;
    padding: 0.9rem 1.25rem;
    border-radius: 28px;
    margin-bottom: 0.75rem;
    text-align: center;
    box-shadow: 0 8px 20px rgba(37, 99, 235, 0.3);
    border: 1px solid rgba(255, 255, 255, 0.2);
}
.app-banner h1 {
    margin: 0;
    font-size: 1.25rem;
    font-weight: 700;
    letter-spacing: 0.3px;
}

.subject-pill {
    display: inline-block;
    background: linear-gradient(135deg, #F59E0B, #D97706);
    color: #fff;
    padding: 0.35rem 0.9rem;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 600;
    margin-bottom: 0.75rem;
}

.stChatMessage[data-message-role="user"] { background: #EFF6FF !important; border-left: 4px solid #3B82F6 !important; border-radius: 16px !important; }
.stChatMessage[data-message-role="assistant"] { background: #F0FDF4 !important; border-left: 4px solid #10B981 !important; border-radius: 16px !important; }

/* FIXED BOTTOM INPUT BAR (PERFECT MOBILE FIT) */
[data-testid="stBottom"] {
    padding: 0.4rem 0.5rem !important;
    background: transparent !important;
    width: 100vw !important;
    max-width: 100% !important;
    left: 0 !important;
    right: 0 !important;
    box-sizing: border-box !important;
    z-index: 99999 !important;
}
[data-testid="stBottom"] > div {
    padding: 0 !important;
    max-width: 820px !important;
    margin: 0 auto !important;
}
[data-testid="stBottom"] [data-testid="stHorizontalBlock"] {
    display: grid !important;
    grid-template-columns: 34px minmax(0, 1fr) 36px 36px !important;
    align-items: center !important;
    gap: 4px !important;
    background: #2f2f2f !important;
    border: 1px solid #4a4a4a !important;
    border-radius: 999px !important;
    padding: 4px 6px !important;
    width: 100% !important;
    box-sizing: border-box !important;
}
[data-testid="stBottom"] [data-testid="stColumn"] {
    width: 100% !important;
    min-width: 0 !important;
    max-width: 100% !important;
    padding: 0 !important;
    margin: 0 !important;
}
[data-testid="stBottom"] input[type="text"] {
    background: #2f2f2f !important;
    color: #fff !important;
    -webkit-text-fill-color: #fff !important;
    border: none !important;
    padding: 6px 4px !important;
    font-size: 0.92rem !important;
    width: 100% !important;
}
[data-testid="stBottom"] div[data-baseweb="input"] {
    background: #2f2f2f !important;
    border: none !important;
}
[data-testid="stBottom"] [data-testid="InputInstructions"],
[data-testid="stBottom"] [data-testid="stPopover"] svg {
    display: none !important;
}
[data-testid="stBottom"] button {
    border-radius: 50% !important;
    width: 34px !important;
    height: 34px !important;
    min-height: 34px !important;
    padding: 0 !important;
    border: none !important;
    color: #fff !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
[data-testid="stBottom"] button[kind="secondary"],
[data-testid="stBottom"] [data-testid="stPopover"] > button {
    background: #3f3f3f !important;
    font-size: 16px !important;
}
[data-testid="stBottom"] button[kind="primary"] {
    background: #2563EB !important;
    font-size: 15px !important;
}

/* HIDE COMPONENT IFRAME SPACE */
iframe[height="0"] {
    display: none !important;
    position: absolute !important;
}

@media (max-width: 768px) {
    .block-container {
        padding: 0.5rem 0.65rem 6rem !important;
        max-width: 100vw !important;
        overflow-x: hidden !important;
    }
    .app-banner {
        padding: 0.75rem 0.9rem;
        border-radius: 24px;
    }
    .app-banner h1 {
        font-size: 1.05rem;
    }
}
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE INIT (BEFORE WIDGETS RENDER) ---
defaults = {
    "messages": [], "mcq_questions": None, "mcq_user_answers": {}, "mcq_checked": False,
    "show_voice": False, "audio_counter": 0, "draft_text": "", "focus_input": False,
    "clear_draft": False
}
for k, v in defaults.items():
    if k not in st.session_state: st.session_state[k] = v

if st.session_state.clear_draft:
    st.session_state.draft_text = ""
    st.session_state.clear_draft = False

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("### 🎓 સ્માર્ટ AI શિક્ષક (GCERT)")
    raw_keys = (st.secrets.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEYS") or
                st.secrets.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY") or "")
    api_keys = [k.strip().strip('"\'') for k in str(raw_keys).split(",") if k.strip()]

    model_choice = st.selectbox("🤖 AI મોડેલ:", ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3.5-flash-lite"])
    grade_choice = st.selectbox("🎓 ધોરણ:", ["🎯 આપમેળે ઓળખો (Auto)"] + [f"ધોરણ {i}" for i in range(3, 9)])

    is_auto = grade_choice.startswith("🎯")
    sel_subj, sel_chap, chapters = None, None, []
    if not is_auto:
        subjs = syllabus_data.get(grade_choice, {}).get("subjects", {})
        if subjs:
            sel_subj = st.selectbox("📖 વિષય:", list(subjs.keys()))
            chapters = subjs[sel_subj].get("chapters", [])
            ch_opts = ["બધા પ્રકરણો / સામાન્ય પ્રશ્ન"] + [
                f"પ્રકરણ {i}: " + re.sub(r'^(?:પ્રકરણ\s*\d+\s*[:\-\.]\s*|\d+[\.\)]\s*)', '', c.get("name", "")).strip()
                for i, c in enumerate(chapters, 1)
            ]
            ch_idx = st.selectbox("📑 પ્રકરણ:", range(len(ch_opts)), format_func=lambda i: ch_opts[i])
            if ch_idx > 0: sel_chap = chapters[ch_idx - 1]
    else:
        st.info("💡 સીધો કોઈ પણ ધોરણ કે વિષયનો પ્રશ્ન પૂછી શકો છો!")

    st.markdown("### 🛠️ ક્વિક ટૂલ્સ")
    quick_action = None
    c1, c2 = st.columns(2)
    if c1.button("📖 સારાંશ"): quick_action = "summary"
    if c1.button("📝 MCQ ટેસ્ટ"): quick_action = "mcq"
    if c2.button("📝 સ્વાધ્યાય"): quick_action = "exercise"
    if c2.button("💡 ઉદાહરણ"): quick_action = "easy_example"

    st.divider()
    if st.button("🗑️ નવી ચેટ", use_container_width=True):
        st.session_state.update({"messages": [], "mcq_questions": None, "mcq_user_answers": {}, "mcq_checked": False, "clear_draft": True})
        st.rerun()

    u1, u2 = st.columns([1, 2])
    dl_fmt = u1.selectbox("ફોર્મેટ", [".pdf", ".txt", ".md"], label_visibility="collapsed")
    if u2.button("📥 નોટ્સ", use_container_width=True) and st.session_state.messages:
        s_name, c_name = sel_subj or "સામાન્ય", sel_chap["name"] if sel_chap else "બધા પ્રકરણો"
        if dl_fmt == ".pdf":
            data, mime = build_pdf_bytes(st.session_state.messages, s_name, c_name), "application/pdf"
        else:
            data = "\n\n".join(f"{'વિદ્યાર્થી' if m['role']=='user' else 'શિક્ષક'}: {m['content']}" for m in st.session_state.messages)
            mime = "text/plain"
        st.download_button("⬇️ ડાઉનલોડ કરો", data=data, file_name=f"notes_{s_name}{dl_fmt}", mime=mime, use_container_width=True)

# --- HEADER & PILL ---
st.markdown('<div class="app-banner"><h1>📚 standard 3 to 8 smart AI palaj teacher</h1></div>', unsafe_allow_html=True)
pill_txt = f"🎓 {grade_choice} | 📌 {sel_subj} | {sel_chap['name'] if sel_chap else 'બધા પ્રકરણો'}" if not is_auto and sel_subj else "✨ સ્માર્ટ મોડ (ધોરણ 3 થી 8)"
st.markdown(f'<div class="subject-pill">{pill_txt}</div>', unsafe_allow_html=True)

if quick_action:
    tg, ts, cl = ("ધોરણ 3 થી 8" if is_auto else grade_choice), (sel_subj or "સંબંધિત વિષય"), (sel_chap["name"] if sel_chap else "છેલ્લી ચર્ચા મુજબના પ્રકરણ")
    prompts = {
        "summary": f"{tg} ના {ts} ના '{cl}' નો સરળ ગુજરાતીમાં મુદ્દાસર સારાંશ આપો.",
        "exercise": f"{tg} ના {ts} ના '{cl}' ના સ્વાધ્યાયના પ્રશ્નો અને જવાબો સમજૂતી સાથે આપો.",
        "mcq": f"{tg} ના {ts} ના '{cl}' આધારિત ગુજરાતીમાં ૫ MCQ બનાવો. ફોર્મેટ:\nપ્રશ્ન 1: પ્રશ્ન?\nA. ...\nB. ...\nC. ...\nD. ...\nસાચો જવાબ: B\nસમજૂતી: ...",
        "easy_example": f"{tg} ના {ts} ના '{cl}' નું વાસ્તવિક જીવનના સરળ ઉદાહરણો દ્વારા સમજાવો."
    }
    if quick_action == "mcq": st.session_state.update({"mcq_questions": None, "mcq_user_answers": {}, "mcq_checked": False})
    st.session_state.messages.append({"role": "user", "content": prompts[quick_action]})

for m in st.session_state.messages:
    with st.chat_message(m["role"]): st.markdown(m["content"])

# --- INTERACTIVE MCQ SECTION ---
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
    if c1.button("🏆 સ્કોર તપાસો"): st.session_state.mcq_checked = True
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
                st.markdown(f"**પ્રશ્ન {i+1}:** {'✅ સાચો!' if ua == ca else f'❌ ખોટો! સાચો જવાબ: **{ca}. {correct_opt}**'}")
                if q.get("explanation"): st.caption(f"💡 સમજૂતી: {q['explanation']}")

# --- ATTACHMENT PREVIEW ---
attached = st.session_state.get("bottom_uploader") or st.session_state.get("bottom_camera")
if attached:
    with st.container(border=True):
        t1, t2, t3 = st.columns([1, 6, 1])
        try:
            t1.image(Image.open(io.BytesIO(attached.getvalue())), width=45)
        except Exception:
            t1.markdown("📎")
        t2.caption(f"📎 જોડાયેલ ફાઈલ: {getattr(attached, 'name', 'ફોટો')}")
        if t3.button("❌", key="rm_att"):
            st.session_state.pop("bottom_uploader", None)
            st.session_state.pop("bottom_camera", None)
            st.rerun()

# --- BOTTOM INPUT BAR + VOICE RECORDER INSIDE BOTTOM CONTAINER ---
with getattr(st, "bottom", st.container()):
    if st.session_state.show_voice:
        with st.container(border=True):
            v1, v2 = st.columns([6, 1])
            v1.markdown("🎙️ **બોલો અને પૂરું થાય એટલે ⏹ દબાવો:**")
            if v2.button("✖", key="close_mic"):
                st.session_state.show_voice = False
                st.session_state.focus_input = True
                st.rerun()
            audio_val = st.audio_input("રેકોર્ડ", key=f"rec_{st.session_state.audio_counter}", label_visibility="collapsed")
            if audio_val:
                with st.spinner("🎧 ગુજરાતીમાં લખાઈ રહ્યું છે..."):
                    spoken = transcribe_gujarati(audio_val, api_keys)
                st.session_state.audio_counter += 1
                st.session_state.show_voice = False
                if spoken:
                    existingText = st.session_state.draft_text.strip()
                    st.session_state.draft_text = f"{existingText} {spoken}".strip() if existingText else spoken
                    st.session_state.focus_input = True
                else:
                    st.warning("⚠️ અવાજ સ્પષ્ટ સંભળાયો નથી, ફરીથી પ્રયત્ન કરો.")
                st.rerun()

    col_plus, col_in, col_mic, col_send = st.columns([1, 8, 1, 1], vertical_alignment="center")
    with col_plus:
        with st.popover("➕"):
            st.file_uploader("📁 ગેલેરી / PDF", key="bottom_uploader")
            st.camera_input("📸 કેમેરા", key="bottom_camera")
    with col_in:
        user_text = st.text_input("પ્રશ્ન...", key="draft_text", placeholder="પ્રશ્ન લખો અથવા 🎤 દબાવો...", label_visibility="collapsed")
    with col_mic:
        if st.button("🎤", help="બોલીને લખો"):
            st.session_state.show_voice = not st.session_state.show_voice
            st.rerun()
    with col_send:
        send_clicked = st.button("➤", type="primary", help="મોકલો")

# --- AUTO-FOCUS & CURSOR TO END AFTER SPEAKING ---
if st.session_state.focus_input:
    st.session_state.focus_input = False
    components.html("""
    <script>
    setTimeout(function() {
        const doc = window.parent.document;
        const inputField = doc.querySelector('[data-testid="stBottom"] input[type="text"]');
        if (inputField) {
            inputField.focus();
            const len = inputField.value.length;
            inputField.setSelectionRange(len, len);
        }
    }, 150);
    </script>
    """, height=0, width=0)

# --- MANUAL SEND ONLY ---
if send_clicked and (user_text.strip() or attached):
    st.session_state.messages.append({"role": "user", "content": user_text.strip() or "[ફાઈલ સંલગ્ન છે]"})
    st.session_state.clear_draft = True
    st.rerun()

# --- AI RESPONSE STREAMING ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    clean_q = st.session_state.messages[-1]["content"].strip()
    with st.chat_message("assistant"):
        if not HAS_GENAI or not api_keys:
            st.error("⚠️ Secrets માં GEMINI_API_KEY દાખલ કરો.")
        else:
            mode_inst = (
                f"વિદ્યાર્થીએ કોઈ ધોરણ પસંદ કર્યું નથી. પ્રશ્ન પરથી ધોરણ 3-8 સમજાય તો સીધો જવાબ આપો, નહીંતર ધોરણ અને વિષય પૂછો.\nGCERT અનુક્રમણિકા:\n{ALL_GRADES_REF}"
                if is_auto else
                f"ધોરણ: {grade_choice} | વિષય: {sel_subj} | પ્રકરણ: {sel_chap['name'] if sel_chap else 'બધા'}.\nપ્રકરણો: {', '.join(c['name'] for c in chapters)}"
            )
            sys_prompt = f"તમે GCERT ધોરણ 3 થી 8 (ગુજરાતી માધ્યમ) ના નિષ્ણાત AI શિક્ષક છો.\n{mode_inst}\nસરળ ગુજરાતીમાં જવાબ આપો. સૂત્રો $...$ માં લખો."

            contents = []
            att = st.session_state.get("bottom_uploader") or st.session_state.get("bottom_camera")
            if att:
                fb = att.getvalue()
                if getattr(att, "type", "") == "application/pdf":
                    contents.append(types.Part.from_bytes(data=fb, mime_type="application/pdf"))
                else:
                    contents.append(Image.open(io.BytesIO(fb)))
            st.session_state.pop("bottom_uploader", None)
            st.session_state.pop("bottom_camera", None)

            hist = "\n".join(f"{'વિદ્યાર્થી' if m['role']=='user' else 'શિક્ષક'}: {m['content']}" for m in st.session_state.messages[:-1][-6:])
            contents.append(f"{sys_prompt}\n\n{hist}\nવિદ્યાર્થીનો પ્રશ્ન: {clean_q}")

            models = [model_choice] + [m for m in ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3.5-flash-lite"] if m != model_choice]
            placeholder = st.empty()
            placeholder.markdown("⚡ *જવાબ લખાઈ રહ્યો છે...*")
            answer_text, success, last_err = "", False, None

            for key in api_keys:
                client = genai.Client(api_key=key)
                for mod in models:
                    try:
                        temp = ""
                        for chunk in client.models.generate_content_stream(model=mod, contents=contents):
                            if chunk.text:
                                temp += chunk.text
                                placeholder.markdown(temp + "▌")
                        placeholder.markdown(temp)
                        answer_text, success = temp, True
                        break
                    except Exception as e:
                        last_err = e
                        if any(x in str(e) for x in ["429", "RESOURCE_EXHAUSTED"]): break
                if success: break

            if success:
                st.session_state.messages.append({"role": "assistant", "content": answer_text})
                if quick_action == "mcq" and st.session_state.mcq_questions is None:
                    if parsed := parse_mcq(answer_text):
                        st.session_state.mcq_questions = parsed
                    st.rerun()
            else:
                placeholder.empty()
                err_msg = f"❌ સર્વર વ્યસ્ત છે. ફરી પ્રયત્ન કરો. ({last_err})"
                st.error(err_msg)
                st.session_state.messages.append({"role": "assistant", "content": err_msg})