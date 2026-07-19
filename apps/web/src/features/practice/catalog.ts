import type {
  PendingPractice,
  PracticeCatalogByPart,
  PracticeCatalogItem,
  PracticeId,
  ReadyPart1Practice,
  ReadyPart2Practice,
  ReadyPart3Practice,
  ReadyPart4Practice,
  SpeakingPart,
} from "./types";

const TOTAL_PRACTICES_PER_PART = 50;

const idFor = (part: SpeakingPart, ordinal: number): PracticeId =>
  `P${part}-${String(ordinal).padStart(3, "0")}`;

const topicSetIdFor = (ordinal: number): string =>
  `TOPIC-${String(ordinal).padStart(3, "0")}`;

const originalBase = (part: SpeakingPart, ordinal: number) => ({
  id: idFor(part, ordinal),
  part,
  ordinal,
  display_label: `Practice ${String(ordinal).padStart(3, "0")}`,
  source: "original" as const,
  exam_variant: "academy_original" as const,
});

const readyPart1: readonly ReadyPart1Practice[] = [
  {
    ...originalBase(1, 9),
    part: 1,
    ready: true,
    title: "Work and studies",
    question_groups: [
      {
        topic: "Your occupation",
        questions: [
          "Do you work or are you a student? What do you like most about it?",
        ],
      },
      {
        topic: "Daily routine",
        questions: [
          "What do you usually do when you finish work or classes? Why?",
        ],
      },
      {
        topic: "Learning",
        questions: [
          "Would you like to learn something new this year? What would it be?",
        ],
      },
    ],
    duration_seconds: 60,
  },
  {
    ...originalBase(1, 10),
    part: 1,
    ready: true,
    title: "Where you live",
    question_groups: [
      {
        topic: "Your home",
        questions: [
          "Tell us about the place where you live. What do you like about it?",
        ],
      },
      {
        topic: "City or town",
        questions: ["Do you prefer living in a city or in a small town? Why?"],
      },
      {
        topic: "Your neighbourhood",
        questions: [
          "What would you change about your neighbourhood if you could? Why?",
        ],
      },
    ],
    duration_seconds: 60,
  },
  {
    ...originalBase(1, 11),
    part: 1,
    ready: true,
    title: "Food and meals",
    question_groups: [
      {
        topic: "Favourite food",
        questions: ["What kind of food do you enjoy eating most? Why?"],
      },
      {
        topic: "Eating out",
        questions: ["Do you prefer eating at home or in restaurants? Why?"],
      },
      {
        topic: "A recent meal",
        questions: ["Tell us about a meal you really enjoyed recently."],
      },
    ],
    duration_seconds: 60,
  },
  {
    ...originalBase(1, 12),
    part: 1,
    ready: true,
    title: "Travel and free time",
    question_groups: [
      {
        topic: "Weekends",
        questions: ["How do you usually spend your free time at the weekend?"],
      },
      {
        topic: "Holidays",
        questions: [
          "Do you prefer holidays in your own country or abroad? Why?",
        ],
      },
      {
        topic: "Future plans",
        questions: [
          "Tell us about a place you would like to visit in the future.",
        ],
      },
    ],
    duration_seconds: 60,
  },
];

