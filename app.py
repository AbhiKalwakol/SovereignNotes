import streamlit as st
import json
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timezone
from io import BytesIO

from PIL import Image
import pytesseract
from pypdf import PdfReader
from docx import Document

from ai_handler import AIModelManager
from database import (
    add_log,
    add_mood,
    add_mood_at,
    add_upload,
    authenticate,
    decrypt_database,
    decrypted_db_exists,
    delete_decrypted_db,
    delete_all_user_data,
    add_event,
    list_events,
    encrypt_database,
    encrypted_db_exists,
    get_setting,
    has_password,
    init_db,
    list_logs,
    list_moods,
    list_uploads,
    set_password,
    set_setting,
)
from pathlib import Path

st.set_page_config(page_title="AI Mood Dashboard", layout="centered")

def _ensure_session_defaults():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if "db_password" not in st.session_state:
        st.session_state.db_password = None

_ensure_session_defaults()

# Create three columns after a file uploader (to be used in main_dashboard)
def mood_dashboard_sections():
    st.markdown("---")
    col1, col2, col3 = st.columns(3)

    # Quotes for current mental state
    with col1:
        st.subheader("📝 Quotes for Current Mental State")
        st.write("> \"Keep your face always toward the sunshine—and shadows will fall behind you.\"")
        st.write("> \"This too shall pass.\"")
        st.write("> \"You are stronger than you know.\"")
    
    # Mood Analytics - Placeholder
    with col2:
        st.subheader("📊 Mood Analytics")
        st.info("Mood and mental health charts will appear here.")
        st.line_chart([1, 2, 3, 2, 4, 3, 5])
        st.bar_chart([3, 1, 4, 2, 5, 3, 4])

    # Schedule of upcoming/past events
    with col3:
        st.subheader("📅 Schedule")
        events = [
            {"date": "2024-06-03", "event": "Therapy Session"},
            {"date": "2024-06-07", "event": "Friend Meetup"},
            {"date": "2024-06-01", "event": "Morning Jog"},
        ]
        for e in events:
            st.markdown(f"**{e['date']}**: {e['event']}")

def login_screen():
    st.title("🔒 Secure Login")
    st.markdown("Enter your password to decrypt your encrypted database and access your dashboard.")
    pw = st.text_input("Password", type="password")
    login_btn = st.button("Login", type="primary")
    if login_btn and pw:
        # If we have an encrypted DB, decrypt it first. Wrong passwords will fail here.
        if encrypted_db_exists():
            ok = decrypt_database(pw)
            if not ok:
                st.session_state.authenticated = False
                st.session_state.db_password = None
                st.error("Wrong password (could not decrypt database).")
                return

        # Ensure schema exists in decrypted DB
        init_db()

        # Validate against stored hash (inside the decrypted DB)
        if authenticate(pw):
            st.session_state.db_password = pw
            st.session_state.authenticated = True
            # Migrate legacy plaintext DB to encrypted-at-rest on first successful login.
            if not encrypted_db_exists():
                encrypt_database(pw)
                decrypt_database(pw)
            st.success("Successfully logged in!")
            if hasattr(st, "rerun"):
                st.rerun()
            else:
                st.experimental_rerun()
        else:
            st.session_state.authenticated = False
            st.session_state.db_password = None
            st.error("Login failed. Please try again.")

def setup_password_screen():
    st.title("🔑 Set Up Your Password")
    st.markdown("No password is set yet. Create one now to secure and encrypt your database.")
    pw1 = st.text_input("New password", type="password")
    pw2 = st.text_input("Confirm password", type="password")
    create_btn = st.button("Create Password", type="primary")

    if create_btn:
        if not pw1 or not pw2:
            st.warning("Please fill both password fields.")
            return
        if pw1 != pw2:
            st.error("Passwords do not match.")
            return
        if len(pw1) < 6:
            st.warning("Please use a password of at least 6 characters.")
            return

        # Fresh DB setup (first run)
        init_db()
        set_password(pw1)
        st.session_state.authenticated = True
        st.session_state.db_password = pw1
        st.success("Password created. You’re now logged in.")
        # Encrypt immediately so the DB is protected at rest.
        encrypt_database(pw1)
        # After encrypting, decrypt again for the active session.
        decrypt_database(pw1)
        # Force a rerun so main render logic re-evaluates and shows dashboard
        if hasattr(st, "rerun"):
            st.rerun()
        else:
            st.experimental_rerun()

def lock_and_encrypt():
    pw = st.session_state.db_password
    if not pw:
        st.session_state.authenticated = False
        return
    encrypt_database(pw)
    delete_decrypted_db()
    st.session_state.authenticated = False
    st.session_state.db_password = None
    if hasattr(st, "rerun"):
        st.rerun()
    else:
        st.experimental_rerun()

