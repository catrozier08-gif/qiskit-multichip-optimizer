Qiskit Multi-Chip Placement Optimizer
A prototype hardware-aware qubit layout and abstract routing framework for modular quantum architectures.

Overview
This project explores qubit placement for modular multi-chip quantum systems, where remote interactions across chips can introduce additional latency, routing overhead, and fidelity loss relative to local operations.

Given a Qiskit circuit and a weighted chip-level topology graph, the optimizer:

builds a weighted logical interaction graph,
generates an initial placement using topology-aware community structure,
refines the layout using local move/swap search, and
emits an abstract routed circuit annotated with inter-chip communication markers.
What it does
Builds a weighted logical interaction graph from 2-qubit gates
Generates a topology-aware initial placement under chip-capacity constraints
Refines layouts using fast local move/swap search
Emits abstract inter-chip routing markers along shortest chip-level paths
Reports modeled communication and routing metrics
Important note
This is a prototype placement and abstract routing tool, not a hardware-exact transpiler pass.

It does not currently synthesize vendor-native inter-chip operations or perform full timing-aware scheduling. Routing markers are used to estimate communication burden, not to claim executable hardware decomposition.

Optimization pipeline
1. Interaction graph extraction
Convert the circuit into a weighted graph where edge weights reflect repeated 2-qubit interactions.

2. Topology-aware community initialization
Cluster highly interacting qubits and assign them to chips using a capacity-constrained, topology-aware heuristic.

3. Fast local refinement
Improve placement using move/swap local search under chip-capacity constraints.

4. Abstract path-aware routing
Insert one communication-hop marker per traversed chip-to-chip edge for remote interactions.

5. Metric reporting
Report:

communication cost
inter-chip gate count
total inter-chip hop count
total modeled routing latency
average hops per remote gate
average latency per remote gate
modeled success probability
Example benchmark results
Benchmarks were run on clustered synthetic circuits mapped to 4-chip modular topologies.

Average communication-cost reduction versus naive placement:

Full mesh: ~52.6%
Line: ~58.9%
Ring: ~58.5%
These results are based on a simplified chip-level communication and fidelity model and should be interpreted as optimization benchmarks, not hardware execution claims.

Public API
The higher-level wrapper API is:

ModularLayoutOptimizer.analyze(...)
ModularLayoutOptimizer.run(...)
ModularLayoutOptimizer.baseline_report(...)
Quick start
Python

from multichip_optimizer import (
    build_line_topology,
    create_clustered_test_circuit,
    ModularLayoutOptimizer,
)

topology = build_line_topology()
circuit = create_clustered_test_circuit(
    num_qubits=120,
    num_clusters=4,
    num_gates=400,
    seed=0,
)

optimizer = ModularLayoutOptimizer(topology=topology, max_passes=10)
result = optimizer.run(circuit, routing_mode="path")
optimizer.summarize(result)
Example script

Bash

python example_usage.py
