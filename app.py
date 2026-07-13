# --- 2. STREAMLIT RUNTIME (Updated) ---
st.set_page_config(page_title="LazyKern", layout="centered")
inject_pro_cleaner()

st.title("LazyKern")
uploaded_file = st.file_uploader("Upload Font (TTF/OTF)", type=["ttf", "otf"])

if uploaded_file:
    if "filename" not in st.session_state or st.session_state.filename != uploaded_file.name:
        with st.spinner("Analyzing high-density geometry profiles..."):
            font_bytes = uploaded_file.read()
            st.session_state.original_bytes = font_bytes
            st.session_state.filename = uploaded_file.name
            
            font = TTFont(io.BytesIO(font_bytes))
            st.session_state.profiles = get_glyph_profiles(font)
            # EXTRACT SUPPORTED CHARS
            st.session_state.supported_chars = {chr(cp) for cp in font.getBestCmap().keys()}
            
            glyphs = [g for g in st.session_state.profiles.keys() if g not in [".notdef", "space"]]
            st.session_state.pairs = [(a, b) for a in glyphs for b in glyphs]

    gap = st.slider("Target Gap (Tightness)", min_value=10, max_value=100, value=60, step=5)
    use_kerning = st.toggle("Apply Auto-Kerning", value=True)
    
    if use_kerning and "profiles" in st.session_state:
        font = TTFont(io.BytesIO(st.session_state.original_bytes))
        kern_pairs = calculate_kerning(st.session_state.profiles, st.session_state.pairs, target_gap=gap)
        
        if kern_pairs:
            fea_lines = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in kern_pairs.items()] + ["} kern;"]
            addOpenTypeFeaturesFromString(font, "\n".join(fea_lines))
        
        out = io.BytesIO()
        font.save(out)
        active_font_bytes = out.getvalue()
    else:
        active_font_bytes = st.session_state.original_bytes

    b64_font = base64.b64encode(active_font_bytes).decode('utf-8')
    
    # --- SANITIZATION LOGIC ---
    # We use a session state key for the text area to allow re-running
    if "user_text" not in st.session_state:
        st.session_state.user_text = "START.YOUR.ENGINES."
        
    def validate_input():
        # Strip characters not in the font's cmap
        raw = st.session_state.user_input
        clean = "".join([c for c in raw if c in st.session_state.supported_chars or c in [" ", "\n", "."]])
        if raw != clean:
            st.session_state.user_text = clean
            st.rerun()

    st.subheader("Live Preview")
    st.text_area("Type your text here:", key="user_input", on_change=validate_input)
    
    # Render using the sanitized text
    st.markdown(f"""
        <style>
            @font-face {{
                font-family: 'LiveFont';
                src: url('data:font/truetype;base64,{b64_font}');
            }}
            .tester-box {{
                font-family: 'LiveFont', sans-serif !important;
                font-size: 48px;
                padding: 15px;
                border: 1px solid #DAE1E8;
                border-radius: 10px;
            }}
        </style>
        <div class="tester-box">{st.session_state.user_text}</div>
    """, unsafe_allow_html=True)

    st.download_button("📥 Download Kerned Font File", active_font_bytes, f"kerned_{uploaded_file.name}")
