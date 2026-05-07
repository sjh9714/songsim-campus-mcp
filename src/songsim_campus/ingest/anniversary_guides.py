from __future__ import annotations

from .static_resource_guides import StaticResourceGuideSourceBase


class AnniversaryGuideSourceBase(StaticResourceGuideSourceBase):
    source_tag = "cuk_anniversary_guides"


class AnniversaryPresidentMessageGuideSource(AnniversaryGuideSourceBase):
    topic = "president_message"
    default_title = "총장 축사글"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/170ani/president-message-170.do",
    ):
        super().__init__(url)


class AnniversaryMilestoneGuideSource(AnniversaryGuideSourceBase):
    topic = "milestone"
    default_title = "170년의 빛, 30년의 도약"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/170ani/milestone-170.do"):
        super().__init__(url)


class AnniversarySloganGuideSource(AnniversaryGuideSourceBase):
    topic = "slogan"
    default_title = "슬로건"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/170ani/slogan-170.do"):
        super().__init__(url)


class AnniversaryPromoVideoGuideSource(AnniversaryGuideSourceBase):
    topic = "promo_video"
    default_title = "170주년 홍보영상"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/170ani/promo-video-170.do"):
        super().__init__(url)


class AnniversaryOnlineMuseumGuideSource(AnniversaryGuideSourceBase):
    topic = "online_museum"
    default_title = "온라인 역사관"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/170ani/online-museum-170.do"):
        super().__init__(url)


class AnniversaryEventScheduleGuideSource(AnniversaryGuideSourceBase):
    topic = "event_schedule"
    default_title = "기념사업 일정표"

    def __init__(
        self,
        url: str = "https://www.catholic.ac.kr/ko/170ani/event-schedule-170_1.do",
    ):
        super().__init__(url)


class AnniversaryDonationInfoGuideSource(AnniversaryGuideSourceBase):
    topic = "donation_info"
    default_title = "기부소개"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/170ani/donation-info-170.do"):
        super().__init__(url)
