-- =====================================================================
-- NOTE MARKET AI — ADDITIONAL RLS POLICIES & HELPER FUNCTIONS
-- Run this script in Supabase Dashboard → SQL Editor to enable full
-- purchases, moderation, and secure downloads.
-- =====================================================================

-- 1. Purchases table insert and update policies
do $$
begin
  if not exists (
    select 1 from pg_policies 
    where tablename = 'purchases' and policyname = 'purchases_insert_own'
  ) then
    create policy "purchases_insert_own" on public.purchases
    for insert to authenticated
    with check(buyer_id = auth.uid());
  end if;

  if not exists (
    select 1 from pg_policies 
    where tablename = 'purchases' and policyname = 'purchases_update_own'
  ) then
    create policy "purchases_update_own" on public.purchases
    for update to authenticated
    using(buyer_id = auth.uid()) with check(buyer_id = auth.uid());
  end if;
end $$;

-- 2. Allow admins or sellers to read/update note statuses for moderation
do $$
begin
  if not exists (
    select 1 from pg_policies 
    where tablename = 'notes' and policyname = 'notes_read_all_authenticated'
  ) then
    -- Allow authenticated users to view all notes (including pending) if admin or in dashboard
    create policy "notes_read_all_authenticated" on public.notes
    for select to authenticated
    using(true);
  end if;

  if not exists (
    select 1 from pg_policies 
    where tablename = 'notes' and policyname = 'notes_moderation_update'
  ) then
    -- Allow updating status
    create policy "notes_moderation_update" on public.notes
    for update to authenticated
    using(true) with check(true);
  end if;
end $$;

-- 3. Stored procedure to complete a purchase securely
create or replace function public.complete_note_purchase(
  p_note_id uuid,
  p_payment_provider text default 'simulated_upi',
  p_payment_reference text default null
)
returns json
language plpgsql
security definer
set search_path = public
as $$
declare
  v_note record;
  v_purchase_id uuid;
  v_buyer_id uuid;
begin
  v_buyer_id := auth.uid();
  if v_buyer_id is null then
    raise exception 'Authentication required to make a purchase';
  end if;

  select * into v_note from public.notes where id = p_note_id;
  if not found then
    raise exception 'Note with ID % not found', p_note_id;
  end if;

  insert into public.purchases(
    buyer_id,
    note_id,
    amount,
    payment_status,
    payment_provider,
    payment_reference
  )
  values(
    v_buyer_id,
    p_note_id,
    v_note.price,
    'paid',
    p_payment_provider,
    coalesce(p_payment_reference, 'NM-' || upper(substr(md5(random()::text), 1, 8)))
  )
  on conflict (buyer_id, note_id) do update set
    payment_status = 'paid',
    payment_provider = p_payment_provider
  returning id into v_purchase_id;

  -- Increment purchase count on note
  update public.notes
  set purchases_count = coalesce(purchases_count, 0) + 1
  where id = p_note_id;

  return json_build_object(
    'success', true,
    'purchase_id', v_purchase_id,
    'note_id', p_note_id,
    'amount', v_note.price,
    'file_path', v_note.file_path
  );
end;
$$;

-- 4. Stored procedure for note moderation (Approve / Reject)
create or replace function public.moderate_note(
  p_note_id uuid,
  p_status text
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
begin
  if p_status not in ('approved', 'rejected', 'pending') then
    raise exception 'Invalid status: must be approved, rejected, or pending';
  end if;

  update public.notes
  set status = p_status
  where id = p_note_id;

  return true;
end;
$$;

-- 5. Storage policy to allow buyers of a note to access the file
do $$
begin
  if not exists (
    select 1 from pg_policies 
    where tablename = 'objects' and schemaname = 'storage' and policyname = 'note_read_purchased_or_approved'
  ) then
    create policy "note_read_purchased_or_approved"
    on storage.objects for select to authenticated
    using (
      bucket_id = 'notes'
      and (
        -- Seller
        (storage.foldername(name))[1] = auth.uid()::text
        or
        -- Purchased
        exists (
          select 1 from public.purchases p
          join public.notes n on p.note_id = n.id
          where p.buyer_id = auth.uid()
            and p.payment_status = 'paid'
            and n.file_path = storage.objects.name
        )
      )
    );
  end if;
end $$;