def ai_model_setup_screen():
    st.title("🤖 AI Model Setup")
    st.markdown("Choose an AI mode. If you don’t configure cloud, the app will try local first.")

    mode = st.radio(
        "AI Mode",
        options=["Local (recommended)", "Cloud (OpenAI-compatible)"],
        index=0,
    )
    local_provider = st.selectbox(
        "Local provider",
        options=["Ollama (Llama models)", "Custom HTTP endpoint"],
        index=0,
        disabled=mode.startswith("Cloud"),
    )

    local_model = None
    if local_provider.startswith("Ollama"):
        local_endpoint = st.text_input(
            "Ollama base URL",
            value=get_setting("ai.local_endpoint") or "http://localhost:11434",
            disabled=mode.startswith("Cloud"),
        )
        probe_mgr = AIModelManager(local_endpoint=local_endpoint, local_provider="ollama")
        local_models = probe_mgr.list_local_models()
        if local_models:
            # Prefer previously saved model if present
            saved = get_setting("ai.local_model")
            idx = local_models.index(saved) if saved in local_models else 0
            local_model = st.selectbox(
                "Local model",
                options=local_models,
                index=idx,
                disabled=mode.startswith("Cloud"),
            )
        else:
            st.warning("Could not fetch models from Ollama. Make sure Ollama is running, then refresh.")
            local_model = st.text_input(
                "Local model name",
                value=get_setting("ai.local_model") or "llama3",
                disabled=mode.startswith("Cloud"),
            )
    else:
        local_endpoint = st.text_input(
            "Local endpoint",
            value=get_setting("ai.local_endpoint") or "http://localhost:8000/llm",
            disabled=mode.startswith("Cloud"),
        )
        local_model = st.text_input(
            "Local model (optional)",
            value=get_setting("ai.local_model") or "",
            disabled=mode.startswith("Cloud"),
        )
    cloud_api_key = None
    cloud_endpoint = "https://api.openai.com/v1/chat/completions"
    cloud_model = "gpt-4o-mini"

    if mode.startswith("Cloud"):
        cloud_endpoint = st.text_input("Cloud endpoint", value=cloud_endpoint)
        cloud_model = st.text_input("Cloud model", value=cloud_model)
        cloud_api_key = st.text_input("Cloud API key", type="password")

    if st.button("Save AI Settings", type="primary"):
        set_setting("ai.mode", "cloud" if mode.startswith("Cloud") else "local")
        set_setting("ai.local_provider", "ollama" if local_provider.startswith("Ollama") else "custom")
        set_setting("ai.local_endpoint", local_endpoint)
        if local_model is not None:
            set_setting("ai.local_model", local_model)
        set_setting("ai.cloud_endpoint", cloud_endpoint)
        set_setting("ai.cloud_model", cloud_model)
        if cloud_api_key:
            # NOTE: this stores the key in the encrypted DB; it's still sensitive.
            set_setting("ai.cloud_api_key", cloud_api_key)
        st.success("AI settings saved.")
        if hasattr(st, "rerun"):
            st.rerun()
        else:
            st.experimental_rerun()

def _get_ai_manager() -> AIModelManager:
    local_endpoint = get_setting("ai.local_endpoint") or "http://localhost:11434"
    local_provider = get_setting("ai.local_provider") or "ollama"
    local_model = get_setting("ai.local_model")
    cloud_endpoint = get_setting("ai.cloud_endpoint") or "https://api.openai.com/v1/chat/completions"
    cloud_api_key = get_setting("ai.cloud_api_key")
    return AIModelManager(
        local_endpoint=local_endpoint,
        local_provider=local_provider,
        local_model=local_model,
        cloud_endpoint=cloud_endpoint,
        cloud_api_key=cloud_api_key,
    )

def _ai_extract_points(manager: AIModelManager, text: str):
    """
    Minimal "extraction" step: ask the model for a small JSON summary.
    If AI isn't available, fall back to a simple heuristic structure.
    """
    prompt = (
        "Extract structured information from the user's material.\n\n"
        "Return STRICT JSON with keys:\n"
        "- mood (string|null)\n"
        "- mood_score (1-5|null)\n"
        "- topics (array of strings)\n"
        "- action_items (array of strings)\n"
        "- summary (string)\n"
        "- events (array of objects {date: string|null, title: string, details: string|null})\n"
        "- mood_entries (array of objects {date: string, mood_score: 1-5, mood: string|null})\n\n"
        "Rules:\n"
        "- If the text mentions dates like 'yesterday', 'tomorrow', or 'on March 5', resolve them to ISO date strings.\n"
        "- If no reliable date can be inferred for a mood mention, do not add it to mood_entries.\n"
        "- Prefer YYYY-MM-DD for dates; include time only if explicitly mentioned.\n\n"
        f"Material:\n{text}"
    )
    resp = manager.generate(prompt, max_tokens=256)
    if isinstance(resp, dict) and resp.get("error"):
        return None, None
    # Keep raw response JSON as string for storage/debugging
    return resp.get("source"), json.dumps(resp.get("result"), ensure_ascii=False)

