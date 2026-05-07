from __future__ import annotations

from .static_resource_guides import StaticResourceGuideSourceBase


class NewsroomResourceGuideSourceBase(StaticResourceGuideSourceBase):
    source_tag = "cuk_newsroom_resource_guides"


class BrochureGuideSource(NewsroomResourceGuideSourceBase):
    topic = "brochure"
    default_title = "공식브로슈어"
    default_summary = "가톨릭대학교 공식 브로슈어 열람 링크를 제공합니다."

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/newsroom/brochure.do"):
        super().__init__(url)


class CukStoryGuideSource(NewsroomResourceGuideSourceBase):
    topic = "cuk_story"
    default_title = "소식지 가대이야기"
    default_summary = "가톨릭대학교 소식지 가대이야기 열람 링크를 제공합니다."

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/newsroom/cukstory.do"):
        super().__init__(url)


class GalleryGuideSource(NewsroomResourceGuideSourceBase):
    topic = "gallery"
    default_title = "홍보자료실"
    default_summary = "가톨릭대학교 홍보자료실의 이미지 사진 DB 이용 안내를 제공합니다."

    def __init__(self, url: str = "https://www.catholic.ac.kr/ko/newsroom/gallery.do"):
        super().__init__(url)
