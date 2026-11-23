import { create } from 'zustand';
import { Campaign } from './types';
import { History } from './history';
type CampaignStore = { campaigns: Record<string, History>; load: (id: string) => Promise<History> };
export const useCampaigns = create<CampaignStore>((set, get) => ({
  campaigns: {},
  async load(id) {
    if (get().campaigns[id]) return get().campaigns[id];
    const [tasks, dependencies, events] = await Promise.all(
      ['tasks', 'dependencies', 'events'].map(route => fetch(`/api/campaigns/${id}/${route}`).then(response => {
        if (!response.ok) throw new Error(`Campaign request failed: ${response.status}`);
        return response.json();
      })));
    const history = new History({ ...tasks, ...dependencies, ...events } as Campaign);
    set(state => ({ campaigns: { ...state.campaigns, [id]: history } }));
    return history;
  }
}));
