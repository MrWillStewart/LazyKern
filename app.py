# --- 2. STREAMLIT RUNTIME ---
st.set_page_config(page_title="LazyKern", layout="centered")
inject_pro_cleaner()

st.title("LazyKern")
uploaded_file = st.file_uploader("Upload Font", type=["ttf", "otf"])

if uploaded_file:
    if "filename" not in st.session_state or st.session_state.filename != uploaded_file.name:
        font_bytes = uploaded_file.read()
        font = TTFont(io.BytesIO(font_bytes))
        st.session_state.original_bytes = font_bytes
        st.session_state.filename = uploaded_file.name
        st.session_state.profiles = get_glyph_profiles(font)
        st.session_state.supported = {chr(cp) for cp in font.getBestCmap().keys()}
    
    gap = st.slider("Target Gap", 10, 100, 60, 5)
    use_kern = st.toggle("Apply Auto-Kerning", True)
    
    bytes_data = st.session_state.original_bytes
    if use_kern:
        font = TTFont(io.BytesIO(bytes_data))
        pairs = [(a, b) for a in st.session_state.profiles for b in st.session_state.profiles]
        k = calculate_kerning(st.session_state.profiles, pairs, gap)
        fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in k.items()] + ["} kern;"]
        addOpenTypeFeaturesFromString(font, "\n".join(fea))
        out = io.BytesIO()
        font.save(out)
        bytes_data = out.getvalue()

    b64 = base64.b64encode(bytes_data).decode()
    
    # Inject CSS that targets the text area directly
    st.markdown(f"""
        <style>
            @font-face {{font-family:'LiveFont'; src:url('data:font/ttf;base64,{b64}');}}
            .stTextArea textarea {{
                font-family: 'LiveFont', sans-serif !important;
                font-size: 48px !important;
                min-height: 140px !important;
            }}
        </style>
    """, unsafe_allow_html=True)
    
    # Single text area
    user_in = st.text_area("Live Preview", value="START.YOUR.ENGINES.", key="t")
    
    # Sanitization
    clean = "".join([c for c in user_in if c in st.session_state.supported or c in [" ", "\n", "."]])
    if user_in != clean:
        st.session_state.t = clean
        st.rerun()

    st.download_button("📥 Download Kerned Font", bytes_data, f"kerned_{uploaded_file.name}")
