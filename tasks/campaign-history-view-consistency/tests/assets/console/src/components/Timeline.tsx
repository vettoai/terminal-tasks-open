import { useRef } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { Event } from '../lib/types';
export function Timeline({ events, at, navigate }: { events: Event[]; at: string | null; navigate: (at: string) => void }) {
  const parent = useRef<HTMLDivElement>(null);
  const virtual = useVirtualizer({ count: events.length, getScrollElement: () => parent.current,
    estimateSize: () => 30, overscan: 128, getItemKey: index => events[index].id });
  return <div ref={parent} role="list" aria-label="Campaign events" className="event-scroll">
    <div style={{ height: virtual.getTotalSize(), position: 'relative' }}>
      {virtual.getVirtualItems().map(item => {
        const event = events[item.index];
        return <button key={event.id} data-testid={`event-${event.id}`}
          data-applied={!at || Date.parse(event.timestamp) <= Date.parse(at) ? 'true' : 'false'}
          className="event-row" style={{ transform: `translateY(${item.start}px)` }}
          onClick={() => navigate(event.timestamp)}>{event.timestamp} · {event.task_id} · {event.type}</button>;
      })}
    </div>
  </div>;
}