def _extract_text_from_upload(uploaded_file):
    """
    Returns (extracted_text, warnings:list[str])
    """
    warnings = []
    name = uploaded_file.name
    mime = uploaded_file.type
    ext = Path(name).suffix.lower()
    data = uploaded_file.getvalue()

    if ext == ".txt" or (mime and mime.startswith("text/")):
        try:
            return data.decode("utf-8"), warnings
        except Exception:
            return data.decode("utf-8", errors="replace"), ["Text decode used replacement characters."]

    if ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"]:
        try:
            img = Image.open(BytesIO(data))
            text = pytesseract.image_to_string(img)
            if not text.strip():
                warnings.append("OCR returned empty text (image may not contain readable text).")
            return text, warnings
        except pytesseract.TesseractNotFoundError:
            warnings.append("Tesseract OCR is not installed or not on PATH. Install Tesseract to OCR images.")
            return None, warnings
        except Exception as e:
            warnings.append(f"OCR failed: {e}")
            return None, warnings

    if ext == ".pdf" or mime == "application/pdf":
        try:
            reader = PdfReader(BytesIO(data))
            parts = []
            for page in reader.pages:
                parts.append(page.extract_text() or "")
            text = "\n\n".join(parts).strip()
            if not text:
                warnings.append("PDF text extraction returned empty (may be scanned; try OCR after converting pages to images).")
            return text, warnings
        except Exception as e:
            warnings.append(f"PDF extraction failed: {e}")
            return None, warnings

    if ext == ".docx" or mime in [
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]:
        try:
            doc = Document(BytesIO(data))
            text = "\n".join(p.text for p in doc.paragraphs).strip()
            if not text:
                warnings.append("DOCX extraction returned empty.")
            return text, warnings
        except Exception as e:
            warnings.append(f"DOCX extraction failed: {e}")
            return None, warnings

    warnings.append(f"No extractor for file type: {ext or mime}")
    return None, warnings

def _normalize_ai_result(ai_source: str | None, ai_json_str: str | None):
    """
    Convert stored raw AI result into a parsed dict if possible.
    Supports:
    - Ollama: raw contains {"response": "<json string>"} or {"response": "..."}
    - OpenAI chat: raw contains {"choices":[{"message":{"content":"<json>"}}]}
    Returns dict|None
    """
    if not ai_json_str:
        return None
    try:
        raw = json.loads(ai_json_str)
    except Exception:
        return None

    # Ollama: sometimes response is the JSON string we asked for
    if isinstance(raw, dict) and "response" in raw and isinstance(raw["response"], str):
        try:
            return json.loads(raw["response"])
        except Exception:
            return {"raw_response": raw["response"]}

    # OpenAI chat completions
    try:
        content = raw["choices"][0]["message"]["content"]
        if isinstance(content, str):
            return json.loads(content)
    except Exception:
        pass

    return raw if isinstance(raw, dict) else None

def _apply_ai_decisions(source_type: str, source_id: int | None, extracted_text: str, ai_source: str | None, ai_json_str: str | None):
    """
    Use AI output (if parseable) to add calendar events and dated mood entries.
    """
    parsed = _normalize_ai_result(ai_source, ai_json_str)
    if not isinstance(parsed, dict):
        return

    # Expected optional structures:
    # - events: [{date: "YYYY-MM-DD"|"YYYY-MM-DDTHH:MM:SS", title: "...", details: "..."}]
    # - mood_entries: [{date: "...", mood_score: 1-5, mood: "HAPPY"}]
    events = parsed.get("events") or []
    if isinstance(events, list):
        for e in events:
            if not isinstance(e, dict):
                continue
            add_event(
                event_date=e.get("date"),
                title=e.get("title") or "Reminder",
                details=e.get("details"),
                source_type=source_type,
                source_id=source_id,
            )

    mood_entries = parsed.get("mood_entries") or []
    if isinstance(mood_entries, list):
        for m in mood_entries:
            if not isinstance(m, dict):
                continue
            dt = m.get("date")
            score = m.get("mood_score")
            if dt and score:
                try:
                    add_mood_at(dt, int(score), m.get("mood"))
                except Exception:
                    pass

