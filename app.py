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
    if len(profile_dict) < 4: return "STRAIGHT"
    ys = sorted(profile_dict.keys())
    top_y, bot_y = ys[-1], ys[0]
    h = top_y - bot_y
    if h == 0: return "STRAIGHT"
    
    top_ys = [y for y in ys if y > bot_y + h * 0.6]
    mid_ys = [y for y in ys if bot_y + h * 0.4 <= y <= bot_y + h * 0.6]
    bot_ys = [y for y in ys if y < bot_y + h * 0.4]
    
    def avg_x(y_list): return sum(profile_dict[y] for y in y_list) / len(y_list) if y_list else None
    t_x, m_x, b_x = avg_x(top_ys), avg_x(mid_ys), avg_x(bot_ys)
    if t_x is None or m_x is None or b_x is None: return "STRAIGHT"
    
    x_spread = max(profile_dict.values()) - min(profile_dict.values())
    if x_spread < h * 0.08: return "STRAIGHT"
    
    # Check for "Waisted" (narrow in middle)
    if not is_left_side:
        if m_x < t_x - x_spread * 0.15 and m_x < b_x - x_spread * 0.15: return "WAISTED"
        if t_x > m_x + x_spread * 0.15 and t_x > b_x + x_spread * 0.15: return "OVERHANG_TOP"
        if b_x > m_x + x_spread * 0.15 and b_x > t_x + x_spread * 0.15: return "OVERHANG_BOTTOM"
        if m_x > t_x + x_spread * 0.15 and m_x > b_x + x_spread * 0.15: return "ROUND"
        if b_x > t_x + x_spread * 0.15 and m_x > t_x: return "SLOPE_OUT"
        if t_x > b_x + x_spread * 0.15 and m_x > b_x: return "SLOPE_IN"
    else:
        if m_x > t_x + x_spread * 0.15 and m_x > b_x + x_spread * 0.15: return "WAISTED"
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
        ys_raw = []
        for x, y in pen.points:
            ys_raw.append(y)
            y_slice = int(round(y / step_size) * step_size)
            slices.setdefault(y_slice, []).append(x)
        left_prof = {y: min(x_vals) for y, x_vals in slices.items()}
        right_prof = {y: max(x_vals) for y, x_vals in slices.items()}
        profiles[name] = {
            "left": left_prof, "right": right_prof,
            "advance": glyph_set[name].width,
            "height": max(ys_raw) - min(ys_raw) if ys_raw else 0,
            "shape_left": analyze_profile_zones(left_prof, True),
            "shape_right": analyze_profile_zones(right_prof, False)
        }
    return profiles

