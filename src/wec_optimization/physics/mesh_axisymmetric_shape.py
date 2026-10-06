"""Generate the quarter-symmetric cylinder/hemisphere mesh used by WAMIT."""

from pathlib import Path

import numpy as np


def generate_cylinder_hemisphere_mesh(
    radius,
    draft_cylinder,
    max_elements=500,
    output_path=None,
    display_mesh=False,
):
    """Generate and optionally export a cylinder with a hemispherical bottom."""
    radius = float(radius)
    draft_cylinder = float(draft_cylinder)
    max_elements = int(max_elements)
    if radius <= 0 or draft_cylinder <= 0:
        raise ValueError("Radius and cylinder draft must be positive.")
    if max_elements < 1:
        raise ValueError("Maximum element count must be positive.")

    side_length = draft_cylinder
    arc_length = radius * np.pi / 2
    circumference = 2 * np.pi * radius
    target_mesh_size = np.sqrt((side_length + arc_length) * circumference / max_elements)

    side_segments = max(2, int(side_length / target_mesh_size))
    hemisphere_segments = max(2, int(arc_length / target_mesh_size))
    angular_segments = max(2, int(circumference / target_mesh_size) // 2)

    profile = get_cylinder_hemisphere_profile(
        radius,
        draft_cylinder,
        side_segments,
        hemisphere_segments,
    )
    nodes, quads, triangles = revolve_profile(profile, angular_segments)
    process_in_gmsh(
        nodes,
        quads,
        triangles,
        output_path=output_path,
        display=display_mesh,
    )


def get_cylinder_hemisphere_profile(
    radius: float,
    draft_cylinder: float,
    side_segments: int,
    hemisphere_segments: int,
) -> np.ndarray:
    """Return an ``(r, z)`` profile without duplicate junction or pole points."""
    if side_segments < 1 or hemisphere_segments < 1:
        raise ValueError("Profile segment counts must be positive.")

    profile = [
        (radius, -draft_cylinder * index / side_segments) for index in range(side_segments + 1)
    ]
    for index in range(1, hemisphere_segments + 1):
        phi = np.pi / 2 * index / hemisphere_segments
        radial_position = 0.0 if index == hemisphere_segments else radius * np.cos(phi)
        depth = -draft_cylinder - radius * np.sin(phi)
        profile.append((radial_position, depth))

    return np.asarray(profile, dtype=float)


def revolve_profile(profile_points, num_angular_segments: int, theta_revolve=90):
    """Revolve a profile and return flattened nodes and panel connectivity."""
    if num_angular_segments < 1:
        raise ValueError("Angular segment count must be positive.")

    profile = np.asarray(profile_points, dtype=float)
    if profile.ndim != 2 or profile.shape[1] != 2 or len(profile) < 2:
        raise ValueError("Profile must contain at least two (radius, depth) points.")
    if np.any(profile[:, 0] < 0):
        raise ValueError("Profile radii must be non-negative.")

    nodes = []
    quads = []
    triangles = []
    node_indices = {}
    pole_rows = []
    next_node_tag = 1

    for row, (radius, depth) in enumerate(profile):
        is_pole = np.isclose(radius, 0.0, atol=1e-12)
        pole_rows.append(is_pole)
        if is_pole:
            nodes.extend([0.0, 0.0, depth])
            for column in range(num_angular_segments + 1):
                node_indices[(row, column)] = next_node_tag
            next_node_tag += 1
            continue

        for column in range(num_angular_segments + 1):
            theta = np.deg2rad(theta_revolve) * column / num_angular_segments
            nodes.extend([radius * np.cos(theta), radius * np.sin(theta), depth])
            node_indices[(row, column)] = next_node_tag
            next_node_tag += 1

    for row in range(len(profile) - 1):
        if pole_rows[row] and pole_rows[row + 1]:
            continue

        for column in range(num_angular_segments):
            n1 = node_indices[(row, column)]
            n2 = node_indices[(row, column + 1)]
            n3 = node_indices[(row + 1, column + 1)]
            n4 = node_indices[(row + 1, column)]

            if pole_rows[row]:
                triangles.extend([n1, n4, n3])
            elif pole_rows[row + 1]:
                triangles.extend([n1, n3, n2])
            else:
                quads.extend([n1, n4, n3, n2])

    return nodes, quads, triangles


def process_in_gmsh(nodes, quads, triangles, output_path=None, display=False):
    """Load raw mesh data into Gmsh and optionally export or display it."""
    import gmsh

    gmsh.initialize()
    try:
        surface_tag = 1
        gmsh.model.add("WEC_Cylinder_Hemisphere")
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.addDiscreteEntity(2, surface_tag)

        node_tags = list(range(1, len(nodes) // 3 + 1))
        gmsh.model.mesh.addNodes(2, surface_tag, node_tags, nodes)

        next_element_tag = 1
        if quads:
            quad_count = len(quads) // 4
            quad_tags = list(range(next_element_tag, next_element_tag + quad_count))
            gmsh.model.mesh.addElements(2, surface_tag, [3], [quad_tags], [quads])
            next_element_tag += quad_count

        if triangles:
            triangle_count = len(triangles) // 3
            triangle_tags = list(range(next_element_tag, next_element_tag + triangle_count))
            gmsh.model.mesh.addElements(
                2,
                surface_tag,
                [2],
                [triangle_tags],
                [triangles],
            )

        if output_path:
            output_path = Path(output_path)
            if output_path.suffix.lower() == ".msh":
                gmsh.write(str(output_path))
            elif output_path.suffix.lower() == ".gdf":
                exported_node_tags, node_coords, _ = gmsh.model.mesh.getNodes()
                panel_types, panel_tags, panel_nodes = gmsh.model.mesh.getElements(dim=2)
                _write_gdf(
                    output_path,
                    exported_node_tags,
                    node_coords,
                    panel_types,
                    panel_tags,
                    panel_nodes,
                )
            else:
                raise ValueError(f"Unsupported mesh output format: {output_path.suffix}")

        if display:
            gmsh.option.setNumber("Mesh.SurfaceEdges", 1)
            gmsh.option.setNumber("Mesh.Normals", 20)
            gmsh.fltk.run()
    finally:
        gmsh.finalize()


def _write_gdf(
    output_path,
    node_tags,
    node_coords,
    panel_types,
    panel_tags,
    panel_nodes,
    gravity=9.80665,
    symmetry_x=1,
    symmetry_y=1,
):
    """Write Gmsh surface panels in WAMIT GDF format."""
    node_map = {
        tag: tuple(node_coords[3 * index : 3 * index + 3]) for index, tag in enumerate(node_tags)
    }
    panel_count = sum(
        len(panel_tags[index])
        for index, element_type in enumerate(panel_types)
        if element_type in {2, 3}
    )
    if panel_count == 0:
        raise ValueError("Mesh contains no triangle or quadrilateral surface panels.")

    with Path(output_path).open("w", encoding="utf-8", newline="\n") as output:
        output.write(" WAMIT GDF file exported from Gmsh\n")
        output.write(f"{1.0:12.6f} {gravity:12.6f}      ULEN GRAV\n")
        output.write(f"{symmetry_x:12d} {symmetry_y:12d}      ISX  ISY\n")
        output.write(f"{panel_count:12d}      NEQN\n")

        for index, element_type in enumerate(panel_types):
            nodes_per_panel = {2: 3, 3: 4}.get(element_type)
            if nodes_per_panel is None:
                continue

            tags = panel_nodes[index]
            for start in range(0, len(tags), nodes_per_panel):
                coordinates = [node_map[tag] for tag in tags[start : start + nodes_per_panel]]
                if element_type == 2:
                    coordinates.insert(1, coordinates[0])
                for x, y, z in coordinates:
                    output.write(f"{x:13.6e} {y:13.6e} {z:13.6e}\n")