def mood_checkin_ui():
    # Borrow the look/flow from your `ui_reference.jpg`
    st.markdown('<p style="text-align:center; color:#888; font-size:14px; font-weight:600; letter-spacing:1px; margin-bottom:-10px; text-transform:uppercase;">4th Check-in</p>', unsafe_allow_html=True)
    st.markdown('<p style="text-align:center; font-size:32px; font-weight:700; margin-bottom:18px; color:#222;">How are you today?</p>', unsafe_allow_html=True)

    cols = st.columns(5)
    moods = [
        ("😣", "AWFUL", 1),
        ("🙁", "BAD", 2),
        ("😐", "OKAY", 3),
        ("🙂", "GOOD", 4),
        ("😄", "GREAT", 5),
    ]
    for i, (emoji, name, score) in enumerate(moods):
        with cols[i]:
            if st.button(f"{emoji}\n{name}", use_container_width=True):
                add_mood(score, name)
                st.success(f"Recorded: {name}")
                if hasattr(st, "rerun"):
                    st.rerun()
                else:
                    st.experimental_rerun()

def mood_analysis_chart():
    st.subheader("Mood Analysis")
    st.write("**This week**")
    rows = list_moods(limit=30)
    if not rows:
        st.info("No mood data recorded yet.")
        return

    df = pd.DataFrame(rows, columns=["id", "created_at", "mood_score", "mood"])
    df["created_at"] = pd.to_datetime(df["created_at"])
    df = df.sort_values("created_at")
    df["day"] = df["created_at"].dt.strftime("%a").str.upper().str[:3]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["created_at"],
        y=df["mood_score"],
        mode="lines",
        line=dict(shape="spline", width=4, color="#A0D4C2"),
        hovertemplate="%{x|%a %b %d}<br>Score: %{y}<extra></extra>",
    ))

    colors_map = {1: "#5C73F2", 2: "#56B0D8", 3: "#F2C94C", 4: "#8BC34A", 5: "#4CAF50"}
    marker_colors = [colors_map.get(int(s), "#A0D4C2") for s in df["mood_score"]]
    fig.add_trace(go.Scatter(
        x=df["created_at"],
        y=df["mood_score"],
        mode="markers",
        marker=dict(size=16, color=marker_colors, line=dict(width=0)),
        hovertemplate="%{x|%a %b %d}<br>%{text}<extra></extra>",
        text=df["mood"].fillna(""),
    ))

    fig.update_layout(
        xaxis=dict(showgrid=False, fixedrange=True),
        yaxis=dict(
            showgrid=True,
            gridcolor="#EAEAEA",
            zeroline=False,
            showticklabels=False,
            range=[0.5, 5.5],
            fixedrange=True,
        ),
        plot_bgcolor="white",
        paper_bgcolor="white",
        showlegend=False,
        margin=dict(l=10, r=10, t=10, b=10),
        height=260,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

def main_dashboard():
    top = st.columns([1, 1, 1])
    with top[0]:
        st.title("Sovereign Notes")
    with top[2]:
        st.button("🔒 Lock & Encrypt", type="primary", on_click=lock_and_encrypt)

    with st.sidebar:
        st.subheader("Settings")
        st.caption("All data is stored locally in your user profile (not in this repo).")
        with st.expander("Danger zone"):
            st.warning("This will permanently delete your encrypted database and all logs/uploads/moods.")
            confirm = st.text_input("Type DELETE to confirm", value="")
            if st.button("Delete all data", type="primary"):
                if confirm.strip().upper() != "DELETE":
                    st.error("Confirmation text did not match.")
                else:
                    # Best effort: lock current session first (ensures connections close)
                    st.session_state.authenticated = False
                    st.session_state.db_password = None
                    ok = delete_all_user_data()
                    if ok:
                        st.success("All data deleted. Restarting...")
                        if hasattr(st, "rerun"):
                            st.rerun()
                        else:
                            st.experimental_rerun()
                    else:
                        st.error("Could not delete database files (they may be locked). Close other app instances and try again.")

    st.markdown("---")

    # Mood check-in + chart
    mood_checkin_ui()
    st.markdown("---")
    mood_analysis_chart()
    st.markdown("---")

    # --- Calendar / reminders ---
    st.subheader("📅 Calendar & Reminders")
    upcoming = list_events(limit=20, upcoming_only=True)
    if not upcoming:
        st.info("No reminders yet. Add logs/uploads with dates (or run AI) to generate them.")
    else:
        for (eid, created_at, event_date, title, details, source_type, source_id) in upcoming:
            label = f"{event_date or created_at} — {title}"
            with st.expander(label):
                if details:
                    st.write(details)
                st.caption(f"Source: {source_type} #{source_id}" if source_type else "Source: (unknown)")

    st.markdown("---")

    # --- File Uploader ---
    st.header("Upload (images, PDF, TXT, DOCX)")
    uploaded_file = st.file_uploader(
        "Upload Image, PDF, TXT, or DOCX",
        type=["png", "jpg", "jpeg", "pdf", "txt", "docx"]
    )
    if uploaded_file:
        file_ext = Path(uploaded_file.name).suffix.lower()
        if file_ext in [".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"]:
            st.image(uploaded_file, caption=uploaded_file.name)
        elif file_ext == ".pdf":
            st.info("PDF uploaded. Text extraction will run when you click below.")

        extracted_text, extract_warnings = _extract_text_from_upload(uploaded_file)
        if extract_warnings:
            for w in extract_warnings:
                st.warning(w)
        if extracted_text:
            st.text_area("Extracted text", extracted_text, height=200)

        manager = _get_ai_manager()
        if st.button("Run AI extraction on upload"):
            material = extracted_text or f"Uploaded file: {uploaded_file.name} ({uploaded_file.type}). No text could be extracted."
            ai_source, ai_json = _ai_extract_points(manager, material)
            upload_id = add_upload(
                filename=uploaded_file.name,
                mime_type=uploaded_file.type,
                size_bytes=uploaded_file.size,
                extracted_text=extracted_text,
                ai_source=ai_source,
                ai_json=ai_json,
            )
            # Apply AI decisions to calendar + mood timeline
            _apply_ai_decisions("upload", int(upload_id) if upload_id else None, material, ai_source, ai_json)
            if ai_source:
                st.success(f"Stored upload + AI insights ({ai_source}).")
            else:
                st.warning("Stored upload. AI was unavailable, so no insights were saved.")

    # --- Feelings Log ---
    st.header("Log Your Feelings & Thoughts")
    thoughts = st.text_area("How are you feeling today?", height=150)
    col_a, col_b = st.columns([1, 1])
    with col_a:
        save_only = st.button("Save Log")
    with col_b:
        save_with_ai = st.button("Save + AI Insights", type="primary")

    if save_only or save_with_ai:
        if thoughts.strip():
            ai_source = None
            ai_json = None
            if save_with_ai:
                manager = _get_ai_manager()
                ai_source, ai_json = _ai_extract_points(manager, thoughts)
            log_id = add_log(thoughts, ai_source=ai_source, ai_json=ai_json)
            _apply_ai_decisions("log", int(log_id) if log_id else None, thoughts, ai_source, ai_json)
            st.success("Saved to encrypted database.")
        else:
            st.warning("Please write something before saving.")

    st.markdown("### Past Entries")
    logs = list_logs(limit=25)
    if not logs:
        st.info("No logs yet.")
    else:
        for (log_id, created_at, text, ai_source, ai_json) in logs:
            with st.expander(f"{created_at} — Entry #{log_id}"):
                st.write(text)
                if ai_source and ai_json:
                    st.caption(f"AI source: {ai_source}")
                    st.code(ai_json, language="json")

    st.markdown("---")
    st.subheader("Upload History")
    uploads = list_uploads(limit=25)
    if not uploads:
        st.info("No uploads yet.")
    else:
        for (up_id, created_at, filename, mime_type, size_bytes, extracted_text, ai_source, ai_json) in uploads:
            with st.expander(f"{created_at} — {filename}"):
                st.write({"mime_type": mime_type, "size_bytes": size_bytes})
                if extracted_text:
                    st.text_area("Extracted text", extracted_text, height=120, key=f"up_txt_{up_id}")
                if ai_source and ai_json:
                    st.caption(f"AI source: {ai_source}")
                    st.code(ai_json, language="json")

# ---- Main Render Logic ----
# NOTE: We do NOT delete a decrypted DB on startup anymore. On restart, Streamlit will
# not have the password yet, so auto-deleting would destroy user data. Instead, login
# will re-encrypt/migrate as needed after the user enters the password.

if not encrypted_db_exists() and not has_password():
    # First run: create password and encrypt DB at rest.
    setup_password_screen()
elif not st.session_state.authenticated:
    login_screen()
else:
    # After login, ensure schema exists
    init_db()
    # First time after setup/login: choose AI model if not set
    if not get_setting("ai.mode"):
        ai_model_setup_screen()
    else:
        main_dashboard()