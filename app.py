def get_glyph_profiles(font, step_size=5):
    glyph_set = font.getGlyphSet()
    profiles = {}
    for name in glyph_set.keys():
        pen = ProfilePen(glyph_set)
        try: 
            glyph_set[name].draw(pen)
        except: 
            continue
        
        if not pen.points: 
            continue
        
        left_prof, right_prof = {}, {}
        left_slopes, right_slopes = {}, {}
        
        slices = {}
        for x, y in pen.points:
            y_slice = int(round(y / step_size) * step_size)
            slices.setdefault(y_slice, []).append(x)
            
        for y, x_vals in slices.items():
            left_prof[y] = min(x_vals)
            right_prof[y] = max(x_vals)
            # Calculate local slant (dx/dy)
            # Trend of the points in this slice vs the one below it
            prev_l = left_prof.get(y - step_size, left_prof[y])
            prev_r = right_prof.get(y - step_size, right_prof[y])
            left_slopes[y] = left_prof[y] - prev_l
            right_slopes[y] = right_prof[y] - prev_r
        
        profiles[name] = {
            "left": left_prof, 
            "right": right_prof,
            "l_slopes": left_slopes, 
            "r_slopes": right_slopes,
            "advance": glyph_set[name].width
        }
    return profiles

def calculate_kerning(profiles, pairs_to_kern, target_gap=60):
    kern_pairs = {}
    
    for left, right in pairs_to_kern:
        if left not in profiles or right not in profiles: 
            continue
        
        prof_l = profiles[left]["right"]
        prof_r = profiles[right]["left"]
        slopes_l = profiles[left]["r_slopes"]
        slopes_r = profiles[right]["l_slopes"]
        
        common_ys = set(prof_l.keys()).intersection(set(prof_r.keys()))
        if not common_ys: 
            continue
        
        # Find the bottleneck (tightest point)
        bottleneck_y = min(common_ys, key=lambda y: (prof_r[y] + profiles[left]["advance"]) - prof_l[y])
        min_dist = (prof_r[bottleneck_y] + profiles[left]["advance"]) - prof_l[bottleneck_y]
        
        # --- VECTOR-BASED ADJUSTMENT ---
        slope_l = slopes_l[bottleneck_y]
        slope_r = slopes_r[bottleneck_y]
        
        # If slopes have the same sign, they are slanted in the same direction (Parallel/Nesting)
        # We tighten the gap by 15. If opposite, we push by 10 to avoid collision.
        nesting_factor = 0
        if slope_l * slope_r > 0: 
            nesting_factor = -15 
        elif slope_l * slope_r < 0: 
            nesting_factor = 10  
            
        final_target = target_gap + nesting_factor
        kern_val = int(final_target - min_dist)
        
        if abs(kern_val) > 2:
            kern_pairs[(left, right)] = int(round(kern_val / 5.0) * 5)
            
    return kern_pairs
