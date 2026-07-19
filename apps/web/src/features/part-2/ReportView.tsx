"use client";

import { useRef } from "react";

import type {
  Observation,
  StudentPracticeScore,
  StudentPronunciation,
  StudentCriterion,
  StudentReport,
  TaskCheck,
} from "./types";

type ReportViewProps = {
  report: StudentReport;
  onNewAttempt: () => void;
  onExit?: () => void;
};

const TASK_LABELS: Record<string, string> = {
  answers_questions: "Responde a las tres preguntas",
  develops_answers: "Desarrolla sus respuestas",
  gives_reasons_examples: "Añade razones o ejemplos",
  response_length_appropriate: "Da respuestas de longitud adecuada",
  discusses_both: "Habla de las dos fotografías",
  compares_photos: "Compara, no solo describe",
  answers_question: "Responde a la pregunta",
  similarities_differences: "Explica semejanzas y diferencias",
  speculates: "Expresa posibilidades",
  justifies_opinions: "Justifica sus ideas",
  relevant: "Mantiene la respuesta relevante",
  develops_ideas: "Desarrolla sus ideas",
  uses_minute: "Aprovecha el minuto",
  finishes_early: "Evita terminar demasiado pronto",
  excessive_silence: "Mantiene la continuidad",
  responds_to_partner: "Responde a las ideas del compañero",
  links_contributions: "Enlaza su aportación con el turno anterior",
  invites_partner: "Invita o deja participar al compañero",
  negotiates: "Negocia acuerdo y desacuerdo",
  moves_towards_decision: "Ayuda a alcanzar una decisión",
  covers_options: "Explora varias opciones",
  balances_participation: "Mantiene una participación equilibrada",
};

const STATUS_LABELS: Record<string, string> = {
  logrado: "Logrado",
  parcial: "En desarrollo",
  no_logrado: "A revisar",
  no_evaluable: "No evaluable",
};

function formatTimestamp(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1_000));
  return `${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, "0")}`;
}

