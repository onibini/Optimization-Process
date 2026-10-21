# Optimization Conventions and Coordinate Mapping Reference (for LLM)

This document describes the key mathematical conventions, vector formats, and geometric representations used in the optimization models.

---

## 0. Positivity Rule for Design Variables

**Every design variable is strictly positive.** This covers the radius $R$, the cylindrical draft $D$, and all WEC coordinates $x_i, y_i$ in the optimization vector.
- Search bounds in `config.cfg` must satisfy $0 < \text{Min} < \text{Max}$ for every variable used by the selected mode. `FixedRadius`, `FixedDraft`, `MinSpacing` and `StepSize` must also be $> 0$.
- This is checked when the problem is built (`get_shape_config` / `get_layout_config` / `get_joint_config` → `src/utils/validation.py`) and raises `ConfigValidationError` listing every offending variable.
- Because every candidate is clipped to $[\text{Min}, \text{Max}]$ during grid quantization, all evaluated vectors stay positive during the whole optimization.
- The *mirrored* bodies of side pairs are placed at $-y_i$ by the mapper; that is a derived physical coordinate, not a design variable.
- The total draft of the body is $D + R$ (hemispherical bottom of radius $R$ under the cylinder of length $D$).

---

## 1. WEC Array Symmetry Model

To reduce the dimensionality of the search space, WEC arrays are assumed to be symmetric with respect to the X-axis ($y = 0$).
- **WEC 1** (Center WEC): Always placed on the X-axis (coordinates: $(x_1, 0.0)$).
- **WEC 2 & 3** (Side WEC Pairs): Mirror-placed across the X-axis.
  - If a side WEC is at $(x_2, y_2)$, its symmetric partner is at $(x_2, -y_2)$.
  - Consequently, each side pair adds 2 variables to the vector but defines 2 physical bodies in the simulation.
  - Variable $y_i$ is strictly positive ($y_i > 0$), so a side WEC never coincides with its mirror image.

---

## 2. Optimization Vector Formats

Depending on the `OptMode` (1, 2, or 3) and `NumWECs` (1, 3, or 5), the structure of the 1D parameter array `vector` changes as follows:

| OptMode | NumWECs | Dimensions | Vector Layout Description | Vector Array Index Diagram |
| :--- | :--- | :--- | :--- | :--- |
| **1: Shape Only** | 1 | 2 | `[Radius, Draft]` | `[0: R, 1: D]` |
| **2: Layout Only**| 1 | 1 | `[x1]` | `[0: x1]` |
| | 3 | 3 | `[x1, x2, y2]` | `[0: x1, 1: x2, 2: y2]` |
| | 5 | 5 | `[x1, x2, y2, x3, y3]` | `[0: x1, 1: x2, 2: y2, 3: x3, 4: y3]` |
| **3: Joint Both** | 1 | 3 | `[Radius, Draft, x1]` | `[0: R, 1: D, 2: x1]` |
| | 3 | 5 | `[Radius, Draft, x1, x2, y2]` | `[0: R, 1: D, 2: x1, 3: x2, 4: y2]` |
| | 5 | 7 | `[Radius, Draft, x1, x2, y2, x3, y3]` | `[0: R, 1: D, 2: x1, 3: x2, 4: y2, 5: x3, 6: y3]` |

---

## 3. Vector Canonicalization (Symmetry & Order Independence)

### The Redundancy Problem
When `NumWECs == 5`, the vector contains two side pairs: WEC2 $(x_2, y_2)$ and WEC3 $(x_3, y_3)$.
Because the WECs are physically identical, their order in the vector does not affect the physical layout.
For example, the layout defined by:
- $V_A = [x_1, \mathbf{15.0, 20.0}, \mathbf{25.0, 30.0}]$
- $V_B = [x_1, \mathbf{25.0, 30.0}, \mathbf{15.0, 20.0}]$

represent the **exact same physical coordinates** and produce identical power output. However, without canonicalization:
1. The optimization algorithm searches redundant spaces (slowing convergence).
2. The memory cache misses, causing redundant, slow WAMIT runs.

### The Solution: Lexicographical In-place Sorting
To eliminate this redundancy, we apply `canonicalize_vector_inplace` to any trial vector before checking the cache or evaluating:
1. Extract $(x_2, y_2)$ and $(x_3, y_3)$ based on the mode offset.
2. Compare them lexicographically: first by $x$, then by $y$.
3. If $(x_2, y_2) > (x_3, y_3)$, swap their values in the vector.

This guarantees that the vector is always represented in its ascending sorted state, i.e., $(x_2, y_2) \le (x_3, y_3)$, which solves the caching and search-space redundancy.

PSO and CMA-ES pass a canonicalized *copy* to the evaluator so their internal state (particle position/velocity, sampled points) is not reordered; their reported best designs are canonical.
