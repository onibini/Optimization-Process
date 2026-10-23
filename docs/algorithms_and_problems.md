# Optimization Algorithms and Problem Formulations (for LLM)

This document describes the mathematical formulation of the optimization problem, the fitness objective, constraints, and the parameters of the optimization engines.

---

## 1. Objective Function & Fitness Evaluation

The goal is to maximize the **total wave power absorbed by the WEC array** (ideal linear PTO, heave only).
The fitness returned is the total absorbed power $P_{\text{total}}$ in Watts:

$$f(\vec{v}) = P_{\text{total}}(\vec{v}) = \sum_k \int B_{\text{PTO},k}\,\omega^2 |\text{RAO}_k(\omega)|^2 S(\omega)\,d\omega$$

### Hydrodynamic Simulation with WAMIT
For valid configurations, the evaluation runs a boundary element method solver (WAMIT):
1. **Mesh Generation**: Generates a cylinder-hemisphere quarter-model GDF mesh based on $R$ (radius) and $D$ (cylindrical draft). The total draft is $D + R$. The panel count per body is set directly by `MeshPanels` (default 120; 5-WEC convergence tests show about 0.5% total-power and 1.2% per-WEC error for most designs, but slender shapes need 160 or more) (hemisphere: cubed-sphere patches without pole fans; cylinder: quads with the same angular division). Because 32-bit WAMIT runs out of memory when (`MeshPanels` × number of bodies) exceeds about 1,100 and run time grows with roughly the 2.5–3rd power of the panel count, keep `MeshPanels` × `NumWECs` modest (see `config.cfg`).
2. **Radiation/Diffraction Analysis**: WAMIT solves the velocity potentials and calculates the hydrodynamic coefficients (added mass $A(\omega)$, radiation damping $B(\omega)$, and wave excitation forces $F_{\text{exc}}(\omega)$) for $\omega = 0.5 \sim \omega_{max}$ rad/s ($\Delta\omega = 0.05$, `OmegaMax` in `config.cfg`, default 3.0), heading 0°. The linear systems are solved with WAMIT's iterative solver by default (`Solver`; direct solver available). A warning is issued if the iteration limit is reached at some frequency or if the response is not negligible at the highest frequency (the grid may truncate resonances of small bodies).
3. **RAO & Power Calculation**:
   - $B_{\text{PTO},k}$ is set to the radiation damping $B_{kk}(\omega_n)$ at the peak frequency of the uncontrolled RAO of body $k$.
   - Solve the equations of motion with this PTO to obtain Response Amplitude Operators (RAO).
   - Integrate the power extraction across the selected wave spectrum (`WaveSpec`: 1 JONSWAP ITTC form, default; 2 JONSWAP Goda form, whose integral gives an Hs about 4% too high at gamma 1.4; 3 Pierson-Moskowitz in the Hs-Tp (Bretschneider) form) with Simpson's rule.

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

The system implements five optimization engines. With `Workers > 1` (`[WAMIT Settings]`) every batch of independent evaluations (initial populations; whole generations of GA, CMA-ES and generation-wise DE) runs several WAMIT processes at the same time through `CachedEvaluator.evaluate_batch`; results are identical to evaluating one by one. All engines use the shared `CachedEvaluator` to quantize vectors to the configured `StepSize`, canonicalize symmetric layouts, and query a grid-indexed in-memory cache before running the expensive physics evaluation. DE, GA, CMA-ES and DEPSO require `PopSize >= 4`.

### 1. Differential Evolution (DE)
- **Strategy**: `DE/rand/1/bin`
- **Equation**: $\vec{u}_i = \vec{x}_{r_1} + F \cdot (\vec{x}_{r_2} - \vec{x}_{r_3})$
- **Parameters**: `F` (mutation scale), `CR` (crossover probability), `DEUpdate` (0: the trial replaces its target immediately, so later mutants of the same generation see it, as in the paper; 1: generation-wise, all trials are built from the previous population and evaluated together, which allows several WAMIT runs at the same time).

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

### 5. DEPSO (DE + PSO hybrid)
- **Source**: the author's DEPSO (Lee, Heo, Koo, 2026, *Ocean Engineering* 355, 125173); only its update rule is ported, everything else uses the shared project functions.
- **Per particle and generation**: (1) PSO move: velocity update $ec{v}_i \leftarrow wec{v}_i + c_1 r_1 (ec{p}_i - ec{x}_i) + c_2 r_2 (ec{g} - ec{x}_i)$, clipped to 10% of the range, moved point $ec{m}_i = ec{x}_i + ec{v}_i$; (2) DE mutation $ec{x}_{r_1} + F(ec{x}_{r_2} - ec{x}_{r_3})$ from the current positions of three other particles; (3) binomial crossover with the **moved point** as the base vector; (4) one evaluation and greedy selection: the particle moves only if the trial is better, then `pbest`/`gbest` are updated. The velocity keeps its update either way. Updates are immediate within a generation, as in DE.
- Because positions only change when they improve, `pbest` always equals the current position and the $c_1$ term is effectively zero; the greedy selection keeps an elitist population, which the DE mutation needs to converge.
- **Comparison variants** (`update` argument, not in `config.cfg`): `"pbest"` (mutation from personal bests, particles always move) and `"move"` (particles always move like PSO). In the benchmark of `docs/reports/2026-10-23_11_*` both were worse than the default; `"move"` did not converge.
- **Canonicalization**: evaluated through a canonicalized copy, like PSO.
- **Parameters**: `F`, `CR`, `w`, `c1`, `c2`.
