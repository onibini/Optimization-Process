"""STEP file of the Shape 1 body for cad2bem: a cylinder of radius R and length D fused with a sphere of radius R
centred at z = -D (total draft D + R), the top 1 m above the waterline (cad2bem cuts it at z = 0).

The numbers are metres; gmsh labels the STEP file in millimetres, so read it with ``cad2bem --unit m``.

    python scripts/make_hemisphere_step.py RADIUS DRAFT OUT.step   (needs gmsh)
"""

import sys

import gmsh


def main(radius, draft, out):
    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    occ = gmsh.model.occ
    cylinder = occ.addCylinder(0, 0, -draft, 0, 0, draft + 1.0, radius)
    sphere = occ.addSphere(0, 0, -draft, radius)
    occ.fuse([(3, cylinder)], [(3, sphere)])
    occ.synchronize()
    gmsh.write(out)
    gmsh.finalize()


if __name__ == "__main__":
    main(float(sys.argv[1]), float(sys.argv[2]), sys.argv[3])