def calculate_kerning(profiles, pairs_to_kern, target_gap, overhang_mode):
    # Config setup
    cfg = {"Open": (25, 0.22, 120), "Standard": (15, 0.30, 180), "Deep": (5, 0.45, 280)}
    min_clearance, safe_ratio, max_cap = cfg.get(overhang_mode, cfg["Standard"])
    
    kern_pairs = {}
    for left, right in pairs_to_kern:
        if left not in profiles or right not in profiles: continue
        
        prof_l, prof_r = profiles[left]["right"], profiles[right]["left"]
        adv_l = profiles[left]["advance"]
        h_l, h_r = profiles[left]["height"], profiles[right]["height"]
        
        common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
        if not common_ys: continue
        
        distances = {y: (prof_r[y] + adv_l) - prof_l[y] for y in common_ys}
        min_dist = min(distances.values())
        
        # Sharp/Point detection
        tolerance = 15
        bottleneck_slices = [y for y, d in distances.items() if d <= min_dist + tolerance]
        is_sharp_contact = len(bottleneck_slices) <= max(2, int(len(common_ys) * 0.12))
        sharp_modifier = -15 if is_sharp_contact else 0
        
        # Optical Modifier logic
        shape_l, shape_r = profiles[left]["shape_right"], profiles[right]["shape_left"]
        opt = 0
        if shape_l == "WAISTED" or shape_r == "WAISTED": opt = -10
        elif shape_l == "STRAIGHT" and shape_r == "STRAIGHT": opt = 15
        elif shape_l == "ROUND" and shape_r == "ROUND": opt = -10
        elif (shape_l == "ROUND" and shape_r == "STRAIGHT") or (shape_l == "STRAIGHT" and shape_r == "ROUND"): opt = -5
        elif shape_l == "SLOPE_OUT" and shape_r == "SLOPE_IN": opt = -20
        elif shape_l == "SLOPE_IN" and shape_r == "SLOPE_OUT": opt = -20
        
        # Dynamic Tuck
        overlap_h = max(common_ys) - min(common_ys)
        is_tucking = overlap_h < (h_l * 0.4) or overlap_h < (h_r * 0.4)
        tuck_boost = 1.2 if is_tucking else 1.0
        
        kern_val = (target_gap + opt + sharp_modifier) - min_dist
        
        # Safety guards
        actual_distance = min_dist + kern_val
        if actual_distance < min_clearance: kern_val += (min_clearance - actual_distance)
        
        max_negative_kern = -abs(max(adv_l, profiles[right]["advance"]) * safe_ratio * tuck_boost)
        if abs(max_negative_kern) > max_cap: max_negative_kern = -max_cap
        
        if kern_val < max_negative_kern: kern_val = max_negative_kern
        
        kern_val = int(round(kern_val / 5.0) * 5)
        if abs(kern_val) > 2: kern_pairs[(left, right)] = kern_val
            
    # Contextual Triplet Engine
    punctuation_glyphs = [g for g in profiles.keys() if g in ["period", "comma", "colon", "semicolon", "dot", "commaaccent"] or (0 < profiles[g]["height"] < 350)]
    overhanging_left = [g for g in profiles.keys() if profiles[g]["shape_right"] in ["OVERHANG_TOP", "SLOPE_IN", "ROUND"]]
    overhanging_right = [g for g in profiles.keys() if profiles[g]["shape_left"] in ["OVERHANG_TOP", "SLOPE_OUT", "ROUND"]]
    
    contextual_rules = []
    for p in punctuation_glyphs:
        for l in overhanging_left:
            for r in overhanging_right:
                k_lp = kern_pairs.get((l, p), 0)
                k_pr = kern_pairs.get((p, r), 0)
                if k_lp == 0 and k_pr == 0: continue
                
                # Check clearance for triplets
                if not profiles[p]["right"].keys(): continue
                max_p_y = max(profiles[p]["right"].keys())
                prof_ll, prof_rr = profiles[l]["right"], profiles[r]["left"]
                adv_ll, adv_pp = profiles[l]["advance"], profiles[p]["advance"]
                
                above_ys = [y for y in set(prof_ll.keys()).intersection(set(prof_rr.keys())) if y > max_p_y]
                if not above_ys: continue
                
                min_clearance_above = min((prof_rr[y] + adv_ll + adv_pp + k_lp + k_pr) - prof_ll[y] for y in above_ys)
                
                if min_clearance_above < min_clearance + 15:
                    needed_extra = int(round((min_clearance + 15 - min_clearance_above) / 5.0) * 5)
                    if needed_extra > 5: contextual_rules.append(f"    pos {l} {p}' {needed_extra} {r};")

    return kern_pairs, contextual_rules

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
        glyphs = [g for g in st.session_state.profiles.keys() if g not in [".notdef", "space"]]
        st.session_state.pairs = [(a, b) for a in glyphs for b in glyphs]

    col1, col2 = st.columns([1, 1])
    target_gap = col1.slider("Target Gap", 0, 150, 40, 5)
    overhang_mode = col2.radio("Overhang", ["Open", "Standard", "Deep"], index=1, horizontal=True)
    
    bytes_data = st.session_state.original_bytes
    if st.toggle("✨ Apply LazyKern", True):
        font = TTFont(io.BytesIO(bytes_data))
        k, rules = calculate_kerning(st.session_state.profiles, st.session_state.pairs, target_gap, overhang_mode)
        fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in k.items()] + rules + ["} kern;"]
        
        try:
            addOpenTypeFeaturesFromString(font, "\n".join(fea))
            out = io.BytesIO()
            font.save(out)
            bytes_data = out.getvalue()
        except: st.error("Compilation failed.")

    b64 = base64.b64encode(bytes_data).decode('utf-8')
    fmt = "opentype" if uploaded_file.name.lower().endswith('.otf') else "truetype"
    st.markdown(f"""<style>@font-face {{font-family:'LiveFont'; src:url('data:font/{fmt};charset=utf-8;base64,{b64}');}}</style>""", unsafe_allow_html=True)

    if "user_text" not in st.session_state: st.session_state.user_text = "AUTO KERNED."
    st.text_area("Test your typography:", value=st.session_state.user_text, key="input_key")
    st.download_button("📥 Download Compiled Font", bytes_data, f"LazyKern_{uploaded_file.name}")
