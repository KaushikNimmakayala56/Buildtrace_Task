def diff(a, b):
    """Compare two drawing versions and return changes."""
    a_dict = {obj["id"]: obj for obj in a}
    b_dict = {obj["id"]: obj for obj in b}
    
    added_ids = set(b_dict.keys()) - set(a_dict.keys())
    removed_ids = set(a_dict.keys()) - set(b_dict.keys())
    common_ids = set(a_dict.keys()) & set(b_dict.keys())
    
    def get_center(obj):
        return (obj["x"] + obj["width"] / 2, obj["y"] + obj["height"] / 2)
    
    def distance_between(obj1, obj2):
        c1, c2 = get_center(obj1), get_center(obj2)
        return ((c2[0] - c1[0])**2 + (c2[1] - c1[1])**2)**0.5
    
    def find_nearby(obj, all_objs, threshold=5):
        for other_id, other_obj in all_objs.items():
            if other_id != obj["id"] and distance_between(obj, other_obj) < threshold:
                return other_id
        return None
    
    added = []
    removed = []
    moved = []
    
    for obj_id in added_ids:
        obj = b_dict[obj_id]
        nearby = find_nearby(obj, b_dict, threshold=5)
        location = f"near {nearby}" if nearby else f"at {obj['x']},{obj['y']}"
        added.append(f"{obj_id} ({obj['type']} {location})")
    
    for obj_id in removed_ids:
        obj = a_dict[obj_id]
        removed.append(f"{obj_id} ({obj['type']} at {obj['x']},{obj['y']})")
    
    for obj_id in common_ids:
        old, new = a_dict[obj_id], b_dict[obj_id]
        if old["x"] != new["x"] or old["y"] != new["y"]:
            dx, dy = new["x"] - old["x"], new["y"] - old["y"]
            distance = round((dx**2 + dy**2)**0.5, 1)
            direction = ""
            if dy < 0: direction = "south"
            if dy > 0: direction = "north"
            if dx > 0: direction += "east"
            if dx < 0: direction += "west"
            moved.append(f"{obj_id} moved {distance} units {direction}")
    
    summary_parts = moved + [f"{a} added" for a in added] + [f"{r} removed" for r in removed]
    summary = "; ".join(summary_parts) + "." if summary_parts else "No changes detected."
    
    return {
        "added": added,
        "removed": removed,
        "moved": moved,
        "summary": summary
    }