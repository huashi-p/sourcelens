from application_service import dump


def reflect_match_result(match_result):
    issues = []

    for item in match_result.get("matches", []):
        requirement = item.get("requirement", "")
        status = item.get("match_status")
        evidence = item.get("evidence", [])

        if status in {"matched", "partial"} and not evidence:
            issues.append(
                f"{requirement}：状态为 {status}，但没有证据"
            )
        elif status == "missing" and evidence:
            issues.append(
                f"{requirement}：标记缺失，却返回了证据"
            )
        elif status not in {"matched", "partial", "missing"}:
            issues.append(
                f"{requirement}：未知匹配状态 {status}"
            )
            for evidence_item in evidence:
                if not evidence_item.get("evidence_id"):
                    issues.append(
                        f"{requirement}：证据缺少 evidence_id"
                    )
                if not evidence_item.get("quote", "").strip():
                    issues.append(
                        f"{requirement}：证据缺少原文引用"
                    )

        return dump(
            {
                "ok": not issues,
                "issues": issues,
            }
        )