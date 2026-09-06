import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';

const fixture = JSON.parse(await readFile(new URL('../../data/qa/web-fixture.json', import.meta.url), 'utf8'));
createServer((request, response) => {
  const url = new URL(request.url, 'http://127.0.0.1:8019');
  const path = url.pathname.slice(1);
  const query = (url.searchParams.get('query') ?? '').replace(/\s+/g, '');
  let data = fixture[path] ?? [];
  let status = 200;
  if (path === 'healthz') data = { status: 'ok' };
  if (path === 'places') {
    data = fixture.places.filter((p) => !query || [p.name, ...p.aliases].some((name) => query.includes(name.replace(/\s+/g, ''))));
    const facility = fixture.facilities.find((f) => query.includes(f.name.replace(/\s+/g, '')));
    if (facility) data = [{ ...fixture.places.find((p) => p.slug === facility.slug), matched_facility: facility }];
    if (url.searchParams.has('category')) data = data.filter((p) => p.category === url.searchParams.get('category'));
  } else if (path.startsWith('places/')) {
    data = fixture.places.find((p) => p.slug === path.split('/')[1]);
    if (!data) { status = 404; data = { detail: 'Not found' }; }
  } else if (path === 'phone-book' && query) {
    data = data.filter((p) => query.includes(p.department) || query.includes(p.tasks));
  }
  if (query.includes('부분실패') && path === 'courses') status = 503;
  if (query.includes('부분실패') && path === 'places') data = [fixture.places[0]];
  response.writeHead(status, { 'Content-Type': 'application/json' });
  response.end(JSON.stringify(data));
}).listen(8019, '127.0.0.1');
