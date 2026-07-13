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
    </style>
    """, unsafe_allow_html=True)

# --- 1. CORE GEOMETRY ENGINE ---
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

# --- TYPOGRAPHIC KNOWLEDGE ENGINE (THE INTELLIGENCE LAYER) ---
def get_optical_class(glyph_name):
    """Categorizes glyph profiles to apply structural typographic offsets."""
    name = glyph_name.lower().strip('_')
    
    # Punctuation bounds behave erratically compared to letterforms
    if name in ['period', 'comma', 'colon', 'semicolon', 'hyphen', 'exclam', 'question', 'dot']:
        return 'PUNCTUATION'
    # Open / Diagonal structures create visual vacuum zones but hazard points at terminal edges
    if name in ['t', 'v', 'w', 'y', 'a', 'x', 'f', 'k', 'l']:
        return 'DIAGONAL_OPEN'
    # Round structures create soft visual whitespace edges
    if name in ['o', 'c', 'q', 'g', 'e', 'd', 'p', 'b']:
        return 'ROUND'
    # Straight parallel configurations demand higher breathing room to prevent optical choking
    if name in ['h', 'i', 'm', 'n', 'u', 'j', 'r']:
        return 'STRAIGHT'
    return 'DEFAULT'

def calculate_kerning(profiles, pairs_to_kern, target_gap=60):
    kern_pairs = {}
    
    # Strict physical floor threshold (In font units). Outlines cannot cross closer than this.
    ABS_SAFE_CLEARANCE = 15 

    for left, right in pairs_to_kern:
        if left in profiles and right in profiles:
            prof_l = profiles[left]["right"]
            prof_r = profiles[right]["left"]
            common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
            if not common_ys: continue
            
            # 1. Apply Typographic Optical Adjustments
            class_l = get_optical_class(left)
            class_r = get_optical_class(get_optical_class(right))
            
            optical_modifier = 0
            if class_l == 'STRAIGHT' and class_r == 'STRAIGHT':
                optical_modifier += 12  # Give parallel straight lines slightly more padding
            elif class_l == 'ROUND' and class_r == 'ROUND':
                optical_modifier -= 10  # Pull rounds tighter together safely
            elif (class_l == 'DIAGONAL_OPEN' and class_r == 'PUNCTUATION') or (class_l == 'PUNCTUATION' and class_r == 'DIAGONAL_OPEN'):
                optical_modifier -= 20  # Tuck punctuation under overhangs aggressively
            elif class_l == 'DIAGONAL_OPEN' and class_r == 'DIAGONAL_OPEN':
                optical_modifier -= 4   # Let diagonals interlock tightly

            adjusted_target = target_gap + optical_modifier
            
            # Base geometric math execution
            min_dist = min((prof_r[y] + profiles[left]["advance"]) - prof_l[y] for y in common_ys)
            kern_val = int(adjusted_target - min_dist)
            
            # 2. THE ANTI-CLASH ENGINE (Matrix Collision Safeguard)
            # Simulates the spatial distribution across every single horizontal layer post-kerning
            for y in common_ys:
                projected_physical_space = (prof_r[y] + profiles[left]["advance"] + kern_val) - prof_l[y]
                if projected_physical_space < ABS_SAFE_CLEARANCE:
                    # Over-interpolation detected. Dial back the adjustment to match the protective floor.
                    clash_overlap_compensation = ABS_SAFE_CLEARANCE - projected_physical_space
                    kern_val -= int(math.ceil(clash_overlap_compensation))

            if abs(kern_val) > 2:
                kern_pairs[(left, right)] = int(round(kern_val / 5.0) * 5)
                
    return kern_pairs

# --- 2. STREAMLIT RUNTIME ---
st.set_page_config(page_title="LazyKern", layout="centered")
inject_pro_cleaner()

st.title("LazyKern")
uploaded_file = st.file_uploader("Upload Font (TTF/OTF)", type=["ttf", "otf"])

if uploaded_file:
    # High-Performance Memory Caching Layer
    if "filename" not in st.session_state or st.session_state.filename != uploaded_file.name:
        with st.spinner("Analyzing font geometry profiles..."):
            font_bytes = uploaded_file.read()
            st.session_state.original_bytes = font_bytes
            st.session_state.filename = uploaded_file.name
            
            font = TTFont(io.BytesIO(font_bytes))
            st.session_state.profiles = get_glyph_profiles(font)
            glyphs = [g for g in st.session_state.profiles.keys() if g not in [".notdef", "space"]]
            st.session_state.pairs = [(a, b) for a in glyphs for b in glyphs]

    # Dynamic Control Mechanics
    gap = st.slider("Target Gap (Tightness)", min_value=10, max_value=100, value=60, step=5)
    use_kerning = st.toggle("Apply Auto-Kerning", value=True)
    
    # Real-Time Kerning Matrix Calculation Pipeline
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

    # Inline Live Font Delivery Matrix
    b64_font = base64.b64encode(active_font_bytes).decode('utf-8')
    font_fmt = "opentype" if uploaded_file.name.lower().endswith('.otf') else "truetype"
    
    st.markdown(f"""
        <style>
            @font-face {{
                font-family: 'LiveFont';
                src: url('data:font/{font_fmt};charset=utf-8;base64,{b64_font}') format('{font_fmt}');
            }}
            .tester-box {{
                font-family: 'LiveFont', sans-serif !important;
                font-size: 48px;
                width: 100%;
                min-height: 140px;
                padding: 15px;
                margin-top: 10px;
                margin-bottom: 20px;
                border: 1px solid #DAE1E8;
                border-radius: 10px;
                color: #000000;
                line-height: 1.2;
                resize: vertical;
            }}
        </style>
    """, unsafe_allow_html=True)

    st.subheader("Live Preview")
    st.markdown('<textarea class="tester-box">AVAW YOU TEST.</textarea>', unsafe_allow_html=True)

    st.download_button(
        label="📥 Download Kerned Font File", 
        data=active_font_bytes, 
        file_name=f"kerned_{uploaded_file.name}"
    )
