from collections import defaultdict


class Network:
    def __init__(self, edges):
        self.edges = defaultdict(list)
        for edge in edges:
            self.edges[edge['edge_id']].append(edge)
        for rows in self.edges.values():
            rows.sort(key=lambda row: row['band_start'])

    def at(self, edge_id, departure):
        for band in self.edges[edge_id]:
            if band['band_start'] <= departure < band['band_end']:
                return band
        raise ValueError(f'No traffic band for {edge_id} at {departure}')

    def trip(self, edge_ids, departure):
        movements = []
        for edge_id in edge_ids:
            band = self.at(edge_id, departure)
            arrival = departure + band['minutes']
            movements.append({'edge_id': edge_id, 'from': band['origin'], 'to': band['destination'],
                              'start': departure, 'end': arrival, 'distance_km': band['distance_km']})
            departure = arrival
        return movements
