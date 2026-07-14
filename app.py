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
    h1, h2, h3, h4, label, .stMarkdown p { font-family: 'Departure Mono', monospace !important; }
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

def analyze_profile_zones(profile_dict, is_left_side):
    """ Divides glyph into zones and detects WAISTED shapes for better kerning. """
    if len(profile_dict) < 4: return "STRAIGHT"
    ys = sorted(profile_dict.keys())
    top_y, bot_y = ys[-1], ys[0]
    h = top_y - bot_y
    if h == 0: return "STRAIGHT"
    
    # Analyze zones
    top_ys = [y for y in ys if y > bot_y + h * 0.6]
    mid_ys = [y for y in ys if bot_y + h * 0.4 <= y <= bot_y + h * 0.6]
    bot_ys = [y for y in ys if y < bot_y + h * 0.4]
    
    def avg_x(y_list): return sum(profile_dict[y] for y in y_list) / len(y_list) if y_list else None
    t_x, m_x, b_x = avg_x(top_ys), avg_x(mid_ys), avg_x(bot_ys)
    if t_x is None or m_x is None or b_x is None: return "STRAIGHT"
    
    x_spread = max(profile_dict.values()) - min(profile_dict.values())
    if x_spread < h * 0.08: return "STRAIGHT"
    
    # Detect shapes
    is_waisted = False
    if not is_left_side:
        if m_x < t_x - x_spread * 0.15 and m_x < b_x - x_spread * 0.15: is_waisted = True
        if is_waisted: return "WAISTED"
        if t_x > m_x + x_spread * 0.15 and t_x > b_x + x_spread * 0.15: return "OVERHANG_TOP"
        if b_x > m_x + x_spread * 0.15 and b_x > t_x + x_spread * 0.15: return "OVERHANG_BOTTOM"
        if m_x > t_x + x_spread * 0.15 and m_x > b_x + x_spread * 0.15: return "ROUND"
        if b_x > t_x + x_spread * 0.15 and m_x > t_x: return "SLOPE_OUT"
        if t_x > b_x + x_spread * 0.15 and m_x > b_x: return "SLOPE_IN"
    else:
        if m_x > t_x + x_spread * 0.15 and m_x > b_x + x_spread * 0.15: is_waisted = True
        if is_waisted: return "WAISTED"
        if t_x < m_x - x_spread * 0.15 and t_x < b_x - x_spread * 0.15: return "OVERHANG_TOP"
        if b_x < m_x - x_spread * 0.15 and b_x < t_x - x_spread * 0.15: return "OVERHANG_BOTTOM"
        if m_x < t_x - x_spread * 0.15 and m_x < b_x - x_spread * 0.15: return "ROUND"
        if b_x < t_x - x_spread * 0.15 and m_x < t_x: return "SLOPE_OUT"
        if t_x < b_x - x_spread * 0.15 and m_x < b_x: return "SLOPE_IN"
    return "STRAIGHT"

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
        left_prof = {y: min(x_vals) for y, x_vals in slices.items()}
        right_prof = {y: max(x_vals) for y, x_vals in slices.items()}
        profiles[name] = {
            "left": left_prof, "right": right_prof,
            "advance": glyph_set[name].width,
            "shape_left": analyze_profile_zones(left_prof, True),
            "shape_right": analyze_profile_zones(right_prof, False)
        }
    return profiles

def calculate_kerning(profiles, pairs_to_kern, target_gap, overhang_mode):
    # Overhang logic
    cfg = {"Open": (25, 0.22, 120), "Standard": (15, 0.30, 180), "Deep": (5, 0.45, 280)}
    min_clearance, safe_ratio, max_cap = cfg.get(overhang_mode, cfg["Standard"])
    
    kern_pairs = {}
    for left, right in pairs_to_kern:
        if left not in profiles or right not in profiles: continue
        prof_l, prof_r = profiles[left]["right"], profiles[right]["left"]
        adv_l, adv_r = profiles[left]["advance"], profiles[right]["advance"]
        common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
        if not common_ys: continue
        
        # Calculate base distances
        dist = {y: (prof_r[y] + adv_l) - prof_l[y] for y in common_ys}
        min_dist = min(dist.values())
        
        # Modifier logic
        shape_l, shape_r = profiles[left]["shape_right"], profiles[right]["left"]
        opt = 0
        if shape_l == "WAISTED" or shape_r == "WAISTED": opt -= 10
        elif shape_l == "STRAIGHT" and shape_r == "STRAIGHT": opt = 15
        elif shape_l == "ROUND" and shape_r == "ROUND": opt = -10
        elif (shape_l == "ROUND" and shape_r == "STRAIGHT") or (shape_l == "STRAIGHT" and shape_r == "ROUND"): opt = -5
        elif shape_l == "SLOPE_OUT" and shape_r == "SLOPE_IN": opt = -20
        elif shape_l == "SLOPE_IN" and shape_r == "SLOPE_OUT": opt = -20

        # Collision avoidance
        kern_val = (target_gap + opt) - min_dist
        if min_dist + kern_val < min_clearance: kern_val += (min_clearance - (min_dist + kern_val))
        
        kern_val = int(round(kern_val / 5.0) * 5)
        if abs(kern_val) > 2: kern_pairs[(left, right)] = kern_val
            
    return kern_pairs, [] # Contextual rules can be added here if needed

# --- 2. STREAMLIT RUNTIME ---
st.set_page_config(page_title="LazyKern Engine", layout="centered")
inject_pro_cleaner()
st.title("LazyKern Auto-Kerning")

uploaded_file = st.file_uploader("Drop your un-kerned Display Font (TTF/OTF)", type=["ttf", "otf"])

if uploaded_file:
    if "filename" not in st.session_state or st.session_state.filename != uploaded_file.name:
        font = TTFont(io.BytesIO(uploaded_file.read()))
        st.session_state.profiles = get_glyph_profiles(font)
        st.session_state.original_bytes = uploaded_file.getvalue()
        glyphs = [g for g in st.session_state.profiles.keys() if g not in [".notdef", "space"]]
        st.session_state.pairs = [(a, b) for a in glyphs for b in glyphs]
        st.session_state.filename = uploaded_file.name

    col1, col2 = st.columns([1, 1])
    target_gap = col1.slider("Target Gap", 0, 150, 40, 5)
    overhang_mode = col2.radio("Overhang", ["Open", "Standard", "Deep"], index=1, horizontal=True)
    
    if st.toggle("✨ Apply LazyKern", True):
        font = TTFont(io.BytesIO(st.session_state.original_bytes))
        k, _ = calculate_kerning(st.session_state.profiles, st.session_state.pairs, target_gap, overhang_mode)
        fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in k.items()] + ["} kern;"]
        try:
            addOpenTypeFeaturesFromString(font, "\n".join(fea))
            out = io.BytesIO()
            font.save(out)
            bytes_data = out.getvalue()
        except: st.error("Compilation failed.")
    else: bytes_data = st.session_state.original_bytes

    st.download_button("📥 Download Compiled Font", bytes_data, f"LazyKern_{uploaded_file.name}")
