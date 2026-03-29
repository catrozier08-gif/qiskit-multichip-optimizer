import networkx as nx
import random
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List

from qiskit import QuantumCircuit
from qiskit.circuit import Gate


# =========================================================
# TOPOLOGY
# =========================================================

@dataclass
class MultiChipTopology:
    num_chips: int
    qubits_per_chip: List[int]
    chip_graph: nx.Graph = field(default_factory=nx.Graph)
    intra_chip_latency: float = 1.0
    intra_chip_fidelity: float = 0.999

    def __post_init__(self):
        if isinstance(self.qubits_per_chip, int):
            self.qubits_per_chip = [self.qubits_per_chip] * self.num_chips

        if len(self.qubits_per_chip) != self.num_chips:
            raise ValueError("qubits_per_chip must match num_chips")

        for chip in range(self.num_chips):
            self.chip_graph.add_node(chip, capacity=self.qubits_per_chip[chip])

    def add_link(self, chip_a: int, chip_b: int, latency: float = 5.0, fidelity: float = 0.95, bandwidth: float = 1.0):
        self.chip_graph.add_edge(
            chip_a, chip_b,
            latency=latency,
            fidelity=fidelity,
            bandwidth=bandwidth
        )

    def shortest_path_latency(self, chip_a: int, chip_b: int) -> float:
        if chip_a == chip_b:
            return self.intra_chip_latency
        return nx.shortest_path_length(self.chip_graph, chip_a, chip_b, weight="latency")

    def shortest_path(self, chip_a: int, chip_b: int) -> List[int]:
        if chip_a == chip_b:
            return [chip_a]
        return nx.shortest_path(self.chip_graph, chip_a, chip_b, weight="latency")

    def path_fidelity(self, chip_a: int, chip_b: int) -> float:
        if chip_a == chip_b:
            return self.intra_chip_fidelity

        path = self.shortest_path(chip_a, chip_b)
        fidelity = 1.0
        for u, v in zip(path[:-1], path[1:]):
            fidelity *= self.chip_graph[u][v].get("fidelity", 0.95)
        return fidelity

    def chip_distance(self, chip_a: int, chip_b: int) -> float:
        return self.shortest_path_latency(chip_a, chip_b)


def build_line_topology(num_chips=4, qubits_per_chip=34):
    topo = MultiChipTopology(
        num_chips=num_chips,
        qubits_per_chip=[qubits_per_chip] * num_chips,
        intra_chip_latency=1.0,
        intra_chip_fidelity=0.999
    )
    for i in range(num_chips - 1):
        topo.add_link(i, i + 1, latency=5.0, fidelity=0.95)
    return topo


def build_ring_topology(num_chips=4, qubits_per_chip=34):
    topo = MultiChipTopology(
        num_chips=num_chips,
        qubits_per_chip=[qubits_per_chip] * num_chips,
        intra_chip_latency=1.0,
        intra_chip_fidelity=0.999
    )
    for i in range(num_chips):
        topo.add_link(i, (i + 1) % num_chips, latency=5.0, fidelity=0.95)
    return topo


def build_full_mesh_topology(num_chips=4, qubits_per_chip=34):
    topo = MultiChipTopology(
        num_chips=num_chips,
        qubits_per_chip=[qubits_per_chip] * num_chips,
        intra_chip_latency=1.0,
        intra_chip_fidelity=0.999
    )
    for i in range(num_chips):
        for j in range(i + 1, num_chips):
            topo.add_link(i, j, latency=5.0, fidelity=0.95)
    return topo


# =========================================================
# CIRCUIT / GRAPH UTILITIES
# =========================================================