const readyPart2: readonly ReadyPart2Practice[] = [
  {
    ...originalBase(2, 9),
    part: 2,
    ready: true,
    title: "Learning practical skills",
    scene_setup: "People learning practical skills in different situations.",
    comparison_question:
      "What might the people find useful about learning in these ways?",
    follow_up_question: "Which way of learning would you prefer? Why?",
    photos: [
      {
        asset_path:
          "/practice-assets/original/academy-part2/p2-009-photo-a.jpg",
        alt: "People learning to prepare food together in a kitchen.",
        sha256:
          "0965F8ABE2E0B19F7C6E9CB15D68F65618D5357398BF51637E7501E2E6FFF4D6",
      },
      {
        asset_path:
          "/practice-assets/original/academy-part2/p2-009-photo-b.jpg",
        alt: "Students learning together with laptops around a table.",
        sha256:
          "903A72B8C3327BE8864113B1B3D755E42A53F6738020636A61895B3D20163205",
      },
    ],
    long_turn_seconds: 60,
    follow_up_seconds: 30,
  },
  {
    ...originalBase(2, 10),
    part: 2,
    ready: true,
    title: "Keeping fit",
    scene_setup: "People exercising in different situations.",
    comparison_question:
      "Why might the people have chosen to exercise in these ways?",
    follow_up_question:
      "Do you prefer exercising alone or with other people? Why?",
    photos: [
      {
        asset_path:
          "/practice-assets/original/academy-part2/p2-010-photo-a.jpg",
        alt: "A person training with weights in a modern gym.",
        sha256:
          "928ACBB5FE44F42B1B78AE1E0DCA1F87D7FB293194ACA7B96BDC1FED19649582",
      },
      {
        asset_path:
          "/practice-assets/original/academy-part2/p2-010-photo-b.jpg",
        alt: "A group of runners exercising outside together.",
        sha256:
          "F588FCC8BFD11AFA2EBBABA9D4B78CD76C85D47F99B7623AE9ECE8FC3912B69F",
      },
    ],
    long_turn_seconds: 60,
    follow_up_seconds: 30,
  },
  {
    ...originalBase(2, 11),
    part: 2,
    ready: true,
    title: "Social occasions",
    scene_setup: "People enjoying different social occasions.",
    comparison_question:
      "What might the people enjoy about these social occasions?",
    follow_up_question: "Which occasion would you prefer to attend? Why?",
    photos: [
      {
        asset_path:
          "/practice-assets/original/academy-part2/p2-011-photo-a.jpg",
        alt: "A large crowd enjoying a live event together.",
        sha256:
          "A1D6F1FB9164BFB80660984471C01795ACCBB4BDBD4883EE143A4D5A71DF779F",
      },
      {
        asset_path:
          "/practice-assets/original/academy-part2/p2-011-photo-b.jpg",
        alt: "Friends sharing a meal around a long table.",
        sha256:
          "7F04B69ED9343CBE4822FFE4AC30162BB77E2A3EC847FAAF7A3870CDA77000D6",
      },
    ],
    long_turn_seconds: 60,
    follow_up_seconds: 30,
  },
  {
    ...originalBase(2, 12),
    part: 2,
    ready: true,
    title: "Places to work",
    scene_setup: "People working in different places.",
    comparison_question:
      "What might be difficult about working in these places?",
    follow_up_question: "Where would you prefer to work? Why?",
    photos: [
      {
        asset_path:
          "/practice-assets/original/academy-part2/p2-012-photo-a.jpg",
        alt: "A worker taking part in a conversation in a shared office.",
        sha256:
          "EBB8F003D5BABADD7A53C52518FB5DEBA63CBC6B9A49642EDBAE1AFA5CC0FF8B",
      },
      {
        asset_path:
          "/practice-assets/original/academy-part2/p2-012-photo-b.jpg",
        alt: "A person working alone on a laptop at home.",
        sha256:
          "6FF99BFD621B60B96E1980511FDE12CA0BFF07337F736EB603AD7A037CD9D937",
      },
    ],
    long_turn_seconds: 60,
    follow_up_seconds: 30,
  },
];

