import { Dependency } from './types';

export function dependencyGroups(ids: string[], dependencies: Dependency[]) {
  const branches = new Map(ids.map(id => [id, [] as string[]]));
  const dependents = new Map(ids.map(id => [id, [] as string[]]));
  for (const edge of dependencies) {
    if (!branches.has(edge.task_id) || !branches.has(edge.prerequisite_id)) continue;
    branches.get(edge.task_id)!.push(edge.prerequisite_id);
    dependents.get(edge.prerequisite_id)!.push(edge.task_id);
  }
  const visited = new Set<string>();
  const finished: string[] = [];
  for (const id of ids) {
    if (visited.has(id)) continue;
    visited.add(id);
    const stack: [string, number][] = [[id, 0]];
    while (stack.length) {
      const frame = stack[stack.length - 1];
      const next = branches.get(frame[0])!;
      if (frame[1] === next.length) {
        finished.push(frame[0]); stack.pop();
      } else {
        const child = next[frame[1]++];
        if (!visited.has(child)) { visited.add(child); stack.push([child, 0]); }
      }
    }
  }
  const component = new Map<string, number>();
  const groups: string[][] = [];
  for (const id of finished.reverse()) {
    if (component.has(id)) continue;
    const group: string[] = [];
    const pending = [id];
    component.set(id, groups.length);
    while (pending.length) {
      const member = pending.pop()!;
      group.push(member);
      for (const parent of dependents.get(member)!) {
        if (!component.has(parent)) { component.set(parent, groups.length); pending.push(parent); }
      }
    }
    groups.push(group);
  }
  const outgoing = groups.map(() => new Set<number>());
  const incoming = groups.map(() => new Set<number>());
  for (const [id, children] of branches) {
    const source = component.get(id)!;
    for (const child of children) {
      const target = component.get(child)!;
      if (source !== target) { outgoing[source].add(target); incoming[target].add(source); }
    }
  }
  return { component, groups, outgoing, incoming };
}