class InteractionGraphBuilder:
    @staticmethod
    def build(circuit: QuantumCircuit) -> nx.Graph:
        G = nx.Graph()
        G.add_nodes_from(range(circuit.num_qubits))

        for instruction in circuit.data:
            if len(instruction.qubits) == 2:
                q1 = circuit.qubits.index(instruction.qubits[0])
                q2 = circuit.qubits.index(instruction.qubits[1])

                if G.has_edge(q1, q2):
                    G[q1][q2]["weight"] += 1
                else:
                    G.add_edge(q1, q2, weight=1)

        return G


def create_clustered_test_circuit(num_qubits=120, num_clusters=4, num_gates=400, seed=42):
    random.seed(seed)
    qc = QuantumCircuit(num_qubits)

    clusters = [[] for _ in range(num_clusters)]
    for q in range(num_qubits):
        clusters[q % num_clusters].append(q)

    for _ in range(num_gates):
        if random.random() < 0.8:
            cluster = random.choice(clusters)
            if len(cluster) >= 2:
                q1, q2 = random.sample(cluster, 2)
                qc.cx(q1, q2)
        else:
            c1, c2 = random.sample(range(num_clusters), 2)
            q1 = random.choice(clusters[c1])
            q2 = random.choice(clusters[c2])
            qc.cx(q1, q2)

    return qc


# =========================================================
# PLACEMENT HELPERS
# =========================================================

def naive_sequential_placement(num_qubits: int, topology: MultiChipTopology) -> Dict[int, int]:
    placement = {}
    q = 0
    for chip, cap in enumerate(topology.qubits_per_chip):
        for _ in range(cap):
            if q < num_qubits:
                placement[q] = chip
                q += 1
    if len(placement) != num_qubits:
        raise ValueError("Not enough total chip capacity for all qubits")
    return placement


def random_placement(num_qubits: int, topology: MultiChipTopology, seed=42) -> Dict[int, int]:
    random.seed(seed)
    qubits = list(range(num_qubits))
    random.shuffle(qubits)

    placement = {}
    idx = 0
    for chip, cap in enumerate(topology.qubits_per_chip):
        for _ in range(cap):
            if idx < num_qubits:
                placement[qubits[idx]] = chip
                idx += 1

    if len(placement) != num_qubits:
        raise ValueError("Not enough total chip capacity for all qubits")

    return placement


class TopologyAwareCommunityPlacement:
    def __init__(self, topology: MultiChipTopology):
        self.topology = topology

    def place(self, interaction_graph: nx.Graph) -> Dict[int, int]:
        from networkx.algorithms.community import greedy_modularity_communities

        communities = list(greedy_modularity_communities(interaction_graph, weight="weight"))
        communities = sorted(communities, key=len, reverse=True)

        placement = {}
        chip_loads = [0] * self.topology.num_chips

        for comm in communities:
            comm_list = list(comm)
            comm_size = len(comm_list)

            feasible_chips = [
                chip for chip in range(self.topology.num_chips)
                if chip_loads[chip] + comm_size <= self.topology.qubits_per_chip[chip]
            ]

            if feasible_chips:
                best_chip = None
                best_cost = float("inf")

                for chip in feasible_chips:
                    marginal_cost = 0.0
                    for q in comm_list:
                        for neighbor in interaction_graph.neighbors(q):
                            if neighbor in placement:
                                weight = interaction_graph[q][neighbor].get("weight", 1)
                                neighbor_chip = placement[neighbor]
                                marginal_cost += weight * self.topology.chip_distance(chip, neighbor_chip)

                    marginal_cost += 0.001 * chip_loads[chip]

                    if marginal_cost < best_cost:
                        best_cost = marginal_cost
                        best_chip = chip

                for q in comm_list:
                    placement[q] = best_chip
                    chip_loads[best_chip] += 1
            else:
                for q in comm_list:
                    best_chip = None
                    best_cost = float("inf")

                    for chip in range(self.topology.num_chips):
                        if chip_loads[chip] >= self.topology.qubits_per_chip[chip]:
                            continue

                        marginal_cost = 0.0
                        for neighbor in interaction_graph.neighbors(q):
                            if neighbor in placement:
                                weight = interaction_graph[q][neighbor].get("weight", 1)
                                neighbor_chip = placement[neighbor]
                                marginal_cost += weight * self.topology.chip_distance(chip, neighbor_chip)

                        marginal_cost += 0.001 * chip_loads[chip]

                        if marginal_cost < best_cost:
                            best_cost = marginal_cost
                            best_chip = chip

                    if best_chip is None:
                        raise ValueError("No available chip capacity")

                    placement[q] = best_chip
                    chip_loads[best_chip] += 1

        for q in interaction_graph.nodes():
            if q not in placement:
                for chip in range(self.topology.num_chips):
                    if chip_loads[chip] < self.topology.qubits_per_chip[chip]:
                        placement[q] = chip
                        chip_loads[chip] += 1
                        break

        return placement


