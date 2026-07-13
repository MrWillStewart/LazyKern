import streamlit as st
import io
import math
from fontTools.ttLib import TTFont
from fontTools.pens.basePen import BasePen
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString

# --- 1. CORE GEOMETRY ENGINE ---
class ProfilePen(BasePen):
    def __init__(self, glyph_set):
        super().__init__(glyph_set)
        self.points = []

    def _moveTo(self, p): 
        self.points.append(p)

    def _lineTo(self, p): 
        self.points.append(p)

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
    
    for glyph_name in glyph_set.keys():
        pen = ProfilePen(glyph_set)
        glyph = glyph_set[glyph_name]
        
        try:
            glyph.draw(pen)
        except Exception:
            continue
            
        if not pen.points: 
            continue
            
        slices = {}
        for x, y in pen.points:
            y_slice = int(round(y / step_size) * step_size)
            slices.setdefault(y_slice, []).append(x)
            
        left_profile, right_profile = {}, {}
        for y_slice, x_vals in slices.items():
            left_profile[y_slice] = min(x_vals)
            right_profile[y_slice] = max(x_vals)
            
        profiles[glyph_name] = {
            "left": left_profile, 
            "right": right_profile, 
            "advance": glyph.width,
            "nodes_count": len(pen.points)
        }
    return profiles

def analyze_character_set(font):
    cmap = font.getBestCmap()
    stats = {"type": "Standard Latin", "caps": 0, "lower": 0, "digits": 0, "punct": 0, "total": 0}
    if not cmap: 
        stats["type"] = "Unknown (No Cmap Table)"
        return stats
        
    for char_code in cmap.keys():
        try:
            char = chr(char_code)
            stats["total"] += 1
            if char.isupper(): stats["caps"] += 1
            elif char.islower(): stats["lower"] += 1
            elif char.isdigit(): stats["digits"] += 1
            elif char.isascii() and not char.isalnum() and not char.isspace(): stats["punct"] += 1
        except Exception:
            continue
            
    if stats["caps"] > 0 and stats["lower"] == 0:
        stats["type"] = "All Caps / Display"
    elif stats["total"] > 500:
        stats["type"] = "Extended / Multilingual"
        
    return stats

def calculate_kerning(profiles, pairs_to_kern, target_gap=40):
    kern_pairs = {}
    for left, right in pairs_to_kern:
        if left in profiles and right in profiles:
            prof_l = profiles[left]["right"]
            prof_r = profiles[right]["left"]
            common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
            if not common_ys: 
                continue
            # Distance formula taking glyph advance into account
            min_dist = min((prof_r[y] + profiles[left]["advance"]) - prof_l[y] for y in common_ys)
            kern_val = int(target_gap - min_dist)
            if abs(kern_val) > 2:
                kern_pairs[(left, right)] = int(round(kern_val / 5.0) * 5)
    return kern_pairs

# --- 2. STREAMLIT INTERFACE ---
st.set_page_config(page_title="LazyKern", layout="centered")

st.title("LazyKern ✒️")
st.write("A clean, dynamic font auto-kerning utility tool.")

uploaded_file = st.file_uploader("Upload Font (TTF/OTF)", type=["ttf", "otf"])

if uploaded_file:
    gap = st.slider("Target Gap Distance", min_value=10, max_value=100, value=40, step=5)
    
    if st.button("Analyze & Process Font"):
        with st.spinner("Executing geometric matrix scan..."):
            # 1. Load data
            font = TTFont(io.BytesIO(uploaded_file.read()))
            
            # 2. Extract telemetry
            stats = analyze_character_set(font)
            profiles = get_glyph_profiles(font)
            
            # 3. Generate kerning pairs
            glyphs = [g for g in profiles.keys() if g not in [".notdef", "space"]]
            pairs_to_kern = [(a, b) for a in glyphs for b in glyphs]
            kern_pairs = calculate_kerning(profiles, pairs_to_kern, target_gap=gap)
            
            # 4. Inject GPOS table
            fea_lines = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in kern_pairs.items()] + ["} kern;"]
            addOpenTypeFeaturesFromString(font, "\n".join(fea_lines))
            
            # 5. Output file compilation
            out = io.BytesIO()
            font.save(out)
            
            # 6. Display visual completion card
            st.success("Analysis Complete!")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric(label="Font Style Profile", value=stats["type"])
                st.metric(label="Total Scanned Characters", value=stats["total"])
            with col2:
                st.metric(label="Generated Kern Pairs", value=len(kern_pairs))
                st.metric(label="Glyph Node Count", value=sum(p["nodes_count"] for p in profiles.values()))
                
            st.download_button(
                label="📥 Download Kerned Font File", 
                data=out.getvalue(), 
                file_name=f"kerned_{uploaded_file.name}"
            )
