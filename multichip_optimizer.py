"""
Qiskit Multi-Chip Optimizer - FIXED VERSION WITH BUILT-IN NETWORKX
"""

from qiskit import QuantumCircuit
import networkx as nx
from collections import defaultdict
import random


# ============================================================================
# TOPOLOGY DEFINITIONS
# ============================================================================

class ChipTopology:
    """Base class for multi-chip topology definitions."""
    
    def __init__(self, num_chips, qubits_per_chip, inter_chip_links, 
                 inter_chip_fidelity=0.95, intra_chip_fidelity=0.999):
        self.num_chips = num_chips
        
        if isinstance(qubits_per_chip, int):
            self.qubits_per_chip = [qubits_per_chip] * num_chips
        else:
            self.qubits_per_chip = qubits_per_chip
            
        self.total_qubits = sum(self.qubits_per_chip)
        self.inter_chip_links = inter_chip_links
        self.inter_chip_fidelity = inter_chip_fidelity
        self.intra_chip_fidelity = intra_chip_fidelity
        
        # Build qubit-to-chip mapping
        self.qubit_to_chip = {}
        qubit_idx = 0
        for chip_idx, num_qubits in enumerate(self.qubits_per_chip):
            for _ in range(num_qubits):
                self.qubit_to_chip[qubit_idx] = chip_idx
                qubit_idx += 1
    
    def get_chip(self, qubit):
        """Return which chip a qubit belongs to."""
        return self.qubit_to_chip.get(qubit, 0)


class GenericMultiChipTopology(ChipTopology):
    """Generic multi-chip topology for testing."""
    
    def __init__(self, num_chips=3, qubits_per_chip=100):
        links = [(i, j) for i in range(num_chips) for j in range(i+1, num_chips)]
        super().__init__(
            num_chips=num_chips,
            qubits_per_chip=qubits_per_chip,
            inter_chip_links=links,
            inter_chip_fidelity=0.95,
            intra_chip_fidelity=0.999
        )


# ============================================================================
# OPTIMIZER - FIXED VERSION
# ============================================================================