# =========================================================
# COST MODEL
# =========================================================

class FastPlacementCostModel:
    def __init__(self, topology: MultiChipTopology):
        self.topology = topology

    def communication_cost(self, interaction_graph: nx.Graph, placement: Dict[int, int]) -> float:
        total_cost = 0.0
        for q1, q2, data in interaction_graph.edges(data=True):
            weight = data.get("weight", 1)
            chip1 = placement[q1]
            chip2 = placement[q2]
            total_cost += weight * self.topology.chip_distance(chip1, chip2)
        return total_cost

    def inter_chip_gate_count(self, interaction_graph: nx.Graph, placement: Dict[int, int]) -> int:
        total = 0
        for q1, q2, data in interaction_graph.edges(data=True):
            if placement[q1] != placement[q2]:
                total += data.get("weight", 1)
        return total

    def estimated_success_probability(self, interaction_graph: nx.Graph, placement: Dict[int, int]) -> float:
        success = 1.0
        for q1, q2, data in interaction_graph.edges(data=True):
            weight = data.get("weight", 1)
            chip1 = placement[q1]
            chip2 = placement[q2]

            if chip1 == chip2:
                gate_fidelity = self.topology.intra_chip_fidelity
            else:
                gate_fidelity = self.topology.path_fidelity(chip1, chip2)

            success *= gate_fidelity ** weight
        return success

    def evaluate(self, interaction_graph: nx.Graph, placement: Dict[int, int]) -> Dict[str, float]:
        return {
            "communication_cost": self.communication_cost(interaction_graph, placement),
            "inter_chip_gates": self.inter_chip_gate_count(interaction_graph, placement),
            "estimated_success_probability": self.estimated_success_probability(interaction_graph, placement),
        }

    def delta_cost_for_move(self, interaction_graph: nx.Graph, placement: Dict[int, int], qubit: int, new_chip: int) -> float:
        old_chip = placement[qubit]
        if old_chip == new_chip:
            return 0.0

        delta = 0.0
        for neighbor in interaction_graph.neighbors(qubit):
            weight = interaction_graph[qubit][neighbor].get("weight", 1)
            neighbor_chip = placement[neighbor]
            old_cost = weight * self.topology.chip_distance(old_chip, neighbor_chip)
            new_cost = weight * self.topology.chip_distance(new_chip, neighbor_chip)
            delta += (new_cost - old_cost)
        return delta

    def delta_cost_for_swap(self, interaction_graph: nx.Graph, placement: Dict[int, int], q1: int, q2: int) -> float:
        chip1 = placement[q1]
        chip2 = placement[q2]

        if chip1 == chip2:
            return 0.0

        before = 0.0
        after = 0.0

        trial = placement.copy()
        trial[q1], trial[q2] = trial[q2], trial[q1]

        considered_edges = set()
        for q in [q1, q2]:
            for neighbor in interaction_graph.neighbors(q):
                edge = tuple(sorted((q, neighbor)))
                if edge in considered_edges:
                    continue
                considered_edges.add(edge)

                weight = interaction_graph[q][neighbor].get("weight", 1)
                before += weight * self.topology.chip_distance(placement[edge[0]], placement[edge[1]])
                after += weight * self.topology.chip_distance(trial[edge[0]], trial[edge[1]])

        return after - before


