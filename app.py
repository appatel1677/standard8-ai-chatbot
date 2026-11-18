import streamlit as st
import json, os, re, hashlib

try:
    from fpdf import FPDF
    HAS_FPDF = True
except ImportError:
    HAS_FPDF = False

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

st.set_page_config(page_title="Standard 3 to 8 Smart AI Palaj Teacher", page_icon="📚",
                   layout="wide", initial_sidebar_state="collapsed")

CHAT_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-3.5-flash-lite"]
TRANSCRIBE_MODELS = ["gemini-2.5-flash-lite", "gemini-2.5-flash"]


# ---------------------------------------------------------------- HELPERS
def parse_mcq(text):
    text = text.replace("*", "").replace("#", "")
    questions = []
    for part in re.split(r"\n?\s*પ્રશ્ન\s*\d+\s*[:.\-)]", text)[1:]:
        lines = [l.strip() for l in part.strip().splitlines() if l.strip()]
        if not lines:
            continue
        q_text, options, answer, explanation = lines[0], {}, None, ""
        for l in lines[1:]:
            if re.match(r"^(સમજૂતી|Explanation)", l):
                explanation = re.sub(r"^(સમજૂતી|Explanation)\s*[:.\-]?\s*", "", l)
            elif m := re.match(r"^([ABCD])\s*[\).:]\s*(.*)", l):
                options[m.group(1)] = m.group(2)
            elif re.search(r"જવાબ|Answer", l) and (ma := re.search(r"(?:જવાબ|Answer)[^ABCD]*([ABCD])", l)):
                answer = ma.group(1)
        if q_text and len(options) >= 2 and answer:
            questions.append({"question": q_text, "options": options, "answer": answer, "explanation": explanation})
    return questions


@st.cache_resource
def get_pdf_font():
    for p in ["C:/Windows/Fonts/Nirmala.ttf", "C:/Windows/Fonts/Shruti.ttf",
              "/usr/share/fonts/truetype/noto/NotoSansGujarati-Regular.ttf", "NotoSansGujarati-Regular.ttf"]:
        if os.path.exists(p):
            return p
    try:
        import urllib.request
        urllib.request.urlretrieve(
            "https://github.com/google/fonts/raw/main/ofl/notosansgujarati/NotoSansGujarati%5Bwdth%2Cwght%5D.ttf",
            "NotoSansGujarati-Regular.ttf")
        return "NotoSansGujarati-Regular.ttf"
    except Exception:
        return None


