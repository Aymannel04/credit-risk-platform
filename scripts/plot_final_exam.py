"""Redraw docs/final_exam.png from results/final_exam.json (cosmetic: legend outside the bars).
Does not touch the frozen modelling code and does not recompute any number."""
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
r = json.loads((ROOT / "results" / "final_exam.json").read_text(encoding="utf-8"))
exams = list(r["exams"])
names = list(r["exams"][exams[0]]["models"])
x, w = np.arange(len(exams)), 0.2
fig, axes = plt.subplots(1, 2, figsize=(13, 4.8))
for j, n in enumerate(names):
    g = np.array([r["exams"][e]["models"][n]["gini"] for e in exams])
    lo = np.array([r["exams"][e]["models"][n]["ci95"]["gini"][0] for e in exams])
    hi = np.array([r["exams"][e]["models"][n]["ci95"]["gini"][1] for e in exams])
    axes[0].bar(x + (j - 1) * w, g, w, yerr=[g - lo, hi - g], capsize=3, label=n)
axes[0].set_xticks(x, exams)
axes[0].set_ylabel("Gini (higher = better ranking)")
axes[0].set_title("Ranking quality on the final exam (95% intervals)")
axes[0].legend(loc="lower center", ncol=3, fontsize=8)
axes[0].set_ylim(0, 0.9)
real = [r["exams"][e]["default_rate"] * 100 for e in exams]
axes[1].bar(x - 1.5 * w, real, w, color="black", label="real default rate")
for j, n in enumerate(names):
    axes[1].bar(x + (j - 0.5) * w, [r["exams"][e]["models"][n]["mean_predicted_pd"] * 100 for e in exams], w, label=n)
axes[1].set_xticks(x, exams)
axes[1].set_ylabel("average default rate (%)")
axes[1].set_title("Level: predicted vs real (the models over-predict out of time)")
axes[1].set_ylim(0, 2.9)
axes[1].legend(loc="upper left", ncol=2, fontsize=8)
fig.tight_layout()
fig.savefig(ROOT / "docs" / "final_exam.png", dpi=130)
print("redrawn docs/final_exam.png")
