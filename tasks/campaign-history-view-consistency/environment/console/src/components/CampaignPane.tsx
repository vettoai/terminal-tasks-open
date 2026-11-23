import { useEffect, useMemo, useState } from 'react';
import { History } from '../lib/history';
import { Filter } from '../lib/types';
import { TaskTable } from './TaskTable';
import { Graph } from './Graph';
import { Timeline } from './Timeline';
export function CampaignPane({ history, at, navigate, name }: {
  history: History; at: string | null; navigate: (value: string | null) => void; name: string;
}) {
  const snapshot = useMemo(() => history.snapshot(at), [history, at]);
  const states = useMemo(() => history.states(snapshot), [history, snapshot]);
  const [filter, setFilter] = useState<Filter>('all');
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const [view, setView] = useState('graph'); const [input, setInput] = useState(at ?? '');
  const [playing, setPlaying] = useState(false);
  useEffect(() => setInput(at ?? ''), [at]);
  useEffect(() => {
    if (selected && !snapshot.tasks.some(task => task.id === selected)) setSelected(null);
  }, [snapshot, selected]);
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      const next = history.events.find(event => !at || Date.parse(event.timestamp) > Date.parse(at));
      if (next) navigate(next.timestamp); else setPlaying(false);
    }, 250);
    return () => clearInterval(timer);
  }, [playing, at, history, navigate]);
  const rows = useMemo(() => snapshot.tasks.filter(task => filter === 'all' ||
    (filter === 'blocked' || filter === 'ready' ? states.get(task.id)![filter] : task.status === filter))
    .sort((left, right) => left.id < right.id ? -1 : left.id > right.id ? 1 : 0), [snapshot, states, filter]);
  const blocked = [...states.values()].filter(state => state.blocked).length;
  const ready = [...states.values()].filter(state => state.ready).length;
  const toggle = (id: string) => setExpanded(previous => {
    const next = new Set(previous); if (next.has(id)) next.delete(id); else next.add(id); return next;
  });
  return <section data-testid={name} className="campaign-pane" aria-label={name === 'comparison-pane-at' ? 'Primary snapshot' : 'Comparison snapshot'}>
    <div className="toolbar">
      <label>Historical time<input aria-label="Historical time" value={input} placeholder="2026-04-16T10:15:00Z"
        onChange={event => setInput(event.target.value)} onKeyDown={event => {
          if (event.key === 'Enter' && Number.isFinite(Date.parse(input))) navigate(new Date(input).toISOString());
        }} /></label>
      <button onClick={() => Number.isFinite(Date.parse(input)) && navigate(new Date(input).toISOString())}>Go to time</button>
      <button onClick={() => navigate(null)}>Live</button>
      <button onClick={() => setPlaying(value => !value)}>{playing ? 'Pause playback' : 'Play'}</button>
      <label>Timeline position<input aria-label="Timeline position" type="range" min="0" max={history.events.length - 1}
        value={Math.max(0, history.events.findIndex(event => Date.parse(event.timestamp) >= Date.parse(at ?? '')))}
        onChange={event => navigate(history.events[Number(event.target.value)].timestamp)} /></label>
    </div>
    <p aria-label="Selected time">{at ?? 'live'}</p>
    <div className="toolbar">
      <label>Status filter<select aria-label="Status filter" value={filter} onChange={event => setFilter(event.target.value as Filter)}>
        {['all', 'pending', 'in_progress', 'completed', 'blocked', 'ready'].map(value => <option key={value}>{value}</option>)}
      </select></label>
      <output aria-label="Matching tasks">{rows.length}</output> matching tasks ·
      <output aria-label="Blocked tasks">{blocked}</output> blocked ·
      <output aria-label="Ready tasks">{ready}</output> ready
      <button onClick={() => setExpanded(new Set(snapshot.tasks.map(task => task.id)))}>Expand all</button>
      <button onClick={() => setExpanded(new Set())}>Collapse all</button>
      <button name="campaign-view" value="graph" onClick={event => setView(event.currentTarget.value)}>Graph view</button>
      <button name="campaign-view" value="timeline" onClick={event => setView(event.currentTarget.value)}>Timeline view</button>
    </div>
    <TaskTable tasks={rows} states={states} selected={selected} select={setSelected} />
    <Graph snapshot={snapshot} expanded={expanded} toggle={toggle} selected={selected} select={setSelected} active={view === 'graph'} />
    <Timeline events={history.events} at={at} navigate={navigate} />
  </section>;
}
