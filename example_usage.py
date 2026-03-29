from multichip_optimizer import (
    build_line_topology,
    create_clustered_test_circuit,
    MultiChipPlacementOptimizer,
)

def main():
    topology = build_line_topology()
    circuit = create_clustered_test_circuit(
        num_qubits=120,
        num_clusters=4,
        num_gates=400,
        seed=0
    )

    optimizer = MultiChipPlacementOptimizer(topology, max_passes=10)
    result = optimizer.optimize(circuit, routing_mode="path")
    optimizer.summarize_result(result)

if __name__ == "__main__":
    main()
