"""Small inline-SVG line charts for the engine page, copied from the Arma 3 lab (ac-lab/lab/charts.py); no scripts, colours from the page's CSS tokens,
so they follow light and dark mode)."""
from html import escape

COLOURS = ["var(--accent)", "var(--hostile)", "var(--unknown)", "var(--neutral)"]
W, H = 640, 250
L, R, T, B = 44, 12, 34, 34   # plot margins: left (y labels), right, top (legend), bottom (x labels)


def _nice_max(v: float) -> float:
    for m in (1, 2, 3, 5, 10, 20, 25, 40, 50, 60, 80, 100, 120, 150, 200):
        if v <= m:
            return m
    return v


def line_chart(title: str, versions: list, series: list, *, unit: str = "", ymax: float = None,
               target: tuple = None, band: tuple = None, notes: dict = None, better: str = "",
               prefix: str = "v") -> str:
    """series: [(name, {version: value})]; target: (value, label) dashed line; band: (lo, hi, label)
    shaded; notes: {version: short label} as faint vertical lines; better: 'higher' / 'lower'."""
    vals = [v for _, d in series for v in d.values() if v is not None]
    top = ymax or _nice_max(max(vals + [target[0] if target else 0, band[1] if band else 0]) * 1.08)
    pw, ph = W - L - R, H - T - B
    n = len(versions)
    x = {v: L + (pw * i / max(n - 1, 1)) for i, v in enumerate(versions)}
    y = lambda val: T + ph * (1 - min(val, top) / top)
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{escape(title)}" class="pchart">']
    # grid and y labels
    for k in range(5):
        val = top * k / 4
        yy = y(val)
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="var(--rule)" stroke-width="1"/>')
        lab = f"{val:.0f}" if top >= 10 else f"{val:.1f}"
        out.append(f'<text x="{L - 6}" y="{yy + 4:.1f}" text-anchor="end" class="ax">{lab}{unit}</text>')
    if band:
        out.append(f'<rect x="{L}" width="{pw}" y="{y(band[1]):.1f}" height="{y(band[0]) - y(band[1]):.1f}" fill="var(--neutral)" opacity="0.13"/>')
        out.append(f'<text x="{W - R - 4}" y="{y(band[1]) + 13:.1f}" text-anchor="end" class="ax">{escape(band[2])}</text>')
    if target:
        out.append(f'<line x1="{L}" x2="{W - R}" y1="{y(target[0]):.1f}" y2="{y(target[0]):.1f}" stroke="var(--ink)" stroke-dasharray="5 4" stroke-width="1.2" opacity="0.7"/>')
        out.append(f'<text x="{W - R - 4}" y="{y(target[0]) - 5:.1f}" text-anchor="end" class="ax">{escape(target[1])}</text>')
    for i, (v, lab) in enumerate(sorted((notes or {}).items())):
        if v in x:
            out.append(f'<line x1="{x[v]:.1f}" x2="{x[v]:.1f}" y1="{T}" y2="{T + ph}" stroke="var(--muted)" stroke-width="1" opacity="0.35"/>')
            right = x[v] > W - R - 90
            tx = x[v] - 3 if right else x[v] + 3
            out.append(f'<text x="{tx:.1f}" y="{T + 10 + 11 * (i % 2)}" text-anchor="{"end" if right else "start"}" class="ax note">{escape(lab)}</text>')
    # x labels: every one when few, else every other
    step = 1 if n <= 18 else 2
    for i, v in enumerate(versions):
        if i % step == 0 or i == n - 1:
            out.append(f'<text x="{x[v]:.1f}" y="{H - B + 16}" text-anchor="middle" class="ax">{prefix}{v}</text>')
    # series
    lx = L
    for si, (name, d) in enumerate(series):
        col = COLOURS[si % len(COLOURS)]
        pts = [(x[v], y(d[v])) for v in versions if d.get(v) is not None]
        if len(pts) > 1:
            out.append(f'<polyline fill="none" stroke="{col}" stroke-width="2.4" stroke-linejoin="round" points="'
                       + " ".join(f"{a:.1f},{b:.1f}" for a, b in pts) + '"/>')
        for v in versions:
            if d.get(v) is not None:
                out.append(f'<circle cx="{x[v]:.1f}" cy="{y(d[v]):.1f}" r="3.4" fill="{col}"><title>{escape(name)} {prefix}{v}: {d[v]}{unit}</title></circle>')
        out.append(f'<rect x="{lx}" y="10" width="12" height="4" fill="{col}"/><text x="{lx + 16}" y="16" class="lg">{escape(name)}</text>')
        lx += 22 + 7.2 * len(name)
    if better:
        out.append(f'<text x="{W - R}" y="16" text-anchor="end" class="ax">{"higher" if better == "higher" else "lower"} is better</text>')
    out.append("</svg>")
    return "".join(out)
