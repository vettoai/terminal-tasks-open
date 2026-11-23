import { useRouter } from 'next/router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ParsedUrlQuery } from 'querystring';
import { CampaignPane } from '../../components/CampaignPane';
import { useCampaigns } from '../../lib/store';
import { History } from '../../lib/history';

function selections(query: ParsedUrlQuery) {
  return {
    at: typeof query.at === 'string' ? query.at : null,
    compareAt: typeof query.compareAt === 'string' && query.compareAt !== 'live' ? query.compareAt : null,
    comparing: typeof query.compareAt === 'string',
  };
}

export default function CampaignPage() {
  const router = useRouter();
  const [history, setHistory] = useState<History | null>(null);
  const [error, setError] = useState('');
  const load = useCampaigns(state => state.load);
  const id = typeof router.query.id === 'string' ? router.query.id : '';
  const [selected, setSelected] = useState(() => selections(router.query));
  const desired = useRef<ParsedUrlQuery>({ ...router.query });
  const routing = useRef(router);
  const writing = useRef(false);
  const revision = useRef(0);
  routing.current = router;

  useEffect(() => {
    if (!router.isReady || writing.current) return;
    desired.current = { ...router.query };
    setSelected(selections(router.query));
  }, [router.isReady, router.asPath]);

  useEffect(() => {
    if (!id) return;
    let active = true;
    load(id).then(value => active && setHistory(value)).catch(reason => active && setError(String(reason)));
    return () => { active = false; };
  }, [id, load]);

  const publish = useCallback(async () => {
    if (writing.current) return;
    writing.current = true;
    try {
      let published: number;
      do {
        published = revision.current;
        await routing.current.replace({ pathname: routing.current.pathname, query: { ...desired.current } },
          undefined, { shallow: true, scroll: false });
      } while (published !== revision.current);
    } finally {
      writing.current = false;
    }
  }, []);

  const navigate = useCallback((key: string, value: string | null | undefined) => {
    const query = { ...desired.current };
    if (key === 'compareAt' && value === null) query[key] = 'live';
    else if (value) query[key] = value;
    else delete query[key];
    desired.current = query;
    revision.current += 1;
    setSelected(selections(query));
    void publish().catch(reason => setError(String(reason)));
  }, [publish]);
  const navigatePrimary = useCallback((value: string | null) => navigate('at', value), [navigate]);
  const navigateComparison = useCallback((value: string | null) => navigate('compareAt', value), [navigate]);

  if (error) return <p role="alert">{error}</p>;
  if (!history) return <p>Loading campaign…</p>;
  return <main>
    <header><h1>Campaign administration · {id}</h1>
      <button onClick={() => navigate('compareAt', selected.comparing ? undefined : '2026-04-16T10:50:00.000Z')}>
        {selected.comparing ? 'Close comparison' : 'Compare snapshots'}</button></header>
    <div className={selected.comparing ? 'comparison' : ''}>
      <CampaignPane key={`${id}-at`} history={history} at={selected.at} navigate={navigatePrimary} name="comparison-pane-at" />
      {selected.comparing && <CampaignPane key={`${id}-compare`} history={history} at={selected.compareAt}
        navigate={navigateComparison} name="comparison-pane-compare-at" />}
    </div>
  </main>;
}
