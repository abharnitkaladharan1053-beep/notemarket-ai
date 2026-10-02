-- NOTE MARKET AI — SUPABASE DATABASE
-- Run this complete file in Supabase Dashboard → SQL Editor.

create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  full_name text,
  college text,
  branch text,
  semester text,
  role text not null default 'student'
    check (role in ('student','seller','admin')),
  created_at timestamptz not null default now()
);

create table if not exists public.notes (
  id uuid primary key default gen_random_uuid(),
  seller_id uuid not null references public.profiles(id) on delete cascade,
  title text not null,
  description text,
  subject text not null,
  subject_code text,
  college text,
  semester text,
  price numeric(10,2) not null default 0 check(price >= 0),
  rating numeric(2,1) not null default 0 check(rating between 0 and 5),
  reviews_count integer not null default 0,
  purchases_count integer not null default 0,
  pages integer not null default 0,
  seller_name text,
  tag text default 'Verified',
  file_path text not null,
  status text not null default 'pending'
    check(status in ('pending','approved','rejected')),
  created_at timestamptz not null default now()
);

create table if not exists public.purchases (
  id uuid primary key default gen_random_uuid(),
  buyer_id uuid not null references public.profiles(id) on delete cascade,
  note_id uuid not null references public.notes(id) on delete cascade,
  amount numeric(10,2) not null check(amount >= 0),
  payment_status text not null default 'pending'
    check(payment_status in ('pending','paid','failed','refunded')),
  payment_provider text,
  payment_reference text,
  created_at timestamptz not null default now(),
  unique(buyer_id,note_id)
);

create table if not exists public.reviews (
  id uuid primary key default gen_random_uuid(),
  buyer_id uuid not null references public.profiles(id) on delete cascade,
  note_id uuid not null references public.notes(id) on delete cascade,
  rating integer not null check(rating between 1 and 5),
  review_text text,
  created_at timestamptz not null default now(),
  unique(buyer_id,note_id)
);

create table if not exists public.wishlists (
  user_id uuid not null references public.profiles(id) on delete cascade,
  note_id uuid not null references public.notes(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key(user_id,note_id)
);

create table if not exists public.reports (
  id uuid primary key default gen_random_uuid(),
  reporter_id uuid not null references public.profiles(id) on delete cascade,
  note_id uuid references public.notes(id) on delete cascade,
  reason text not null,
  details text,
  status text not null default 'open'
    check(status in ('open','reviewing','resolved','dismissed')),
  created_at timestamptz not null default now()
);

-- Create profile automatically after signup.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles(id,full_name,college,branch,semester)
  values(
    new.id,
    coalesce(new.raw_user_meta_data->>'full_name','Student'),
    new.raw_user_meta_data->>'college',
    new.raw_user_meta_data->>'branch',
    new.raw_user_meta_data->>'semester'
  )
  on conflict(id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
after insert on auth.users
for each row execute procedure public.handle_new_user();

-- Indexes
create index if not exists notes_subject_idx on public.notes(subject);
create index if not exists notes_status_idx on public.notes(status);
create index if not exists notes_seller_idx on public.notes(seller_id);
create index if not exists purchases_buyer_idx on public.purchases(buyer_id);

-- Enable Row Level Security
alter table public.profiles enable row level security;
alter table public.notes enable row level security;
alter table public.purchases enable row level security;
alter table public.reviews enable row level security;
alter table public.wishlists enable row level security;
alter table public.reports enable row level security;

-- Profiles
create policy "profile_read_own" on public.profiles
for select using(auth.uid()=id);

create policy "profile_update_own" on public.profiles
for update using(auth.uid()=id) with check(auth.uid()=id);

-- Notes
create policy "notes_read_approved_or_own" on public.notes
for select using(status='approved' or seller_id=auth.uid());

create policy "notes_insert_own" on public.notes
for insert with check(seller_id=auth.uid());

create policy "notes_update_own" on public.notes
for update using(seller_id=auth.uid()) with check(seller_id=auth.uid());

-- Purchases
create policy "purchases_read_own" on public.purchases
for select using(buyer_id=auth.uid());

-- Reviews
create policy "reviews_read_all" on public.reviews
for select using(true);

create policy "reviews_insert_own" on public.reviews
for insert with check(buyer_id=auth.uid());

create policy "reviews_update_own" on public.reviews
for update using(buyer_id=auth.uid()) with check(buyer_id=auth.uid());

-- Wishlist
create policy "wishlist_own" on public.wishlists
for all using(user_id=auth.uid()) with check(user_id=auth.uid());

-- Reports
create policy "reports_insert_own" on public.reports
for insert with check(reporter_id=auth.uid());

create policy "reports_read_own" on public.reports
for select using(reporter_id=auth.uid());

-- Private note PDF bucket
insert into storage.buckets(id,name,public)
values('notes','notes',false)
on conflict(id) do update set public=false;

create policy "note_upload_own_folder"
on storage.objects for insert to authenticated
with check(
  bucket_id='notes'
  and (storage.foldername(name))[1]=auth.uid()::text
);

create policy "note_read_own_folder"
on storage.objects for select to authenticated
using(
  bucket_id='notes'
  and (storage.foldername(name))[1]=auth.uid()::text
);

create policy "note_delete_own_folder"
on storage.objects for delete to authenticated
using(
  bucket_id='notes'
  and (storage.foldername(name))[1]=auth.uid()::text
);

-- Keep the bucket private. Paid downloads should use short-lived signed URLs
-- after server-side purchase verification.