class MultiChipOptimizer:
    """
    Optimize quantum circuits for multi-chip architectures.
    Minimizes inter-chip gate operations to reduce fidelity loss.
    """
    
    def __init__(self, topology):
        self.topology = topology

    def optimize(self, circuit):
        """Optimize a quantum circuit for the multi-chip topology."""
        qubit_interactions = self._analyze_circuit(circuit)
        qubit_placement = self._partition_qubits_fixed(circuit, qubit_interactions)
        optimized = self._remap_circuit(circuit, qubit_placement)
        return optimized
    
    def _analyze_circuit(self, circuit):
        """Analyze qubit interactions in the circuit."""
        interactions = defaultdict(int)
        for instruction in circuit.data:
            if len(instruction.qubits) == 2:
                q1 = circuit.qubits.index(instruction.qubits[0])
                q2 = circuit.qubits.index(instruction.qubits[1])
                pair = tuple(sorted([q1, q2]))
                interactions[pair] += 1
        return interactions
    
    def _partition_qubits_fixed(self, circuit, interactions):
        """
        Uses NetworkX greedy modularity to find clusters of highly interacting qubits,
        then packs them onto chips.
        """
        num_qubits = circuit.num_qubits
        num_chips = self.topology.num_chips
        qubits_per_chip = self.topology.qubits_per_chip[0]
        
        # 1. Build weighted interaction graph
        G = nx.Graph()
        G.add_nodes_from(range(num_qubits))
        for (q1, q2), weight in interactions.items():
            G.add_edge(q1, q2, weight=weight)
            
        print("   [Optimizer] Running graph partitioning...")
        
        # 2. Find communities (groups of qubits that talk to each other a lot)
        from networkx.algorithms.community import greedy_modularity_communities
        communities = list(greedy_modularity_communities(G, weight='weight'))
        
        # 3. Pack communities onto chips (Bin Packing)
        placement = {}
        chip_sizes = [0] * num_chips
        
        # Sort communities by size (largest first)
        communities.sort(key=len, reverse=True)
        
        for comm in communities:
            comm_list = list(comm)
            
            # Find the chip with the most available space
            best_chip = 0
            max_space = 0
            for i in range(num_chips):
                space = qubits_per_chip - chip_sizes[i]
                if space > max_space:
                    max_space = space
                    best_chip = i
            
            # Put the community on the chip with the most space
            for q in comm_list:
                # If the best chip gets full, find the next one
                if chip_sizes[best_chip] >= qubits_per_chip:
                    for i in range(num_chips):
                        if chip_sizes[i] < qubits_per_chip:
                            best_chip = i
                            break
                
                placement[q] = best_chip
                chip_sizes[best_chip] += 1
                
        # 4. Handle isolated qubits that didn't get placed
        for q in range(num_qubits):
            if q not in placement:
                for i in range(num_chips):
                    if chip_sizes[i] < qubits_per_chip:
                        placement[q] = i
                        chip_sizes[i] += 1
                        break
                        
        print(f"   [Optimizer] Placed {len(placement)} qubits across {num_chips} chips.")
        return placement
    
    def _remap_circuit(self, circuit, placement):
        """Create new circuit with qubits remapped according to placement."""
        optimized = circuit.copy()
        optimized.metadata = {'qubit_placement': placement}
        return optimized
    
    def count_inter_chip_gates(self, circuit, placement=None):
        """Count number of gates crossing chip boundaries."""
        if placement is None:
            placement = circuit.metadata.get('qubit_placement', {})
            if not placement:
                placement = {q: self.topology.get_chip(q) for q in range(circuit.num_qubits)}
        
        inter_chip_count = 0
        for instruction in circuit.data:
            if len(instruction.qubits) == 2:
                q1 = circuit.qubits.index(instruction.qubits[0])
                q2 = circuit.qubits.index(instruction.qubits[1])
                
                chip1 = placement.get(q1, 0)
                chip2 = placement.get(q2, 0)
                
                if chip1 != chip2:
                    inter_chip_count += 1
        return inter_chip_count
    
    def estimate_fidelity(self, circuit, placement=None):
        """Estimate circuit fidelity based on gate counts and topology."""
        if placement is None:
            placement = circuit.metadata.get('qubit_placement', {})
            if not placement:
                placement = {q: self.topology.get_chip(q) for q in range(circuit.num_qubits)}
        
        total_fidelity = 1.0
        for instruction in circuit.data:
            if len(instruction.qubits) == 2:
                q1 = circuit.qubits.index(instruction.qubits[0])
                q2 = circuit.qubits.index(instruction.qubits[1])
                
                chip1 = placement.get(q1, 0)
                chip2 = placement.get(q2, 0)
                
                if chip1 != chip2:
                    total_fidelity *= self.topology.inter_chip_fidelity
                else:
                    total_fidelity *= self.topology.intra_chip_fidelity
        return total_fidelity
    
    def analyze_placement(self, circuit, placement=None):
        """Analyze and print detailed placement statistics."""
        if placement is None:
            placement = circuit.metadata.get('qubit_placement', {})
        
        chip_counts = defaultdict(int)
        for q, chip in placement.items():
            chip_counts[chip] += 1
        print(f"\nPlacement Analysis:")
        print(f"  Qubits per chip: {dict(chip_counts)}")
        
        intra_chip_gates = defaultdict(int)
        inter_chip_gates = 0
        for instruction in circuit.data:
            if len(instruction.qubits) == 2:
                q1 = circuit.qubits.index(instruction.qubits[0])
                q2 = circuit.qubits.index(instruction.qubits[1])
                
                chip1 = placement.get(q1, 0)
                chip2 = placement.get(q2, 0)
                
                if chip1 == chip2:
                    intra_chip_gates[chip1] += 1
                else:
                    inter_chip_gates += 1
        
        print(f"  Intra-chip gates per chip: {dict(intra_chip_gates)}")
        print(f"  Inter-chip gates: {inter_chip_gates}")


