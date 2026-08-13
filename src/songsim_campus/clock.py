"""학교 시계.

이 서비스가 다루는 시각은 전부 성심교정 기준이다. 수업 교시, 시설 운영시간,
식당 영업시간, 학기 경계는 모두 한국 시간으로 적힌 값이고, 코드는 그 시/분을
그대로 읽어 판정한다.

예전에는 모듈마다 ``datetime.now().astimezone()`` 을 따로 두어 호스트 시간대를
따라갔다. 개발 기기가 KST 라 로컬에서는 늘 맞아 보였지만, 배포된 서버는 UTC 로
돌기 때문에 아홉 시간 어긋난 시각으로 판정했다. 실제로 빈 강의실이 목9교시
수업을 "오전 2:00" 이라고 답했고, 같은 실수가 끼니 판정과 식당 영업중 판정,
학기 계산에도 그대로 있었다.

같은 버그를 여섯 군데에 복사해 두었던 셈이라 한곳으로 모은다.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def now() -> datetime:
    """지금. 호스트가 어디에 있든 서울 기준이다."""
    return datetime.now(KST)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")


def coerce_datetime(value: datetime | None = None) -> datetime:
    """받은 시각을 서울 기준으로 읽는다.

    시간대가 없으면 서울로 본다. 붙어 있으면 서울로 환산한다. 같은 순간을
    UTC 로 적어 넘기든 KST 로 적어 넘기든 같은 답이 나와야 한다.
    """
    current = value if value is not None else now()
    if current.tzinfo is None:
        return current.replace(tzinfo=KST)
    return current.astimezone(KST)
