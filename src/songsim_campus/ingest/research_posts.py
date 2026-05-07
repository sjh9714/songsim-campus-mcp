from __future__ import annotations

from .official_board_posts import OfficialBoardPostSourceBase


class ResearchResultPostSource(OfficialBoardPostSourceBase):
    source_tag = "cuk_research_posts"
    topic = "research_result"

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/research/result.do"):
        super().__init__(url)
