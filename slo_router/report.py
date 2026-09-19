"""Render a dependency-free Markdown summary and SVG policy comparison."""
import argparse
import html
import json
from pathlib import Path

from .replay import summarize


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results")
    parser.add_argument("--output", default="benchmark-report.md")
    parser.add_argument("--svg", default="benchmark-report.svg")
    args = parser.parse_args()
    rows = [json.loads(line) for line in Path(args.results).read_text().splitlines() if line.strip()]
    policies = list(dict.fromkeys(row["policy"] for row in rows))
    metrics = [(policy, summarize([row for row in rows if row["policy"] == policy])) for policy in policies]
    lines = [
        "# Replay benchmark report", "",
        "> Results reflect the supplied replay file. The bundled demo uses deterministic simulated backends and is not a model benchmark.", "",
        "| Policy | Completed | Accuracy | SLO success | p50 ms | p95 ms | Predicted cost | Cost / correct-in-SLO | Routes | Features |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for policy, m in metrics:
        routes = ", ".join("%s=%s" % item for item in m["routes"].items())
        sources = ", ".join("%s=%s" % item for item in m["feature_sources"].items())
        lines.append("| %s | %d/%d | %.3f | %.3f | %.2f | %.2f | $%.8f | $%.8f | %s | %s |" % (
            policy, m["completed"], m["requests"], m["accuracy"] or 0, m["slo_success_rate"] or 0,
            m["p50_ms"] or 0, m["p95_ms"] or 0, m["predicted_cost_usd"],
            m["cost_per_correct_in_slo_usd"] or 0, routes, sources,
        ))
    Path(args.output).write_text("\n".join(lines) + "\n")

    width, height = 900, 110 + 45 * len(metrics)
    max_cost = max((m["predicted_cost_usd"] for _, m in metrics), default=1) or 1
    max_latency = max((m["p95_ms"] or 0 for _, m in metrics), default=1) or 1
    svg = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
           '<rect width="100%" height="100%" fill="#0b1020"/>',
           '<style>text{font-family:ui-monospace,monospace;fill:#e5e7eb;font-size:12px}.h{font-size:16px;font-weight:bold}.a{fill:#34d399}.l{fill:#60a5fa}.c{fill:#f59e0b}</style>',
           '<text x="20" y="28" class="h">SLO Router replay: quality, p95 latency, predicted cost</text>',
           '<text x="220" y="55">accuracy</text><text x="470" y="55">p95 latency</text><text x="720" y="55">cost</text>']
    for i, (policy, m) in enumerate(metrics):
        y = 80 + i * 45
        accuracy = m["accuracy"] or 0
        latency = m["p95_ms"] or 0
        cost = m["predicted_cost_usd"]
        svg.extend([
            f'<text x="20" y="{y + 14}">{html.escape(policy)}</text>',
            f'<rect class="a" x="220" y="{y}" width="{200 * accuracy:.1f}" height="18"/><text x="425" y="{y + 14}">{accuracy:.3f}</text>',
            f'<rect class="l" x="470" y="{y}" width="{170 * latency / max_latency:.1f}" height="18"/><text x="645" y="{y + 14}">{latency:.1f}ms</text>',
            f'<rect class="c" x="720" y="{y}" width="{120 * cost / max_cost:.1f}" height="18"/><text x="845" y="{y + 14}">${cost:.6f}</text>',
        ])
    svg.append('</svg>')
    Path(args.svg).write_text("\n".join(svg) + "\n")
    print(json.dumps({"report": args.output, "svg": args.svg, "policies": len(metrics)}))


if __name__ == "__main__":
    main()
