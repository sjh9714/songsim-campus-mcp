import EmptyState from '@/components/EmptyState';
import StaleBadge from '@/components/StaleBadge';
import TopBar from '@/components/TopBar';
import { getPhoneBook, getPlaces, requireFreshOrKeepLastPage } from '@/lib/api';

export const revalidate = 86400;

export default async function FindPage() {
  const [buildings, facilities, phones] = await Promise.all([
    getPlaces({ category: 'building', limit: 50 }),
    getPlaces({ category: 'facility', limit: 50 }),
    getPhoneBook({ limit: 30 }),
  ]);
  requireFreshOrKeepLastPage(buildings, '건물 목록');

  return (
    <>
      <TopBar title="찾기" subtitle="건물, 시설, 부서 전화번호" />

      <section className="card">
        <div className="card__head">
          <h2 className="card__title">건물</h2>
          <StaleBadge state={buildings} />
        </div>
        {buildings.data.length === 0 ? (
          <EmptyState degraded={buildings.degraded} message="등록된 건물이 없어요." />
        ) : (
          <ul className="list">
            {buildings.data.map((place) => (
              <li key={place.id}>
                <div className="row__title">{place.name}</div>
                {place.aliases.length > 0 ? (
                  <div className="row__sub">{place.aliases.join(', ')}</div>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <div className="card__head">
          <h2 className="card__title">시설</h2>
        </div>
        {facilities.data.length === 0 ? (
          <EmptyState degraded={facilities.degraded} message="등록된 시설이 없어요." />
        ) : (
          <ul className="list">
            {facilities.data.map((place) => (
              <li key={place.id}>
                <div className="row__title">{place.name}</div>
                {place.description ? <div className="row__sub">{place.description}</div> : null}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="card">
        <div className="card__head">
          <h2 className="card__title">부서 전화번호</h2>
          <StaleBadge state={phones} />
        </div>
        {phones.data.length === 0 ? (
          <EmptyState degraded={phones.degraded} message="등록된 전화번호가 없어요." />
        ) : (
          <ul className="list">
            {phones.data.map((entry) => (
              <li key={entry.id} className="row--split">
                <span>
                  <span className="row__title">{entry.department}</span>
                  {entry.tasks ? <span className="row__sub">{entry.tasks}</span> : null}
                </span>
                <a className="row__value" href={`tel:${entry.phone.replace(/[^0-9+]/g, '')}`}>
                  {entry.phone}
                </a>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