# =========================================================
# LOCAL REFINEMENT
# =========================================================

class FastLocalSearchPlacementOptimizer:
    def __init__(self, topology: MultiChipTopology, cost_model: FastPlacementCostModel):
        self.topology = topology
        self.cost_model = cost_model

    def chip_loads(self, placement: Dict[int, int]) -> Dict[int, int]:
        loads = defaultdict(int)
        for q, chip in placement.items():
            loads[chip] += 1
        return dict(loads)

    def can_move(self, placement: Dict[int, int], qubit: int, new_chip: int) -> bool:
        old_chip = placement[qubit]
        if old_chip == new_chip:
            return False
        loads = self.chip_loads(placement)
        return loads.get(new_chip, 0) < self.topology.qubits_per_chip[new_chip]

    def refine(self, interaction_graph: nx.Graph, initial_placement: Dict[int, int], max_passes: int = 10):
        current = initial_placement.copy()
        current_cost = self.cost_model.communication_cost(interaction_graph, current)

        print(f"Initial cost = {current_cost}")

        for pass_num in range(1, max_passes + 1):
            improved = False

            for q in interaction_graph.nodes():
                old_chip = current[q]
                best_chip = old_chip
                best_delta = 0.0

                for candidate_chip in range(self.topology.num_chips):
                    if candidate_chip == old_chip:
                        continue
                    if not self.can_move(current, q, candidate_chip):
                        continue

                    delta = self.cost_model.delta_cost_for_move(interaction_graph, current, q, candidate_chip)

                    if delta < best_delta:
                        best_delta = delta
                        best_chip = candidate_chip

                if best_chip != old_chip:
                    current[q] = best_chip
                    current_cost += best_delta
                    improved = True

            qubits = list(interaction_graph.nodes())
            for i in range(len(qubits)):
                q1 = qubits[i]
                for j in range(i + 1, len(qubits)):
                    q2 = qubits[j]
                    if current[q1] == current[q2]:
                        continue

                    delta = self.cost_model.delta_cost_for_swap(interaction_graph, current, q1, q2)
                    if delta < 0:
                        current[q1], current[q2] = current[q2], current[q1]
                        current_cost += delta
                        improved = True

            print(f"Pass {pass_num}: cost = {current_cost}")
            if not improved:
                break

        return current


# =========================================================
# REMAPPING / ROUTING
# =========================================================

def build_physical_qubit_mapping(placement: Dict[int, int], topology: MultiChipTopology) -> Dict[int, int]:
    chip_to_qubits = defaultdict(list)
    for logical_q, chip in placement.items():
        chip_to_qubits[chip].append(logical_q)

    for chip in chip_to_qubits:
        chip_to_qubits[chip].sort()

    chip_offsets = []
    offset = 0
    for cap in topology.qubits_per_chip:
        chip_offsets.append(offset)
        offset += cap

    logical_to_physical = {}
    for chip, logical_qubits in chip_to_qubits.items():
        base = chip_offsets[chip]
        for local_slot, logical_q in enumerate(logical_qubits):
            logical_to_physical[logical_q] = base + local_slot

    return logical_to_physical


class InterChipCommGate(Gate):
    def __init__(self, label=None):
        super().__init__("interchip_comm", 2, [], label=label)

    def _define(self):
        qc = QuantumCircuit(2, name=self.name)
        self.definition = qc


class InterChipHopGate(Gate):
    def __init__(self, label=None):
        super().__init__("interchip_hop", 2, [], label=label)

    def _define(self):
        qc = QuantumCircuit(2, name=self.name)
        self.definition = qc


