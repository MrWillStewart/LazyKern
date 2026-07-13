def get_glyph_profiles(font):
    glyph_set = font.getGlyphSet()
    ignore = {'.notdef', 'space', 'null', 'CR', 'nonmarkingreturn'}
    profiles = {}
    for name in font.getGlyphOrder():
        if name in ignore: continue
        pen = ProfilePen(glyph_set)
        try: glyph_set[name].draw(pen)
        except: continue
        if not pen.points: continue
        
        # --- NEW: STEM DETECTION ---
        # We analyze the points to see if the vertical edges are "flat"
        # If the X-coords change very little over a long Y-range, it's a stem.
        points = pen.points
        xs = [p[0] for p in points]
        
        # Calculate average "verticality" (Slope weight)
        # We categorize the glyph as 'vertical' if it has strong straight edges
        is_vertical = False
        if len(points) > 10:
            # Check if there's a long vertical segment
            vertical_segments = 0
            for i in range(len(points)-5):
                if abs(points[i][0] - points[i+5][0]) < 2: # X stays same
                    vertical_segments += 1
            if vertical_segments > len(points) * 0.3: # 30% of glyph is vertical
                is_vertical = True

        profiles[name] = {
            "points": points, 
            "advance": glyph_set[name].width,
            "min_x": min(xs), "max_x": max(xs),
            "is_vertical": is_vertical
        }
    return profiles

def calculate_kerning(profiles, target_gap=60):
    glyph_list = list(profiles.keys())
    pairs_to_kern = [(a, b) for a in glyph_list for b in glyph_list]
    kern_pairs = {}
    
    for left, right in pairs_to_kern:
        if left not in profiles or right not in profiles: continue
        
        # --- NEW: JIGSAW LOGIC ---
        # If both are vertical stems, we tighten the gap by 20 units
        # If one is a curve, we maintain the safety gap
        base_gap = target_gap
        if profiles[left]["is_vertical"] and profiles[right]["is_vertical"]:
            base_gap = target_gap - 25 # The Jigsaw effect: tighter
        elif not profiles[left]["is_vertical"] and not profiles[right]["is_vertical"]:
            base_gap = target_gap + 10 # Loose for curves
            
        # Collision scan
        needed_kern = base_gap - 100
        for lx, ly in profiles[left]["points"]:
            for rx, ry in profiles[right]["points"]:
                if abs(ly - ry) < 5:
                    dist = (rx + profiles[left]["advance"]) - lx
                    if dist < base_gap:
                        needed_kern = max(needed_kern, base_gap - dist)
        
        if needed_kern > 5:
            kern_pairs[(left, right)] = int(round(needed_kern / 5.0) * 5)
            
    return kern_pairs
