from __future__ import annotations

from .official_board_posts import OfficialBoardPostSourceBase


class ServicePolicyPostSourceBase(OfficialBoardPostSourceBase):
    source_tag = "cuk_service_policy_posts"


class BiddingPostSource(ServicePolicyPostSourceBase):
    topic = "bidding"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/service/Bidding.do"):
        super().__init__(url)


class JobPostingPostSource(ServicePolicyPostSourceBase):
    topic = "job_posting"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/service/Job-posting.do"):
        super().__init__(url)