class CircuitRemapper:
    def __init__(self, topology: MultiChipTopology):
        self.topology = topology

    def remap_with_interchip_markers(self, circuit: QuantumCircuit, placement: Dict[int, int]) -> QuantumCircuit:
        logical_to_physical = build_physical_qubit_mapping(placement, self.topology)
        new_circuit = QuantumCircuit(sum(self.topology.qubits_per_chip), circuit.num_clbits)

        for instruction in circuit.data:
            op = instruction.operation
            old_qubits = instruction.qubits
            old_clbits = instruction.clbits

            logical_indices = [circuit.qubits.index(q) for q in old_qubits]
            new_qubit_indices = [logical_to_physical[q] for q in logical_indices]
            new_qubits = [new_circuit.qubits[i] for i in new_qubit_indices]
            new_clbits = [new_circuit.clbits[circuit.clbits.index(c)] for c in old_clbits]

            if len(logical_indices) == 2:
                q1, q2 = logical_indices
                chip1 = placement[q1]
                chip2 = placement[q2]
                if chip1 != chip2:
                    new_circuit.append(InterChipCommGate(label=f"chip{chip1}->chip{chip2}"), new_qubits)

            new_circuit.append(op, new_qubits, new_clbits)

        new_circuit.metadata = {"logical_to_physical": logical_to_physical, "chip_placement": placement}
        return new_circuit


class PathAwareCircuitRemapper:
    def __init__(self, topology: MultiChipTopology):
        self.topology = topology

    def remap_with_path_markers(self, circuit: QuantumCircuit, placement: Dict[int, int]) -> QuantumCircuit:
        logical_to_physical = build_physical_qubit_mapping(placement, self.topology)
        new_circuit = QuantumCircuit(sum(self.topology.qubits_per_chip), circuit.num_clbits)

        for instruction in circuit.data:
            op = instruction.operation
            old_qubits = instruction.qubits
            old_clbits = instruction.clbits

            logical_indices = [circuit.qubits.index(q) for q in old_qubits]
            new_qubit_indices = [logical_to_physical[q] for q in logical_indices]
            new_qubits = [new_circuit.qubits[i] for i in new_qubit_indices]
            new_clbits = [new_circuit.clbits[circuit.clbits.index(c)] for c in old_clbits]

            if len(logical_indices) == 2:
                q1, q2 = logical_indices
                chip1 = placement[q1]
                chip2 = placement[q2]

                if chip1 != chip2:
                    chip_path = self.topology.shortest_path(chip1, chip2)
                    for u, v in zip(chip_path[:-1], chip_path[1:]):
                        new_circuit.append(InterChipHopGate(label=f"hop_{u}_{v}"), new_qubits)

            new_circuit.append(op, new_qubits, new_clbits)

        new_circuit.metadata = {"logical_to_physical": logical_to_physical, "chip_placement": placement}
        return new_circuit


def expected_total_hops(interaction_graph: nx.Graph, placement: Dict[int, int], topology: MultiChipTopology) -> int:
    total_hops = 0
    for q1, q2, data in interaction_graph.edges(data=True):
        weight = data.get("weight", 1)
        chip1 = placement[q1]
        chip2 = placement[q2]
        if chip1 != chip2:
            total_hops += weight * (len(topology.shortest_path(chip1, chip2)) - 1)
    return total_hops


def parse_hop_label(label: str):
    if label is None:
        return None
    parts = label.split("_")
    if len(parts) != 3 or parts[0] != "hop":
        return None
    return int(parts[1]), int(parts[2])


