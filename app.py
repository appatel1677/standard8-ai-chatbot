import streamlit as st
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
        pdf.multi_cell(0, 6, m["content"])
        pdf.ln(2)
    return bytes(pdf.output(dest="S"))

def transcribe_gujarati(audio_file, api_keys):
    """Returns (transcribed_text, error_message)."""
    if not HAS_GENAI:
        return "", "google-genai library install નથી."
    if not api_keys:
        return "", "Secrets માં GEMINI_API_KEY મળેલ નથી."
    if not audio_file:
        return "", "ઓડિયો ફાઈલ ખાલી છે."

    audio_bytes = audio_file.getvalue()
    if len(audio_bytes) < 100:
        return "", f"ઓડિયો રેકોર્ડ થયો નથી (Size: {len(audio_bytes)} bytes)."

    detected_mime = getattr(audio_file, "type", None) or "audio/wav"
    mime_candidates = list(dict.fromkeys([detected_mime, "audio/wav", "audio/webm", "audio/mp4"]))
    model_candidates = ["gemini-2.5-flash", "gemini-2.5-flash-lite"]

    prompt = (
        "Listen to this audio carefully and transcribe ONLY the exact spoken words in Gujarati script (ગુજરાતી લિપિ). "
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
                    if "429" in last_err or "RESOURCE_EXHAUSTED" in last_err:
                        break
            if "429" in last_err or "RESOURCE_EXHAUSTED" in last_err:
                break

    return "", f"ઓડિયો ટ્રાન્સક્રાઈબ ન થઈ શક્યો: {last_err}"

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

# --- MOBILE-SAFE HIGH-CONTRAST CSS ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Gujarati:wght@400;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"], .main {
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

.block-container {
    padding-top: 2.8rem !important;
    padding-bottom: 6.5rem !important;
    padding-left: 0.75rem !important;
    padding-right: 0.75rem !important;
    max-width: 820px !important;
    margin: 0 auto !important;
}

.slim-header {
    background: linear-gradient(90deg, #1E3A8A 0%, #2563EB 50%, #0284C7 100%);
    color: #ffffff;
    padding: 9px 16px;
    border-radius: 50px;
    text-align: center;
    font-size: 1.05rem;
    font-weight: 700;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.25);
    margin-bottom: 10px;
}

.stChatMessage[data-message-role="user"] {
    background: #EFF6FF !important;
    border-left: 4px solid #3B82F6 !important;
    border-radius: 14px !important;
    padding: 0.6rem 0.9rem !important;
    color: #111827 !important;
}
.stChatMessage[data-message-role="assistant"] {
    background: #F0FDF4 !important;
    border-left: 4px solid #10B981 !important;
    border-radius: 14px !important;
    padding: 0.6rem 0.9rem !important;
    color: #111827 !important;
}
.stChatMessage p, .stChatMessage li, .stChatMessage span {
    color: #111827 !important;
}

/* BOTTOM BAR STYLING - IMMUNE TO MOBILE DARK MODE INVERSION */
[data-testid="stBottom"] {
    padding: 0.4rem 0.5rem !important;
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
    grid-template-columns: 38px minmax(0, 1fr) 38px 38px !important;
    align-items: center !important;
    gap: 6px !important;
    background: #1f2937 !important;
    border: 1px solid #374151 !important;
    border-radius: 999px !important;
    padding: 5px 7px !important;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.3) !important;
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
[data-testid="stBottom"] div[data-baseweb="input"],
[data-testid="stBottom"] div[data-baseweb="base-input"] {
    background-color: #111827 !important;
    border-radius: 999px !important;
    border: 1px solid #4B5563 !important;
    color-scheme: dark !important;
}
[data-testid="stBottom"] input[type="text"] {
    background-color: #111827 !important;
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
    caret-color: #FFFFFF !important;
    color-scheme: dark !important;
    border-radius: 999px !important;
    border: none !important;
    padding: 7px 12px !important;
    font-size: 16px !important;
    font-weight: 500 !important;
    opacity: 1 !important;
}
[data-testid="stBottom"] input[type="text"]::placeholder {
    color: #9CA3AF !important;
    -webkit-text-fill-color: #9CA3AF !important;
    opacity: 1 !important;
}
[data-testid="stBottom"] [data-testid="InputInstructions"],
[data-testid="stBottom"] [data-testid="stPopover"] svg {
    display: none !important;
}
[data-testid="stBottom"] button {
    border-radius: 50% !important;
    width: 38px !important;
    height: 38px !important;
    min-height: 38px !important;
    padding: 0 !important;
    border: none !important;
    color: #ffffff !important;
    -webkit-text-fill-color: #ffffff !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
[data-testid="stBottom"] [data-testid="stPopover"] > button {
    background: #374151 !important;
    font-size: 16px !important;
}
[data-testid="stBottom"] button[kind="secondary"] {
    background: #10B981 !important;
    font-size: 16px !important;
}
[data-testid="stBottom"] button[kind="primary"] {
    background: #2563EB !important;
    font-size: 15px !important;
}

@media (max-width: 600px) {
    .slim-header { font-size: 0.9rem; padding: 7px 10px; }
}
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE INIT ---
defaults = {
    "messages": [], "mcq_questions": None, "mcq_user_answers": {}, "mcq_checked": False,
    "draft_text": "", "mic_open": False, "audio_counter": 0, "input_version": 0,
    "voice_error": ""
}
for k, v in defaults.items():
    if k not in st.session_state: st.session_state[k] = v

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

# --- SLIM HEADER ---
st.markdown('<div class="slim-header">📚 standard 3 to 8 smart AI palaj teacher</div>', unsafe_allow_html=True)

if quick_action:
    prompts = {
        "summary": "છેલ્લી ચર્ચા મુજબના પાઠનો સરળ ગુજરાતીમાં મુદ્દાસર સારાંશ આપો.",
        "exercise": "છેલ્લી ચર્ચા મુજબના પાઠના સ્વાધ્યાયના પ્રશ્નો અને જવાબો સમજૂતી સાથે આપો.",
        "mcq": "છેલ્લી ચર્ચા મુજબના પાઠ આધારિત ગુજરાતીમાં ૫ MCQ બનાવો. ફોર્મેટ:\nપ્રશ્ન 1: પ્રશ્ન?\nA. ...\nB. ...\nC. ...\nD. ...\nસાચો જવાબ: B\nસમજૂતી: ...",
        "easy_example": "છેલ્લી ચર્ચા મુજબના વિષયનું વાસ્તવિક જીવનના સરળ ઉદાહરણો દ્વારા સમજાવો."
    }
    if quick_action == "mcq":
        st.session_state.update({"mcq_questions": None, "mcq_user_answers": {}, "mcq_checked": False})
    st.session_state.messages.append({"role": "user", "content": prompts[quick_action]})

# --- CHAT MESSAGES ---
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

# --- SHOW VOICE ERROR IF ANY ---
if st.session_state.voice_error:
    st.error(f"⚠️ {st.session_state.voice_error}")

# --- VOICE RECORDER IN MAIN PAGE ---
if st.session_state.mic_open:
    with st.container(border=True):
        st.markdown("🎙️ **માઈક પર દબાવી ગુજરાતીમાં બોલો, પૂરું થાય એટલે ⏹ દબાવો:**")
        audio_val = st.audio_input("રેકોર્ડ", key=f"mob_rec_{st.session_state.audio_counter}", label_visibility="collapsed")
        if st.button("❌ બંધ કરો", key="close_rec_btn"):
            st.session_state.mic_open = False
            st.rerun()
        if audio_val is not None:
            with st.spinner("🎧 ગુજરાતીમાં લખાઈ રહ્યું છે..."):
                spoken, err = transcribe_gujarati(audio_val, api_keys)
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
        try: t1.image(Image.open(io.BytesIO(attached.getvalue())), width=45)
        except Exception: t1.markdown("📎")
        t2.caption(f"📎 જોડાયેલ: {getattr(attached, 'name', 'ફોટો')}")
        if t3.button("❌", key="rm_att"):
            st.session_state.pop("bottom_uploader", None)
            st.session_state.pop("bottom_camera", None)
            st.rerun()

# --- BOTTOM BAR ---
with getattr(st, "bottom", st.container()):
    col_plus, col_in, col_mic, col_send = st.columns([1, 8, 1, 1], vertical_alignment="center")
    with col_plus:
        with st.popover("➕"):
            st.file_uploader("📁 ગેલેરી / PDF પસંદ કરો", key="bottom_uploader")
            st.camera_input("📸 કેમેરાથી ફોટો પાડો", key="bottom_camera")
    with col_in:
        user_text = st.text_input(
            "પ્રશ્ન...",
            value=st.session_state.draft_text,
            key=f"chat_box_{st.session_state.input_version}",
            placeholder="પ્રશ્ન લખો અથવા 🎤 દબાવો...",
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

# --- MANUAL SEND ONLY ---
if send_clicked and (user_text.strip() or attached):
    st.session_state.messages.append({"role": "user", "content": user_text.strip() or "[ફાઈલ સંલગ્ન છે]"})
    st.session_state.draft_text = ""
    st.session_state.voice_error = ""
    st.session_state.input_version += 1
    st.session_state.mic_open = False
    st.rerun()

# --- AI RESPONSE STREAMING ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    clean_q = st.session_state.messages[-1]["content"].strip()
    with st.chat_message("assistant"):
        if not HAS_GENAI or not api_keys:
            st.error("⚠️ Secrets માં GEMINI_API_KEY દાખલ કરો.")
        else:
            mode_inst = (
                "વિદ્યાર્થીના પ્રશ્ન, આગળની વાતચીત કે ફોટો પરથી ધોરણ (3 થી 8) અને વિષય સમજીને તરત જ સરળ ગુજરાતીમાં સંપૂર્ણ જવાબ આપો. "
                "જો ફક્ત અધૂરો પ્રશ્ન પૂછે (જેમ કે 'પાઠ 2 સમજાવો' જેમાં ધોરણ અને વિષય સ્પષ્ટ ન હોય), તો નમ્રતાથી પૂછો કે કયા ધોરણ (3 થી 8) અને કયા વિષયના પાઠ વિશે જાણવું છે.\n"
                f"GCERT સત્તાવાર અનુક્રમણિકા:\n{ALL_GRADES_REF}"
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