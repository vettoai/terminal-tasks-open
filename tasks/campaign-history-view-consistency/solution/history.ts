import { Availability, Campaign, Dependency, Event, Snapshot, Task, edgeId } from './types';

export class History {
  readonly events: Event[];
  private times: number[];
  private catalog: Map<string, Task>;
  private snapshots = new Map<string, Snapshot>();
  private availability = new WeakMap<Snapshot, Map<string, Availability>>();
  private live: Snapshot;

  constructor(readonly campaign: Campaign) {
    this.events = [...campaign.events].sort((left, right) =>
      Date.parse(left.timestamp) - Date.parse(right.timestamp) ||
      (BigInt(left.sequence) < BigInt(right.sequence) ? -1 : BigInt(left.sequence) > BigInt(right.sequence) ? 1 : 0) ||
      (left.id < right.id ? -1 : left.id > right.id ? 1 : 0));
    this.times = this.events.map(event => Date.parse(event.timestamp));
    this.catalog = new Map(campaign.tasks.map(task => [task.id, task]));
    this.live = { at: null, tasks: campaign.tasks.map(task => ({ ...task })),
      dependencies: campaign.dependencies.map(edge => ({ ...edge })) };
  }

  snapshot(at: string | null): Snapshot {
    if (!at) return this.live;
    const key = String(Date.parse(at));
    const cached = this.snapshots.get(key);
    if (cached) {
      this.snapshots.delete(key); this.snapshots.set(key, cached);
      return cached;
    }
    const cutoff = Date.parse(at);
    const tasks = new Map<string, Task>();
    const dependencies = new Map<string, Dependency>();
    for (let index = 0; index < this.events.length && this.times[index] <= cutoff; index++) {
      const event = this.events[index]; const payload = event.payload;
      let task = tasks.get(event.task_id);
      if (!task) {
        task = { id: event.task_id, title: this.catalog.get(event.task_id)!.title,
          owner: payload.initial_owner!, status: payload.initial_status!, review_state: 'pending', reviewer_id: null };
        tasks.set(task.id, task);
      }
      if (event.type === 'task_assigned' || event.type === 'task_reassigned') task.owner = payload.owner!;
      if (event.type === 'task_completed') task.status = 'completed';
      if (event.type === 'task_reopened') task.status = 'in_progress';
      if (event.type === 'review_updated') {
        if (payload.review_state !== undefined) task.review_state = payload.review_state;
        if (payload.reviewer_id !== undefined) task.reviewer_id = payload.reviewer_id;
      }
      if (event.type === 'dependency_added' || event.type === 'dependency_removed') {
        const edge = { task_id: event.task_id, prerequisite_id: payload.prerequisite_id! };
        if (event.type === 'dependency_added') dependencies.set(edgeId(edge), edge);
        else dependencies.delete(edgeId(edge));
      }
    }
    const result = { at, tasks: [...tasks.values()], dependencies: [...dependencies.values()]
      .filter(edge => tasks.has(edge.task_id) && tasks.has(edge.prerequisite_id)) };
    this.snapshots.set(key, result);
    if (this.snapshots.size > 8) this.snapshots.delete(this.snapshots.keys().next().value!);
    return result;
  }

  states(snapshot: Snapshot) {
    const cached = this.availability.get(snapshot);
    if (cached) return cached;
    const tasks = new Map(snapshot.tasks.map(task => [task.id, task]));
    const blocked = new Set<string>();
    snapshot.dependencies.forEach(edge => {
      if (tasks.get(edge.prerequisite_id)?.status !== 'completed') blocked.add(edge.task_id);
    });
    const result = new Map(snapshot.tasks.map(task => [task.id, {
      blocked: blocked.has(task.id), ready: !blocked.has(task.id) && task.status !== 'completed'
    }]));
    this.availability.set(snapshot, result);
    return result;
  }
}