def routed_circuit_latency_summary(circuit: QuantumCircuit, topology: MultiChipTopology) -> Dict[str, float]:
    total_hop_markers = 0
    total_latency = 0.0
    total_fidelity_factor = 1.0

    for instr in circuit.data:
        if instr.operation.name == "interchip_hop":
            total_hop_markers += 1
            hop = parse_hop_label(instr.operation.label)
            if hop is None:
                continue

            u, v = hop
            edge_data = topology.chip_graph.get_edge_data(u, v)
            if edge_data is None:
                edge_data = topology.chip_graph.get_edge_data(v, u)
            if edge_data is None:
                raise ValueError(f"No topology edge found for hop {u}-{v}")

            total_latency += edge_data.get("latency", 0.0)
            total_fidelity_factor *= edge_data.get("fidelity", 1.0)

    return {
        "total_interchip_hop_markers": total_hop_markers,
        "total_interchip_latency": total_latency,
        "total_interchip_fidelity_factor": total_fidelity_factor,
        "average_latency_per_hop": (total_latency / total_hop_markers) if total_hop_markers > 0 else 0.0
    }


def add_remote_gate_latency_metrics(summary: Dict[str, float], refined_metrics: Dict[str, float]) -> Dict[str, float]:
    updated = dict(summary)
    inter_chip_gates = refined_metrics.get("inter_chip_gates", 0)

    updated["average_hops_per_interchip_gate"] = (
        summary["total_interchip_hop_markers"] / inter_chip_gates if inter_chip_gates > 0 else 0.0
    )
    updated["average_latency_per_interchip_gate"] = (
        summary["total_interchip_latency"] / inter_chip_gates if inter_chip_gates > 0 else 0.0
    )
    return updated


# =========================================================
# MAIN OPTIMIZER
# =========================================================

