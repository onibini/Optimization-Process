# Optimization Conventions and Coordinate Mapping Reference (for LLM)

This document describes the key mathematical conventions, vector formats, and geometric representations used in the optimization models.

---

## 1. WEC Array Symmetry Model

To reduce the dimensionality of the search space, WEC arrays are assumed to be symmetric with respect to the X-axis ($y = 0$).
- **WEC 1** (Center WEC): Always placed on the X-axis (coordinates: $(x_1, 0.0)$).
- **WEC 2 & 3** (Side WEC Pairs): Mirror-placed across the X-axis. 
  - If a side WEC is at $(x_2, y_2)$, its symmetric partner is at $(x_2, -y_2)$.
  - Consequently, each side pair adds 2 variables to the vector but defines 2 physical bodies in the simulation.
  - Variable $y_i$ is kept non-negative ($y_i \ge 0$).

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
