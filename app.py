import streamlit as st
import json
import os
import io
from PIL import Image

try:
    from google import genai
    from google.genai import types
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

st.set_page_config(
    page_title="ધોરણ ૮ ગુજરાતી માધ્યમ - સ્માર્ટ AI શિક્ષક",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)

@st.cache_data
def load_syllabus():
    syllabus_path = "diksha_syllabus.json"
    if os.path.exists(syllabus_path):
        with open(syllabus_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

syllabus_data = load_syllabus()

st.markdown("""
<style>
    /* Unified single-row bottom bar styling */
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
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.image("https://img.icons8.com/color/96/school.png", width=70)
    st.markdown("### 🎓 સ્માર્ટ AI શિક્ષક")
    st.markdown("ગુજરાત રાજ્ય શાળા પાઠ્યપુસ્તક મંડળ (GCERT) અને **DIKSHA** આધારિત ધોરણ ૮.")
    st.divider()
    
    api_key = st.secrets.get("GEMINI_API_KEY", "") if hasattr(st, "secrets") else ""
    if not api_key:
        api_key = os.environ.get("GEMINI_API_KEY", "")
    
    user_api_key = st.text_input("🔑 Gemini API Key દાખલ કરો:", value=api_key, type="password")
    if user_api_key:
        os.environ["GEMINI_API_KEY"] = user_api_key
    
    st.divider()
    model_choice = st.selectbox(
        "🤖 AI મોડેલ પસંદ કરો:",
        ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-1.5-flash"],
        index=0
    )
    
    st.divider()
    
    if syllabus_data:
        subject_names = list(syllabus_data.keys())
        selected_subject_name = st.selectbox("📖 વિષય પસંદ કરો:", subject_names)
        subject_info = syllabus_data[selected_subject_name]
        chapters = subject_info.get("chapters", [])
        chapter_names = [ch["name"] for ch in chapters]
        
        selected_chapter_name = st.selectbox("📑 પ્રકરણ પસંદ કરો:", ["બધા પ્રકરણો / સામાન્ય પ્રશ્ન"] + chapter_names)
        
        selected_chapter_obj = None
        if selected_chapter_name != "બધા પ્રકરણો / સામાન્ય પ્રશ્ન":
            for ch in chapters:
                if ch["name"] == selected_chapter_name:
                    selected_chapter_obj = ch
                    break
    else:
        selected_subject_name = None
        selected_chapter_obj = None
        st.warning("⚠️ diksha_syllabus.json ફાઈલ મળી નથી.")

    st.divider()
    st.markdown("### 🛠️ ક્વિક સ્ટડી ટૂલ્સ")
    quick_action = None
    col_q1, col_q2 = st.columns(2)
    with col_q1:
        if st.button("📖 સારાંશ"): quick_action = "summary"
        if st.button("🎯 MCQ ટેસ્ટ"): quick_action = "mcq"
        if st.button("📐 સૂત્રો/વ્યાકરણ"): quick_action = "formulas"
    with col_q2:
        if st.button("📝 સ્વાધ્યાય"): quick_action = "exercise"

st.markdown('<div class="main-header">📚 ધોરણ ૮ ગુજરાતી માધ્યમ - સ્માર્ટ AI શિક્ષક</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">તમારા બધા જ વિષયોના પ્રશ્નો, સ્વાધ્યાય ઉકેલ, અને માર્ગદર્શન માટેનો ડિજિટલ સાથી.</div>', unsafe_allow_html=True)

if "messages" not in st.session_state:
    st.session_state.messages = []

if selected_subject_name:
    ch_text = f" | પ્રકરણ: **{selected_chapter_obj['name']}**" if selected_chapter_obj else ""
    st.info(f"📌 વર્તમાન વિષય: **{selected_subject_name}**{ch_text}")

client = None
if HAS_GENAI and (user_api_key or os.environ.get("GEMINI_API_KEY")):
    try:
        client = genai.Client(api_key=user_api_key or os.environ.get("GEMINI_API_KEY"))
    except Exception as e:
        st.error(f"❌ Gemini Client Error: {e}")

if quick_action and selected_subject_name:
    prompt_map = {
        "summary": f"{selected_subject_name} ના પ્રકરણ '{selected_chapter_obj['name'] if selected_chapter_obj else 'આખા અભ્યાસક્રમ'}' નો સરસ અને સરળ ગુજરાતીમાં મુદ્દાસર સારાંશ આપો.",
        "exercise": f"{selected_subject_name} ના પ્રકરણ '{selected_chapter_obj['name'] if selected_chapter_obj else 'આ અભ્યાસક્રમ'}' ના સ્વાધ્યાયના પ્રશ્નો અને તેના સાચા જવાબો સમજૂતી સાથે આપો.",
        "mcq": f"{selected_subject_name} ના પ્રકરણ '{selected_chapter_obj['name'] if selected_chapter_obj else 'આ અભ્યાસક્રમ'}' આધારિત ૧૦ મહત્વના MCQ ગુજરાતીમાં બનાવો, જેમાં છેલ્લે સાચા જવાબોની યાદી પણ આપો.",
        "imp": f"{selected_subject_name} ના પ્રકરણ '{selected_chapter_obj['name'] if selected_chapter_obj else 'આ અભ્યાસક્રમ'}' માંથી વાર્ષિક પરીક્ષા માટે અતિ મહત્વના (IMP) પ્રશ્નો અને ઉત્તરો જણાવો.",
        "formulas": f"{selected_subject_name} ના પ્રકરણ '{selected_chapter_obj['name'] if selected_chapter_obj else 'આ અભ્યાસક્રમ'}' ના તમામ મહત્વના સૂત્રો, નિયમો અથવા વ્યાકરણના મુદ્દાઓની યાદી બનાવીને સમજાવો.",
        "nmms": f"{selected_subject_name} માટે NMMS સ્કોલરશીપ પરીક્ષામાં પૂછાઈ શકે તેવા મહત્વના પ્રશ્નો અને શોર્ટકટ ટ્રીક્સ ગુજરાતીમાં સમજાવો."
    }
    action_prompt = prompt_map.get(quick_action, "")
    if action_prompt:
        st.session_state.messages.append({"role": "user", "content": action_prompt})

# Render chat history messages first
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Bottom attachment preview badge above bottom bar
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

# Unified single-row bottom bar inside st.bottom
if "input_counter" not in st.session_state:
    st.session_state.input_counter = 0

bottom_container = getattr(st, "bottom", st.container())
with bottom_container:
    col_plus, col_input, col_send = st.columns([1, 10, 1.5], vertical_alignment="center")
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
તમે ગુજરાત રાજ્ય શાળા પાઠ્યપુસ્તક મંડળ (GCERT) અભ્યાસક્રમ આધારિત ધોરણ ૮ (ગુજરાતી માધ્યમ) ના નિષ્ણાત અને મૈત્રીપૂર્ણ AI શિક્ષક છો.
વિદ્યાર્થીઓને હંમેશા સરળ, સ્પષ્ટ અને સચોટ ગુજરાતી ભાષામાં સ્ટેપ-બાય-સ્ટેપ સમજૂતી આપો.
વર્તમાન પસંદ કરેલ વિષય: {selected_subject_name if selected_subject_name else 'સામાન્ય'}
પ્રકરણ: {selected_chapter_obj['name'] if selected_chapter_obj else 'કોઈપણ'}
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
                                contents.append("[અપલોડ કરેલી PDF ફાઈલ સંલગ્ન છે]")
                            else:
                                try:
                                    contents.append(Image.open(io.BytesIO(file_bytes)))
                                except Exception:
                                    contents.append("[અપલોડ કરેલી ફાઈલ સંલગ્ન છે]")
                        except Exception as file_err:
                            contents.append(f"[ફાઈલ જોડવામાં ભૂલ: {file_err}]")
                    
                    # Clear attachment after sending
                    st.session_state.pop("bottom_uploader", None)
                    st.session_state.pop("bottom_camera", None)
                    
                    history_text = ""
                    for msg in st.session_state.messages[:-1]:
                        history_text += f"{'વિદ્યાર્થી' if msg['role'] == 'user' else 'શિક્ષક'}: {msg['content']}\n"
                    
                    full_prompt = f"{system_instruction}\n\nઇતિહાસ:\n{history_text}\nપ્રશ્ન: {last_user_msg}"
                    contents.append(full_prompt)
                    
                    available_models = [model_choice] + [m for m in ["gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-1.5-flash"] if m != model_choice]
                    stream_obj = None
                    last_error = None
                    success = False
                    
                    for cur_model in available_models:
                        try:
                            stream_obj = client.models.generate_content_stream(
                                model=cur_model,
                                contents=contents
                            )
                            success = True
                            if cur_model != model_choice:
                                st.info(f"ℹ️ Model '{model_choice}' was busy/unavailable. Automatically switched to '{cur_model}'.")
                            break
                        except Exception as err:
                            last_error = err
                            err_str = str(err)
                            if "503" in err_str or "429" in err_str or "404" in err_str or "UNAVAILABLE" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                                continue
                            else:
                                raise err
                    
                    if not success:
                        raise last_error
                    
                    def response_generator():
                        for chunk in stream_obj:
                            if chunk.text:
                                yield chunk.text
                    
                    answer_text = st.write_stream(response_generator())
                    st.session_state.messages.append({"role": "assistant", "content": answer_text})
                except Exception as e:
                    err_msg = f"❌ AI જવાબ મેળવવામાં ભૂલ આવી: {e}"
                    st.error(err_msg)
                    st.session_state.messages.append({"role": "assistant", "content": err_msg})


        if st.button("⭐ IMP પ્રશ્નો"): quick_action = "imp"
        if st.button("🚀 NMMS પ્રેક્ટિસ"): quick_action = "nmms"
