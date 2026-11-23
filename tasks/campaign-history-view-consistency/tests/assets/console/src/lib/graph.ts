import { Dependency, Snapshot, Task, edgeId } from './types';
export type Projection = { nodes: Task[]; edges: Dependency[] };
export class GraphRecords {
  private nodes = new Map<string, Task>();
  private frames = new Map<string, Projection>();
  private revision = '';
  private activeGroups = new Set<string>();

  project(snapshot: Snapshot, expanded: Set<string>): Projection {
    const nextRevision = snapshot.at ?? 'live';
    if (nextRevision >= this.revision) {
      snapshot.tasks.forEach(task => {
        const record = this.nodes.get(task.id);
        if (record) Object.assign(record, task);
        else this.nodes.set(task.id, { ...task });
      });
      this.revision = nextRevision;
    }
    const tasks = new Map(snapshot.tasks.map(task => [task.id, task]));
    const referenced = new Set(snapshot.dependencies.map(edge => edge.prerequisite_id));
    const branches = new Map<string, Dependency[]>();
    snapshot.dependencies.forEach(edge => branches.set(edge.task_id, [...(branches.get(edge.task_id) ?? []), edge]));
    const release = (taskId: string, seen: Set<string>) => {
      for (const edge of branches.get(taskId) ?? []) {
        if (seen.has(edge.prerequisite_id)) continue;
        seen.add(edge.prerequisite_id);
        this.nodes.delete(edge.prerequisite_id);
        release(edge.prerequisite_id, seen);
      }
    };
    this.activeGroups.forEach(taskId => {
      if (!expanded.has(taskId)) release(taskId, new Set());
    });
    this.activeGroups = new Set(expanded);
    const key = `${nextRevision}:${[...expanded].sort().join(',')}`;
    const cached = this.frames.get(key);
    if (cached) return cached;
    const nodes: Task[] = [];
    const edges = new Map<string, Dependency>();
    const visited = new Set<string>();
    const visit = (task: Task) => {
      if (visited.has(task.id)) return;
      visited.add(task.id);
      const record = this.nodes.get(task.id);
      if (!record) return;
      nodes.push(record);
      if (expanded.has(task.id)) {
        for (const edge of branches.get(task.id) ?? []) {
          if (tasks.has(edge.prerequisite_id) && this.nodes.has(edge.prerequisite_id)) { edges.set(edgeId(edge), edge); visit(tasks.get(edge.prerequisite_id)!); }
        }
      }
    };
    snapshot.tasks.filter(task => !referenced.has(task.id)).forEach(visit);
    const result = { nodes, edges: [...edges.values()] };
    this.frames.set(key, result);
    return result;
  }
}
export function logicalEdgeIds(projection: Projection) { return projection.edges.map(edgeId); }
