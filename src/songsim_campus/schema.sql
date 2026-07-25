CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS places (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    aliases_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    description TEXT NOT NULL DEFAULT '',
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    geom GEOGRAPHY(Point, 4326) GENERATED ALWAYS AS (
        CASE
            WHEN longitude IS NULL OR latitude IS NULL THEN NULL
            ELSE ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
        END
    ) STORED,
    opening_hours_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS courses (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    year INTEGER NOT NULL,
    semester INTEGER NOT NULL,
    code TEXT NOT NULL,
    title TEXT NOT NULL,
    professor TEXT,
    department TEXT,
    section TEXT,
    day_of_week TEXT,
    period_start INTEGER,
    period_end INTEGER,
    room TEXT,
    raw_schedule TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS restaurants (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    min_price INTEGER,
    max_price INTEGER,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    geom GEOGRAPHY(Point, 4326) GENERATED ALWAYS AS (
        CASE
            WHEN longitude IS NULL OR latitude IS NULL THEN NULL
            ELSE ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
        END
    ) STORED,
    tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    description TEXT NOT NULL DEFAULT '',
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS restaurant_cache_snapshots (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    origin_slug TEXT NOT NULL,
    kakao_query TEXT NOT NULL,
    radius_meters INTEGER NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL,
    source_tag TEXT NOT NULL DEFAULT 'kakao_local_cache'
);

CREATE TABLE IF NOT EXISTS restaurant_cache_items (
    snapshot_id INTEGER NOT NULL,
    item_order INTEGER NOT NULL,
    restaurant_id INTEGER NOT NULL,
    slug TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    min_price INTEGER,
    max_price INTEGER,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    kakao_place_id TEXT,
    source_url TEXT,
    geom GEOGRAPHY(Point, 4326) GENERATED ALWAYS AS (
        CASE
            WHEN longitude IS NULL OR latitude IS NULL THEN NULL
            ELSE ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)::geography
        END
    ) STORED,
    tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    description TEXT NOT NULL DEFAULT '',
    source_tag TEXT NOT NULL DEFAULT 'kakao_local_cache',
    last_synced_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (snapshot_id, item_order),
    FOREIGN KEY (snapshot_id) REFERENCES restaurant_cache_snapshots(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS restaurant_hours_cache (
    kakao_place_id TEXT PRIMARY KEY,
    source_url TEXT,
    raw_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    opening_hours_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    fetched_at TIMESTAMPTZ NOT NULL,
    source_tag TEXT NOT NULL DEFAULT 'kakao_place_detail_cache'
);

CREATE TABLE IF NOT EXISTS library_seat_status_cache (
    room_name TEXT PRIMARY KEY,
    remaining_seats INTEGER,
    occupied_seats INTEGER,
    total_seats INTEGER,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS notices (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    category TEXT NOT NULL,
    published_at DATE NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    labels_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS affiliated_notices (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at DATE NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    body_text TEXT NOT NULL DEFAULT '',
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS campus_life_notices (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at DATE NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS transport_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    mode TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS certificate_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS scholarship_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS leave_of_absence_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS wifi_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    building_name TEXT NOT NULL,
    ssids_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS academic_support_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    contacts_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS academic_status_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    status TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS registration_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS class_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS seasonal_semester_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS academic_milestone_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS student_exchange_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS student_activity_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS student_activity_notices (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    article_no TEXT,
    title TEXT NOT NULL,
    published_at DATE,
    summary TEXT NOT NULL DEFAULT '',
    body_text TEXT NOT NULL DEFAULT '',
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS about_resource_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS service_policy_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS service_policy_posts (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    article_no TEXT,
    title TEXT NOT NULL,
    published_at DATE,
    summary TEXT NOT NULL DEFAULT '',
    body_text TEXT NOT NULL DEFAULT '',
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS newsroom_posts (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    article_no TEXT,
    title TEXT NOT NULL,
    published_at DATE,
    summary TEXT NOT NULL DEFAULT '',
    thumbnail_url TEXT,
    external_url TEXT,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS research_posts (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    article_no TEXT,
    title TEXT NOT NULL,
    published_at DATE,
    summary TEXT NOT NULL DEFAULT '',
    body_text TEXT NOT NULL DEFAULT '',
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS newsroom_resource_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS anniversary_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS student_exchange_partners (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    partner_code TEXT NOT NULL,
    university_name TEXT NOT NULL,
    country_ko TEXT,
    country_en TEXT,
    continent TEXT,
    location TEXT,
    agreement_date TEXT,
    homepage_url TEXT,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS dormitory_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS phone_book_entries (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    department TEXT NOT NULL,
    tasks TEXT NOT NULL,
    phone TEXT NOT NULL,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS campus_life_support_guides (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    steps_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS pc_software_entries (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room TEXT NOT NULL,
    pc_count INTEGER,
    software_list_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS academic_calendar (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    academic_year INTEGER NOT NULL,
    title TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    campuses_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS campus_dining_menus (
    venue_slug TEXT PRIMARY KEY,
    venue_name TEXT NOT NULL,
    place_slug TEXT,
    place_name TEXT,
    week_label TEXT,
    week_start DATE,
    week_end DATE,
    menu_text TEXT,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS campus_facilities (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    facility_name TEXT NOT NULL,
    category TEXT,
    phone TEXT,
    location_text TEXT,
    hours_text TEXT,
    place_slug TEXT,
    source_url TEXT,
    source_tag TEXT NOT NULL DEFAULT 'demo',
    last_synced_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS profiles (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL DEFAULT '',
    department TEXT,
    student_year INTEGER,
    admission_type TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE IF NOT EXISTS profile_courses (
    profile_id TEXT NOT NULL,
    year INTEGER NOT NULL,
    semester INTEGER NOT NULL,
    code TEXT NOT NULL,
    section TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (profile_id, year, semester, code, section),
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS profile_notice_preferences (
    profile_id TEXT PRIMARY KEY,
    categories_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    keywords_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS profile_interests (
    profile_id TEXT PRIMARY KEY,
    tags_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);

ALTER TABLE profiles ADD COLUMN IF NOT EXISTS department TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS student_year INTEGER;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS admission_type TEXT;
ALTER TABLE restaurant_cache_items ADD COLUMN IF NOT EXISTS kakao_place_id TEXT;
ALTER TABLE restaurant_cache_items ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE affiliated_notices ADD COLUMN IF NOT EXISTS body_text TEXT NOT NULL DEFAULT '';

CREATE TABLE IF NOT EXISTS sync_runs (
    id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    target TEXT NOT NULL,
    trigger TEXT NOT NULL DEFAULT 'manual',
    status TEXT NOT NULL,
    params_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error_text TEXT,
    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ
);

ALTER TABLE sync_runs ADD COLUMN IF NOT EXISTS trigger TEXT NOT NULL DEFAULT 'manual';

CREATE INDEX IF NOT EXISTS idx_places_name ON places(name);
CREATE INDEX IF NOT EXISTS idx_places_geom ON places USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_courses_title ON courses(title);
CREATE INDEX IF NOT EXISTS idx_courses_code ON courses(code);
CREATE INDEX IF NOT EXISTS idx_courses_year_semester_room
ON courses(year, semester, room);
CREATE INDEX IF NOT EXISTS idx_restaurants_name ON restaurants(name);
CREATE INDEX IF NOT EXISTS idx_restaurants_geom ON restaurants USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_restaurant_cache_key
ON restaurant_cache_snapshots(origin_slug, kakao_query, radius_meters);
CREATE INDEX IF NOT EXISTS idx_restaurant_cache_items_geom
ON restaurant_cache_items USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_restaurant_hours_cache_fetched_at
ON restaurant_hours_cache(fetched_at DESC);
CREATE INDEX IF NOT EXISTS idx_library_seat_status_cache_last_synced_at
ON library_seat_status_cache(last_synced_at DESC);
CREATE INDEX IF NOT EXISTS idx_notices_published_at ON notices(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_campus_life_notices_topic
ON campus_life_notices(topic);
CREATE INDEX IF NOT EXISTS idx_campus_life_notices_title
ON campus_life_notices(title);
CREATE INDEX IF NOT EXISTS idx_transport_guides_mode ON transport_guides(mode);
CREATE INDEX IF NOT EXISTS idx_certificate_guides_title ON certificate_guides(title);
CREATE INDEX IF NOT EXISTS idx_leave_of_absence_guides_title ON leave_of_absence_guides(title);
CREATE INDEX IF NOT EXISTS idx_scholarship_guides_title ON scholarship_guides(title);
CREATE INDEX IF NOT EXISTS idx_wifi_guides_building_name ON wifi_guides(building_name);
CREATE INDEX IF NOT EXISTS idx_academic_support_guides_title ON academic_support_guides(title);
CREATE INDEX IF NOT EXISTS idx_student_activity_guides_topic
ON student_activity_guides(topic);
CREATE INDEX IF NOT EXISTS idx_student_activity_guides_title
ON student_activity_guides(title);
CREATE INDEX IF NOT EXISTS idx_student_activity_notices_topic
ON student_activity_notices(topic);
CREATE INDEX IF NOT EXISTS idx_student_activity_notices_published_at
ON student_activity_notices(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_student_activity_notices_title
ON student_activity_notices(title);
CREATE INDEX IF NOT EXISTS idx_about_resource_guides_topic
ON about_resource_guides(topic);
CREATE INDEX IF NOT EXISTS idx_about_resource_guides_title
ON about_resource_guides(title);
CREATE INDEX IF NOT EXISTS idx_service_policy_guides_topic
ON service_policy_guides(topic);
CREATE INDEX IF NOT EXISTS idx_service_policy_guides_title
ON service_policy_guides(title);
CREATE INDEX IF NOT EXISTS idx_service_policy_posts_topic
ON service_policy_posts(topic);
CREATE INDEX IF NOT EXISTS idx_service_policy_posts_published_at
ON service_policy_posts(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_service_policy_posts_title
ON service_policy_posts(title);
CREATE INDEX IF NOT EXISTS idx_newsroom_posts_topic
ON newsroom_posts(topic);
CREATE INDEX IF NOT EXISTS idx_newsroom_posts_published_at
ON newsroom_posts(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_newsroom_posts_title
ON newsroom_posts(title);
CREATE INDEX IF NOT EXISTS idx_research_posts_topic
ON research_posts(topic);
CREATE INDEX IF NOT EXISTS idx_research_posts_published_at
ON research_posts(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_research_posts_title
ON research_posts(title);
CREATE INDEX IF NOT EXISTS idx_newsroom_resource_guides_topic
ON newsroom_resource_guides(topic);
CREATE INDEX IF NOT EXISTS idx_newsroom_resource_guides_title
ON newsroom_resource_guides(title);
CREATE INDEX IF NOT EXISTS idx_anniversary_guides_topic
ON anniversary_guides(topic);
CREATE INDEX IF NOT EXISTS idx_anniversary_guides_title
ON anniversary_guides(title);
CREATE INDEX IF NOT EXISTS idx_campus_life_support_guides_topic
ON campus_life_support_guides(topic);
CREATE INDEX IF NOT EXISTS idx_campus_life_support_guides_title
ON campus_life_support_guides(title);
CREATE INDEX IF NOT EXISTS idx_pc_software_entries_room
ON pc_software_entries(room);
CREATE INDEX IF NOT EXISTS idx_academic_calendar_year_start_date
ON academic_calendar(academic_year, start_date);
CREATE INDEX IF NOT EXISTS idx_academic_calendar_title ON academic_calendar(title);
CREATE INDEX IF NOT EXISTS idx_campus_dining_menus_place_slug
ON campus_dining_menus(place_slug);
CREATE INDEX IF NOT EXISTS idx_profile_courses_profile_id ON profile_courses(profile_id);
CREATE INDEX IF NOT EXISTS idx_sync_runs_started_at ON sync_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sync_runs_trigger_target_started_at
ON sync_runs(trigger, target, started_at DESC);