def build_pdf_bytes(messages):
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    try:
        pdf.set_text_shaping(True)
    except Exception:
        pass
    font_path = get_pdf_font()
    base_font = "Gujarati" if font_path else "helvetica"
    if font_path:
        pdf.add_font("Gujarati", "", font_path)
        pdf.add_font("Gujarati", "B", font_path)
    pdf.add_page()
    pdf.set_font(base_font, "B", 15)
    pdf.cell(0, 10, "Smart AI Palaj Teacher - Notes", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(4)
    for m in messages:
        pdf.set_font(base_font, "B", 11)
        pdf.cell(0, 7, ("વિદ્યાર્થી:" if m["role"] == "user" else "શિક્ષક:"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(base_font, "", 10)
        pdf.multi_cell(0, 6, re.sub(r"[*#`$]", "", m["content"]))
        pdf.ln(2)
    return bytes(pdf.output())


def transcribe_gujarati(audio_file, api_keys):
    """(text, error) પાછું આપે છે — error હવે છુપાતી નથી."""
    if not HAS_GENAI:
        return "", "google-genai ઇન્સ્ટોલ નથી"
    if not api_keys:
        return "", "GEMINI_API_KEY મળી નથી"
    data = audio_file.getvalue()
    if len(data) < 2000:
        return "", "રેકોર્ડિંગ ખૂબ ટૂંકું છે, ફરી બોલો"
    mime = (getattr(audio_file, "type", None) or "audio/wav").split(";")[0]
    prompt = "આ ઓડિયોમાં વિદ્યાર્થી જે બોલ્યા છે તે ફક્ત ગુજરાતી લિપિમાં લખો. બીજું કોઈ વધારાનું લખાણ લખશો નહીં."
    last_err = "અજાણી સમસ્યા"
    for key in api_keys:
        client = genai.Client(api_key=key)
        for mod in TRANSCRIBE_MODELS:
            try:
                resp = client.models.generate_content(
                    model=mod,
                    contents=[types.Part.from_bytes(data=data, mime_type=mime), prompt])
                txt = (resp.text or "").strip()
                if txt:
                    return txt, ""
                last_err = "અવાજ સ્પષ્ટ ન સંભળાયો"
            except Exception as e:
                last_err = str(e)[:160]
                if "429" in last_err or "RESOURCE_EXHAUSTED" in last_err:
                    break
    return "", last_err


@st.cache_data
def load_syllabus():
    if os.path.exists("diksha_syllabus.json"):
        with open("diksha_syllabus.json", "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


syllabus_data = load_syllabus()
ALL_GRADES_REF = "\n".join(
    f"[{g}] " + " | ".join(
        f"{s}: {', '.join(c['name'] for c in info.get('chapters', []))}"
        for s, info in d.get("subjects", {}).items())
    for g, d in syllabus_data.items() if isinstance(d, dict) and d.get("subjects")
)


def read_api_keys():
    raw = ""
    try:
        raw = st.secrets.get("GEMINI_API_KEYS") or st.secrets.get("GEMINI_API_KEY") or ""
    except Exception:
        raw = ""
    raw = raw or os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
    return [k.strip().strip("\"'") for k in str(raw).split(",") if k.strip()]


# ---------------------------------------------------------------- CSS
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Gujarati:wght@400;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"], .main {
    max-width: 100vw !important;
    overflow-x: hidden !important;
    font-family: 'Noto Sans Gujarati', sans-serif !important;
}
p, h1, h2, h3, input, textarea, button, .stMarkdown {
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
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: #EFF6FF !important;
    border-left: 4px solid #3B82F6 !important;
    border-radius: 14px !important;
    padding: 0.6rem 0.9rem !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
    background: #F0FDF4 !important;
    border-left: 4px solid #10B981 !important;
    border-radius: 14px !important;
    padding: 0.6rem 0.9rem !important;
}

/* BOTTOM BAR */
[data-testid="stBottom"] {
    padding: 0.4rem 0.5rem !important;
    background: rgba(255, 255, 255, 0.95) !important;
    z-index: 99999 !important;
}
[data-testid="stBottom"] > div {
    max-width: 820px !important;
    margin: 0 auto !important;
    padding: 0 !important;
}
[data-testid="stBottom"] [data-testid="stHorizontalBlock"] {
    display: grid !important;
    grid-template-columns: 36px minmax(0, 1fr) 36px 36px !important;
    align-items: center !important;
    gap: 5px !important;
    background: #1f2937 !important;
    border: 1px solid #374151 !important;
    border-radius: 999px !important;
    padding: 5px 7px !important;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25) !important;
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
    background: #ffffff !important;
    color: #111827 !important;
    -webkit-text-fill-color: #111827 !important;
    caret-color: #111827 !important;
    border-radius: 999px !important;
    border: none !important;
    padding: 6px 12px !important;
    font-size: 0.95rem !important;
}
[data-testid="stBottom"] input[type="text"]::placeholder {
    color: #6B7280 !important;
    -webkit-text-fill-color: #6B7280 !important;
}
[data-testid="stBottom"] div[data-baseweb="input"] {
    background: #ffffff !important;
    border-radius: 999px !important;
    border: none !important;
}
[data-testid="stBottom"] [data-testid="InputInstructions"],
[data-testid="stBottom"] [data-testid="stPopover"] svg {
    display: none !important;
}
[data-testid="stBottom"] button {
    border-radius: 50% !important;
    width: 36px !important;
    height: 36px !important;
    min-height: 36px !important;
    padding: 0 !important;
    border: none !important;
    color: #ffffff !important;
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
}
[data-testid="stBottom"] [data-testid="stPopover"] > button {
    background: #374151 !important;
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

# ---------------------------------------------------------------- SESSION STATE
defaults = {
    "messages": [], "mcq_questions": None, "mcq_test_id": 0, "mcq_checked": False,
    "want_mcq": False, "draft_text": "", "audio_counter": 0, "input_version": 0,
    "last_audio_id": None, "mic_error": "", "att_ver": 0, "pending_att": None, "failed_at": -1,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

api_keys = read_api_keys()

# ---------------------------------------------------------------- SIDEBAR
quick_action = None
with st.sidebar:
    st.markdown("### 🎓 સ્માર્ટ AI શિક્ષક")
    model_choice = st.selectbox("🤖 AI મોડેલ:", CHAT_MODELS)

    st.markdown("### 🛠️ ક્વિક ટૂલ્સ")
    c1, c2 = st.columns(2)
    if c1.button("📖 સારાંશ", key="sb_summary"): quick_action = "summary"
    if c1.button("📝 MCQ ટેસ્ટ", key="sb_mcq"): quick_action = "mcq"
    if c2.button("📝 સ્વાધ્યાય", key="sb_exercise"): quick_action = "exercise"
    if c2.button("💡 ઉદાહરણ", key="sb_example"): quick_action = "easy_example"

    st.divider()
    if st.button("🗑️ નવી ચેટ", use_container_width=True):
        for k, v in defaults.items():
            if k not in ("audio_counter", "att_ver", "input_version"):
                st.session_state[k] = v
        st.session_state.audio_counter += 1
        st.session_state.att_ver += 1
        st.session_state.input_version += 1
        st.rerun()

    if st.session_state.messages:
        dl_fmt = st.selectbox("ફોર્મેટ", [".pdf", ".txt", ".md"])
        if dl_fmt == ".pdf":
            if HAS_FPDF:
                try:
                    st.download_button("📥 નોટ્સ ડાઉનલોડ", data=build_pdf_bytes(st.session_state.messages),
                                       file_name="notes.pdf", mime="application/pdf", use_container_width=True)
                except Exception:
                    st.caption("⚠️ PDF બની નથી, .txt પસંદ કરો.")
            else:
                st.caption("⚠️ fpdf2 ઇન્સ્ટોલ નથી, .txt પસંદ કરો.")
        else:
            txt_data = "\n\n".join(
                f"{'વિદ્યાર્થી' if m['role'] == 'user' else 'શિક્ષક'}: {m['content']}"
                for m in st.session_state.messages)
            st.download_button("📥 નોટ્સ ડાઉનલોડ", data=txt_data.encode("utf-8"),
                               file_name=f"notes{dl_fmt}", mime="text/plain", use_container_width=True)

# ---------------------------------------------------------------- HEADER
st.markdown('<div class="slim-header">📚 standard 3 to 8 smart AI palaj teacher</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------- BOTTOM BAR (➕ | ટેક્સ્ટ | 🎤 | ➤)
# st.bottom સ્ક્રીનની નીચે ચોંટેલું રહે છે; કોડમાં તેને પહેલા દોરવાથી ફાઈલ/ઓડિયો તરત મળે છે.
with getattr(st, "bottom", st.container()):
    col_plus, col_in, col_mic, col_send = st.columns([1, 8, 1, 1], vertical_alignment="center")
    with col_plus:
        with st.popover("➕"):
            up_file = st.file_uploader("📁 ગેલેરી / PDF પસંદ કરો", type=["png", "jpg", "jpeg", "pdf"],
                                       key=f"up_{st.session_state.att_ver}")
            cam_file = st.camera_input("📸 કેમેરાથી ફોટો પાડો", key=f"cam_{st.session_state.att_ver}")
    with col_in:
        user_text = st.text_input(
            "પ્રશ્ન...", value=st.session_state.draft_text,
            key=f"chat_box_{st.session_state.input_version}",
            placeholder="પ્રશ્ન લખો અથવા 🎤 દબાવો...", label_visibility="collapsed")
        st.session_state.draft_text = user_text
    with col_mic:
        with st.popover("🎤"):
            st.caption("🎙️ માઈક દબાવી ગુજરાતીમાં બોલો, પૂરું થાય એટલે ⏹ દબાવો")
            audio_val = st.audio_input("રેકોર્ડ", key=f"rec_{st.session_state.audio_counter}",
                                       label_visibility="collapsed")
    with col_send:
        send_clicked = st.button("➤", type="primary", key="real_send_btn", help="મોકલો")

attached = up_file or cam_file

# ---------------------------------------------------------------- ATTACHMENT PREVIEW
if attached:
    with st.container(border=True):
        t1, t2, t3 = st.columns([1, 6, 1])
        if (getattr(attached, "type", "") or "").startswith("image"):
            t1.image(attached.getvalue(), width=45)
        else:
            t1.markdown("📄")
        t2.caption(f"📎 જોડાયેલ: {getattr(attached, 'name', 'ફોટો')}")
        if t3.button("❌", key="rm_att"):
            st.session_state.att_ver += 1
            st.rerun()

if st.session_state.mic_error:
    st.warning(f"⚠️ અવાજ લખી શકાયો નહીં: {st.session_state.mic_error}")

# ---------------------------------------------------------------- VOICE → ટેક્સ્ટ બોક્સમાં
if audio_val is not None:
    aid = hashlib.md5(audio_val.getvalue()).hexdigest()
    if aid != st.session_state.last_audio_id:
        st.session_state.last_audio_id = aid
        with st.spinner("🎧 ગુજરાતીમાં લખાઈ રહ્યું છે..."):
            spoken, err = transcribe_gujarati(audio_val, api_keys)
        st.session_state.audio_counter += 1
        if spoken:
            existing = st.session_state.draft_text.strip()
            st.session_state.draft_text = f"{existing} {spoken}".strip() if existing else spoken
            st.session_state.input_version += 1
            st.session_state.mic_error = ""
        else:
            st.session_state.mic_error = err
        st.rerun()

# ---------------------------------------------------------------- INPUT HANDLING
if quick_action:
    if not st.session_state.messages:
        st.toast("પહેલા કોઈ પાઠ/પ્રશ્ન પૂછો, પછી ક્વિક ટૂલ વાપરો 🙂")
    else:
        prompts = {
            "summary": "છેલ્લી ચર્ચા મુજબના પાઠનો સરળ ગુજરાતીમાં મુદ્દાસર સારાંશ આપો.",
            "exercise": "છેલ્લી ચર્ચા મુજબના પાઠના સ્વાધ્યાયના પ્રશ્નો અને જવાબો સમજૂતી સાથે આપો.",
            "mcq": ("છેલ્લી ચર્ચા મુજબના પાઠ આધારિત ગુજરાતીમાં ૫ MCQ બનાવો. બરાબર આ ફોર્મેટ રાખો:\n"
                    "પ્રશ્ન 1: પ્રશ્ન?\nA. ...\nB. ...\nC. ...\nD. ...\nસાચો જવાબ: B\nસમજૂતી: ..."),
            "easy_example": "છેલ્લી ચર્ચા મુજબના વિષયનું વાસ્તવિક જીવનના સરળ ઉદાહરણો દ્વારા સમજાવો.",
        }
        if quick_action == "mcq":
            st.session_state.update({"mcq_questions": None, "mcq_checked": False, "want_mcq": True})
        st.session_state.messages.append({"role": "user", "content": prompts[quick_action]})
        st.session_state.failed_at = -1

elif send_clicked and (user_text.strip() or attached):
    if attached:
        st.session_state.pending_att = {
            "data": attached.getvalue(),
            "mime": getattr(attached, "type", None) or "image/jpeg",
        }
        st.session_state.att_ver += 1
    st.session_state.messages.append({"role": "user", "content": user_text.strip() or "[ફાઈલ સંલગ્ન છે] આ સમજાવો."})
    st.session_state.draft_text = ""
    st.session_state.input_version += 1
    st.session_state.mic_error = ""
    st.session_state.failed_at = -1
    st.rerun()

# ---------------------------------------------------------------- CHAT MESSAGES
for m in st.session_state.messages:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# ---------------------------------------------------------------- AI RESPONSE
msgs = st.session_state.messages
if msgs and msgs[-1]["role"] == "user" and st.session_state.failed_at != len(msgs):
    clean_q = msgs[-1]["content"].strip()
    with st.chat_message("assistant"):
        if not HAS_GENAI or not api_keys:
            st.error("⚠️ Secrets માં GEMINI_API_KEY દાખલ કરો.")
            st.session_state.failed_at = len(msgs)
        else:
            mode_inst = (
                "વિદ્યાર્થીના પ્રશ્ન, આગળની વાતચીત કે ફોટો પરથી ધોરણ (3 થી 8) અને વિષય સમજીને તરત જ સરળ ગુજરાતીમાં સંપૂર્ણ જવાબ આપો. "
                "બાળકોને ગમે તેવી મૈત્રીપૂર્ણ ભાષા વાપરો. "
                "જો ફક્ત અધૂરો પ્રશ્ન પૂછે (જેમ કે 'પાઠ 2 સમજાવો' જેમાં ધોરણ અને વિષય સ્પષ્ટ ન હોય), તો નમ્રતાથી પૂછો કે કયા ધોરણ (3 થી 8) અને કયા વિષયના પાઠ વિશે જાણવું છે.\n"
                f"GCERT સત્તાવાર અનુક્રમણિકા:\n{ALL_GRADES_REF}"
            )
            sys_prompt = (f"તમે GCERT ધોરણ 3 થી 8 (ગુજરાતી માધ્યમ) ના નિષ્ણાત AI શિક્ષક છો.\n{mode_inst}\n"
                          "સરળ ગુજરાતીમાં જવાબ આપો. સૂત્રો $...$ માં લખો.")

            contents = []
            att = st.session_state.pending_att
            if att:
                contents.append(types.Part.from_bytes(data=att["data"], mime_type=att["mime"]))
            hist = "\n".join(
                f"{'વિદ્યાર્થી' if m['role'] == 'user' else 'શિક્ષક'}: {m['content']}"
                for m in msgs[:-1][-6:])
            contents.append(f"{sys_prompt}\n\n{hist}\nવિદ્યાર્થીનો પ્રશ્ન: {clean_q}")

            models = [model_choice] + [m for m in CHAT_MODELS if m != model_choice]
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
                        if not temp:
                            raise RuntimeError("ખાલી જવાબ")
                        placeholder.markdown(temp)
                        answer_text, success = temp, True
                        break
                    except Exception as e:
                        last_err = e
                        if any(x in str(e) for x in ["429", "RESOURCE_EXHAUSTED"]):
                            break
                if success:
                    break

            st.session_state.pending_att = None
            if success:
                st.session_state.messages.append({"role": "assistant", "content": answer_text})
                if st.session_state.want_mcq:
                    st.session_state.want_mcq = False
                    parsed = parse_mcq(answer_text)
                    if parsed:
                        st.session_state.mcq_questions = parsed
                        st.session_state.mcq_test_id += 1
                        st.session_state.mcq_checked = False
                    else:
                        st.toast("MCQ ફોર્મેટ ઓળખાયું નહીં, ફરી 'MCQ ટેસ્ટ' દબાવો.")
                st.rerun()
            else:
                placeholder.empty()
                st.session_state.want_mcq = False
                st.session_state.failed_at = len(msgs)
                st.error(f"❌ સર્વર વ્યસ્ત છે. ફરી પ્રયત્ન કરો. ({str(last_err)[:150]})")

if (st.session_state.failed_at == len(msgs) and msgs and msgs[-1]["role"] == "user"):
    if st.button("🔁 ફરી પ્રયત્ન કરો", key="retry_btn"):
        st.session_state.failed_at = -1
        st.rerun()

# ---------------------------------------------------------------- INTERACTIVE MCQ
if st.session_state.mcq_questions:
    st.divider()
    st.markdown(f"### 📝 MCQ ટેસ્ટ - {len(st.session_state.mcq_questions)} પ્રશ્નો")
    tid = st.session_state.mcq_test_id
    answers = {}
    for i, q in enumerate(st.session_state.mcq_questions):
        st.markdown(f"**પ્રશ્ન {i + 1}:** {q['question']}")
        keys = list(q["options"].keys())
        labels = [f"{k}. {q['options'][k]}" for k in keys]
        choice = st.radio("વિકલ્પ પસંદ કરો:", labels, index=None, key=f"mcq_{tid}_{i}")
        answers[i] = choice[0] if choice else None

    b1, b2 = st.columns(2)
    if b1.button("🏆 સ્કોર તપાસો", key=f"chk_{tid}"):
        st.session_state.mcq_checked = True
    if b2.button("🔄 નવો ટેસ્ટ", key=f"new_{tid}"):
        st.session_state.update({"mcq_questions": None, "mcq_checked": False})
        st.rerun()

    if st.session_state.mcq_checked:
        total = len(st.session_state.mcq_questions)
        score = sum(1 for i, q in enumerate(st.session_state.mcq_questions) if answers.get(i) == q["answer"])
        st.success(f"🎯 તમારો સ્કોર: **{score} / {total}**")
        for i, q in enumerate(st.session_state.mcq_questions):
            ua, ca = answers.get(i), q["answer"]
            correct_opt = q["options"].get(ca, "")
            with st.container(border=True):
                st.markdown(f"**પ્રશ્ન {i + 1}:** " + ("✅ સાચો!" if ua == ca else f"❌ ખોટો! સાચો જવાબ: **{ca}. {correct_opt}**"))
                if q.get("explanation"):
                    st.caption(f"💡 સમજૂતી: {q['explanation']}")
