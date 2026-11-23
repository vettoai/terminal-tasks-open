import { useEffect, useMemo, useRef, useState } from 'react';
import { scalePoint } from 'd3';
import { GraphRecords } from '../lib/graph';
import { dependencyGroups } from '../lib/topology';
import { Snapshot, Task, edgeId } from '../lib/types';
type Hit = { task: Task; x: number; y: number };
export function Graph({ snapshot, expanded, toggle, selected, select, active }: {
  snapshot: Snapshot; expanded: Set<string>; toggle: (id: string) => void;
  selected: string | null; select: (id: string) => void; active: boolean;
}) {
  const [records] = useState(() => new GraphRecords());
  const projection = useMemo(() => records.project(snapshot, expanded), [records, snapshot, expanded]);
  const canvas = useRef<HTMLCanvasElement>(null); const hits = useRef<Hit[]>([]);
  const [tooltip, setTooltip] = useState<Task | null>(null);
  const [zoom, setZoom] = useState(1); const [pan, setPan] = useState({ x: 0, y: 0 });
  const [focus, setFocus] = useState(''); const [branch, setBranch] = useState('');
  const drag = useRef<{ x: number; y: number; pan: { x: number; y: number } } | null>(null);
  const dragged = useRef(false);
  function viewport(command: string) {
    if (command === 'zoom-in') setZoom(value => value * 1.2);
    if (command === 'zoom-out') setZoom(value => value / 1.2);
    if (command === 'pan-right') setPan(value => ({ ...value, x: value.x + 120 }));
    if (command === 'pan-left') setPan(value => ({ ...value, x: value.x - 120 }));
  }
  useEffect(() => {
    const element = canvas.current; if (!element) return;
    const wheel = (event: WheelEvent) => {
      event.preventDefault(); viewport(event.deltaY < 0 ? 'zoom-in' : 'zoom-out');
    };
    element.addEventListener('wheel', wheel, { passive: false });
    return () => element.removeEventListener('wheel', wheel);
  }, []);
  const positions = useMemo(() => {
    const topology = dependencyGroups(projection.nodes.map(task => task.id), projection.edges);
    const ranks = topology.groups.map(() => 0);
    const remaining = topology.outgoing.map(children => children.size);
    const pending = remaining.flatMap((count, index) => count === 0 ? [index] : []);
    while (pending.length) {
      const group = pending.pop()!;
      for (const parent of topology.incoming[group]) {
        ranks[parent] = Math.max(ranks[parent], ranks[group] + 1);
        if (--remaining[parent] === 0) pending.push(parent);
      }
    }
    const depths = new Map(projection.nodes.map(task => [task.id, ranks[topology.component.get(task.id)!]]));
    const columns = [...new Set(depths.values())].sort((left, right) => left - right);
    const horizontal = scalePoint<number>().domain(columns).range([100, Math.max(700, columns.length * 190)]);
    const rows = new Map<number, number>();
    return new Map(projection.nodes.map(task => {
      const column = depths.get(task.id)!; const row = rows.get(column) ?? 0;
      rows.set(column, row + 1); return [task.id, { x: horizontal(column)!, y: 45 + row * 54 }];
    }));
  }, [projection]);
  useEffect(() => {
    const context = canvas.current?.getContext('2d'); if (!context) return;
    context.clearRect(0, 0, 900, 300); context.fillStyle = '#f4f7fb'; context.fillRect(0, 0, 900, 300);
    const point = (id: string) => { const position = positions.get(id)!;
      return { x: position.x * zoom + pan.x, y: position.y * zoom + pan.y }; };
    context.strokeStyle = '#a2b4cb';
    for (const edge of projection.edges) {
      const start = point(edge.task_id); const end = point(edge.prerequisite_id);
      context.beginPath(); context.moveTo(start.x, start.y); context.lineTo(end.x, end.y); context.stroke();
    }
    const frame: Hit[] = [];
    for (const task of projection.nodes) {
      const position = point(task.id);
      if (position.x < -85 || position.x > 985 || position.y < -20 || position.y > 320) continue;
      context.fillStyle = task.id === selected ? '#b8d7ff' : '#fff';
      context.fillRect(position.x - 80, position.y - 18, 160, 36);
      context.strokeRect(position.x - 80, position.y - 18, 160, 36);
      context.fillStyle = '#163453'; context.font = '11px sans-serif';
      context.fillText(task.id, position.x - 75, position.y - 3, 150);
      context.fillText(`${task.owner} · ${task.status}`, position.x - 75, position.y + 11, 150);
      frame.push({ task, ...position });
    }
    hits.current = frame; setTooltip(null);
  }, [projection, positions, zoom, pan, selected, active]);
  function taskAt(event: React.MouseEvent<HTMLCanvasElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const horizontal = (event.clientX - bounds.left) * 900 / bounds.width;
    const vertical = (event.clientY - bounds.top) * 300 / bounds.height;
    const hit = [...hits.current].reverse().find(item => Math.abs(item.x - horizontal) <= 80 && Math.abs(item.y - vertical) <= 18);
    return hit?.task ?? null;
  }
  function hover(event: React.MouseEvent<HTMLCanvasElement>) {
    setTooltip(taskAt(event));
  }
  return <section aria-label="Dependency graph" hidden={!active}>
    <div className="toolbar">
      <label>Branch task<input aria-label="Branch task" value={branch} onChange={event => setBranch(event.target.value)} /></label>
      <button onClick={() => toggle(branch)}>Toggle branch</button>
      <label>Focus task<input aria-label="Focus task" value={focus} onChange={event => setFocus(event.target.value)} /></label>
      <button onClick={() => { const position = positions.get(focus); if (position) setPan({ x: 450 - position.x * zoom, y: 150 - position.y * zoom }); }}>Center task</button>
      <button name="graph-viewport" value="zoom-in" aria-label="Zoom in" onClick={event => viewport(event.currentTarget.value)}>+</button>
      <button name="graph-viewport" value="zoom-out" aria-label="Zoom out" onClick={event => viewport(event.currentTarget.value)}>−</button>
      <button name="graph-viewport" value="pan-right" onClick={event => viewport(event.currentTarget.value)}>Pan right</button>
      <button name="graph-viewport" value="pan-left" onClick={event => viewport(event.currentTarget.value)}>Pan left</button>
    </div>
    <canvas ref={canvas} width={900} height={300} aria-label="Campaign dependency canvas" onMouseMove={hover}
      onMouseLeave={() => setTooltip(null)} onPointerDown={event => {
        dragged.current = false; drag.current = { x: event.clientX, y: event.clientY, pan };
        event.currentTarget.setPointerCapture(event.pointerId);
      }} onPointerMove={event => {
        if (!drag.current) return;
        const bounds = event.currentTarget.getBoundingClientRect();
        const horizontal = event.clientX - drag.current.x; const vertical = event.clientY - drag.current.y;
        if (Math.abs(horizontal) + Math.abs(vertical) > 3) dragged.current = true;
        setPan({ x: drag.current.pan.x + horizontal * 900 / bounds.width,
          y: drag.current.pan.y + vertical * 300 / bounds.height });
      }} onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}
      onClick={event => { const task = taskAt(event); if (!dragged.current && task) select(task.id); }} />
    {tooltip && <output data-testid="graph-node-tooltip">{tooltip.id} · {tooltip.owner} · {tooltip.status}</output>}
    <div className="graph-mirror" aria-label="Accessible dependency graph">
      {projection.nodes.map(task => <button key={task.id} data-testid={`graph-node-${task.id}`}
        aria-selected={selected === task.id} onClick={() => select(task.id)}>
        <span>{task.id}</span> <span data-field="owner">{task.owner}</span> <span data-field="status">{task.status}</span>
      </button>)}
      {projection.edges.map(edge => <span key={edgeId(edge)} data-testid={`graph-edge-${edgeId(edge)}`}
        data-task-id={edge.task_id} data-prerequisite-id={edge.prerequisite_id}>
        {edge.task_id} → {edge.prerequisite_id}</span>)}
    </div>
  </section>;
}
