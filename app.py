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
    
    if not is_left_side: 
        if t_x > m_x + x_spread * 0.15 and t_x > b_x + x_spread * 0.15: return "OVERHANG_TOP"
        if b_x > m_x + x_spread * 0.15 and b_x > t_x + x_spread * 0.15: return "OVERHANG_BOTTOM"
        if m_x > t_x + x_spread * 0.15 and m_x > b_x + x_spread * 0.15: return "ROUND"
        if b_x > t_x + x_spread * 0.15 and m_x > t_x: return "SLOPE_OUT"
        if t_x > b_x + x_spread * 0.15 and m_x > b_x: return "SLOPE_IN"
    else: 
        if t_x < m_x - x_spread * 0.15 and t_x < b_x - x_spread * 0.15: return "OVERHANG_TOP"
        if b_x < m_x - x_spread * 0.15 and b_x < t_x - x_spread * 0.15: return "OVERHANG_BOTTOM"
        if m_x < t_x - x_spread * 0.15 and m_x < b_x - x_spread * 0.15: return "ROUND"
        if b_x < t_x - x_spread * 0.15 and m_x < t_x: return "SLOPE_OUT"
        if t_x < b_x - x_spread * 0.15 and m_x < b_x: return "SLOPE_IN"
    return "STRAIGHT"

def get_glyph_profiles(font, step_size=5):
    glyph_set = font.getGlyphSet()
    profiles = {}
    total_w = 0
    total_h = 0
    count = 0
    
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
            
        left_prof, right_prof = {}, {}
        for y_slice, x_vals in slices.items():
            left_prof[y_slice] = min(x_vals)
            right_prof[y_slice] = max(x_vals)
            
        h = max(ys_raw) - min(ys_raw) if ys_raw else 0
        w = glyph_set[name].width
        
        profiles[name] = {
            "left": left_prof, 
            "right": right_prof, 
            "advance": w,
            "height": h,
            "shape_left": analyze_profile_zones(left_prof, is_left_side=True),
            "shape_right": analyze_profile_zones(right_prof, is_left_side=False)
        }
        if name not in [".notdef", "space"] and h > 0:
            total_w += w
            total_h += h
            count += 1
            
    # Calculate overall font vibe for auto-recommendations
    font_avg_width = total_w / count if count > 0 else 500
    font_avg_height = total_h / count if count > 0 else 700
    return profiles, font_avg_width, font_avg_height

