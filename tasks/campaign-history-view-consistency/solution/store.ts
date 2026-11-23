import { create } from 'zustand';
import { Campaign } from './types';
import { History } from './history';
import { decodeCollections } from './ledger';
type CampaignStore = { campaigns: Record<string, History>; load: (id: string) => Promise<History> };
export const useCampaigns = create<CampaignStore>((set, get) => ({
  campaigns: {},
  async load(id) {
    if (get().campaigns[id]) return get().campaigns[id];
    const collections = await Promise.all(
      ['tasks', 'dependencies', 'events'].map(async route => {
        const response = await fetch(`/api/campaigns/${id}/${route}`);
        if (!response.ok) throw new Error(`Campaign request failed: ${response.status}`);
        return decodeCollections(await response.text());
      }));
    const history = new History(Object.assign({}, ...collections) as Campaign);
    set(state => ({ campaigns: { ...state.campaigns, [id]: history } }));
    return history;
  }
}));
