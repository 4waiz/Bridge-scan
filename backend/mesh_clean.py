import trimesh


def clean_and_decimate(mesh: trimesh.Trimesh) -> trimesh.Trimesh:
    mesh.remove_unreferenced_vertices()

    try:
        mesh.fill_holes()
    except:
        pass

    try:
        mesh.remove_degenerate_faces()
    except:
        pass

    try:
        mesh.merge_vertices()
    except:
        pass

    try:
        mesh.remove_infinite_values()
    except:
        pass

    mesh.remove_unreferenced_vertices()

    # If still broken, force convex repair fallback
    if not mesh.is_watertight:
        try:
            mesh = mesh.convex_hull
        except:
            pass

    return mesh