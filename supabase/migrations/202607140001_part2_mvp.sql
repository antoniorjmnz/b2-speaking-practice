-- Part 2 vertical-slice schema. Student traffic never talks to these tables directly.
-- The API uses a trusted database role; RLS therefore remains closed to anon/authenticated.

create extension if not exists pgcrypto;

create table if not exists public.practice_tasks (
  id varchar(36) primary key,
  part integer not null default 2 constraint practice_tasks_part_two_only check (part = 2),
  version varchar(32) not null,
  status varchar(16) not null default 'draft' constraint practice_tasks_status check (status in ('draft', 'published', 'retired')),
  examiner_instruction text not null,
  examiner_audio_path varchar(255) not null,
  question text not null,
  image_one_path varchar(255) not null,
  image_two_path varchar(255) not null,
  photo_one_keywords jsonb not null default '[]'::jsonb,
  photo_two_keywords jsonb not null default '[]'::jsonb,
  license_information text not null,
  content_notice text not null,
  teacher_approved_at timestamptz,
  created_at timestamptz not null default now()
);

create table if not exists public.practice_sessions (
  id varchar(36) primary key,
  access_token_hash varchar(64) not null unique,
  task_id varchar(36) not null references public.practice_tasks(id),
  status varchar(24) not null default 'created' constraint practice_sessions_status check (status in ('created', 'upload_authorized', 'uploaded', 'processing', 'completed', 'failed')),
  protocol_version varchar(32) not null default 'part2-v1',
  consent_policy_version varchar(32) not null,
  recording_consent boolean not null,
  response_started_at timestamptz,
  response_ended_at timestamptz,
  expires_at timestamptz not null,
  last_error_code varchar(64),
  created_at timestamptz not null default now()
);
create index if not exists ix_practice_sessions_expires_at on public.practice_sessions(expires_at);

create table if not exists public.recordings (
  id varchar(36) primary key,
  session_id varchar(36) not null references public.practice_sessions(id) on delete cascade,
  kind varchar(24) not null default 'candidate_response',
  storage_path varchar(512) not null,
  mime_type varchar(96),
  size_bytes integer,
  duration_ms integer,
  sha256 varchar(64),
  upload_status varchar(16) not null default 'pending' constraint recordings_upload_status check (upload_status in ('pending', 'authorized', 'uploaded', 'validated', 'rejected')),
  created_at timestamptz not null default now(),
  constraint uq_recording_session_kind unique(session_id, kind)
);
create index if not exists ix_recordings_session_id on public.recordings(session_id);

create table if not exists public.processing_jobs (
  id varchar(36) primary key,
  session_id varchar(36) not null references public.practice_sessions(id) on delete cascade,
  job_type varchar(32) not null default 'full_evaluation',
  status varchar(16) not null default 'pending' constraint processing_jobs_status check (status in ('pending', 'processing', 'completed', 'failed')),
  attempt_count integer not null default 0,
  last_error_code varchar(64),
  last_error_detail text,
  available_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  constraint uq_job_session_type unique(session_id, job_type)
);
create index if not exists ix_processing_jobs_ready on public.processing_jobs(status, available_at);

create table if not exists public.transcript_segments (
  id varchar(36) primary key,
  session_id varchar(36) not null references public.practice_sessions(id) on delete cascade,
  position integer not null,
  start_ms integer not null,
  end_ms integer not null,
  text text not null,
  confidence double precision,
  created_at timestamptz not null default now(),
  constraint transcript_valid_time check (start_ms >= 0 and end_ms >= start_ms)
);
create index if not exists ix_transcript_segments_session_time on public.transcript_segments(session_id, start_ms);

create table if not exists public.evaluations (
  id varchar(36) primary key,
  session_id varchar(36) not null unique references public.practice_sessions(id) on delete cascade,
  rubric_version varchar(32) not null,
  transcription_provider varchar(64) not null,
  evaluation_provider varchar(64) not null,
  model_snapshot jsonb not null,
  strengths jsonb not null,
  priority_improvements jsonb not null,
  grammar_vocabulary_result jsonb not null,
  discourse_management_result jsonb not null,
  task_performance_result jsonb not null,
  pronunciation_result jsonb,
  objective_metrics jsonb not null,
  suggested_exercises jsonb not null,
  overall_confidence double precision not null,
  status varchar(16) not null default 'completed',
  created_at timestamptz not null default now()
);

create table if not exists public.evaluation_evidence (
  id varchar(36) primary key,
  evaluation_id varchar(36) not null references public.evaluations(id) on delete cascade,
  category varchar(64) not null,
  transcript_segment_id varchar(36) references public.transcript_segments(id) on delete set null,
  start_ms integer not null,
  end_ms integer not null,
  excerpt text not null,
  explanation text not null,
  constraint evidence_valid_time check (start_ms >= 0 and end_ms >= start_ms)
);
create index if not exists ix_evidence_evaluation on public.evaluation_evidence(evaluation_id);

create table if not exists public.teacher_reviews (
  id varchar(36) primary key,
  session_id varchar(36) not null references public.practice_sessions(id) on delete cascade,
  teacher_identifier varchar(128) not null,
  feedback_accuracy integer not null check (feedback_accuracy between 1 and 5),
  feedback_usefulness integer not null check (feedback_usefulness between 1 and 5),
  comments text,
  created_at timestamptz not null default now()
);
create index if not exists ix_teacher_reviews_session_id on public.teacher_reviews(session_id);

alter table public.practice_tasks enable row level security;
alter table public.practice_sessions enable row level security;
alter table public.recordings enable row level security;
alter table public.processing_jobs enable row level security;
alter table public.transcript_segments enable row level security;
alter table public.evaluations enable row level security;
alter table public.evaluation_evidence enable row level security;
alter table public.teacher_reviews enable row level security;

-- Private bucket. Signed upload/read capabilities are minted only by the API.
insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
values (
  'part2-recordings',
  'part2-recordings',
  false,
  8388608,
  array['audio/webm', 'audio/ogg', 'audio/wav', 'audio/mp4', 'audio/x-m4a']
)
on conflict (id) do update set
  public = excluded.public,
  file_size_limit = excluded.file_size_limit,
  allowed_mime_types = excluded.allowed_mime_types;

insert into public.practice_tasks (
  id, part, version, status, examiner_instruction, examiner_audio_path, question,
  image_one_path, image_two_path, photo_one_keywords, photo_two_keywords,
  license_information, content_notice
) values (
  '99999999-9999-4999-8999-999999999999',
  2,
  'open-original-part2-v1',
  'published',
  'Now look at the two photographs. They show people learning practical skills in different situations. Please compare the photographs and say what the people might find useful about learning in these ways. You have one minute.',
  '/assets/temporary-part2/examiner-p2-009-sonia.mp3',
  'What might the people find useful about learning in these ways?',
  '/practice-assets/original/academy-part2/p2-009-photo-a.jpg',
  '/practice-assets/original/academy-part2/p2-009-photo-b.jpg',
  '["first picture", "first photograph", "cooking", "kitchen", "food", "together"]'::jsonb,
  '["second picture", "second photograph", "students", "laptops", "group", "together"]'::jsonb,
  'Original task with photographs distributed under the Unsplash License.',
  'Tarea original con fotografías de licencia trazable. No es material ni evaluación oficial de Cambridge.'
)
on conflict (id) do nothing;
