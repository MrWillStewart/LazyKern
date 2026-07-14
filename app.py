import streamlit as st
import io
import math
import base64
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

# --- 0. BRANDING STRIPPER & TYPOGRAPHY ENFORCER ---
def inject_pro_cleaner():
    st.markdown("""
    <style>
    [data-testid="stHeader"] { display: none !important; }
    footer { visibility: hidden !important; }
    #MainMenu { visibility: hidden !important; }
    .header-anchor { display: none !important; }
    h1 a, h2 a, h3 a, h4 a { display: none !important; }
    h1, h2, h3, h4, label, .stMarkdown p {
        font-family: 'Departure Mono', monospace !important;
    }
    .stTextArea textarea {
        font-family: 'LiveFont', sans-serif !important;
        font-size: 64px !important; /* Increased for better display font preview */
        min-height: 180px !important;
        border: 2px solid #DAE1E8 !important;
        border-radius: 10px !important;
        color: #000000 !important;
        line-height: 1.2 !important;
        letter-spacing: normal !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 1. CORE GEOMETRY ENGINE ---
class ProfilePen(BasePen):
    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.points = []
    def _moveTo(self, p): self.points.append(p)
    def _lineTo(self, p):
        p0 = self._getCurrentPoint()
        if p0:
            dist = math.dist(p0, p)
            steps = max(1, int(dist / 3.0)) # Increased resolution for display fonts
            for i in range(steps + 1):
                t = i / float(steps)
                self.points.append((p0[0] + (p[0] - p0[0]) * t, p0[1] + (p[1] - p0[1]) * t))
        else: self.points.append(p)
    def _curveToOne(self, p1, p2, p3):
        p0 = self._getCurrentPoint()
        if not p0: return
        approx_len = math.dist(p0, p1) + math.dist(p1, p2) + math.dist(p2, p3)
        steps = max(10, min(50, int(approx_len / 3.0)))
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
            y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
            self.points.append((x, y))
    def _qCurveToOne(self, p1, p2):
        p0 = self._getCurrentPoint()
        if not p0: return
        approx_len = math.dist(p0, p1) + math.dist(p1, p2)
        steps = max(8, min(40, int(approx_len / 3.0)))
        for i in range(steps + 1):
            t = i / float(steps)
            x = (1-t)**2 * p0[0] + 2*(1-t)*t * p1[0] + t**2 * p2[0]
            y = (1-t)**2 * p0[1] + 2*(1-t)*t * p1[1] + t**2 * p2[1]
            self.points.append((x, y))

def get_glyph_profiles(font, step_size=5):
    glyph_set = font.getGlyphSet()
    profiles = {}
    for name in glyph_set.keys():
        pen = ProfilePen(glyph_set)
        try: glyph_set[name].draw(pen)
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
        profiles[name] = {"left": left_prof, "right": right_prof, "advance": glyph_set[name].width}
    return profiles

def calculate_kerning(profiles, pairs_to_kern, target_gap, min_clearance, safe_ratio):
    kern_pairs = {}
    for left, right in pairs_to_kern:
        if left not in profiles or right not in profiles: continue
        
        prof_l, prof_r = profiles[left]["right"], profiles[right]["left"]
        adv_l = profiles[left]["advance"]
        adv_r = profiles[right]["advance"]
        
        common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
        if not common_ys: continue # No horizontal overlap (e.g., period and quote)
        
        # 1. Find the absolute closest point between the two glyphs
        min_dist = min((prof_r[y] + adv_l) - prof_l[y] for y in common_ys)
        
        # 2. Base kerning logic: Pull them together until they hit the target gap
        kern_val = target_gap - min_dist
        
        # 3. PAIR GUARD: Hard Minimum Clearance 
        # No matter the target gap, they CANNOT get closer than min_clearance
        actual_distance = min_dist + kern_val
        if actual_distance < min_clearance:
            kern_val += (min_clearance - actual_distance)
            
        # 4. TRIPLE GUARD: The Overhang Limit
        # Prevent A-B-C overlaps by capping how far a letter can tuck under another.
        # We limit the negative kern value to a percentage of the narrowest letter in the pair.
        max_negative_kern = -abs(min(adv_l, adv_r) * safe_ratio)
        if kern_val < max_negative_kern:
            kern_val = max_negative_kern
            
        # 5. Clean up values for OpenType
        kern_val = int(round(kern_val / 5.0) * 5)
        
        if abs(kern_val) > 2: 
            kern_pairs[(left, right)] = kern_val
            
    return kern_pairs

# --- 2. STREAMLIT RUNTIME ---
st.set_page_config(page_title="LazyKern Engine", layout="centered")
inject_pro_cleaner()
st.title("LazyKern Auto-Kerning")

uploaded_file = st.file_uploader("Drop your un-kerned Display Font (TTF/OTF)", type=["ttf", "otf"])

if uploaded_file:
    if "filename" not in st.session_state or st.session_state.filename != uploaded_file.name:
        font_bytes = uploaded_file.read()
        st.session_state.original_bytes = font_bytes
        st.session_state.filename = uploaded_file.name
        font = TTFont(io.BytesIO(font_bytes))
        st.session_state.profiles = get_glyph_profiles(font)
        st.session_state.supported_chars = {chr(cp) for cp in font.getBestCmap().keys()}
        
        # Filter out massive glyph sets to prevent freezing on load
        # You can expand this logic later to include standard kerning groups
        glyphs = [g for g in st.session_state.profiles.keys() if g not in [".notdef", "space"]]
        st.session_state.pairs = [(a, b) for a in glyphs for b in glyphs]

    st.markdown("---")
    col1, col2 = st.columns([1, 1])
    with col1:
        use_kerning = st.toggle("✨ Enable LazyKern", True)
    
    # Expose the physics parameters to the user
    target_gap = st.slider("Optical Spacing (Overall Tightness)", 0, 150, 40, 5, help="How close the letters should feel overall.")
    min_clearance = st.slider("Strict Collision Guard", 0, 100, 15, 5, help="Absolute minimum distance allowed between any two points. Prevents pair overlaps.")
    safe_ratio = st.slider("Triple Clash Prevention", 0.1, 0.5, 0.3, 0.05, help="Caps negative kerning based on letter width. Lower = safer from 3-letter clashing (like ToT).")
    
    bytes_data = st.session_state.original_bytes
    if use_kerning:
        font = TTFont(io.BytesIO(bytes_data))
        k = calculate_kerning(st.session_state.profiles, st.session_state.pairs, target_gap, min_clearance, safe_ratio)
        
        if k:
            fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in k.items()] + ["} kern;"]
            try:
                addOpenTypeFeaturesFromString(font, "\n".join(fea))
                out = io.BytesIO()
                font.save(out)
                bytes_data = out.getvalue()
            except Exception as e:
                st.error("Kerning compilation failed. The font might have conflicting tables.")

    b64 = base64.b64encode(bytes_data).decode('utf-8')
    fmt = "opentype" if uploaded_file.name.lower().endswith('.otf') else "truetype"
    st.markdown(f"""<style>@font-face {{font-family:'LiveFont'; src:url('data:font/{fmt};charset=utf-8;base64,{b64}');}}</style>""", unsafe_allow_html=True)

    st.markdown("---")
    if "user_text" not in st.session_state: st.session_state.user_text = "AUTO KERNED."
    
    user_input = st.text_area("Test your typography:", value=st.session_state.user_text, key="input_key")
    
    clean = "".join([c for c in user_input if c in st.session_state.supported_chars or c in [" ", "\n", "."]])
    if user_input != clean:
        st.session_state.user_text = clean
        st.rerun()

    st.download_button("📥 Download Compiled Font", bytes_data, f"LazyKern_{uploaded_file.name}")
