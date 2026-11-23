import { Dependency, Snapshot, Task, edgeId } from './types';
import { dependencyGroups } from './topology';
export type Projection = { nodes: Task[]; edges: Dependency[] };
type Index = { tasks: Map<string, Task>; branches: Map<string, Dependency[]>; roots: Task[] };

export class GraphRecords {
  private indices = new WeakMap<Snapshot, Index>();

  project(snapshot: Snapshot, expanded: Set<string>): Projection {
    let index = this.indices.get(snapshot);
    if (!index) {
      const tasks = new Map(snapshot.tasks.map(task => [task.id, task]));
      const branches = new Map<string, Dependency[]>();
      snapshot.dependencies.forEach(edge => {
        if (!tasks.has(edge.task_id) || !tasks.has(edge.prerequisite_id)) return;
        const branch = branches.get(edge.task_id) ?? [];
        branch.push(edge); branches.set(edge.task_id, branch);
      });
      const topology = dependencyGroups([...tasks.keys()], snapshot.dependencies);
      index = { tasks, branches, roots: snapshot.tasks.filter(task =>
        topology.incoming[topology.component.get(task.id)!].size === 0) };
      this.indices.set(snapshot, index);
    }
    const nodes = new Map<string, Task>();
    const edges = new Map<string, Dependency>();
    const pending = [...index.roots];
    while (pending.length) {
      const task = pending.pop()!;
      if (nodes.has(task.id)) continue;
      nodes.set(task.id, task);
      if (expanded.has(task.id)) {
        for (const edge of index.branches.get(task.id) ?? []) {
          edges.set(edgeId(edge), edge); pending.push(index.tasks.get(edge.prerequisite_id)!);
        }
      }
    }
    return { nodes: [...nodes.values()].sort((left, right) => left.id < right.id ? -1 : left.id > right.id ? 1 : 0),
      edges: [...edges.values()] };
  }
}
export function logicalEdgeIds(projection: Projection) { return projection.edges.map(edgeId); }
