from __future__ import annotations

import re


PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
EMAIL_RE = re.compile(r"([A-Za-z0-9._%+-])[A-Za-z0-9._%+-]*(@[A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def redact_pii(text: str) -> str:
    """
    PII 脱敏 (新版函数名,用于 Guardrails)

    脱敏规则:
    - 手机号: 保留前3位和后4位,中间用 **** 代替
    - 邮箱: 保留第一个字符和 @ 后的域名,用户名部分用 *** 代替
    """
    text = PHONE_RE.sub(lambda m: f"{m.group(1)[:3]}****{m.group(1)[-4:]}", text)
    return EMAIL_RE.sub(lambda m: f"{m.group(1)}***{m.group(2)}", text)
