export type Task = {
  id: string;
  part: 1 | 2 | 3;
  version: string;
  examiner_instruction: string;
  examiner_audio_path: string;
  setup: string;
  question: string;
  questions: string[];
  decision_question: string;
  image_one_path: string;
  image_two_path: string;
  content_notice: string;
  evaluation_available: boolean;
  diarization_available: boolean;
};

export type SessionCapability = {
  session_id: string;
  session_token: string;
  status: string;
  expires_at: string;
};

export type AiPartnerTurn = {
  follow_up_question: string;
  spoken_text: string;
  interaction_move: "brief_opinion" | "brief_preference";
  estimated_seconds: number;
  model: string;
  source: "ai" | "prepared";
  disclaimer_es: string;
};

export type UploadGrant = {
  provider: "local" | "supabase";
  recording_id: string;
  storage_path: string;
  upload_url: string | null;
  upload_token: string;
  bucket: string | null;
  expires_in_seconds: number;
};

export type SessionStatus = {
  session_id: string;
  status: string;
  processing_stage: string;
  stage_started_at: string | null;
  heartbeat_at: string | null;
  can_retry: boolean;
  error_message_es: string | null;
};

export type TranscriptSegment = {
  id: string;
  position: number;
  start_ms: number;
  end_ms: number;
  text: string;
  confidence: number | null;
};

export type Observation = {
  category: string;
  evidence: string;
  start_ms: number;
  end_ms: number;
  explanation_es: string;
  suggestion_es: string;
  severity: string;
  confidence: number;
};

export type StudentCriterion = {
  summary_es: string;
  confidence: number;
  practice_band?: number | null;
  observations: Observation[];
};

export type StudentPracticeScore = {
  global_band: number;
  tier_key: string;
  tier_label: string;
  tier_caption_es: string;
  tier_index: number;
  tier_count: number;
  counted_criteria: string[];
  confidence: number;
  disclaimer_es: string;
};

export type TaskCheck = {
  key: string;
  status: string;
  explanation_es: string;
  evidence: string;
  start_ms: number | null;
  end_ms: number | null;
  confidence: number;
};

export type PronunciationObservation = {
  feature: string;
  start_ms: number;
  end_ms: number;
  explanation_es: string;
  suggestion_es: string;
  confidence: number;
};

export type StudentPronunciation = {
  available: boolean;
  withheld_reason_es: string | null;
  confidence: number;
  summary_es: string;
  observations: PronunciationObservation[];
};

export type StudentReport = {
  session_id: string;
  candidate_label?: "A" | "B";
  speaking_part?: 1 | 2 | 3;
  task_question: string;
  evaluation_status: "evaluated" | "insufficient" | "demo";
  evaluation_status_reason_es: string;
  disclaimer_es: string;
  strengths: Observation[];
  priority_improvements: Observation[];
  grammar_vocabulary: StudentCriterion;
  discourse_management: StudentCriterion;
  interactive_communication?: StudentCriterion;
  pronunciation: StudentPronunciation;
  practice_score?: StudentPracticeScore | null;
  task_performance: TaskCheck[];
  suggested_exercises: string[];
  overall_confidence: number;
  transcript: TranscriptSegment[];
  audio_playback_url: string;
  expires_at: string;
};
