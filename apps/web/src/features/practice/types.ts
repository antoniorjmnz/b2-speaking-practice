export type SpeakingPart = 1 | 2 | 3 | 4;

export type PracticeSource = "original";

export type ExamVariant = "academy_original";

export type PracticeId = `P${SpeakingPart}-${string}`;

export interface PracticeBase {
  id: PracticeId;
  part: SpeakingPart;
  ordinal: number;
  display_label: string;
  source: PracticeSource;
  exam_variant: ExamVariant;
  ready: boolean;
}

export interface PendingPractice extends PracticeBase {
  ready: false;
  pending_reason: string;
  topic_set_id?: string;
}

export interface Part1QuestionGroup {
  topic: string;
  questions: readonly string[];
}

export interface ReadyPart1Practice extends PracticeBase {
  part: 1;
  ready: true;
  title: string;
  question_groups: readonly Part1QuestionGroup[];
  duration_seconds: 60;
}

export interface PracticePhoto {
  asset_path: string;
  alt: string;
  sha256: string;
}

export interface ReadyPart2Practice extends PracticeBase {
  part: 2;
  ready: true;
  title: string;
  scene_setup: string;
  comparison_question: string;
  follow_up_question: string;
  photos: readonly [PracticePhoto, PracticePhoto];
  long_turn_seconds: 60;
  follow_up_seconds: 30;
}

export interface ReadyPart3Practice extends PracticeBase {
  part: 3;
  ready: true;
  title: string;
  topic_set_id: string;
  setup: string;
  discussion_question: string;
  prompts: readonly [string, string, string, string, string];
  decision_question: string;
  preview_seconds: 15;
  discussion_seconds: 120;
  decision_seconds: 60;
}

export interface ReadyPart4Practice extends PracticeBase {
  part: 4;
  ready: true;
  title: string;
  topic_set_id: string;
  questions: readonly string[];
  discussion_seconds: 240;
}

export type ReadyPractice =
  | ReadyPart1Practice
  | ReadyPart2Practice
  | ReadyPart3Practice
  | ReadyPart4Practice;

export type PracticeCatalogItem = ReadyPractice | PendingPractice;

export interface PracticeCatalogByPart {
  1: readonly PracticeCatalogItem[];
  2: readonly PracticeCatalogItem[];
  3: readonly PracticeCatalogItem[];
  4: readonly PracticeCatalogItem[];
}
