-- ═══════════════════════════════════════════════════════════════════════════
-- BrandWave — public.users ke RLS policies aur column grants
--
-- Isay Supabase SQL editor mein chalao (project: ppjvdgwytmffrskayhzl).
-- Poori file idempotent hai — dobara chalane se kuch nahi tootta.
--
-- YEH FILE KYUN MOJOOD HAI
-- ────────────────────────
-- Sirf RLS enable karna kaafi NAHI tha. RLS ka faisla "kaunsi ROW" par hota
-- hai, "kaunsa COLUMN" par nahi — aur asli masla column ka tha: user apni hi
-- row mein `role` ko 'admin' likh sakta tha. Do rastay khule the:
--
--   1. Browser console se:
--        supabase.from('users').update({ role: 'admin' }).eq('id', <apna id>)
--      users_update_own ki USING (auth.uid() = id) yeh rok nahi sakti, kyunke
--      row to waqai usi ki hai. WITH CHECK bhi nahi rok sakti: WITH CHECK OLD
--      row dekh hi nahi sakti, is liye "role badla to nahi" likha hi nahi ja
--      sakta.
--
--   2. Bilkul normal UI se: /admin-login ka Google button sessionStorage mein
--      selectedRole='admin' rakhta tha, aur /auth/callback wahi parh kar row
--      `role: 'admin'` ke saath INSERT kar deta tha. Koi bhi Google account,
--      koi exploit nahi.
--
-- Dono ka ek hi hal hai: column-level GRANT. Jo haq diya hi na ho, RLS us tak
-- pahunchne se pehle hi Postgres mana kar deta hai.
--
-- Iske saath frontend mein bhi changes hain (in ke baghair signup toot jayega):
--   components/auth/LoginForm.tsx        insert se role + email_verified nikale
--   app/auth/callback/page.tsx           role ab sessionStorage se nahi aata
--   app/auth/verify-email/page.tsx       upsert -> ON CONFLICT DO NOTHING
--   components/auth/SignupForm.tsx       anon pre-flight check hataya
-- ═══════════════════════════════════════════════════════════════════════════


-- ── 1. RLS on ────────────────────────────────────────────────────────────────
alter table public.users enable row level security;


-- ── 2. is_admin() ────────────────────────────────────────────────────────────
--
-- security definer LAZMI hai: yeh function un policies ke andar chalta hai jo
-- KHUD public.users par lagi hain. Bina security definer ke policy -> function
-- -> policy ka infinite recursion ban jata hai ("infinite recursion detected in
-- policy for relation users"). definer hone se yeh table owner ke tor par
-- chalta hai, jo RLS bypass karta hai.
--
-- `set search_path = public` bhi lazmi hai — warna caller apna search_path
-- badal kar `users` naam ki apni nakli table aage rakh sakta hai.
create or replace function public.is_admin()
returns boolean
language sql
security definer
stable
set search_path = public
as $$
  select exists (
    select 1 from public.users
    where id = auth.uid() and role = 'admin'
  )
$$;


-- ── 3. Policies ──────────────────────────────────────────────────────────────
drop policy if exists users_select_own  on public.users;
drop policy if exists users_insert_own  on public.users;
drop policy if exists users_update_own  on public.users;
drop policy if exists users_admin_all   on public.users;

create policy users_select_own on public.users
  for select to authenticated
  using (auth.uid() = id);

create policy users_insert_own on public.users
  for insert to authenticated
  with check (auth.uid() = id);

-- WITH CHECK yahan explicitly likha gaya hai. Chhorne par Postgres USING ko hi
-- WITH CHECK maan leta hai, natija wahi hota — lekin likha hua hona batata hai
-- ke yeh soch kar rakha gaya hai. Yaad rahe: yeh sirf ROW rokta hai, COLUMN
-- nahi. `role` ki asli hifazat neeche block 4 hai.
create policy users_update_own on public.users
  for update to authenticated
  using (auth.uid() = id)
  with check (auth.uid() = id);

create policy users_admin_all on public.users
  for all to authenticated
  using (public.is_admin())
  with check (public.is_admin());


-- ── 4. Column grants — ASAL FIX ──────────────────────────────────────────────
--
-- Column-level grant dene se PEHLE table-level grant hatana zaroori hai:
-- Postgres mein table-level UPDATE har column ko cover karta hai, aur column
-- grants uske upar kuch add nahi karte.
--
-- Note: admin bhi `authenticated` hi hai, to admin bhi ab browser se role
-- nahi badal sakta. Yeh jaan boojh kar hai — role change service-role key se
-- (FastAPI backend) ya is SQL editor se hona chahiye, kabhi browser se nahi.
revoke update on public.users from authenticated;
grant  update (business_name) on public.users to authenticated;

revoke insert on public.users from authenticated;
grant  insert (id, email, business_name, auth_provider) on public.users to authenticated;

-- `role` grant list mein NAHI hai, to nayi row hamesha table ke default par
-- banti hai. Confirm:
alter table public.users alter column role set default 'user';

-- anon ko is table par kuch nahi chahiye. RLS pehle hi rok deti (koi policy
-- `to anon` nahi hai), lekin grant bhi na dena behtar hai.
revoke all on public.users from anon;


-- ── 5. email_verified ab client nahi likhta ──────────────────────────────────
--
-- Yeh column bhi client-writable tha, is liye bemani tha: user khud ko verified
-- mark kar sakta tha. Asli sach auth.users.email_confirmed_at hai, jo Supabase
-- khud set karta hai aur client chhoo bhi nahi sakta.
--
-- Trigger use public.users mein mirror karta hai, taake admin UI
-- (app/admin/users/page.tsx ka "✓ Verified" badge) sahi dikhta rahe.
create or replace function public.sync_email_verified()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.users
     set email_verified = (new.email_confirmed_at is not null)
   where id = new.id;
  return new;
end;
$$;

drop trigger if exists on_auth_user_verified on auth.users;
create trigger on_auth_user_verified
  after insert or update of email_confirmed_at on auth.users
  for each row execute function public.sync_email_verified();

-- Mojooda rows ke liye ek dafa backfill.
update public.users u
   set email_verified = (a.email_confirmed_at is not null)
  from auth.users a
 where a.id = u.id
   and u.email_verified is distinct from (a.email_confirmed_at is not null);


-- ═══════════════════════════════════════════════════════════════════════════
-- VERIFY — yeh chala kar natija dekho
-- ═══════════════════════════════════════════════════════════════════════════
--
-- (a) Policies:
--     select policyname, cmd, qual, with_check
--       from pg_policies where schemaname='public' and tablename='users';
--
-- (b) Column grants — `role` aur `email_verified` is list mein NAHI hone
--     chahiye, warna fix laga hi nahi:
--     select grantee, privilege_type, column_name
--       from information_schema.column_privileges
--      where table_schema='public' and table_name='users'
--        and grantee in ('anon','authenticated')
--      order by grantee, privilege_type, column_name;
--
-- (c) Asli test — kisi normal (non-admin) user se login kar ke browser console:
--       await supabase.from('users')
--         .update({ role: 'admin' })
--         .eq('id', (await supabase.auth.getUser()).data.user.id)
--     Ab isay FAIL hona chahiye:
--       "permission denied for column role of relation users" (42501)
--     Agar yeh success de raha hai, to block 4 nahi chala.
