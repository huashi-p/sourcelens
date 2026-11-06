CLAIM_FIELDS = {
    "common_points": 2,
    "conflicts": 1,
    "unanswered": 1,
    "limitations": 1,
}

def source_links(source_ids, source_urls):
    return ", ".join(
        f"[{source_id}]({url})"
        for source_id, url in zip(source_ids, source_urls)
    )


def claim_lines(claims, heading):
    lines = [f"## {heading}"]

    if not claims:
        return lines + ["- 暂无"]

    for claim in claims:
        lines.append(f"- {claim['text']}")
        lines.append(
            "  - 来源："
            + source_links(
                claim["source_ids"],
                claim["source_urls"],
            )
        )

    return lines

def verify_report(report, sources):
    allowed_urls = {
        source.final_url or source.url
        for source in sources
        if source.ok
    }
    issues = []

    for field, minimum_sources in CLAIM_FIELDS.items():
        for claim in report.get(field, []):
            source_urls = claim.get("source_urls", [])
            unique_urls = set(source_urls)

            if len(unique_urls) < minimum_sources:
                issues.append(
                    f"{field} 来源数量不足：{claim.get('text', '')}"
                )

            if not unique_urls <= allowed_urls:
                issues.append(
                    f"{field} 引用了失败或不存在的来源"
                )

            if not claim.get("evidence_quote", "").strip():
                issues.append(
                    f"{field} 缺少证据原文"
                )

    return {
        "ok": not issues,
        "issues": issues,
    }

def render_markdown(report):
    lines = ["# SourceLens 交叉验证报告", ""]

    lines += claim_lines(report.get("common_points", []), "共同观点")
    lines.append("")
    lines += claim_lines(report.get("conflicts", []), "冲突信息")
    lines.append("")
    lines += claim_lines(report.get("unanswered", []), "未回答问题")
    lines.append("")
    lines += claim_lines(report.get("limitations", []), "资料限制")
    lines.append("")
    lines.append("## 来源")

    for source in report.get("successful_sources", []):
        lines.append(
            f"- {source['source_id']}: {source['url']}"
        )

    for source in report.get("failed_sources", []):
        lines.append(
            f"- 失败来源：{source['url']}，原因：{source['error']}"
        )

    return "\n".join(lines)