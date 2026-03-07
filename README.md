# Qiskit Multi-Chip Optimizer

A quantum circuit optimizer and routing tool designed for modular, multi-chip quantum computing architectures like the upcoming **IBM Kookaburra**.

As quantum hardware scales by connecting multiple chips via microwave links (l-couplers), inter-chip 2-qubit gates become the primary bottleneck. They are significantly slower and noisier than intra-chip gates. 

This tool analyzes the interaction graph of a generic Qiskit `QuantumCircuit` (like VQE or QAOA ansatzes) and uses **NetworkX greedy modularity community detection** to intelligently partition highly-entangled qubit clusters onto the same physical chip.

## Performance 

Tested on a highly entangled 100-qubit scrambled test circuit mapped to a 3-chip topology (34 qubits/chip):

* **Inter-chip gates:** Reduced from 92 to 35 (**62.0% reduction**)
* **Estimated Circuit Fidelity:** Improved by **1657%**

```text
Placement Analysis:
  Qubits per chip: {0: 32, 1: 34, 2: 34}
  Intra-chip gates per chip: {1: 39, 0: 35, 2: 41}
  Inter-chip gates: 35

4. Results:
   - Inter-chip gate reduction: 62.0%
   - Fidelity improvement: 1657.87%

How it works
Analyze: Parses the Qiskit circuit to build a weighted interaction graph of all 2-qubit gates.
Partition: Uses nx.community.greedy_modularity_communities to find hidden clusters of interacting qubits.
Bin Packing: Intelligently maps these communities to physical chips based on available qubit capacities.
Remap: Outputs a mapped circuit with optimized virtual-to-physical qubit assignments.
Usage
Simply define your topology and pass your circuit to the optimizer: from multichip_optimizer import MultiChipOptimizer, IBMKookaburraTopology

# 1. Define Topology (e.g., 3 chips, 1386 qubits each)
topology = IBMKookaburraTopology()

# 2. Initialize Optimizer
optimizer = MultiChipOptimizer(topology)

# 3. Optimize Circuit
optimized_circuit = optimizer.optimize(my_qiskit_circuit)

Motivation
This tool was built to highlight the fundamental fidelity limits of planar 2D multi-chip routing, serving as the software baseline for upcoming topological hardware architecture research.
