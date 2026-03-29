# Qiskit Multi-Chip Placement Optimizer

A hardware-aware qubit placement and abstract routing optimizer for modular multi-chip quantum architectures.

This project targets a key scaling problem in modular quantum systems: minimizing expensive inter-chip communication while respecting chip capacities and hardware topology.

## What it does

Given a `Qiskit QuantumCircuit` and a multi-chip hardware graph, the optimizer:

1. Builds a weighted logical interaction graph from 2-qubit gates
2. Generates a topology-aware initial qubit placement using graph communities
3. Refines placement with fast local move/swap search
4. Produces an abstract routed circuit with explicit inter-chip communication-hop markers
5. Reports communication cost, hop count, routing latency, and modeled success probability

## Why this matters

In modular quantum hardware, not all remote 2-qubit interactions are equally expensive.

A placement that reduces:
- inter-chip gates
- chip-to-chip communication hops
- path latency
- path-induced fidelity loss

can significantly improve execution quality compared to naive mapping.

## Current model

This is a **prototype placement + abstract routing framework**, not a hardware-exact transpiler.

It currently supports:
- arbitrary weighted chip graphs
- chip capacity constraints
- communication-cost-aware placement
- path-aware shortest-hop routing annotations
- estimated latency/fidelity metrics
- synthetic benchmark evaluation across multiple topologies

## Optimization pipeline

### 1. Interaction graph extraction
The circuit is converted into a weighted qubit interaction graph where edge weights reflect repeated 2-qubit interactions.

### 2. Topology-aware community initialization
Highly interacting logical qubits are clustered and assigned to chips using a topology-aware community placement heuristic.

### 3. Fast local refinement
A move/swap local search improves the placement under chip-capacity constraints.

### 4. Path-aware abstract routing
For each remote interaction, the tool emits one abstract communication-hop marker per chip-to-chip edge traversed along the shortest hardware path.

### 5. Routing overhead accounting
The optimizer reports:
- communication cost
- inter-chip gate count
- total inter-chip hop count
- total inter-chip routing latency
- average hops per remote gate
- average latency per remote gate
- modeled success probability

## Example benchmark results

Benchmarks were run on 120-qubit clustered synthetic circuits mapped to 4-chip modular topologies.

### Full mesh
- Communication cost reduction vs naive: **52.57%**
- Hop reduction vs naive: **70.06%**
- Average routing latency: **450.00**
- Average runtime: **0.719 sec**

### Line topology
- Communication cost reduction vs naive: **58.85%**
- Hop reduction vs naive: **69.93%**
- Average routing latency: **701.67**
- Average runtime: **1.541 sec**

### Ring topology
- Communication cost reduction vs naive: **58.51%**
- Hop reduction vs naive: **71.49%**
- Average routing latency: **576.67**
- Average runtime: **1.027 sec**

### Success probability trend
Modeled success probability improved substantially relative to naive placement across all tested topologies.

## Example usage

```python
topology = build_line_topology()
circuit = create_clustered_test_circuit(num_qubits=120, num_clusters=4, num_gates=400, seed=0)

optimizer = MultiChipPlacementOptimizer(topology, max_passes=10)
result = optimizer.optimize(circuit, routing_mode="path")

optimizer.summarize_result(result)