# ============================================================================
# TESTING FUNCTIONS
# ============================================================================

def create_test_circuit(num_qubits=50):
    """
    Create a scrambled test circuit where naive placement fails.
    Simulates a complex QAOA or VQE interaction graph.
    """
    qc = QuantumCircuit(num_qubits)
    random.seed(42) # For reproducibility
    
    # Create 3 hidden "clusters" of interacting qubits
    clusters = [
        [i for i in range(num_qubits) if i % 3 == 0],
        [i for i in range(num_qubits) if i % 3 == 1],
        [i for i in range(num_qubits) if i % 3 == 2]
    ]
    
    num_gates = 150
    for _ in range(num_gates):
        if random.random() < 0.80:
            # 80% chance: Intra-cluster gate
            cluster = random.choice(clusters)
            if len(cluster) >= 2:
                q1, q2 = random.sample(cluster, 2)
                qc.cx(q1, q2)
        else:
            # 20% chance: Inter-cluster gate
            c1, c2 = random.sample(clusters, 2)
            q1 = random.choice(c1)
            q2 = random.choice(c2)
            qc.cx(q1, q2)
            
    return qc


def run_quick_test():
    """Run a quick test of the optimizer."""
    print("=" * 60)
    print("Qiskit Multi-Chip Optimizer - BUILT-IN NETWORKX VERSION")
    print("=" * 60)
    
    print("\n1. Creating scrambled test circuit...")
    num_qubits = 100
    circuit = create_test_circuit(num_qubits)
    print(f"   Circuit: {num_qubits} qubits, {len(circuit.data)} gates")
    
    print("\n2. Setting up multi-chip topology...")
    topology = GenericMultiChipTopology(num_chips=3, qubits_per_chip=34)
    print(f"   Topology: {topology.num_chips} chips, {topology.qubits_per_chip[0]} qubits/chip")
    
    print("\n3. Optimizing circuit...")
    optimizer = MultiChipOptimizer(topology)
    
    # Naive sequential mapping
    naive_placement = {q: q // 34 for q in range(num_qubits)}
    original_inter_chip = optimizer.count_inter_chip_gates(circuit, naive_placement)
    original_fidelity = optimizer.estimate_fidelity(circuit, naive_placement)
    
    print(f"\n   BEFORE optimization (naive sequential mapping):")
    print(f"   - Inter-chip gates: {original_inter_chip}")
    print(f"   - Estimated fidelity: {original_fidelity:.6f}")
    
    # Optimize
    optimized_circuit = optimizer.optimize(circuit)
    
    # Analyze
    optimizer.analyze_placement(optimized_circuit, optimized_circuit.metadata['qubit_placement'])
    
    optimized_inter_chip = optimizer.count_inter_chip_gates(optimized_circuit, optimized_circuit.metadata['qubit_placement'])
    optimized_fidelity = optimizer.estimate_fidelity(optimized_circuit, optimized_circuit.metadata['qubit_placement'])
    
    print(f"\n   AFTER optimization:")
    print(f"   - Inter-chip gates: {optimized_inter_chip}")
    print(f"   - Estimated fidelity: {optimized_fidelity:.6f}")
    
    # Calculate improvement
    if original_inter_chip > 0:
        reduction = ((original_inter_chip - optimized_inter_chip) / original_inter_chip * 100)
    else:
        reduction = 0
    
    if original_fidelity > 0:
        fidelity_improvement = ((optimized_fidelity - original_fidelity) / original_fidelity * 100)
    else:
        fidelity_improvement = 0
    
    print(f"\n4. Results:")
    print(f"   - Inter-chip gate reduction: {reduction:.1f}%")
    print(f"   - Fidelity improvement: {fidelity_improvement:.2f}%")
    
    print("\n" + "=" * 60)
    if reduction > 0:
        print("✓ SUCCESS - Optimizer reduced inter-chip gates!")
    else:
        print("⚠ WARNING - Optimizer did not improve placement")
    print("=" * 60)


if __name__ == '__main__':
    run_quick_test()
