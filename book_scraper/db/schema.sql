-- Book scraper schema for Supabase (Postgres).
-- Run once in the Supabase SQL editor. Safe to re-run.
--
-- Each thing has exactly one identifier:
--   category -> slug (from the site, e.g. 'poetry_23')
--   book     -> upc  (the site's product code)
--   run      -> id   (generated; a run has nothing natural to identify it)
--   snapshot -> (run_id, upc)
--
-- If you ran the earlier version of this file, drop the old tables first:
--   drop view if exists books_with_category;
--   drop table if exists book_snapshots, books, categories, scrape_runs cascade;

create table if not exists categories (
    slug  text primary key,
    name  text not null
);

create table if not exists books (
    upc            text primary key,
    title          text not null,
    category_slug  text not null references categories(slug) on delete restrict,
    price          numeric(10,2) not null check (price >= 0),   -- GBP
    stock          integer not null check (stock >= 0),
    rating         smallint not null check (rating between 1 and 5),
    description    text,
    image_url      text,
    url            text not null unique
);
create index if not exists books_category_slug_idx on books(category_slug);

create table if not exists scrape_runs (
    id             bigint generated always as identity primary key,
    started_at     timestamptz not null default now(),
    finished_at    timestamptz,
    status         text not null default 'running'
                   check (status in ('running', 'success', 'partial', 'failed')),
    pages_scraped  integer not null default 0,
    errors         integer not null default 0
);

-- Price and stock of each book in each run: the history.
create table if not exists book_snapshots (
    run_id  bigint not null references scrape_runs(id) on delete cascade,
    upc     text   not null references books(upc) on delete cascade,
    price   numeric(10,2) not null,
    stock   integer not null,
    primary key (run_id, upc)
);
create index if not exists book_snapshots_upc_idx on book_snapshots(upc);

-- Scratch table for the connection smoke test.
create table if not exists connection_test (
    id          bigint generated always as identity primary key,
    message     text not null,
    created_at  timestamptz not null default now()
);

-- Convenience view (stores nothing): each book with its category name.
-- security_invoker makes the view obey the same access rules as the tables.
create or replace view books_with_category with (security_invoker = true) as
select b.*, c.name as category_name
from books b
join categories c on c.slug = b.category_slug;

-- Lock the tables: the public "anon" key can't read or write them.
-- The scraper uses the service_role key, which is not affected.
alter table categories      enable row level security;
alter table books           enable row level security;
alter table scrape_runs     enable row level security;
alter table book_snapshots  enable row level security;
alter table connection_test enable row level security;
