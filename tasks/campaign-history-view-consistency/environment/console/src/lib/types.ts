export type Status = 'pending' | 'in_progress' | 'completed';
export type Task = {
  id: string; title: string; owner: string; status: Status;
  review_state: 'pending' | 'approved' | 'changes_requested'; reviewer_id: string | null;
};
export type Dependency = { task_id: string; prerequisite_id: string };
export type Event = {
  id: string; timestamp: string; sequence: number;
  type: 'task_assigned' | 'task_reassigned' | 'task_completed' | 'task_reopened' |
    'dependency_added' | 'dependency_removed' | 'review_updated';
  task_id: string;
  payload: Partial<Pick<Task, 'owner' | 'review_state' | 'reviewer_id'>> & {
    initial_owner?: string; initial_status?: Status; prerequisite_id?: string;
  };
};
export type Campaign = { tasks: Task[]; dependencies: Dependency[]; events: Event[] };
export type Snapshot = { tasks: Task[]; dependencies: Dependency[]; at: string | null };
export type Availability = { blocked: boolean; ready: boolean };
export type Filter = 'all' | Status | 'blocked' | 'ready';
export const edgeId = (edge: Dependency) => `${edge.task_id}--${edge.prerequisite_id}`;
