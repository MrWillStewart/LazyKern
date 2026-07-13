def get_glyph_profiles(font, step_size=5):
    glyph_set = font.getGlyphSet()
    profiles = {}
    for name in glyph_set.keys():
        pen = ProfilePen(glyph_set)
        try: glyph_set[name].draw(pen)
        except: continue
        if not pen.points: continue
        
        # Store both Position (x) and Slope (dx)
        # Slope is calculated by the difference between current point and previous
        left_prof, right_prof = {}, {}
        left_slopes, right_slopes = {}, {}
        
        # Organize points by Y-slice
        slices = {}
        for x, y in pen.points:
            y_slice = int(round(y / step_size) * step_size)
            slices.setdefault(y_slice, []).append(x)
            
        for y, x_vals in slices.items():
            left_prof[y] = min(x_vals)
            right_prof[y] = max(x_vals)
            # Calculate local slant (dx/dy)
            # We look at the average trend of the points in this slice
            left_slopes[y] = (left_prof[y] - left_prof.get(y - step_size, left_prof[y])) 
            right_slopes[y] = (right_prof[y] - right_prof.get(y - step_size, right_prof[y]))
        
        profiles[name] = {
            "left": left_prof, "right": right_prof,
            "l_slopes": left_slopes, "r_slopes": right_slopes,
            "advance": glyph_set[name].width
        }
    return profiles

def calculate_kerning(profiles, pairs_to_kern, target_gap=60):
    kern_pairs = {}
    # Base target gap for straight lines
    # We allow the solver to flex this based on slopes
    
    for left, right in pairs_to_kern:
        if left not in profiles or right not in profiles: continue
        
        prof_l = profiles[left]["right"]
        prof_r = profiles[right]["left"]
        slopes_l = profiles[left]["r_slopes"]
        slopes_r = profiles[right]["l_slopes"]
        
        common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
        if not common_ys: continue
        
        # Find the bottleneck
        bottleneck_y = min(common_ys, key=lambda y: (prof_r[y] + profiles[left]["advance"]) - prof_l[y])
        min_dist = (prof_r[bottleneck_y] + profiles[left]["advance"]) - prof_l[bottleneck_y]
        
        # --- VECTOR-BASED ADJUSTMENT ---
        # Calculate how parallel the edges are at the bottleneck
        slope_l = slopes_l[bottleneck_y]
        slope_r = slopes_r[bottleneck_y]
        
        # If slopes have the same sign, they are slanted in the same direction (Parallel)
        # Parallel edges allow for tighter nesting. 
        # Divergent edges (different signs) require more distance.
        nesting_factor = 0
        if slope_l * slope_r > 0: # Both slant same way
            nesting_factor = -15 # Tighten because they nest
        elif slope_l * slope_r < 0: # Slant opposite ways
            nesting_factor = 10  # Push apart to prevent collision
            
        final_target = target_gap + nesting_factor
        kern_val = int(final_target - min_dist)
        
        if abs(kern_val) > 2:
            kern_pairs[(left, right)] = int(round(kern_val / 5.0) * 5)
            
    return kern_pairs        if not pen.points: continue
        
        slices = {}
        for x, y in pen.points:
            y_slice = int(round(y / step_size) * step_size)
            slices.setdefault(y_slice, []).append(x)
        
        profiles[name] = {
            "left": {y: min(x) for y, x in slices.items()},
            "right": {y: max(x) for y, x in slices.items()},
            "advance": glyph_set[name].width
        }
    return profiles

def calculate_kerning(profiles, pairs_to_kern, target_gap=60):
    kern_pairs = {}
    
    # PURE GEOMETRIC SOLVER
    # No classes, no assumptions, just distance calculation.
    for left, right in pairs_to_kern:
        if left not in profiles or right not in profiles: continue
        
        prof_l = profiles[left]["right"]
        prof_r = profiles[right]["left"]
        common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
        
        if not common_ys: continue
        
        # We need the kerning value that ensures NO point is closer than target_gap.
        # Logic: Current_Distance + Kern = Target_Gap
        # Therefore: Kern = Target_Gap - Current_Distance
        # We must find the maximum 'Kern' needed (the bottleneck point).
        
        max_needed_kern = -9999
        advance_l = profiles[left]["advance"]
        
        for y in common_ys:
            current_dist = (prof_r[y] + advance_l) - prof_l[y]
            needed = target_gap - current_dist
            if needed > max_needed_kern:
                max_needed_kern = needed
        
        if max_needed_kern > 2:
            kern_pairs[(left, right)] = int(round(max_needed_kern / 5.0) * 5)
            
    return kern_pairs

# --- 2. STREAMLIT RUNTIME ---
st.set_page_config(page_title="LazyKern", layout="centered")
inject_pro_cleaner()

st.title("LazyKern")
uploaded_file = st.file_uploader("Upload Font", type=["ttf", "otf"])

if uploaded_file:
    font_bytes = uploaded_file.read()
    font = TTFont(io.BytesIO(font_bytes))
    profiles = get_glyph_profiles(font)
    glyphs = [g for g in profiles.keys() if g not in [".notdef", "space"]]
    pairs = [(a, b) for a in glyphs for b in glyphs]

    gap = st.slider("Target Gap (Tightness)", 10, 100, 60, 5)
    
    if st.toggle("Apply Auto-Kerning", True):
        kern_pairs = calculate_kerning(profiles, pairs, target_gap=gap)
        if kern_pairs:
            fea = ["feature kern {"] + [f"    pos {l} {r} {v};" for (l, r), v in kern_pairs.items()] + ["} kern;"]
            addOpenTypeFeaturesFromString(font, "\n".join(fea))
        
        out = io.BytesIO()
        font.save(out)
        active_bytes = out.getvalue()
    else:
        active_bytes = font_bytes

    b64 = base64.b64encode(active_bytes).decode('utf-8')
    st.markdown(f"""<style>@font-face {{font-family: 'LiveFont'; src: url('data:font/ttf;charset=utf-8;base64,{b64}');}} .tester {{font-family: 'LiveFont'; font-size: 48px; width: 100%;}}</style>""", unsafe_allow_html=True)
    st.markdown('<textarea class="tester">AVAW ST GR TEST.</textarea>', unsafe_allow_html=True)
    st.download_button("Download Kerned Font", active_bytes, f"kerned_{uploaded_file.name}")
