import numpy as np
from math import ceil

class histogram_helpers:

    @staticmethod
    def calculate_histogram(data, bins: int, signal: str):
        t0 = 0
        t1 = data.sample_count / data.sample_frequency

        stats = data.view.statistics_get(t0, t1)['signals'][signal]['statistics']
        maximum, minimum = stats['max'], stats['min']
        width = 3.5 * stats['σ'] / (data.sample_count)**(1. / 3)
        num_bins = bins if bins > 0 else ceil((maximum - minimum) / width)

        data_enum = enumerate(data)
        _, data_chunk = data_enum.__next__()

        # bin edges must be consistent, therefore calculate this first chunk to enforce standard bin edges
        hist, bin_edges = np.histogram(
            data_chunk[signal]['value'], range=(minimum, maximum), bins=num_bins)

        for _, data_chunk in data_enum:
            hist += np.histogram(data_chunk[signal]['value'], bins=bin_edges)[0]

        return hist, bin_edges

    @staticmethod
    def normalize_hist(hist, bin_edges, norm: str = 'density'):
        if norm == 'density':
            db = np.array(np.diff(bin_edges), float)
            return hist/db/hist.sum(), bin_edges
        elif norm == 'unity':
            return hist/hist.sum(), bin_edges
        elif norm == 'count':
            return hist, bin_edges
        else:
            raise RuntimeWarning(
                '_normalize_hist invalid normalization; possible values are "density", "unity", or None')
