import streamlit as st
import io
import math
import base64
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

# --- 1. THE SOPHISTICATED MATH ENGINE ---
class ProfilePen(BasePen):
    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.points = []

    def _moveTo(self, p): self.points.append(p)
    def _lineTo(self, p): self.points.append(p)
    def _curveToOne(self, p1, p2, p3):
        p0 = self._getCurrentPoint()
        approx_len = math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)
        steps = max(8, min(30, int(approx_len / 20)))
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
            y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
            self.points.append((x, y))

    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        approx_len = math.dist(p0, p1) + math.dist(p1, p2)
        steps = max(6, min(20, int(approx_len / 20)))
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
            y = (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
            self.points.append((x, y))

def get_glyph_profiles(font, step_size=10):
    glyph_set = font.getGlyphSet()
    profiles = {}
    for name in glyph_set.keys():
        pen = ProfilePen(glyph_set)
        glyph = glyph_set[name]
        try: glyph.draw(pen)
        except Exception: continue
        if not pen.points: continue
        
        slices = {}
        for x, y in pen.points:
            y_slice = int(round(y / step_size) * step_size)
            slices.setdefault(y_slice, []).append(x)
            
        left_prof, right_prof = {}, {}
        for y_slice, x_vals in slices.items():
            left_prof[y_slice] = min(x_vals)
            right_prof[y_slice] = max(x_vals)
            
        profiles[name] = {"left": left_prof, "right": right_prof, "advance": glyph.width}
    return profiles

def calculate_kerning(profiles, pairs_to_kern, target_gap=40):
    kern_pairs = {}
    for left, right in pairs_to_kern:
        if left in profiles and right in profiles:
            prof_l = profiles[left]["right"]
            prof_r = profiles[right]["left"]
            common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
            if not common_ys: continue
            
            min_dist = min((prof_r[y] + profiles[left]["advance"]) - prof_l[y] for y in common_ys)
            kern_val = int(target_gap - min_dist)
            
            if abs(kern_val) > 2:
                kern_pairs[(left, right)] = int(round(kern_val / 5.0) * 5)
    return kern_pairs

# --- 2. BARE-BONES UI & LOGIC ---
st.set_page_config(page_title="AutoKern Core")
st.title("AutoKern: Core Engine")

uploaded_file = st.file_uploader("1. Upload Font (TTF/OTF)", type=["ttf", "otf"])

if uploaded_file:
    # Set up session state to hold the font data so it can be updated
    if "font_bytes" not in st.session_state or st.session_state.get("filename") != uploaded_file.name:
        st.session_state.font_bytes = uploaded_file.read()
        st.session_state.original_bytes = st.session_state.font_bytes
        st.session_state.filename = uploaded_file.name
        st.session_state.is_kerned = False

    # Inject the current font (original or kerned) into the browser
    b64_font = base64.b64encode(st.session_state.font_bytes).decode('utf-8')
    font_fmt = "opentype" if uploaded_file.name.lower().endswith('.otf') else "truetype"
    
    st.markdown(f"""
        <style>
            @font-face {{
                font-family: 'LiveFont';
                src: url('data:font/{font_fmt};charset=utf-8;base64,{b64_font}') format('{font_fmt}');
            }}
            .tester-box {{
                font-family: 'LiveFont', sans-serif;
                font-size: 48px;
                width: 100%;
                min-height: 120px;
                padding: 15px;
                margin-bottom: 20px;
                border: 2px solid #ddd;
                border-radius: 8px;
                line-height: 1.2;
            }}
        </style>
    """, unsafe_allow_html=True)

    st.subheader("2. Live Preview")
    if st.session_state.is_kerned:
        st.success("Viewing: **Kerned Font**")
    else:
        st.info("Viewing: **Original Font** (Unkerned)")
        
    st.markdown('<textarea class="tester-box">AV TA To Tr We Wa P. Y- Type here...</textarea>', unsafe_allow_html=True)

    st.subheader("3. Kerning Controls")
    gap = st.slider("Target Gap (Tightness)", min_value=10, max_value=100, value=40, step=5)
    
    if st.button("Apply Auto-Kerning"):
        with st.spinner("Processing geometries..."):
            # Always kern from the original file to prevent double-kerning
            font = TTFont(io.BytesIO(st.session_state.original_bytes))
            profiles = get_glyph_profiles(font)
            
            glyphs = [g for g in profiles.keys() if g not in [".notdef", "space"]]
            pairs = [(a, b) for a in glyphs for b in glyphs]
            
            kern_pairs = calculate_kerning(profiles, pairs, target_gap=gap)
            
            fea_lines = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in kern_pairs.items()] + ["} kern;"]
            addOpenTypeFeaturesFromString(font, "\n".join(fea_lines))
            
            out = io.BytesIO()
            font.save(out)
            
            # Update session state with the new kerned font
            st.session_state.font_bytes = out.getvalue()
            st.session_state.is_kerned = True
            
            # Rerun the app to refresh the live preview with the new font
            st.rerun()

    if st.session_state.is_kerned:
        st.download_button(
            label="📥 Download Kerned Font", 
            data=st.session_state.font_bytes, 
            file_name=f"kerned_{uploaded_file.name}"
        )
