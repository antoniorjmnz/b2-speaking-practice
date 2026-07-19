"use client";

import { useEffect, useMemo, useState } from "react";

import { Part1Practice } from "@/features/part-1/Part1Practice";
import { Part2Practice } from "@/features/part-2/Part2Practice";
import { Part3PairPractice } from "@/features/part-3/Part3PairPractice";
import {
  clearActiveRun,
  loadActiveRun,
  loadAiReviewPreference,
  loadTimerPreference,
  saveActiveRun,
  saveAiReviewPreference,
  saveTimerPreference,
} from "@/features/part-2/sessionRecovery";
import {
  createEmptyProgress,
  createReadyCatalog,
  createManualSelection,
  getProgressStatus,
  loadProgress,
  makePracticeId,
  markPracticeCompleted,
  markPracticeSeen,
  parsePracticeId,
  rememberSelection,
  saveProgress,
  shuffleSelection,
  type PracticeMode,
  type PracticePart,
  type PracticeProgress,
  type ProgressStatus,
} from "./progress";
import {
  getReadyPracticesForPart,
  practicesByPart,
  type ReadyPart2Practice,
} from "./index";

type Mode = PracticeMode;
type PartNumber = 1 | 2 | 3;

type AppProfile = "hosted" | "offline" | "custom";

const configuredProfile = process.env.NEXT_PUBLIC_APP_PROFILE;
const APP_PROFILE: AppProfile =
  configuredProfile === "offline" || configuredProfile === "custom"
    ? configuredProfile
    : "hosted";
const IS_OFFLINE = APP_PROFILE === "offline";

const READY_CATALOG = createReadyCatalog({
  P1: getReadyPracticesForPart(1).map((item) => item.ordinal),
  P2: getReadyPracticesForPart(2).map((item) => item.ordinal),
  P3: getReadyPracticesForPart(3).map((item) => item.ordinal),
  P4: getReadyPracticesForPart(4).map((item) => item.ordinal),
});

const PART_2_TASK_IDS: Record<number, string> = {
  9: "99999999-9999-4999-8999-999999999999",
  10: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  11: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  12: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
};

const PART_1_TASK_IDS: Record<number, string> = {
  9: "d9999999-9999-4999-8999-999999999999",
  10: "daaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
  11: "dbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  12: "dccccccc-cccc-4ccc-8ccc-cccccccccccc",
};

const PART_3_TASK_IDS: Record<number, string> = {
  5: "e5555555-5555-4555-8555-555555555555",
  6: "e6666666-6666-4666-8666-666666666666",
  7: "e7777777-7777-4777-8777-777777777777",
  8: "e8888888-8888-4888-8888-888888888888",
};

const TASK_IDS: Record<PartNumber, Record<number, string>> = {
  1: PART_1_TASK_IDS,
  2: PART_2_TASK_IDS,
  3: PART_3_TASK_IDS,
};

const MODES: Array<{
  id: Mode;
  number: string;
  title: string;
  description: string;
  note: string;
}> = [
  {
    id: "individual",
    number: "01",
    title: "Individual",
    description:
      "Responde tú solo y revisa tu inglés con evidencias concretas.",
    note: "Partes 1 y 2 · corrección individual",
  },
  {
    id: "ai_partner",
    number: "02",
    title: "Individual + IA",
    description:
      "En Part 2, Candidate B recibe su pregunta y responde sin pausas manuales.",
    note: "Parte 2 · compañero experimental",
  },
  {
    id: "pair",
    number: "03",
    title: "Dos personas",
    description:
      "Candidate A y Candidate B conversan juntos y reciben informes separados.",
    note: "Parte 3 · separación de voces",
  },
];

const RUNNABLE_PART: {
  id: PartNumber;
  title: string;
  short: string;
  duration: string;
  description: string;
} = {
  id: 2,
  title: "Long turn",
  short: "Comparar fotografías",
  duration: "1 min",
  description:
    "Compara dos fotografías, responde a la pregunta y aprovecha un minuto completo.",
};