const readyPart3: readonly ReadyPart3Practice[] = [
  {
    ...originalBase(3, 5),
    part: 3,
    ready: true,
    title: "Happier at work",
    topic_set_id: topicSetIdFor(5),
    setup: "A company wants its employees to feel happier at work.",
    discussion_question:
      "How would these ideas help employees feel happier at work?",
    prompts: [
      "flexible working hours",
      "a free gym in the office",
      "more team activities",
      "longer holidays",
      "a quiet room for breaks",
    ],
    decision_question: "Which idea would make the biggest difference?",
    preview_seconds: 15,
    discussion_seconds: 120,
    decision_seconds: 60,
  },
  {
    ...originalBase(3, 6),
    part: 3,
    ready: true,
    title: "Protecting the environment",
    topic_set_id: topicSetIdFor(6),
    setup:
      "These are ways people can protect the environment in their daily lives.",
    discussion_question:
      "How useful are these ways of protecting the environment?",
    prompts: [
      "using public transport",
      "recycling at home",
      "buying second-hand clothes",
      "eating less meat",
      "saving water and electricity",
    ],
    decision_question:
      "Which two are the easiest for most people to do every day?",
    preview_seconds: 15,
    discussion_seconds: 120,
    decision_seconds: 60,
  },
  {
    ...originalBase(3, 7),
    part: 3,
    ready: true,
    title: "A free Saturday",
    topic_set_id: topicSetIdFor(7),
    setup: "A family is deciding how to spend a free Saturday together.",
    discussion_question:
      "Why might the family enjoy spending the day in these ways?",
    prompts: [
      "visiting a museum",
      "having a picnic in the countryside",
      "watching films at home",
      "going shopping in town",
      "doing sport together",
    ],
    decision_question: "Which plan would be best for the whole family?",
    preview_seconds: 15,
    discussion_seconds: 120,
    decision_seconds: 60,
  },
  {
    ...originalBase(3, 8),
    part: 3,
    ready: true,
    title: "Choosing a job",
    topic_set_id: topicSetIdFor(8),
    setup: "These are things people often think about when choosing a job.",
    discussion_question: "How important are these things when choosing a job?",
    prompts: [
      "a good salary",
      "friendly colleagues",
      "working near home",
      "opportunities to learn",
      "long holidays",
    ],
    decision_question:
      "Which two matter most for someone starting their first job?",
    preview_seconds: 15,
    discussion_seconds: 120,
    decision_seconds: 60,
  },
];

const readyPart4: readonly ReadyPart4Practice[] = [];

const buildPartCatalog = (
  part: SpeakingPart,
  readyItems: readonly PracticeCatalogItem[],
): readonly PracticeCatalogItem[] => {
  const readyByOrdinal = new Map(
    readyItems.map((item) => [item.ordinal, item]),
  );

  return Object.freeze(
    Array.from({ length: TOTAL_PRACTICES_PER_PART }, (_, index) => {
      const ordinal = index + 1;
      const readyItem = readyByOrdinal.get(ordinal);
      if (readyItem) return readyItem;
      return {
        ...originalBase(part, ordinal),
        ready: false,
        pending_reason:
          "Content has not yet been curated and teacher-approved.",
        ...(part === 3 || part === 4
          ? { topic_set_id: topicSetIdFor(ordinal) }
          : {}),
      } satisfies PendingPractice;
    }),
  );
};

export const part1Practices = buildPartCatalog(1, readyPart1);
export const part2Practices = buildPartCatalog(2, readyPart2);
export const part3Practices = buildPartCatalog(3, readyPart3);
export const part4Practices = buildPartCatalog(4, readyPart4);

export const practicesByPart: PracticeCatalogByPart = Object.freeze({
  1: part1Practices,
  2: part2Practices,
  3: part3Practices,
  4: part4Practices,
});

export const practiceCatalog: readonly PracticeCatalogItem[] = Object.freeze([
  ...part1Practices,
  ...part2Practices,
  ...part3Practices,
  ...part4Practices,
]);

export const getPracticeById = (
  id: PracticeId,
): PracticeCatalogItem | undefined =>
  practiceCatalog.find((practice) => practice.id === id);

export const getPracticesForPart = (
  part: SpeakingPart,
  options: { readyOnly?: boolean } = {},
): readonly PracticeCatalogItem[] => {
  const practices = practicesByPart[part];
  return options.readyOnly
    ? practices.filter((practice) => practice.ready)
    : practices;
};

export const getReadyPracticesForPart = (
  part: SpeakingPart,
): readonly PracticeCatalogItem[] =>
  getPracticesForPart(part, { readyOnly: true });

export const READY_PRACTICE_IDS = Object.freeze(
  practiceCatalog
    .filter((practice) => practice.ready)
    .map((practice) => practice.id),
);

export { TOTAL_PRACTICES_PER_PART };
