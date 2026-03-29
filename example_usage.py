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
