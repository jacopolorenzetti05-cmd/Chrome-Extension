-- Book scraper schema for Supabase (Postgres).
-- Run once in the Supabase SQL editor. Safe to re-run.

create table if not exists categories (
    id          bigint generated always as identity primary key,
    name        text not null,
    slug        text not null unique,
    url         text not null,
    created_at  timestamptz not null default now()
);

create table if not exists books (
    id              bigint generated always as identity primary key,
    upc             text not null unique,
    title           text not null,
    category_id     bigint not null references categories(id) on delete restrict,
    price_excl_tax  numeric(10,2) not null check (price_excl_tax >= 0),
    price_incl_tax  numeric(10,2) not null check (price_incl_tax >= 0),
    tax             numeric(10,2) not null check (tax >= 0),
    currency        char(3) not null default 'GBP',
    stock           integer not null check (stock >= 0),
    rating          smallint not null check (rating between 1 and 5),
    num_reviews     integer not null default 0 check (num_reviews >= 0),
    product_type    text,
    description     text,
    image_url       text,
    url             text not null unique,
    first_seen_at   timestamptz not null default now(),
    last_seen_at    timestamptz not null default now()
);
create index if not exists books_category_id_idx on books(category_id);

create table if not exists scrape_runs (
    id             bigint generated always as identity primary key,
    started_at     timestamptz not null default now(),
    finished_at    timestamptz,
    status         text not null default 'running'
                   check (status in ('running', 'success', 'partial', 'failed')),
    pages_scraped  integer not null default 0,
    books_scraped  integer not null default 0,
    errors         integer not null default 0
);

create table if not exists book_snapshots (
    id              bigint generated always as identity primary key,
    run_id          bigint not null references scrape_runs(id) on delete cascade,
    book_id         bigint not null references books(id) on delete cascade,
    price_incl_tax  numeric(10,2) not null,
    stock           integer not null,
    rating          smallint not null,
    captured_at     timestamptz not null default now(),
    unique (run_id, book_id)
);
create index if not exists book_snapshots_book_id_idx on book_snapshots(book_id);

-- Scratch table for the connection smoke test.
create table if not exists connection_test (
    id          bigint generated always as identity primary key,
    message     text not null,
    created_at  timestamptz not null default now()
);

-- Handy joined view: each book with its category name.
create or replace view books_with_category as
select b.*, c.name as category_name
from books b
join categories c on c.id = b.category_id;
