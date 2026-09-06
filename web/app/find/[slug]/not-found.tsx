import Link from 'next/link';
import TopBar from '@/components/TopBar';
import EmptyState from '@/components/EmptyState';

export default function PlaceNotFound() {
  return <>
    <TopBar title="위치 찾기" subtitle="캠퍼스 장소" />
    <section className="card">
      <EmptyState message="요청한 장소를 찾을 수 없어요." hint="찾기 목록이나 검색에서 장소를 다시 선택해 주세요." />
      <Link className="linkout" href="/find">찾기 목록으로</Link>
    </section>
  </>;
}