class MultiChipPlacementOptimizer:
    """
    Hardware-aware multi-chip placement optimizer with optional circuit transformation
    and routing summary accounting.
    """

    def __init__(self, topology: MultiChipTopology, max_passes: int = 10):
        self.topology = topology
        self.max_passes = max_passes
        self.cost_model = FastPlacementCostModel(topology)
        self.refiner = FastLocalSearchPlacementOptimizer(topology, self.cost_model)
        self.initializer = TopologyAwareCommunityPlacement(topology)
        self.simple_remapper = CircuitRemapper(topology)
        self.path_remapper = PathAwareCircuitRemapper(topology)

    def build_interaction_graph(self, circuit: QuantumCircuit) -> nx.Graph:
        return InteractionGraphBuilder.build(circuit)

    def initial_placement(self, interaction_graph: nx.Graph) -> Dict[int, int]:
        return self.initializer.place(interaction_graph)

    def refine_placement(self, interaction_graph: nx.Graph, placement: Dict[int, int]) -> Dict[int, int]:
        return self.refiner.refine(interaction_graph, placement, max_passes=self.max_passes)

    def evaluate_placement(self, interaction_graph: nx.Graph, placement: Dict[int, int]) -> Dict[str, float]:
        metrics = self.cost_model.evaluate(interaction_graph, placement)
        metrics["total_interchip_hops"] = expected_total_hops(interaction_graph, placement, self.topology)
        return metrics

    def compare_baselines(self, interaction_graph: nx.Graph) -> Dict[str, Dict[str, float]]:
        num_qubits = interaction_graph.number_of_nodes()

        naive = naive_sequential_placement(num_qubits, self.topology)
        random_p = random_placement(num_qubits, self.topology, seed=42)
        initial = self.initial_placement(interaction_graph)
        refined = self.refine_placement(interaction_graph, initial.copy())

        return {
            "naive": self.evaluate_placement(interaction_graph, naive),
            "random": self.evaluate_placement(interaction_graph, random_p),
            "initial": self.evaluate_placement(interaction_graph, initial),
            "refined": self.evaluate_placement(interaction_graph, refined),
        }

    def compute_routing_summary(self, optimized_circuit: QuantumCircuit, refined_metrics: Dict[str, float]) -> Dict[str, float]:
        if any(instr.operation.name == "interchip_hop" for instr in optimized_circuit.data):
            summary = routed_circuit_latency_summary(optimized_circuit, self.topology)
            summary = add_remote_gate_latency_metrics(summary, refined_metrics)
            return summary

        elif any(instr.operation.name == "interchip_comm" for instr in optimized_circuit.data):
            comm_count = sum(1 for instr in optimized_circuit.data if instr.operation.name == "interchip_comm")
            return {"total_interchip_comm_markers": comm_count}

        return {}

    def optimize(
        self,
        circuit: QuantumCircuit,
        routing_mode: str = "path",
        return_circuit_copy: bool = True
    ) -> Dict:
        interaction_graph = self.build_interaction_graph(circuit)

        initial = self.initial_placement(interaction_graph)
        refined = self.refine_placement(interaction_graph, initial.copy())

        initial_metrics = self.evaluate_placement(interaction_graph, initial)
        refined_metrics = self.evaluate_placement(interaction_graph, refined)

        result = {
            "interaction_graph": interaction_graph,
            "initial_placement": initial,
            "refined_placement": refined,
            "initial_metrics": initial_metrics,
            "refined_metrics": refined_metrics,
        }

        if return_circuit_copy and routing_mode != "none":
            if routing_mode == "simple":
                routed_circuit = self.simple_remapper.remap_with_interchip_markers(circuit, refined)
            elif routing_mode == "path":
                routed_circuit = self.path_remapper.remap_with_path_markers(circuit, refined)
            else:
                raise ValueError("routing_mode must be one of: 'none', 'simple', 'path'")

            routed_circuit.metadata = getattr(routed_circuit, "metadata", {}) or {}
            routed_circuit.metadata["multi_chip_initial_placement"] = initial
            routed_circuit.metadata["multi_chip_refined_placement"] = refined
            routed_circuit.metadata["multi_chip_initial_metrics"] = initial_metrics
            routed_circuit.metadata["multi_chip_refined_metrics"] = refined_metrics
            routed_circuit.metadata["routing_mode"] = routing_mode

            result["optimized_circuit"] = routed_circuit
            result["routing_summary"] = self.compute_routing_summary(routed_circuit, refined_metrics)

        return result

    def summarize_result(self, result: Dict):
        print("Multi-Chip Placement Optimization Summary")
        print("-" * 50)

        print("Initial Placement Metrics:")
        for k, v in result["initial_metrics"].items():
            print(f"  {k}: {v}")

        print("\nRefined Placement Metrics:")
        for k, v in result["refined_metrics"].items():
            print(f"  {k}: {v}")

        init_cost = result["initial_metrics"]["communication_cost"]
        ref_cost = result["refined_metrics"]["communication_cost"]
        improvement = (1 - ref_cost / init_cost) * 100 if init_cost > 0 else 0.0

        # =========================================================
# TOPOLOGY DESCRIPTION HELPER
# =========================================================

def describe_topology(topology: MultiChipTopology) -> Dict:
    latencies = []
    fidelities = []
    links = []
    
    for u, v, data in topology.chip_graph.edges(data=True):
        lat = data.get("latency", None)
        fid = data.get("fidelity", None)
        if lat is not None:
            latencies.append(lat)
        if fid is not None:
            fidelities.append(fid)
        links.append({
            "chip_a": u,
            "chip_b": v,
            "latency": lat,
            "fidelity": fid,
            "bandwidth": data.get("bandwidth", None),
        })
    
    return {
        "num_chips": topology.num_chips,
        "qubits_per_chip": topology.qubits_per_chip,
        "total_qubit_capacity": sum(topology.qubits_per_chip),
        "num_links": topology.chip_graph.number_of_edges(),
        "average_link_latency": sum(latencies) / len(latencies) if latencies else None,
        "average_link_fidelity": sum(fidelities) / len(fidelities) if fidelities else None,
        "links": links,
    }


# =========================================================
# ECOSYSTEM-FACING WRAPPER
# =========================================================

