from collections import defaultdict


def summarize(rows, group_by, amount_field):
    groups = defaultdict(list)
    for row in rows:
        groups[row[group_by]].append(float(row[amount_field]))
    result = []
    for group, amounts in groups.items():
        total = sum(amounts)
        count = len(amounts)
        mean = total / count if count else 0.0
        result.append({"group": group, "count": count, "total": total, "mean": mean})
    result.sort(key=lambda x: x["total"], reverse=True)
    return result


def top_n(summaries, n):
    if n <= 0 or n >= len(summaries):
        return list(summaries)
    return summaries[:n]


def format_table(summaries):
    if not summaries:
        return "no rows"
    headers = ["group", "count", "total", "mean"]
    rows = [[str(s["group"]), str(s["count"]), f"{s['total']:.2f}", f"{s['mean']:.2f}"] for s in summaries]
    widths = [max(len(h), max(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    def fmt(cols):
        return "  ".join(c.ljust(w) for c, w in zip(cols, widths)).rstrip()
    lines = [fmt(headers), fmt(["-" * w for w in widths])]
    lines += [fmt(r) for r in rows]
    return "\n".join(lines)
