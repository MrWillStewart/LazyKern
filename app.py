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
        font-size: 64px !important;
        min-height: 180px !important;
        border: 2px solid #DAE1E8 !important;
        border-radius: 10px !important;
        color: #000000 !important;
        line-height: 1.2 !important;
        letter-spacing: normal !important;
    }
    /* Hide Streamlit radio button visual clutter to make it look like a segmented control */
    div[role="radiogroup"] { flex-direction: row; gap: 15px; }
    </style>
    """, unsafe_allow_html=True)

# --- 1. CORE GEOMETRY & SHAPE ENGINE ---
class ProfilePen(BasePen):
    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.points = []
    def _moveTo(self, p): self.points.append(p)
    def _lineTo(self, p):
        p0 = self._getCurrentPoint()
        if p0:
            dist = math.dist(p0, p)
            steps = max(1, int(dist / 3.0))
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

def analyze_shape(profile_dict, is_left_side):
    """ Dynamically determines if a side is STRAIGHT, ROUND, DIAGONAL, or COMPLEX """
    if len(profile_dict) < 4: return "STRAIGHT"
    
    ys = sorted(profile_dict.keys())
    top_y, bot_y = ys[-1], ys[0]
    height = top_y - bot_y
    if height == 0: return "STRAIGHT"
    
    top_x, bot_x = profile_dict[top_y], profile_dict[bot_y]
    
    # Sample the middle 40% of the glyph to find the "bulge" or "bridge"
    mid_ys = [y for y in ys if bot_y + height*0.3 < y < bot_y + height*0.7]
    if not mid_ys: return "STRAIGHT"
    
    mid_x_avg = sum(profile_dict[y] for y in mid_ys) / len(mid_ys)
    
    # Calculate horizontal spread
    x_vals = list(profile_dict.values())
    x_spread = max(x_vals) - min(x_vals)
    
    if x_spread < height * 0.12: 
        return "STRAIGHT" # Very little horizontal movement
        
    expected_mid_x = (top_x + bot_x) / 2.0
    if abs(mid_x_avg - expected_mid_x) < x_spread * 0.25:
        return "DIAGONAL" # Smooth, linear slope between top and bottom
        
    # Check for outward bulge (Roundness)
    if is_left_side and (mid_x_avg < top_x and mid_x_avg < bot_x): return "ROUND"
    if not is_left_side and (mid_x_avg > top_x and mid_x_avg > bot_x): return "ROUND"
        
    return "COMPLEX"

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
            
        profiles[name] = {
            "left": left_prof, 
            "right": right_prof, 
            "advance": glyph_set[name].width,
            "shape_left": analyze_shape(left_prof, is_left_side=True),
            "shape_right": analyze_shape(right_prof, is_left_side=False)
        }
    return profiles

def calculate_kerning(profiles, pairs_to_kern, target_gap, safety_mode):
    # Unpack safety modes (min_clearance, safe_ratio)
    if safety_mode == "Safe": min_clearance, safe_ratio = 30, 0.2
    elif safety_mode == "Standard": min_clearance, safe_ratio = 15, 0.35
    else: min_clearance, safe_ratio = 5, 0.5 # Aggressive

    kern_pairs = {}
    for left, right in pairs_to_kern:
        if left not in profiles or right not in profiles: continue
        
        prof_l, prof_r = profiles[left]["right"], profiles[right]["left"]
        adv_l = profiles[left]["advance"]
        adv_r = profiles[right]["advance"]
        
        common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
        if not common_ys: continue
        
        min_dist = min((prof_r[y] + adv_l) - prof_l[y] for y in common_ys)
        
        # --- APPLY DYNAMIC OPTICAL MODIFIERS ---
        shape_l = profiles[left]["shape_right"] # Right edge of left letter
        shape_r = profiles[right]["shape_left"] # Left edge of right letter
        
        optical_modifier = 0
        if shape_l == "STRAIGHT" and shape_r == "STRAIGHT": optical_modifier = 15 # Push blocks apart
        elif shape_l == "ROUND" and shape_r == "ROUND": optical_modifier = -10 # Tuck bowls together
        elif (shape_l == "ROUND" and shape_r == "STRAIGHT") or (shape_l == "STRAIGHT" and shape_r == "ROUND"): optical_modifier = -5
        elif shape_l == "DIAGONAL" or shape_r == "DIAGONAL": optical_modifier = -15 # Eat up diagonal whitespace

        adjusted_target = target_gap + optical_modifier
        kern_val = adjusted_target - min_dist
        
        # --- APPLY SAFETY GUARDS ---
        actual_distance = min_dist + kern_val
        if actual_distance < min_clearance:
            kern_val += (min_clearance - actual_distance)
            
        max_negative_kern = -abs(min(adv_l, adv_r) * safe_ratio)
        if kern_val < max_negative_kern:
            kern_val = max_negative_kern
            
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
        
        glyphs = [g for g in st.session_state.profiles.keys() if g not in [".notdef", "space"]]
        st.session_state.pairs = [(a, b) for a in glyphs for b in glyphs]

    st.markdown("---")
    
    # --- SIMPLIFIED UI ---
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**Optical Spacing**")
        target_gap = st.slider("Target Gap", 0, 150, 40, 5, label_visibility="collapsed")
    with col2:
        st.markdown("**Clash Protection Mode**")
        safety_mode = st.radio("Safety Mode", ["Safe", "Standard", "Aggressive"], index=1, horizontal=True, label_visibility="collapsed")
    
    use_kerning = st.toggle("✨ Apply LazyKern", True)
    
    bytes_data = st.session_state.original_bytes
    if use_kerning:
        font = TTFont(io.BytesIO(bytes_data))
        k = calculate_kerning(st.session_state.profiles, st.session_state.pairs, target_gap, safety_mode)
        
        if k:
            fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in k.items()] + ["} kern;"]
            try:
                addOpenTypeFeaturesFromString(font, "\n".join(fea))
                out = io.BytesIO()
                font.save(out)
                bytes_data = out.getvalue()
            except Exception:
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
