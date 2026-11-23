import { useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { Availability, Task } from '../lib/types';
export function TaskTable({ tasks, states, selected, select }: {
  tasks: Task[]; states: Map<string, Availability>; selected: string | null; select: (id: string) => void;
}) {
  const parent = useRef<HTMLDivElement>(null);
  const virtual = useVirtualizer({ count: tasks.length, getScrollElement: () => parent.current,
    estimateSize: () => 36, overscan: 20, getItemKey: index => tasks[index].id });
  return <div>
    <div className="table-heading">Task / Owner / Status / Blocked / Ready</div>
    <div ref={parent} role="table" aria-label="Tasks" className="task-scroll">
      <div style={{ height: virtual.getTotalSize(), position: 'relative' }}>
        {virtual.getVirtualItems().map(item => {
          const task = tasks[item.index]; const state = states.get(task.id)!;
          return <div role="row" tabIndex={0} key={task.id} data-testid={`task-row-${task.id}`}
            aria-selected={task.id === selected} onClick={() => select(task.id)}
            onKeyDown={event => event.key === 'Enter' && select(task.id)}
            className="task-row" style={{ transform: `translateY(${item.start}px)` }}>
            <span>{task.id} · {task.title}</span><span data-field="owner">{task.owner}</span>
            <span data-field="status">{task.status}</span><span data-field="blocked">{String(state.blocked)}</span>
            <span data-field="ready">{String(state.ready)}</span>
          </div>;
        })}
      </div>
    </div>
  </div>;
}
