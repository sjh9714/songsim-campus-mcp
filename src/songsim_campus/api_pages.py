from __future__ import annotations

import html
import json


def render_admin_sync_page(
    *,
    state: dict[str, object],
    official_campus_id: str,
    official_course_year: int | None,
    official_course_semester: int | None,
    official_notice_pages: int,
) -> str:
    datasets = state["datasets"]
    recent_runs = state["recent_runs"]
    automation = state["automation"]

    def render_field(name: str, label: str, value: str = "") -> str:
        return (
            f'<label><span>{html.escape(label)}</span>'
            f'<input type="text" name="{html.escape(name)}" '
            f'value="{html.escape(value)}"></label>'
        )

    forms = [
        {
            "title": "snapshot",
            "fields": [
                render_field("campus", "campus", official_campus_id),
                render_field(
                    "year",
                    "year",
                    str(official_course_year or ""),
                ),
                render_field(
                    "semester",
                    "semester",
                    str(official_course_semester or ""),
                ),
                render_field(
                    "notice_pages",
                    "notice_pages",
                    str(official_notice_pages),
                ),
            ],
        },
        {
            "title": "places",
            "fields": [render_field("campus", "campus", official_campus_id)],
        },
        {"title": "library_hours", "fields": []},
        {"title": "library_seat_status", "fields": []},
        {"title": "facility_hours", "fields": []},
        {"title": "dining_menus", "fields": []},
        {
            "title": "courses",
            "fields": [
                render_field(
                    "year",
                    "year",
                    str(official_course_year or ""),
                ),
                render_field(
                    "semester",
                    "semester",
                    str(official_course_semester or ""),
                ),
            ],
        },
        {
            "title": "notices",
            "fields": [
                render_field(
                    "notice_pages",
                    "notice_pages",
                    str(official_notice_pages),
                )
            ],
        },
        {"title": "affiliated_notices", "fields": []},
        {"title": "campus_life_notices", "fields": []},
        {"title": "academic_calendar", "fields": []},
        {"title": "academic_support_guides", "fields": []},
        {"title": "academic_status_guides", "fields": []},
        {"title": "class_guides", "fields": []},
        {"title": "seasonal_semester_guides", "fields": []},
        {"title": "academic_milestone_guides", "fields": []},
        {"title": "student_activity_guides", "fields": []},
        {"title": "about_resource_guides", "fields": []},
        {"title": "student_exchange_guides", "fields": []},
        {"title": "student_exchange_partners", "fields": []},
        {"title": "phone_book_entries", "fields": []},
        {"title": "dormitory_guides", "fields": []},
        {"title": "leave_of_absence_guides", "fields": []},
        {"title": "campus_life_support_guides", "fields": []},
        {"title": "pc_software_entries", "fields": []},
        {"title": "scholarship_guides", "fields": []},
        {"title": "wifi_guides", "fields": []},
        {"title": "transport_guides", "fields": []},
    ]

    dataset_cards = "".join(
        (
            "<article class='card'>"
            f"<h3>{html.escape(str(item['name']))}</h3>"
            f"<p class='count'>{int(item['row_count'])}</p>"
            "<p class='meta'>last_synced_at: "
            f"{html.escape(str(item['last_synced_at'] or '-'))}</p>"
            "</article>"
        )
        for item in datasets
    )
    automation_rows = "".join(
        (
            "<tr>"
            f"<td>{html.escape(job.name)}</td>"
            f"<td>{job.interval_minutes}</td>"
            f"<td>{html.escape(str(job.last_run_at or '-'))}</td>"
            f"<td>{html.escape(str(job.last_status or '-'))}</td>"
            f"<td>{html.escape(str(job.next_due_at or '-'))}</td>"
            "</tr>"
        )
        for job in automation.jobs
    ) or "<tr><td colspan='5'>No automation jobs configured.</td></tr>"
    forms_html = "".join(
        (
            "<form method='post' action='/admin/sync/run' class='card sync-form'>"
            f"<h3>{html.escape(form['title'])}</h3>"
            f"<input type='hidden' name='target' value='{html.escape(form['title'])}'>"
            f"{''.join(form['fields'])}"
            "<button type='submit'>Run</button>"
            "</form>"
        )
        for form in forms
    )
    runs_html = "".join(
        (
            "<tr>"
            f"<td>{run.id}</td>"
            f"<td>{html.escape(run.target)}</td>"
            f"<td>{html.escape(run.status)}</td>"
            f"<td><code>{html.escape(json.dumps(run.params, ensure_ascii=False))}</code></td>"
            f"<td><code>{html.escape(json.dumps(run.summary, ensure_ascii=False))}</code></td>"
            f"<td>{html.escape(run.error_text or '-')}</td>"
            f"<td>{html.escape(run.started_at)}</td>"
            f"<td>{html.escape(run.finished_at or '-')}</td>"
            "</tr>"
        )
        for run in recent_runs
    ) or ("<tr><td colspan='8'>No sync runs yet.</td></tr>")
    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Songsim Admin Sync</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f5f1e7;
        --surface: #fffdf8;
        --ink: #162126;
        --muted: #5f6b6f;
        --line: #d5ccb6;
        --accent: #1c7c54;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: Georgia, "Noto Serif KR", serif;
        background:
          radial-gradient(circle at top left, rgba(28,124,84,0.08), transparent 30%),
          linear-gradient(180deg, #f9f4ea 0%, var(--bg) 100%);
        color: var(--ink);
      }}
      main {{ max-width: 1080px; margin: 0 auto; padding: 32px 20px 48px; }}
      h1 {{ margin: 0 0 8px; font-size: 2.2rem; }}
      p.lead {{ margin: 0 0 24px; color: var(--muted); }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 14px;
      }}
      .card {{
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 16px;
        box-shadow: 0 12px 30px rgba(22,33,38,0.06);
      }}
      .count {{ font-size: 2rem; margin: 8px 0 6px; }}
      .meta {{ color: var(--muted); font-size: 0.92rem; }}
      section {{ margin-top: 28px; }}
      .forms {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
        gap: 14px;
      }}
      .sync-form {{
        display: flex;
        flex-direction: column;
        gap: 10px;
      }}
      label {{ display: flex; flex-direction: column; gap: 6px; font-size: 0.92rem; }}
      input {{
        padding: 10px 12px;
        border-radius: 10px;
        border: 1px solid var(--line);
        background: white;
      }}
      button {{
        margin-top: auto;
        border: 0;
        border-radius: 999px;
        padding: 10px 14px;
        background: var(--accent);
        color: white;
        font-weight: 700;
        cursor: pointer;
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 16px;
        overflow: hidden;
      }}
      th, td {{
        padding: 12px;
        border-bottom: 1px solid #ebe3d1;
        text-align: left;
        vertical-align: top;
        font-size: 0.92rem;
      }}
      th {{ background: #f0e8d4; }}
      code {{ white-space: pre-wrap; word-break: break-word; }}
    </style>
  </head>
  <body>
    <main>
      <h1>Songsim Admin Sync</h1>
      <p class="lead">
        Run official syncs from the browser and inspect the latest results.
        <a href="/admin/observability">Open observability</a>
      </p>
      <section>
        <h2>Dataset Status</h2>
        <div class="grid">{dataset_cards}</div>
      </section>
      <section>
        <h2>Automation Status</h2>
        <p class="meta">
          enabled: {'yes' if automation.enabled else 'no'} · leader:
          {'yes' if automation.leader else 'no'}
        </p>
        <table>
          <thead>
            <tr>
              <th>job</th>
              <th>interval_minutes</th>
              <th>last_run_at</th>
              <th>last_status</th>
              <th>next_due_at</th>
            </tr>
          </thead>
          <tbody>{automation_rows}</tbody>
        </table>
      </section>
      <section>
        <h2>Run Sync</h2>
        <div class="forms">{forms_html}</div>
      </section>
      <section>
        <h2>Recent Runs</h2>
        <table>
          <thead>
            <tr>
              <th>id</th>
              <th>target</th>
              <th>status</th>
              <th>params</th>
              <th>summary</th>
              <th>error</th>
              <th>started_at</th>
              <th>finished_at</th>
            </tr>
          </thead>
          <tbody>{runs_html}</tbody>
        </table>
      </section>
    </main>
  </body>
</html>
"""


def render_landing_page(
    *,
    public_http_url: str,
    mcp_url: str,
    public_readonly: bool,
    oauth_enabled: bool,
    admin_link_html: str,
    gpt_actions_links_html: str,
) -> str:
    docs_url = f"{public_http_url}/docs"
    privacy_url = f"{public_http_url}/privacy"
    example_prompts = [
        "성심교정 중앙도서관 위치 알려줘",
        "2026년 1학기 객체지향 과목 찾아줘",
        "2026학년도 3월 학사일정 보여줘",
        "수업평가 기간 알려줘",
        "계절학기 신청 시기 알려줘",
        "국내 학점교류 신청대상 알려줘",
        "교환학생 프로그램 알려줘",
        "국제학부 최신 공지 알려줘",
        "국제학부 공결 신청 공지 있어?",
        "기숙사 일반공지 알려줘",
        "기숙사 OT 공지 알려줘",
        "프란치스코관 입퇴사공지 알려줘",
        "등록금 납부 방법 알려줘",
        "행사안내 알려줘",
        "학생상담 어디서 받아?",
        "장애학생지원센터 뭐 해줘?",
        "예비군 신고 시기 알려줘",
        "부속병원 이용 안내해줘",
        "성심교정 대관안내 알려줘",
        "개인형 이동장치 안전교육 알려줘",
        "보건실 위치와 운영시간 알려줘",
        "유실물 찾는 방법 알려줘",
        "성심교정 주차요금 알려줘",
        "보건실 전화번호 알려줘",
        "트리니티 문의 전화번호 알려줘",
        "SPSS 설치된 컴퓨터실 어디야",
        "포토샵 있는 PC실 알려줘",
        "Visual Studio 설치된 실습실 있어?",
        "성심교정 기숙사 안내해줘",
        "기숙사 최신 공지 알려줘",
        "외부기관공지 알려줘",
        "재학증명서 발급 안내 알려줘",
        "장학제도 안내 알려줘",
        "니콜스관 WIFI 안내 알려줘",
        "니콜스관인데 지금 예상 빈 강의실 있어?",
        "중앙도서관 근처 밥집 추천해줘",
        "최신 장학 공지 보여줘",
        "성심교정 지하철 오는 길 알려줘",
        "도보 10분 안쪽 카페만 보여줘",
    ]
    product_mode = "Public Read-only" if public_readonly else "Local Full"
    examples_html = "".join(f"<li>{html.escape(prompt)}</li>" for prompt in example_prompts)
    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Songsim Campus MCP</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f5f1e7;
        --surface: #fffdf8;
        --ink: #162126;
        --muted: #5f6b6f;
        --line: #d5ccb6;
        --accent: #174f7a;
        --accent-2: #1c7c54;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: Georgia, "Noto Serif KR", serif;
        background:
          radial-gradient(circle at top left, rgba(23,79,122,0.08), transparent 32%),
          linear-gradient(180deg, #faf5ea 0%, var(--bg) 100%);
        color: var(--ink);
      }}
      main {{ max-width: 1080px; margin: 0 auto; padding: 36px 20px 56px; }}
      h1 {{ margin: 0 0 10px; font-size: 2.4rem; }}
      p.lead {{ margin: 0 0 24px; color: var(--muted); font-size: 1.04rem; }}
      .hero {{
        display: grid;
        grid-template-columns: 1.4fr 1fr;
        gap: 18px;
        align-items: stretch;
      }}
      .card {{
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 18px;
        box-shadow: 0 12px 30px rgba(22,33,38,0.06);
      }}
      .meta {{ color: var(--muted); font-size: 0.92rem; }}
      .pill {{
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        padding: 8px 12px;
        background: #eaf2f7;
        color: var(--accent);
        text-decoration: none;
        font-weight: 700;
        margin-right: 8px;
      }}
      .primary {{ background: var(--accent-2); color: white; }}
      code {{
        display: block;
        padding: 12px;
        border-radius: 12px;
        background: #f3efe5;
        border: 1px solid #e0d6bf;
        overflow-x: auto;
        white-space: pre-wrap;
        word-break: break-word;
      }}
      ul {{ margin: 12px 0 0; padding-left: 18px; }}
      section {{ margin-top: 28px; }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 14px;
      }}
      @media (max-width: 800px) {{
        .hero {{ grid-template-columns: 1fr; }}
      }}
    </style>
  </head>
  <body>
    <main>
      <h1>Songsim Campus MCP</h1>
      <p class="lead">
        Verified Catholic University Songsim campus data server for places, courses,
        academic calendar, certificates, scholarships, campus wifi, notices, restaurants,
        and transit. The remote MCP endpoint is the primary public product surface, and the
        HTTP API is the thin companion layer.
      </p>
      <div class="hero">
        <section class="card">
          <p class="meta">Mode: {html.escape(product_mode)}</p>
          <p>
            This server exposes verified Songsim campus data through a remote read-only MCP
            endpoint for ChatGPT, Claude, and Codex-style clients, plus a companion HTTP API
            for direct lookups and verification.
          </p>
          <p class="meta">
            {
              (
                "Remote MCP access is the core public interface and currently "
                "requires OAuth login."
              )
              if oauth_enabled
              else (
                "Remote MCP access is the core public interface and is currently "
                "configured without OAuth."
              )
            }
          </p>
          <p>
            <a class="pill primary" href="{html.escape(docs_url)}">Open API Docs</a>
            <a class="pill" href="/openapi.json">OpenAPI JSON</a>
            {gpt_actions_links_html}
            <a class="pill" href="{html.escape(privacy_url)}">Privacy Policy</a>
            {admin_link_html}
          </p>
        </section>
        <section class="card">
          <h2>Public URLs</h2>
          <p class="meta">Remote MCP</p>
          <code>{html.escape(mcp_url)}</code>
          <p class="meta">HTTP API</p>
          <code>{html.escape(public_http_url)}</code>
        </section>
      </div>
      <section class="grid">
        <article class="card">
          <h2>What To Ask</h2>
          <ul>{examples_html}</ul>
        </article>
        <article class="card">
          <h2>Student HTTP Companion</h2>
          <ul>
            <li><code>/places</code> campus places and landmarks</li>
            <li><code>/courses</code> public course offerings</li>
            <li><code>/academic-calendar</code> current academic calendar events</li>
            <li>
              <code>/academic-support-guides</code> academic office contacts and
              responsibilities
            </li>
            <li>
              <code>/academic-status-guides</code> return-from-leave, dropout, and
              re-admission guides
            </li>
            <li><code>/registration-guides</code> tuition bill, payment, and refund guides</li>
            <li>
              <code>/class-guides</code> class registration, retake, evaluation,
              and excused-absence guides
            </li>
            <li>
              <code>/seasonal-semester-guides</code> seasonal semester eligibility,
              credit limit, schedule, and procedure guides
            </li>
            <li>
              <code>/academic-milestone-guides</code> grade evaluation, grade check,
              attendance threshold, and graduation requirement guides
            </li>
            <li>
              <code>/student-activity-guides</code> student government, campus media,
              social volunteering, and ROTC guides
            </li>
            <li>
              <code>/about-resource-guides</code> official rules, university bulletin,
              and academic handbook resource links
            </li>
            <li>
              <code>/student-exchange-guides</code> domestic credit exchange, partner
              universities, exchange student, and exchange program guides
            </li>
            <li>
              <code>/student-exchange-partners</code> overseas partner university
              directory search by country, continent, or university name
            </li>
            <li><code>/phone-book</code> campus-wide department contacts and phone numbers</li>
            <li>
              <code>/campus-life-support-guides</code> health center, counseling,
              disability, reservist, hospital use, facility rental, mobility
              safety, lost-found, and Songsim parking guides
            </li>
            <li>
              <code>/campus-life-notices</code> outside-agency and event campus-life
              notice bundles
            </li>
            <li>
              <code>/pc-software</code> lab rooms and installed software search
            </li>
            <li>
              <code>/dormitory-guides</code> dormitory hall info, quick links, and latest
              notice cards
            </li>
            <li>
              <code>/affiliated-notices</code> affiliated department and dormitory board
              notice bundles
            </li>
            <li><code>/certificate-guides</code> certificate issuance guides</li>
            <li><code>/leave-of-absence-guides</code> leave-of-absence application guides</li>
            <li><code>/scholarship-guides</code> scholarship baseline guides</li>
            <li><code>/wifi-guides</code> campus wifi SSIDs and connection steps</li>
            <li><code>/library-seats</code> central-library seat status</li>
            <li><code>/dining-menus</code> official weekly campus dining menus</li>
            <li>
              <code>/classrooms/empty</code> official realtime classrooms first,
              estimated fallback
            </li>
            <li><code>/restaurants/nearby</code> walkable food recommendations</li>
            <li><code>/restaurants/search</code> direct cafe and brand lookup</li>
            <li><code>/notices</code> latest public campus notices</li>
            <li><code>/transport</code> Songsim transit guides</li>
          </ul>
        </article>
        <article class="card">
          <h2>Remote MCP Pattern</h2>
          <ul>
            <li>Read <code>songsim://usage-guide</code> for the public MCP rules</li>
            <li>
              Use prompts to pick the first tool for places, courses, academic
              calendar, notices, guides, dining, library seats, classrooms,
              restaurants, affiliated notices, campus-life notices, or transport
            </li>
            <li>Call tools after the prompt narrows the correct public read-only flow</li>
          </ul>
        </article>
      </section>
    </main>
  </body>
</html>
"""


def render_privacy_page(*, public_http_url: str) -> str:
    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Songsim Campus Privacy Policy</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f5f1e7;
        --surface: #fffdf8;
        --ink: #162126;
        --muted: #5f6b6f;
        --line: #d5ccb6;
        --accent: #174f7a;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: Georgia, "Noto Serif KR", serif;
        background:
          radial-gradient(circle at top left, rgba(23,79,122,0.08), transparent 30%),
          linear-gradient(180deg, #f9f4ea 0%, var(--bg) 100%);
        color: var(--ink);
      }}
      main {{ max-width: 920px; margin: 0 auto; padding: 36px 20px 56px; }}
      .card {{
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 18px;
        padding: 20px;
        box-shadow: 0 12px 30px rgba(22,33,38,0.06);
      }}
      h1 {{ margin: 0 0 10px; font-size: 2.2rem; }}
      h2 {{ margin-top: 28px; }}
      p, li {{ line-height: 1.65; }}
      .meta {{ color: var(--muted); }}
      code {{
        display: inline-block;
        padding: 2px 6px;
        border-radius: 8px;
        background: #f3efe5;
        border: 1px solid #e0d6bf;
      }}
      a {{ color: var(--accent); }}
    </style>
  </head>
  <body>
    <main>
      <article class="card">
        <h1>Songsim Campus Privacy Policy</h1>
        <p class="meta">
          Effective date: 2026-03-14 · Service: Songsim Campus HTTP API,
          ChatGPT Actions, and Remote MCP
        </p>

        <h2>1. What this service does</h2>
        <p>
          Songsim Campus provides read-only access to Catholic University
          Songsim campus information such as
          places, public courses, notices, nearby restaurants, and transport guides.
        </p>

        <h2>2. Data we process</h2>
        <ul>
          <li>
            Request metadata needed to operate the service, such as timestamps,
            endpoint usage, and basic server logs.
          </li>
          <li>
            Query values you send to the API, ChatGPT Actions, or Remote MCP,
            such as place names or course search terms.
          </li>
          <li>
            Cached restaurant lookups from Kakao Local and Kakao place detail
            pages to improve response quality.
          </li>
        </ul>

        <h2>3. What we do not collect intentionally</h2>
        <ul>
          <li>We do not require account creation for the public read-only API.</li>
          <li>
            We do not intentionally collect sensitive personal information
            through the public API or ChatGPT Actions.
          </li>
          <li>We do not sell personal data.</li>
        </ul>

        <h2>4. Third-party services</h2>
        <ul>
          <li>Render is used for hosting the public application services.</li>
          <li>Supabase PostgreSQL is used for persistent storage.</li>
          <li>
            Kakao Local and Kakao place detail sources may be used to provide
            nearby restaurant data and opening hours.
          </li>
          <li>Auth0 and Google login may be used for Remote MCP OAuth access.</li>
          <li>
            ChatGPT Actions may send your requests to this API when you use a
            published GPT.
          </li>
        </ul>

        <h2>5. Retention</h2>
        <p>
          Operational logs and caches may be retained for debugging,
          observability, and service quality improvement.
          Cached restaurant and hours data are periodically cleaned up by automation jobs.
        </p>

        <h2>6. Contact</h2>
        <p>
          For issues related to this deployment, refer to the public service root at
          <a href="{html.escape(public_http_url)}">{html.escape(public_http_url)}</a>.
        </p>
      </article>
    </main>
  </body>
</html>
"""


def render_admin_observability_page(*, state: dict[str, object]) -> str:
    readiness = state["readiness"]
    observability = state["observability"]
    cache = observability["cache"]
    sync = observability["sync"]
    automation = observability["automation"]
    dataset_cards = "".join(
        (
            "<article class='card'>"
            f"<h3>{html.escape(str(item['name']))}</h3>"
            f"<p class='count'>{int(item['row_count'])}</p>"
            "<p class='meta'>last_synced_at: "
            f"{html.escape(str(item['last_synced_at'] or '-'))}</p>"
            "</article>"
        )
        for item in observability["datasets"]
    )
    cache_rows = "".join(
        (
            "<tr>"
            f"<td>{html.escape(str(event['decision']))}</td>"
            f"<td>{html.escape(str(event['origin_slug']))}</td>"
            f"<td>{html.escape(str(event['kakao_query']))}</td>"
            f"<td>{html.escape(str(event['radius_meters']))}</td>"
            f"<td>{html.escape(str(event['error_text'] or '-'))}</td>"
            f"<td>{html.escape(str(event['occurred_at']))}</td>"
            "</tr>"
        )
        for event in cache["recent_events"]
    ) or "<tr><td colspan='6'>No cache events yet.</td></tr>"
    sync_rows = "".join(
        (
            "<tr>"
            f"<td>{html.escape(str(event['target']))}</td>"
            f"<td>{html.escape(str(event['status']))}</td>"
            f"<td>{html.escape(str(event['duration_ms']))}</td>"
            "<td><code>"
            f"{html.escape(json.dumps(event['summary'], ensure_ascii=False))}"
            "</code></td>"
            f"<td>{html.escape(str(event['error_text'] or '-'))}</td>"
            f"<td>{html.escape(str(event['finished_at']))}</td>"
            "</tr>"
        )
        for event in sync["recent_events"]
    ) or "<tr><td colspan='6'>No sync events yet.</td></tr>"
    run_rows = "".join(
        (
            "<tr>"
            f"<td>{run['id']}</td>"
            f"<td>{html.escape(str(run['target']))}</td>"
            f"<td>{html.escape(str(run['status']))}</td>"
            f"<td>{html.escape(str(run['started_at']))}</td>"
            f"<td>{html.escape(str(run['finished_at'] or '-'))}</td>"
            "</tr>"
        )
        for run in observability["recent_sync_runs"]
    ) or "<tr><td colspan='5'>No sync run history yet.</td></tr>"
    readiness_rows = "".join(
        (
            "<tr>"
            f"<td>{html.escape(name)}</td>"
            f"<td>{'yes' if item['ok'] else 'no'}</td>"
            f"<td>{html.escape(str(item.get('row_count', '-')))}</td>"
            f"<td>{html.escape(str(item.get('last_synced_at', '-')))}</td>"
            f"<td>{html.escape(str(item.get('error') or '-'))}</td>"
            "</tr>"
        )
        for name, item in readiness["tables"].items()
    )
    automation_rows = "".join(
        (
            "<tr>"
            f"<td>{html.escape(str(job['name']))}</td>"
            f"<td>{html.escape(str(job['interval_minutes']))}</td>"
            f"<td>{html.escape(str(job['last_run_at'] or '-'))}</td>"
            f"<td>{html.escape(str(job['last_status'] or '-'))}</td>"
            f"<td>{html.escape(str(job['next_due_at'] or '-'))}</td>"
            "</tr>"
        )
        for job in automation["jobs"]
    ) or "<tr><td colspan='5'>No automation jobs configured.</td></tr>"
    return f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Songsim Observability</title>
    <style>
      :root {{
        color-scheme: light;
        --bg: #f5f1e7;
        --surface: #fffdf8;
        --ink: #162126;
        --muted: #5f6b6f;
        --line: #d5ccb6;
        --accent: #174f7a;
      }}
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: Georgia, "Noto Serif KR", serif;
        background:
          radial-gradient(circle at top left, rgba(23,79,122,0.08), transparent 30%),
          linear-gradient(180deg, #f9f4ea 0%, var(--bg) 100%);
        color: var(--ink);
      }}
      main {{ max-width: 1080px; margin: 0 auto; padding: 32px 20px 48px; }}
      h1 {{ margin: 0 0 8px; font-size: 2.2rem; }}
      p.lead {{ margin: 0 0 24px; color: var(--muted); }}
      .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 14px;
      }}
      .card {{
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 16px;
        padding: 16px;
        box-shadow: 0 12px 30px rgba(22,33,38,0.06);
      }}
      .count {{ font-size: 2rem; margin: 8px 0 6px; }}
      .meta {{ color: var(--muted); font-size: 0.92rem; }}
      section {{ margin-top: 28px; }}
      table {{
        width: 100%;
        border-collapse: collapse;
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: 16px;
        overflow: hidden;
      }}
      th, td {{
        padding: 12px;
        border-bottom: 1px solid #ebe3d1;
        text-align: left;
        vertical-align: top;
        font-size: 0.92rem;
      }}
      th {{ background: #f0e8d4; }}
      code {{ white-space: pre-wrap; word-break: break-word; }}
      .nav {{ display: flex; gap: 12px; margin-bottom: 16px; }}
      .pill {{
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        padding: 8px 12px;
        background: #eaf2f7;
        color: var(--accent);
        text-decoration: none;
        font-weight: 700;
      }}
    </style>
  </head>
  <body>
    <main>
      <div class="nav">
        <a class="pill" href="/admin/sync">Admin Sync</a>
        <a class="pill" href="/admin/observability.json">JSON</a>
      </div>
      <h1>Songsim Observability</h1>
      <p class="lead">
        healthz: ok · readyz: {'ok' if readiness['ok'] else 'degraded'} · process_started_at:
        {html.escape(str(observability['process_started_at']))}
      </p>
      <section>
        <h2>Datasets</h2>
        <div class="grid">{dataset_cards}</div>
      </section>
      <section>
        <h2>Readiness</h2>
        <table>
          <thead>
            <tr>
              <th>check</th>
              <th>ok</th>
              <th>row_count</th>
              <th>last_synced_at</th>
              <th>error</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>database</td>
              <td>{'yes' if readiness['database']['ok'] else 'no'}</td>
              <td>-</td>
              <td>-</td>
              <td>{html.escape(str(readiness['database']['error'] or '-'))}</td>
            </tr>
            {readiness_rows}
          </tbody>
        </table>
      </section>
      <section>
        <h2>Automation</h2>
        <p class="meta">
          enabled: {'yes' if automation['enabled'] else 'no'} · leader:
          {'yes' if automation['leader'] else 'no'}
        </p>
        <table>
          <thead>
            <tr>
              <th>job</th>
              <th>interval_minutes</th>
              <th>last_run_at</th>
              <th>last_status</th>
              <th>next_due_at</th>
            </tr>
          </thead>
          <tbody>{automation_rows}</tbody>
        </table>
      </section>
      <section>
        <h2>Cache Counters</h2>
        <div class="grid">
          <article class="card">
            <h3>fresh_hit</h3>
            <p class="count">{cache['fresh_hit']}</p>
          </article>
          <article class="card">
            <h3>stale_hit</h3>
            <p class="count">{cache['stale_hit']}</p>
          </article>
          <article class="card">
            <h3>live_fetch_success</h3>
            <p class="count">{cache['live_fetch_success']}</p>
          </article>
          <article class="card">
            <h3>live_fetch_error</h3>
            <p class="count">{cache['live_fetch_error']}</p>
          </article>
          <article class="card">
            <h3>local_fallback</h3>
            <p class="count">{cache['local_fallback']}</p>
          </article>
          <article class="card">
            <h3>restaurant_hours_fresh_hit</h3>
            <p class="count">{cache['restaurant_hours_fresh_hit']}</p>
          </article>
          <article class="card">
            <h3>restaurant_hours_stale_hit</h3>
            <p class="count">{cache['restaurant_hours_stale_hit']}</p>
          </article>
          <article class="card">
            <h3>restaurant_hours_live_fetch_success</h3>
            <p class="count">{cache['restaurant_hours_live_fetch_success']}</p>
          </article>
          <article class="card">
            <h3>restaurant_hours_live_fetch_error</h3>
            <p class="count">{cache['restaurant_hours_live_fetch_error']}</p>
          </article>
        </div>
      </section>
      <section>
        <h2>Recent Cache Events</h2>
        <table>
          <thead>
            <tr>
              <th>decision</th>
              <th>origin</th>
              <th>query</th>
              <th>radius</th>
              <th>error</th>
              <th>occurred_at</th>
            </tr>
          </thead>
          <tbody>{cache_rows}</tbody>
        </table>
      </section>
      <section>
        <h2>Recent Sync Events</h2>
        <p class="meta">
          last_failure: {html.escape(str(sync['last_failure_message'] or '-'))}
          at {html.escape(str(sync['last_failure_at'] or '-'))}
        </p>
        <table>
          <thead>
            <tr>
              <th>target</th>
              <th>status</th>
              <th>duration_ms</th>
              <th>summary</th>
              <th>error</th>
              <th>finished_at</th>
            </tr>
          </thead>
          <tbody>{sync_rows}</tbody>
        </table>
      </section>
      <section>
        <h2>Recent Sync Runs</h2>
        <table>
          <thead>
            <tr>
              <th>id</th>
              <th>target</th>
              <th>status</th>
              <th>started_at</th>
              <th>finished_at</th>
            </tr>
          </thead>
          <tbody>{run_rows}</tbody>
        </table>
      </section>
    </main>
  </body>
</html>
"""
