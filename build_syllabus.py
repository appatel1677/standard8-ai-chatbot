import json

with open(r"c:\Users\win10\Desktop\standard8chatbot\diksha_syllabus_raw.json", "r", encoding="utf-8") as f:
    raw = json.load(f)

# Organize into clean Gujarati Medium subject structure
subjects = {
    "📐 ગણિત (Mathematics)": {
        "icon": "📐",
        "code": "math",
        "diksha_books": ["ગણિત ધોરણ ૮"],
        "chapters": []
    },
    "🔬 વિજ્ઞાન (Science)": {
        "icon": "🔬",
        "code": "science",
        "diksha_books": ["વિજ્ઞાન ધોરણ ૮"],
        "chapters": []
    },
    "🌍 સામાજિક વિજ્ઞાન (Social Science)": {
        "icon": "🌍",
        "code": "social_science",
        "diksha_books": ["સામાજિક વિજ્ઞાન ધોરણ ૮"],
        "chapters": []
    },
    "📖 ગુજરાતી (Gujarati)": {
        "icon": "📖",
        "code": "gujarati",
        "diksha_books": ["ગુજરાતી ધોરણ ૮ - પ્રથમ સત્ર", "ગુજરાતી ધોરણ ૮ - દ્વિતીય સત્ર"],
        "chapters": []
    },
    "🔤 અંગ્રેજી (English)": {
        "icon": "🔤",
        "code": "english",
        "diksha_books": ["અંગ્રેજી (દ્વિતીય ભાષા) ધોરણ ૮ - પ્રથમ સત્ર", "અંગ્રેજી (દ્વિતીય ભાષા) ધોરણ ૮ - દ્વિતીય સત્ર"],
        "chapters": []
    },
    "🇮🇳 હિન્દી (Hindi)": {
        "icon": "🇮🇳",
        "code": "hindi",
        "diksha_books": ["हिन्दी (द्वितीय भाषा) कक्षा 8 - प्रथम सत्र", "हिन्दी (द्वितीय भाषा) कक्षा 8 - द्वितीय सत्र"],
        "chapters": []
    },
    "🕉️ સંસ્કૃત (Sanskrit)": {
        "icon": "🕉️",
        "code": "sanskrit",
        "diksha_books": ["સંસ્કૃત ધોરણ ૮ - પ્રથમ સત્ર", "સંસ્કૃત ધોરણ ૮ - દ્વિતીય સત્ર"],
        "chapters": []
    },
    "🧮 વૈદિક ગણિત (Vedic Maths)": {
        "icon": "🧮",
        "code": "vedic_math",
        "diksha_books": ["વૈદિક ગણિત ધોરણ 8"],
        "chapters": []
    },
    "🎨 સર્વાંગી શિક્ષણ (Allround Education)": {
        "icon": "🎨",
        "code": "allround",
        "diksha_books": ["સર્વાંગી શિક્ષણ ધોરણ ૮"],
        "chapters": []
    },
}

for subj_name, meta in subjects.items():
    for book_title in meta["diksha_books"]:
        book_data = raw.get(book_title, {})
        sem_label = ""
        if "પ્રથમ સત્ર" in book_title or "प्रथम सत्र" in book_title:
            sem_label = "સત્ર ૧: "
        elif "દ્વિતીય સત્ર" in book_title or "द्वितीय सत्र" in book_title:
            sem_label = "સત્ર ૨: "
        for ch in book_data.get("chapters", []):
            ch_name = ch.get("name", "").strip()
            display_name = f"{sem_label}{ch_name}" if sem_label else ch_name
            meta["chapters"].append({
                "name": display_name,
                "raw_name": ch_name,
                "book": book_title,
                "id": ch.get("id", ""),
                "pdfs": ch.get("pdfs", [])
            })

with open(r"c:\Users\win10\Desktop\standard8chatbot\diksha_syllabus.json", "w", encoding="utf-8") as f:
    json.dump(subjects, f, ensure_ascii=False, indent=2)

for s, m in subjects.items():
    print(f"{s}: {len(m['chapters'])} chapters")
    for ch in m["chapters"]:
        print(f"   - {ch['name']} (PDFs: {len(ch['pdfs'])})")