const RUNNABLE_PARTS = [
  {
    id: 1 as const,
    title: "Interview",
    short: "Preguntas personales",
    duration: "3 x 20 s",
    description:
      "Escucha tres preguntas personales y responde tú solo, una a una.",
  },
  RUNNABLE_PART,
  {
    id: 3 as const,
    title: "Collaborative task",
    short: "Discutir y decidir",
    duration: "2 + 1 min",
    description:
      "Dos candidatos exploran cinco ideas y después negocian una decisión.",
  },
];

function practicePart(part: PartNumber): PracticePart {
  return `P${part}` as PracticePart;
}

function statusLabel(status: ProgressStatus): string {
  if (status === "completed") return "Completada";
  if (status === "seen") return "Vista";
  return "Nueva";
}

function firstReadyPractice(part: PartNumber): number {
  return getReadyPracticesForPart(part)[0]?.ordinal ?? 1;
}

export function SpeakingAcademyApp() {
  const [mode, setMode] = useState<Mode>("individual");
  const [activePart, setActivePart] = useState<PartNumber>(2);
  const [practice, setPractice] = useState(() => firstReadyPractice(2));
  const [progress, setProgress] = useState<PracticeProgress>(() =>
    createEmptyProgress(),
  );
  const [showTimer, setShowTimer] = useState(false);
  const [aiReview, setAiReview] = useState(true);
  const [screen, setScreen] = useState<"setup" | "practice">("setup");

  useEffect(() => {
    queueMicrotask(() => {
      setProgress(loadProgress());
      setAiReview(IS_OFFLINE ? false : loadAiReviewPreference());
      const activeRun = loadActiveRun();
      if (activeRun && TASK_IDS[activeRun.part]?.[activeRun.practice]) {
        setMode(activeRun.mode);
        setActivePart(activeRun.part);
        setPractice(activeRun.practice);
        setShowTimer(activeRun.showTimer);
        setScreen("practice");
        return;
      }
      setShowTimer(loadTimerPreference());
    });
  }, []);

  const activeKey = makePracticeId(practicePart(activePart), practice);
  const activeStatus = getProgressStatus(progress, activeKey);
  const activeCatalogItem = practicesByPart[activePart][practice - 1];
  const activeReady = activeCatalogItem?.ready === true;
  const runningPart: PartNumber = activePart;
  const runningCatalogItem = practicesByPart[runningPart]?.[practice - 1];
  const runningKey = makePracticeId(practicePart(runningPart), practice);

  const completedCount = useMemo(
    () =>
      Object.entries(progress.entries).filter(
        ([id, entry]) =>
          (id.startsWith("P1-") ||
            id.startsWith("P2-") ||
            id.startsWith("P3-")) &&
          entry?.status === "completed",
      ).length,
    [progress],
  );

  const modeDetails = MODES.find((item) => item.id === mode) ?? MODES[0];

  const selectMode = (nextMode: Mode) => {
    if (IS_OFFLINE && nextMode !== "individual") return;
    if (activePart === 1 && nextMode !== "individual") return;
    if (activePart === 2 && nextMode === "pair") return;
    if (activePart === 3 && nextMode !== "pair") return;
    setMode(nextMode);
  };

  const selectPart = (nextPart: PartNumber) => {
    if (IS_OFFLINE && nextPart !== 2) return;
    setActivePart(nextPart);
    setPractice(firstReadyPractice(nextPart));
    if (nextPart === 1) setMode("individual");
    if (nextPart === 2 && mode === "pair") setMode("individual");
    if (nextPart === 3) setMode("pair");
  };

  const shuffle = () => {
    const activePracticePart = practicePart(activePart);
    const selection = shuffleSelection({
      mode,
      parts: [activePracticePart],
      catalog: READY_CATALOG,
      progress,
    });
    const selectedId = selection[activePracticePart]?.[0];
    const next = selectedId ? parsePracticeId(selectedId)?.level : undefined;
    if (next) setPractice(next);
    const nextProgress = rememberSelection(progress, selection);
    setProgress(nextProgress);
    saveProgress(nextProgress);
  };

  const start = () => {
    if (!activeReady) return;
    const runPracticePart = practicePart(runningPart);
    const secondReadyP2 = READY_CATALOG.P2.map(
      (id) => parsePracticeId(id)?.level,
    ).find((level) => level !== undefined && level !== practice);
    const selection = createManualSelection({
      mode,
      parts: [runPracticePart],
      catalog: READY_CATALOG,
      levels: {
        P1: practice,
        P2:
          mode === "individual"
            ? practice
            : [practice, secondReadyP2 ?? practice],
        P3: practice,
        P4: practice,
      },
    });
    const nextProgress = markPracticeSeen(
      rememberSelection(progress, selection),
      runningKey,
    );
    setProgress(nextProgress);
    saveProgress(nextProgress);
    saveActiveRun({ mode, part: runningPart, practice, showTimer });
    setScreen("practice");
  };

  const leavePractice = (completed = false) => {
    clearActiveRun();
    if (completed) {
      const nextProgress = markPracticeCompleted(progress, runningKey);
      setProgress(nextProgress);
      saveProgress(nextProgress);
    }
    setScreen("setup");
  };

  const markCurrentCompleted = () => {
    const nextProgress = markPracticeCompleted(progress, runningKey);
    setProgress(nextProgress);
    saveProgress(nextProgress);
  };

  const changeTimerVisibility = (visible: boolean) => {
    setShowTimer(visible);
    saveTimerPreference(visible);
  };

  const changeAiReview = (enabled: boolean) => {
    if (IS_OFFLINE) return;
    setAiReview(enabled);
    saveAiReviewPreference(enabled);
  };

  const downloadOnlyActive =
    (IS_OFFLINE || !aiReview) && activePart === 2 && mode === "individual";

  if (screen === "practice") {
    if (runningPart === 1) {
      return (
        <Part1Practice
          taskId={PART_1_TASK_IDS[practice]}
          practiceLabel={`Práctica ${String(practice).padStart(2, "0")}`}
          showTimer={showTimer}
          onExit={() => leavePractice(false)}
          onCompleted={markCurrentCompleted}
        />
      );
    }
    if (runningPart === 3) {
      return (
        <Part3PairPractice
          taskId={PART_3_TASK_IDS[practice]}
          practiceLabel={`Práctica ${String(practice).padStart(2, "0")}`}
          showTimer={showTimer}
          onExit={() => leavePractice(false)}
          onCompleted={markCurrentCompleted}
        />
      );
    }
    return (
      <Part2Practice
        taskId={PART_2_TASK_IDS[practice]}
        practiceLabel={`Práctica ${String(practice).padStart(2, "0")}`}
        modeLabel={modeDetails.title}
        withAiPartner={mode === "ai_partner"}
        downloadOnly={downloadOnlyActive}
        showTimer={showTimer}
        followUpQuestion={
          runningCatalogItem?.ready && runningCatalogItem.part === 2
            ? (runningCatalogItem as ReadyPart2Practice).follow_up_question
            : undefined
        }
        onExit={() => leavePractice(false)}
        onCompleted={markCurrentCompleted}
      />
    );
  }

  return (
    <main className="academy-shell">
      <header className="academy-header">
        <div className="academy-wordmark" aria-label="B2 Speaking Practice">
          <span>
            B2 Speaking Practice
            <small>
              {APP_PROFILE === "offline"
                ? "Edición offline · el audio no sale del navegador"
                : APP_PROFILE === "custom"
                  ? "Edición autogestionada · tus propios proveedores"
                  : "Práctica formativa · sin cuentas"}
            </small>
          </span>
        </div>
        <div
          className="academy-progress"
          aria-label={`${completedCount} prácticas completadas`}
        >
          <span>{completedCount}</span>
          <small>completadas en este navegador</small>
        </div>
      </header>

      <div className="academy-grid">
        <section className="academy-main" aria-labelledby="setup-title">
          <div className="setup-intro">
            <p className="academy-kicker">Nueva práctica</p>
            <h1 id="setup-title">Elige cómo quieres practicar</h1>
            <p>
              {IS_OFFLINE
                ? "Practica Part 2 sin cuentas, nube ni servicios externos. Al terminar, descarga tu audio para revisarlo donde quieras."
                : "Elige el formato y una práctica disponible. Sin cuentas ni historial en la nube."}
            </p>
          </div>

          <SetupSection number="1" title="Formato">
            <div className="mode-list">
              {MODES.map((item) => {
                const selected = mode === item.id;
                const disabled =
                  (IS_OFFLINE && item.id !== "individual") ||
                  (activePart === 1 && item.id !== "individual") ||
                  (activePart === 2 && item.id === "pair") ||
                  (activePart === 3 && item.id !== "pair");
                return (
                  <button
                    type="button"
                    className={`mode-option${selected ? " is-selected" : ""}`}
                    data-mode={item.id}
                    onClick={() => selectMode(item.id)}
                    aria-pressed={selected}
                    disabled={disabled}
                    key={item.id}
                  >
                    <span className="mode-number">{item.number}</span>
                    <span className="mode-copy">
                      <strong>{item.title}</strong>
                      <span>{item.description}</span>
                    </span>
                    <small>
                      {disabled
                        ? IS_OFFLINE
                          ? "La edición offline no utiliza servicios de IA"
                          : item.id === "pair"
                            ? "Disponible en Part 3"
                            : item.id === "ai_partner"
                              ? "Disponible en Part 2"
                              : "No corresponde a esta parte"
                        : item.note}
                    </small>
                    <span className="choice-mark" aria-hidden="true">
                      {selected ? "✓" : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          </SetupSection>

          <SetupSection number="2" title="Parte disponible">
            <div className="part-list">
              {RUNNABLE_PARTS.map((item) => (
                <button
                  type="button"
                  className={`part-option${activePart === item.id ? " is-selected" : ""}`}
                  onClick={() => selectPart(item.id)}
                  aria-pressed={activePart === item.id}
                  disabled={IS_OFFLINE && item.id !== 2}
                  key={item.id}
                >
                  <span className="part-index">0{item.id}</span>
                  <span>
                    <strong>
                      Part {item.id} · {item.title}
                    </strong>
                    <small>{item.description}</small>
                  </span>
                  <span className="part-time">{item.duration}</span>
                  <span className="part-toggle" aria-hidden="true" />
                </button>
              ))}
            </div>
          </SetupSection>

          <SetupSection
            number="3"
            title="Número de práctica"
            action={
              <button
                className="shuffle-button"
                type="button"
                onClick={shuffle}
              >
                <span aria-hidden="true">↝</span> Aleatoria
              </button>
            }
          >
            <div className="level-toolbar">
              <p>
                {getReadyPracticesForPart(activePart).length} prácticas ·{" "}
                <strong>Práctica {String(practice).padStart(2, "0")}</strong>
              </p>
              <p className={`status-chip status-${activeStatus}`}>
                {statusLabel(activeStatus)}
              </p>
            </div>
            <div className="level-grid" aria-label="Prácticas disponibles">
              {getReadyPracticesForPart(activePart).map((catalogItem) => {
                const number = catalogItem.ordinal;
                const key = makePracticeId(practicePart(activePart), number);
                const status = getProgressStatus(progress, key);
                return (
                  <button
                    type="button"
                    key={key}
                    className={`${number === practice ? "is-selected" : ""} is-${status}`}
                    onClick={() => setPractice(number)}
                    aria-label={`Práctica ${number}, ${statusLabel(status)}`}
                    aria-pressed={number === practice}
                  >
                    {String(number).padStart(2, "0")}
                  </button>
                );
              })}
            </div>
            <div className="level-legend" aria-label="Leyenda de progreso">
              <span>
                <i className="legend-new" /> Nueva
              </span>
              <span>
                <i className="legend-seen" /> Vista
              </span>
              <span>
                <i className="legend-completed" /> Completada
              </span>
            </div>
          </SetupSection>

          <SetupSection number="4" title="Corrección">
            <label className="timer-setting">
              <span>
                <strong>
                  {IS_OFFLINE
                    ? "Modo privado · solo grabar y descargar"
                    : aiReview
                      ? "Corrección con IA"
                      : "Sin corrección · solo grabar y descargar"}
                </strong>
                <small>
                  {IS_OFFLINE
                    ? "La grabación se mantiene en el navegador y no se envía al backend ni a terceros."
                    : aiReview
                      ? "Al terminar recibes el informe formativo automático."
                      : activePart === 2 && mode === "individual"
                        ? "Al terminar descargas tu audio y las fotos para revisarlos con otra IA. Nada se sube."
                        : "Disponible en Part 2 · formato Individual."}
                </small>
              </span>
              <input
                type="checkbox"
                role="switch"
                checked={aiReview}
                onChange={(event) => changeAiReview(event.target.checked)}
                disabled={IS_OFFLINE}
              />
              <span className="timer-setting-control" aria-hidden="true" />
            </label>
          </SetupSection>

          <SetupSection number="5" title="Vista del tiempo">
            <label className="timer-setting">
              <span>
                <strong>
                  {showTimer
                    ? "Contador visible"
                    : "Modo examen · contador oculto"}
                </strong>
                <small>
                  {showTimer
                    ? "Útil para aprender a distribuir el minuto."
                    : "La examinadora controla el tiempo como en la prueba real."}
                </small>
              </span>
              <input
                type="checkbox"
                role="switch"
                checked={showTimer}
                onChange={(event) =>
                  changeTimerVisibility(event.target.checked)
                }
              />
              <span className="timer-setting-control" aria-hidden="true" />
            </label>
          </SetupSection>
        </section>

        <aside className="session-ticket" aria-label="Resumen de la práctica">
          <div className="ticket-top">
            <p>Sesión preparada</p>
            <span className="live-dot">Lista</span>
          </div>
          <div className="ticket-practice">
            <span>P{activePart}</span>
            <strong>{String(practice).padStart(2, "0")}</strong>
          </div>
          <dl>
            <div>
              <dt>Formato</dt>
              <dd>{modeDetails.title}</dd>
            </div>
            <div>
              <dt>Partes</dt>
              <dd>P{activePart}</dd>
            </div>
            <div>
              <dt>Material</dt>
              <dd>Tarea original · fotos con licencia</dd>
            </div>
            <div>
              <dt>Edición</dt>
              <dd>
                {APP_PROFILE === "offline"
                  ? "Offline"
                  : APP_PROFILE === "custom"
                    ? "Custom"
                    : "Alojada"}
              </dd>
            </div>
            <div>
              <dt>Datos</dt>
              <dd>
                {downloadOnlyActive
                  ? "Solo en tu navegador"
                  : "Temporales · sin cuenta"}
              </dd>
            </div>
            <div>
              <dt>Corrección</dt>
              <dd>
                {downloadOnlyActive ? "Sin IA · descargas" : "Informe IA"}
              </dd>
            </div>
            <div>
              <dt>Contador</dt>
              <dd>{showTimer ? "Visible" : "Oculto · modo examen"}</dd>
            </div>
          </dl>
          {mode === "ai_partner" && (
            <p className="ticket-note">
              Tras tu minuto, Candidate B recibe su pregunta y contesta
              automáticamente con una respuesta breve de nivel B2.
            </p>
          )}
          {mode === "pair" && (
            <p className="ticket-note">
              Una sola sala, dos muestras de voz y un informe independiente para
              cada candidato.
            </p>
          )}
          {activeCatalogItem?.ready && (
            <p className="ticket-task-title">{activeCatalogItem.title}</p>
          )}
          <button
            className="start-session"
            type="button"
            onClick={start}
            disabled={!activeReady}
          >
            <span>Comenzar práctica</span>
            <span aria-hidden="true">→</span>
          </button>
          <p className="ticket-footnote">
            Proyecto independiente inspirado en el formato del examen. No está
            afiliado con Cambridge y no ofrece una calificación oficial.
          </p>
        </aside>
      </div>

      <div
        className="mobile-launch"
        aria-label={"Acceso r\u00e1pido a la pr\u00e1ctica"}
      >
        <div>
          <small>Lista para empezar</small>
          <strong>
            P{activePart} <span>{"\u00b7"}</span>{" "}
            {String(practice).padStart(2, "0")}
          </strong>
        </div>
        <button type="button" onClick={start} disabled={!activeReady}>
          Comenzar <span aria-hidden="true">{"\u2192"}</span>
        </button>
      </div>
    </main>
  );
}

function SetupSection({
  number,
  title,
  action,
  children,
}: {
  number: string;
  title: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="setup-section">
      <header>
        <span>{number}</span>
        <h2>{title}</h2>
        {action}
      </header>
      {children}
    </section>
  );
}