def calculate_kerning(profiles, pairs_to_kern, target_gap, overhang_mode, font_avg_width):
    # Radically widened overhang extremes
    if overhang_mode == "Open": 
        min_clearance, safe_ratio, max_cap = 25, 0.15, 60
    elif overhang_mode == "Standard": 
        min_clearance, safe_ratio, max_cap = 15, 0.35, 180
    else: # Deep
        min_clearance, safe_ratio, max_cap = 0, 0.65, 450

    kern_pairs = {}
    for left, right in pairs_to_kern:
        if left not in profiles or right not in profiles: continue
        
        prof_l, prof_r = profiles[left]["right"], profiles[right]["left"]
        adv_l = profiles[left]["advance"]
        adv_r = profiles[right]["advance"]
        h_l = profiles[left]["height"]
        h_r = profiles[right]["height"]
        
        common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
        if not common_ys: continue
        
        distances = {y: (prof_r[y] + adv_l) - prof_l[y] for y in common_ys}
        min_dist = min(distances.values())
        
        # --- ENHANCED SHARP WEDGE DETECTION ---
        tolerance = 15
        bottleneck_slices = [y for y, d in distances.items() if d <= min_dist + tolerance]
        num_slices = len(common_ys)
        
        # Detect sharp points and apply a dynamic tuck based on the font's natural width
        is_sharp_contact = len(bottleneck_slices) <= max(3, int(num_slices * 0.12))
        sharp_modifier = -int(font_avg_width * 0.06) if is_sharp_contact else 0 
        
        shape_l = profiles[left]["shape_right"] 
        shape_r = profiles[right]["shape_left"] 
        
        optical_modifier = 0
        if shape_l == "STRAIGHT" and shape_r == "STRAIGHT": optical_modifier = 15 
        elif shape_l == "ROUND" and shape_r == "ROUND": optical_modifier = -10 
        elif (shape_l == "ROUND" and shape_r == "STRAIGHT") or (shape_l == "STRAIGHT" and shape_r == "ROUND"): optical_modifier = -5
        elif shape_l == "SLOPE_OUT" and shape_r == "SLOPE_IN": optical_modifier = -25 
        elif shape_l == "SLOPE_IN" and shape_r == "SLOPE_OUT": optical_modifier = -25 
        
        if h_r < h_l * 0.35 or h_l < h_r * 0.35:
            optical_modifier -= 10

        adjusted_target = target_gap + optical_modifier + sharp_modifier
        kern_val = adjusted_target - min_dist
        
        actual_distance = min_dist + kern_val
        if actual_distance < min_clearance:
            kern_val += (min_clearance - actual_distance)
            
        overlap_h = max(common_ys) - min(common_ys)
        is_tucking = overlap_h < (h_l * 0.4) or overlap_h < (h_r * 0.4)
        
        if is_tucking:
            base_adv = max(adv_l, adv_r)
            tuck_boost = 1.3
        else:
            base_adv = min(adv_l, adv_r)
            tuck_boost = 1.0
            
        max_negative_kern = -abs(base_adv * safe_ratio * tuck_boost)
        if abs(max_negative_kern) > max_cap: max_negative_kern = -max_cap
            
        if kern_val < max_negative_kern: kern_val = max_negative_kern
            
        kern_val = int(round(kern_val / 5.0) * 5)
        if abs(kern_val) > 2: 
            kern_pairs[(left, right)] = kern_val
            
    # --- UPGRADED CONTEXTUAL TRIPLET SCANNER (Solves P.T stagger) ---
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
                
                max_p_y = max(profiles[p]["right"].keys()) if profiles[p]["right"] else 0
                
                # Create a total vertical bounding box of the upper elements of both letters
                prof_ll = profiles[l]["right"]
                prof_rr = profiles[r]["left"]
                l_upper_ys = [y for y in prof_ll.keys() if y > max_p_y]
                r_upper_ys = [y for y in prof_rr.keys() if y > max_p_y]
                
                if not l_upper_ys or not r_upper_ys: continue
                
                # Check absolute horizontal boundaries rather than exact Y slice matching
                max_l_x_above = max([prof_ll[y] for y in l_upper_ys])
                min_r_x_above = min([prof_rr[y] for y in r_upper_ys])
                
                adv_ll = profiles[l]["advance"]
                adv_pp = profiles[p]["advance"]
                
                # Calculate the projected physical gap between the two top overhangs
                projected_gap = (min_r_x_above + adv_ll + adv_pp + k_lp + k_pr) - max_l_x_above
                
                safe_triplet_clearance = min_clearance + 20
                if projected_gap < safe_triplet_clearance:
                    needed_extra = int(round((safe_triplet_clearance - projected_gap) / 5.0) * 5)
                    if needed_extra > 5:
                        contextual_rules.append(f"    pos {l} {p}' {needed_extra} {r};")
                        
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
        
        # Analyze font and set Smart Recommendations
        profiles, font_avg_w, font_avg_h = get_glyph_profiles(font)
        st.session_state.profiles = profiles
        st.session_state.font_avg_w = font_avg_w
        st.session_state.supported_chars = {chr(cp) for cp in font.getBestCmap().keys()}
        
        glyphs = [g for g in st.session_state.profiles.keys() if g not in [".notdef", "space"]]
        st.session_state.pairs = [(a, b) for a in glyphs for b in glyphs]
        
        # Smart Init Logic
        density = font_avg_w / font_avg_h if font_avg_h > 0 else 1
        st.session_state.rec_gap = 40 if density < 0.6 else 60 # Tighter gap for condensed fonts
        st.session_state.rec_overhang = 1 if density < 0.6 else 0 # Standard for condensed, Open for wide

    st.markdown("---")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        st.markdown("**Optical Spacing**")
        target_gap = st.slider("Target Gap", 0, 150, st.session_state.rec_gap, 5, label_visibility="collapsed")
    with col2:
        st.markdown("**Overhang**")
        overhang_mode = st.radio("Overhang", ["Open", "Standard", "Deep"], index=st.session_state.rec_overhang, horizontal=True, label_visibility="collapsed")
    
    use_kerning = st.toggle("✨ Apply LazyKern", True)
    
    bytes_data = st.session_state.original_bytes
    if use_kerning:
        font = TTFont(io.BytesIO(bytes_data))
        k, contextual_rules = calculate_kerning(
            st.session_state.profiles, 
            st.session_state.pairs, 
            target_gap, 
            overhang_mode, 
            st.session_state.font_avg_w
        )
        
        if k or contextual_rules:
            fea = ["feature kern {"]
            for (l, r), v in k.items(): fea.append(f"    pos {l} {r} {v};")
            for rule in contextual_rules: fea.append(rule)
            fea.append("} kern;")
            
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
