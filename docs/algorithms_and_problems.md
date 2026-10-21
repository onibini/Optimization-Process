# Optimization Algorithms and Problem Formulations (for LLM)

This document describes the mathematical formulation of the optimization problem, the fitness objective, constraints, and the parameters of the optimization engines.

---

## 1. Objective Function & Fitness Evaluation

The goal is to maximize the **total wave power absorbed by the WEC array** (ideal linear PTO, heave only).
The fitness returned is the total absorbed power $P_{\text{total}}$ in Watts:

$$f(\vec{v}) = P_{\text{total}}(\vec{v}) = \sum_k \int B_{\text{PTO},k}\,\omega^2 |\text{RAO}_k(\omega)|^2 S(\omega)\,d\omega$$

### Hydrodynamic Simulation with WAMIT
For valid configurations, the evaluation runs a boundary element method solver (WAMIT):
1. **Mesh Generation**: Generates a cylinder-hemisphere quarter-model GDF mesh based on $R$ (radius) and $D$ (cylindrical draft). The total draft is $D + R$. The panel count per body is set directly by `MeshPanels` (hemisphere: cubed-sphere patches without pole fans; cylinder: quads with the same angular division). Because 32-bit WAMIT runs out of memory when (`MeshPanels` × number of bodies) exceeds about 1,100 and run time grows with roughly the 2.5–3rd power of the panel count, keep `MeshPanels` × `NumWECs` modest (see `config.cfg`).
2. **Radiation/Diffraction Analysis**: WAMIT solves the velocity potentials and calculates the hydrodynamic coefficients (added mass $A(\omega)$, radiation damping $B(\omega)$, and wave excitation forces $F_{\text{exc}}(\omega)$) for $\omega = 0.5 \sim 3.0$ rad/s ($\Delta\omega = 0.05$), heading 0°.
3. **RAO & Power Calculation**:
   - $B_{\text{PTO},k}$ is set to the radiation damping $B_{kk}(\omega_n)$ at the peak frequency of the uncontrolled RAO of body $k$.
   - Solve the equations of motion with this PTO to obtain Response Amplitude Operators (RAO).
   - Integrate the power extraction across the selected wave spectrum (JONSWAP, ITTC or Goda form) with Simpson's rule.

---

## 2. Constraints & Penalty Method

### Spacing Constraint
To prevent WEC cylinders from colliding or overlapping, they must maintain a minimum clear spacing:
- Let $R$ be the WEC radius.
- Let $s_{\text{min\_spacing}}$ be the minimum center-to-center distance coefficient.
- For any WEC pair $i$ and $j$ located at $(x_i, y_i)$ and $(x_j, y_j)$, the Euclidean distance $D_{ij}$ must satisfy:

$$D_{ij} \ge R \times s_{\text{min\_spacing}}$$

### Boundary Constraints
Lower and upper bounds for each parameter are defined in `config.cfg`. **All design variables are strictly positive**: every bound must satisfy $0 < \text{Min} < \text{Max}$ (checked at start-up, `ConfigValidationError` otherwise). Each variable $j$ has its own grid step $\Delta_j$ (`{Var}Step` in `config.cfg`, default `StepSize`). Candidate vectors are repaired to the nearest grid point and kept inside the valid search range:

$$\vec{k} = \text{round}\left((\vec{v} - \vec{v}_{\text{lower}}) / \Delta\right)$$

$$\vec{v}_{\text{grid}} = \vec{v}_{\text{lower}} + \vec{k}\Delta$$

### Penalty Evaluation
If a layout violates the spacing constraint ($D_{ij} < R \times s_{\text{min\_spacing}}$), a penalty is returned **immediately without running WAMIT** (`src/utils/geometry.py: penalty_result`):

$$\text{Fitness} = -10^6 \times \text{violation\_distance}$$

The result carries `info = {"penalized": True}`, so penalty evaluations are logged (`penalized` column) and counted separately from real WAMIT runs.

---

## 3. Optimization Algorithms

The system implements four distinct optimization engines. All engines use the shared `CachedEvaluator` to quantize vectors to the configured `StepSize`, canonicalize symmetric layouts, and query a grid-indexed in-memory cache before running the expensive physics evaluation. DE, GA and CMA-ES require `PopSize >= 4`.

### 1. Differential Evolution (DE)
- **Strategy**: `DE/rand/1/bin`
- **Equation**: $\vec{u}_i = \vec{x}_{r_1} + F \cdot (\vec{x}_{r_2} - \vec{x}_{r_3})$
- **Parameters**: `F` (mutation scale), `CR` (crossover probability).

### 2. Particle Swarm Optimization (PSO)
- **Velocity Update**: $\vec{v}_i \leftarrow w\vec{v}_i + c_1 r_1 (\vec{p}_i - \vec{x}_i) + c_2 r_2 (\vec{g} - \vec{x}_i)$
- **Canonicalization**: Particles are evaluated through a canonicalized *copy*; the particle's own position is not reordered, so it stays consistent with its velocity. The returned best design is canonicalized.
- **Parameters**: `w` (inertia weight), `c1` (cognitive learning rate), `c2` (social learning rate).

### 3. Genetic Algorithm (GA)
- **Operators**: Tournament selection (size 4), uniform crossover, grid-step mutation.
- **Elitism**: The best individual from the previous generation is always preserved at index 0 of the new population.
- **Parameters**: `MutationRate`.

### 4. CMA-ES
- **Method**: Adapts the covariance matrix of a multivariate normal distribution to guide the search towards promising areas.
- **Normalized Search Space**: The distribution mean, covariance matrix, and global step size are adapted in a dimensionless `[0, 1]` coordinate system. Each sampled normalized vector is converted back to the configured physical bounds before quantization and evaluation. This prevents variables with large numeric ranges from dominating the covariance adaptation.
- **Grid Integration**: Offspring are sampled from the continuous distribution and clipped to `[0, 1]`. A copy is quantized to the `StepSize` grid and canonicalized for evaluation, while the mean/covariance/evolution-path updates use the clipped **continuous** samples. This keeps the update consistent with what was sampled (canonicalization may swap WEC2/WEC3 in 5-WEC layouts). The search step size is not allowed to shrink below one grid step.
- **Parameters**: `SigmaInit` (initial search step ratio).