export function ReportView({ report, onNewAttempt, onExit }: ReportViewProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const part = report.speaking_part ?? 2;
  const isPart1 = part === 1;
  const isPart3 = part === 3;

  if (report.evaluation_status && report.evaluation_status !== "evaluated") {
    return (
      <UnevaluatedReport
        report={report}
        onNewAttempt={onNewAttempt}
        onExit={onExit}
      />
    );
  }

  const seek = (milliseconds: number) => {
    const player = audioRef.current;
    if (!player) return;
    player.currentTime = milliseconds / 1_000;
    void player.play();
  };

  return (
    <main className="report-shell">
      <header className="report-hero">
        <div>
          <p className="eyebrow">Part {part} · Corrección formativa</p>
          <h1>Corrección de tu Parte {part}.</h1>
        </div>
        <div
          className="confidence-stamp"
          aria-label={`Confianza técnica del análisis ${Math.round(report.overall_confidence * 100)} por ciento`}
        >
          <small>Confianza técnica</small>
          <span>{Math.round(report.overall_confidence * 100)}%</span>
          <small>no es una nota</small>
        </div>
      </header>

      <section className="disclaimer" aria-label="Aviso importante">
        <span aria-hidden="true">i</span>
        <p>{report.disclaimer_es}</p>
      </section>

      <section className="report-method" aria-label="Método de revisión">
        <strong>Cómo se ha revisado</strong>
        <span>Evidencia literal</span>
        <span>
          {isPart1
            ? "Mediciones de las respuestas"
            : isPart3
              ? "Diarización y turnos"
              : "Mediciones del minuto"}
        </span>
        <span>Comprobación automática adicional</span>
      </section>

      <section className="report-question">
        <p className="section-number">01</p>
        <div>
          <p className="eyebrow">La tarea</p>
          <h2>{report.task_question}</h2>
          <audio
            ref={audioRef}
            controls
            preload="metadata"
            src={report.audio_playback_url}
          >
            Tu navegador no permite reproducir esta grabación.
          </audio>
          <p className="microcopy">
            La grabación y el informe caducan el{" "}
            {new Date(report.expires_at).toLocaleString("es-ES", {
              dateStyle: "short",
              timeStyle: "short",
            })}
            .
          </p>
        </div>
      </section>

      <section className="report-grid">
        <div className="report-column">
          <p className="eyebrow green">Lo que ya funciona</p>
          <ObservationList
            items={report.strengths}
            seek={seek}
            empty="No hay suficiente evidencia para destacar una fortaleza concreta."
          />
        </div>
        <div className="report-column priority-column">
          <p className="eyebrow vermilion">Próximo foco</p>
          <ObservationList
            items={report.priority_improvements}
            seek={seek}
            empty="No se ha identificado una prioridad fiable."
          />
        </div>
      </section>

      {report.practice_score && (
        <PracticeScoreCard
          score={report.practice_score}
          grammar={report.grammar_vocabulary}
          discourse={report.discourse_management}
          interactive={isPart3 ? report.interactive_communication : undefined}
        />
      )}

      <section className="criteria-section">
        <div className="section-heading">
          <p className="section-number">02</p>
          <div>
            <p className="eyebrow">Cómo construyes la respuesta</p>
            <h2>
              {isPart3
                ? "Tres criterios observados por candidato."
                : "Observaciones por criterio."}
            </h2>
          </div>
        </div>
        <div className="criteria-grid">
          <Criterion
            title="Grammar & Vocabulary"
            criterion={report.grammar_vocabulary}
            seek={seek}
          />
          <Criterion
            title="Discourse Management"
            criterion={report.discourse_management}
            seek={seek}
          />
          {isPart3 && report.interactive_communication && (
            <Criterion
              title="Interactive Communication"
              criterion={report.interactive_communication}
              seek={seek}
            />
          )}
        </div>
      </section>

      <section className="pronunciation-section">
        <div className="section-heading">
          <p className="section-number">03</p>
          <div>
            <p className="eyebrow">Pronunciación</p>
            <h2>Lo que se oye en tu audio.</h2>
          </div>
        </div>
        <PronunciationPanel pronunciation={report.pronunciation} seek={seek} />
      </section>

      <section className="task-section">
        <div className="section-heading">
          <p className="section-number">04</p>
          <div>
            <p className="eyebrow">Comportamientos de Part {part}</p>
            <h2>Qué hiciste con la tarea.</h2>
          </div>
        </div>
        <div className="checks-list">
          {report.task_performance.map((check) => (
            <TaskCheckRow key={check.key} check={check} seek={seek} />
          ))}
        </div>
      </section>

      <section className="transcript-section">
        <div className="section-heading compact">
          <p className="section-number">05</p>
          <div>
            <p className="eyebrow">Transcripción verificable</p>
            <h2>Vuelve al momento exacto.</h2>
          </div>
        </div>
        <ol className="transcript-list">
          {report.transcript.map((segment) => (
            <li key={segment.id}>
              <button
                className="timestamp"
                onClick={() => seek(segment.start_ms)}
              >
                {formatTimestamp(segment.start_ms)}
              </button>
              <p>{segment.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="exercises-section">
        <p className="eyebrow">Práctica recomendada</p>
        <ol>
          {report.suggested_exercises.map((exercise) => (
            <li key={exercise}>{exercise}</li>
          ))}
        </ol>
      </section>

      <footer className="report-footer">
        <p>
          {isPart1
            ? "Interview Lab"
            : isPart3
              ? `Collaborative Task · Candidato ${report.candidate_label ?? ""}`
              : "Long Turn Lab"}{" "}
          · práctica, no certificación
        </p>
        <div className="button-row">
          {onExit && (
            <button className="button button-quiet" onClick={onExit}>
              Volver al menú
            </button>
          )}
          <button className="button button-primary" onClick={onNewAttempt}>
            Repetir práctica
          </button>
        </div>
      </footer>
    </main>
  );
}

function BandMeter({ band }: { band: number | null | undefined }) {
  const value = typeof band === "number" ? band : 0;
  const pending = typeof band !== "number";
  return (
    <div
      className="band-meter"
      role="img"
      aria-label={
        pending
          ? "Indicador interno no disponible"
          : `Indicador interno ${value.toFixed(1)} sobre 5`
      }
    >
      {[1, 2, 3, 4, 5].map((step) => {
        const fill =
          value >= step ? "is-full" : value >= step - 0.5 ? "is-half" : "";
        return (
          <span
            key={step}
            className={`band-seg ${pending ? "is-pending" : fill}`}
            aria-hidden="true"
          />
        );
      })}
    </div>
  );
}

function BandRow({
  title,
  band,
  note,
  pending = false,
}: {
  title: string;
  band?: number | null;
  note?: string;
  pending?: boolean;
}) {
  return (
    <div className={`band-row${pending ? " is-pending" : ""}`}>
      <div className="band-row-head">
        <span>
          {title}
          {note && <small> · {note}</small>}
        </span>
        <strong>
          {pending || typeof band !== "number" ? "—" : band.toFixed(1)}
          {!pending && typeof band === "number" && <small>/5</small>}
        </strong>
      </div>
      <BandMeter band={pending ? null : band} />
    </div>
  );
}

function PracticeScoreCard({
  score,
  grammar,
  discourse,
  interactive,
}: {
  score: StudentPracticeScore;
  grammar: StudentCriterion;
  discourse: StudentCriterion;
  interactive?: StudentCriterion;
}) {
  return (
    <section
      className="score-card"
      aria-label="Indicadores internos de la práctica"
    >
      <div className="score-card-header">
        <div>
          <p className="eyebrow">Referencia de esta respuesta</p>
          <h2>Bandas observadas por criterio</h2>
          <p>
            Escala automática de 0 a 5 para comparar tus propias prácticas con
            el tiempo. Cada criterio se interpreta por separado.
          </p>
        </div>
        <span className="score-reliability">
          {Math.round(score.confidence * 100)}% de confianza técnica
        </span>
      </div>

      <aside className="score-limits">
        <strong>No determina tu nivel.</strong>
        <span>
          Estas bandas internas no equivalen a una nota ni a un resultado de
          Cambridge English. Úsalas junto con las evidencias del informe.
        </span>
      </aside>

      <div className="score-bands">
        <BandRow title="Grammar & Vocabulary" band={grammar.practice_band} />
        <BandRow title="Discourse Management" band={discourse.practice_band} />
        {interactive && (
          <BandRow
            title="Interactive Communication"
            band={interactive.practice_band}
          />
        )}
        <BandRow
          title="Pronunciation"
          note="experimental, no incluida"
          pending
        />
      </div>
    </section>
  );
}

function PronunciationPanel({
  pronunciation,
  seek,
}: {
  pronunciation: StudentPronunciation;
  seek: (milliseconds: number) => void;
}) {
  return (
    <article className="pronunciation-card">
      <div className="criterion-heading">
        <h3>Análisis del audio</h3>
        <span>{Math.round(pronunciation.confidence * 100)}% fiable</span>
      </div>
      <p className="criterion-summary">{pronunciation.summary_es}</p>
      {!pronunciation.available && pronunciation.withheld_reason_es && (
        <p className="pronunciation-withheld">
          {pronunciation.withheld_reason_es}
        </p>
      )}
      {pronunciation.observations.length > 0 && (
        <ul className="pronunciation-list">
          {pronunciation.observations.map((item, index) => (
            <li key={`${item.feature}-${item.start_ms}-${index}`}>
              <button className="timestamp" onClick={() => seek(item.start_ms)}>
                {formatTimestamp(item.start_ms)}
              </button>
              <div>
                <h3>{item.explanation_es}</h3>
                <p>{item.suggestion_es}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}

function UnevaluatedReport({ report, onNewAttempt, onExit }: ReportViewProps) {
  const isDemo = report.evaluation_status === "demo";

  return (
    <main className="unevaluated-shell">
      <div className="unevaluated-orbit" aria-hidden="true">
        <span />
        <span />
        <span />
      </div>
      <section className="unevaluated-panel" aria-labelledby="result-title">
        <div className="result-signal" aria-hidden="true">
          <i />
          <i />
          <i />
          <i />
          <i />
        </div>
        <p className="eyebrow">
          {isDemo ? "Grabaci\u00f3n completada" : "Intento completado"}
        </p>
        <h1 id="result-title">
          {isDemo ? "Práctica completada." : "No podemos evaluarlo bien."}
        </h1>
        <p className="unevaluated-lead">
          {isDemo
            ? "La evaluaci\u00f3n por IA no est\u00e1 conectada en este entorno, as\u00ed que no hemos generado porcentajes, criterios ni comentarios sobre tu ingl\u00e9s."
            : "La grabaci\u00f3n no contiene evidencia suficiente para ofrecerte comentarios responsables. Es mejor repetirla que inventar una valoraci\u00f3n."}
        </p>
        <div className="unevaluated-meta">
          <span>Part {report.speaking_part ?? 2}</span>
          <p>{report.task_question}</p>
        </div>
        <div className="button-row result-actions">
          {onExit && (
            <button className="button button-quiet" onClick={onExit}>
              {"Volver al men\u00fa"}
            </button>
          )}
          <button className="button button-primary" onClick={onNewAttempt}>
            {"Repetir pr\u00e1ctica"}
          </button>
        </div>
        <p className="result-expiry">
          El audio temporal se elimina el{" "}
          {new Date(report.expires_at).toLocaleString("es-ES", {
            dateStyle: "short",
            timeStyle: "short",
          })}
          .
        </p>
      </section>
    </main>
  );
}

function ObservationList({
  items,
  seek,
  empty,
}: {
  items: Observation[];
  seek: (milliseconds: number) => void;
  empty: string;
}) {
  if (!items.length) return <p className="empty-copy">{empty}</p>;
  return (
    <ul className="observation-list">
      {items.map((item, index) => (
        <li key={`${item.category}-${item.start_ms}-${index}`}>
          <button className="timestamp" onClick={() => seek(item.start_ms)}>
            {formatTimestamp(item.start_ms)}
          </button>
          <div>
            <h3>{item.explanation_es}</h3>
            <span className="observation-label">Fragmento de tu respuesta</span>
            <blockquote>“{item.evidence}”</blockquote>
            <span className="observation-label">
              Corrección o siguiente paso
            </span>
            <p>{item.suggestion_es}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

function Criterion({
  title,
  criterion,
  seek,
}: {
  title: string;
  criterion: StudentCriterion;
  seek: (milliseconds: number) => void;
}) {
  return (
    <article className="criterion">
      <div className="criterion-heading">
        <h3>{title}</h3>
        <span>{Math.round(criterion.confidence * 100)}% fiable</span>
      </div>
      <p className="criterion-summary">{criterion.summary_es}</p>
      <ObservationList
        items={criterion.observations}
        seek={seek}
        empty="No hay evidencia específica suficiente."
      />
    </article>
  );
}

function TaskCheckRow({
  check,
  seek,
}: {
  check: TaskCheck;
  seek: (milliseconds: number) => void;
}) {
  const status = STATUS_LABELS[check.status] ?? check.status;
  return (
    <article className="check-row">
      <span
        className={`status-dot status-${check.status}`}
        aria-hidden="true"
      />
      <div>
        <h3>{TASK_LABELS[check.key] ?? check.key}</h3>
        <p>{check.explanation_es}</p>
      </div>
      <span className={`status-label status-${check.status}`}>{status}</span>
      {check.start_ms !== null && check.evidence ? (
        <button
          className="evidence-link"
          onClick={() => seek(check.start_ms ?? 0)}
        >
          “{check.evidence}” · {formatTimestamp(check.start_ms)}
        </button>
      ) : (
        <span />
      )}
    </article>
  );
}
