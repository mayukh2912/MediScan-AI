"""1-D CNN for heartbeat classification (waveform branch + RR-interval branch)."""
from __future__ import annotations

import torch
from torch import nn


class BeatCNN(nn.Module):
    def __init__(self, beat_len: int = 100, n_rr: int = 4, n_classes: int = 4):
        super().__init__()

        def block(cin, cout, k):
            return nn.Sequential(
                nn.Conv1d(cin, cout, k, padding=k // 2), nn.BatchNorm1d(cout), nn.ReLU(),
                nn.Conv1d(cout, cout, k, padding=k // 2), nn.BatchNorm1d(cout), nn.ReLU(),
                nn.MaxPool1d(2),
            )

        self.conv = nn.Sequential(block(1, 16, 7), block(16, 32, 5), block(32, 64, 3))
        self.gap = nn.AdaptiveAvgPool1d(1)
        self.rr = nn.Sequential(nn.Linear(n_rr, 16), nn.ReLU())
        self.head = nn.Sequential(nn.Dropout(0.3), nn.Linear(64 + 16, 64), nn.ReLU(),
                                  nn.Dropout(0.3), nn.Linear(64, n_classes))

    def forward(self, beat: torch.Tensor, rr: torch.Tensor) -> torch.Tensor:
        h = self.gap(self.conv(beat.unsqueeze(1))).squeeze(-1)
        return self.head(torch.cat([h, self.rr(rr)], dim=1))