class ModularLayoutOptimizer:
    """
    Transpiler-adjacent wrapper for modular quantum layout optimization.
    
    This class presents a cleaner ecosystem-facing API around the underlying
    multi-chip placement and abstract routing engine.
    """
    
    def __init__(self, topology: MultiChipTopology, max_passes: int = 10):
        self.topology = topology
        self.max_passes = max_passes
        self.engine = MultiChipPlacementOptimizer(topology=topology, max_passes=max_passes)
    
    def analyze(self, circuit: QuantumCircuit) -> Dict:
        interaction_graph = self.engine.build_interaction_graph(circuit)
        return {
            "num_qubits": circuit.num_qubits,
            "num_operations": len(circuit.data),
            "num_interaction_edges": interaction_graph.number_of_edges(),
            "interaction_graph": interaction_graph,
            "topology": describe_topology(self.topology),
        }
    
    def run(self, circuit: QuantumCircuit, routing_mode: str = "path") -> Dict:
        result = self.engine.optimize(circuit, routing_mode=routing_mode)
        
        wrapped = {
            "topology": describe_topology(self.topology),
            "routing_mode": routing_mode,
            "interaction_graph": result["interaction_graph"],
            "initial_layout": result["initial_placement"],
            "refined_layout": result["refined_placement"],
            "initial_metrics": result["initial_metrics"],
            "refined_metrics": result["refined_metrics"],
        }
        
        if "optimized_circuit" in result:
            wrapped["routed_circuit"] = result["optimized_circuit"]
        
        if "routing_summary" in result:
            wrapped["routing_summary"] = result["routing_summary"]
        
        return wrapped
    
    def baseline_report(self, circuit: QuantumCircuit) -> Dict:
        interaction_graph = self.engine.build_interaction_graph(circuit)
        baselines = self.engine.compare_baselines(interaction_graph)
        
        return {
            "topology": describe_topology(self.topology),
            "baselines": baselines,
        }
    
    def summarize(self, result: Dict):
        print("Modular Layout Optimizer Summary")
        print("-" * 50)
        
        topo = result.get("topology", {})
        print(f"Topology: {topo.get('num_chips')} chips, capacity {topo.get('total_qubit_capacity')} qubits")
        print(f"Links: {topo.get('num_links')} | Avg latency: {topo.get('average_link_latency')} | Avg fidelity: {topo.get('average_link_fidelity')}")
        
        print("\nInitial Layout Metrics:")
        for k, v in result["initial_metrics"].items():
            print(f"  {k}: {v}")
        
        print("\nRefined Layout Metrics:")
        for k, v in result["refined_metrics"].items():
            print(f"  {k}: {v}")
        
        init_cost = result["initial_metrics"]["communication_cost"]
        ref_cost = result["refined_metrics"]["communication_cost"]
        improvement = (1 - ref_cost / init_cost) * 100 if init_cost > 0 else 0.0
        
        print(f"\nRefinement improvement over initial layout: {improvement:.2f}%")
        
        if "routing_summary" in result:
            print("\nRouting Summary:")
            for k, v in result["routing_summary"].items():
                print(f"  {k}: {v}")
        
        if "routed_circuit" in result:
            routed_circuit = result["routed_circuit"]
            print(f"\nRouted circuit operations: {len(routed_circuit.data)}")
            interchip_hops = sum(1 for instr in routed_circuit.data if instr.operation.name == "interchip_hop")
            interchip_comm = sum(1 for instr in routed_circuit.data if instr.operation.name == "interchip_comm")
            
            if interchip_hops:
                print(f"Inserted inter-chip hop markers: {interchip_hops}")
            if interchip_comm:
                print(f"Inserted inter-chip communication markers: {interchip_comm}")

        print(f"\nRefinement improvement over initial placement: {improvement:.2f}%")

        if "routing_summary" in result and result["routing_summary"]:
            print("\nRouting Summary:")
            for k, v in result["routing_summary"].items():
                print(f"  {k}: {v}")
