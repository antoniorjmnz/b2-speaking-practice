import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ReportView } from "./ReportView";
import type { StudentReport } from "./types";

const observation = {
  category: "strength",
  evidence: "Both photographs show people learning",
  start_ms: 0,
  end_ms: 10_000,
  explanation_es: "Abres con una comparación clara.",
  suggestion_es: "Mantén esta apertura.",
  severity: "leve",
  confidence: 0.9,
};

const report: StudentReport = {
  session_id: "session-1",
  task_question: "What might be difficult about learning in these situations?",
  evaluation_status: "evaluated",
  evaluation_status_reason_es: "",
  disclaimer_es:
    "Esta evaluación ha sido generada automáticamente con fines formativos. No es una calificación oficial de Cambridge English.",
  strengths: [observation],
  priority_improvements: [
    {
      ...observation,
      category: "priority_improvement",
      explanation_es: "Desarrolla más la segunda idea.",
    },
  ],
  grammar_vocabulary: {
    summary_es: "Vocabulario pertinente.",
    confidence: 0.9,
    practice_band: 3.5,
    observations: [],
  },
  discourse_management: {
    summary_es: "Progresión clara.",
    confidence: 0.88,
    practice_band: 3,
    observations: [],
  },
  practice_score: {
    global_band: 3.2,
    tier_key: "en_camino",
    tier_label: "En camino",
    tier_caption_es: "acercándote a B2",
    tier_index: 1,
    tier_count: 4,
    counted_criteria: ["grammar_vocabulary", "discourse_management"],
    confidence: 0.87,
    disclaimer_es:
      "Puntuación orientativa y formativa basada en tus bandas internas. No es una calificación oficial de Cambridge English.",
  },
  pronunciation: {
    available: true,
    withheld_reason_es: null,
    confidence: 0.78,
    summary_es: "Pronunciación comprensible en el fragmento analizado.",
    observations: [],
  },
  task_performance: [
    {
      key: "compares_photos",
      status: "logrado",
      explanation_es: "Comparación presente.",
      evidence: observation.evidence,
      start_ms: 0,
      end_ms: 10_000,
      confidence: 0.9,
    },
  ],
  suggested_exercises: ["Graba otra respuesta con dos contrastes."],
  overall_confidence: 0.87,
  transcript: [
    {
      id: "segment-1",
      position: 0,
      start_ms: 0,
      end_ms: 10_000,
      text: observation.evidence,
      confidence: 0.96,
    },
  ],
  audio_playback_url: "http://localhost/audio.wav",
  expires_at: "2026-08-13T10:00:00Z",
};

describe("student report", () => {
  it("shows the mandatory disclaimer and no internal scoring language", () => {
    render(<ReportView report={report} onNewAttempt={vi.fn()} />);
    expect(screen.getByText(report.disclaimer_es)).toBeInTheDocument();
    expect(screen.queryByText(/practice_band/i)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/pronunciación experimental/i),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(report.pronunciation.summary_es),
    ).toBeInTheDocument();
    expect(screen.getByText("Logrado")).toBeInTheDocument();
  });

  it("shows neutral internal bands without claiming a language level", () => {
    render(<ReportView report={report} onNewAttempt={vi.fn()} />);
    expect(
      screen.getByRole("heading", {
        name: "Bandas observadas por criterio",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("No determina tu nivel.")).toBeInTheDocument();
    expect(screen.getByText("3.5")).toBeInTheDocument();
    expect(screen.getByText(/experimental, no incluida/i)).toBeInTheDocument();
    expect(screen.queryByText("acercándote a B2")).not.toBeInTheDocument();
    expect(screen.queryByText("Sólido B2")).not.toBeInTheDocument();
    expect(screen.queryByText("Por encima")).not.toBeInTheDocument();
  });

  it("hides the score when it is not provided", () => {
    render(
      <ReportView
        report={{ ...report, practice_score: null }}
        onNewAttempt={vi.fn()}
      />,
    );
    expect(
      screen.queryByRole("heading", {
        name: "Bandas observadas por criterio",
      }),
    ).not.toBeInTheDocument();
  });

  it("lets the student start a new attempt", () => {
    const onNewAttempt = vi.fn();
    render(<ReportView report={report} onNewAttempt={onNewAttempt} />);
    fireEvent.click(screen.getByRole("button", { name: "Repetir práctica" }));
    expect(onNewAttempt).toHaveBeenCalledOnce();
  });

  it("shows a short honest completion screen in demo mode", () => {
    render(
      <ReportView
        report={{
          ...report,
          evaluation_status: "demo",
          evaluation_status_reason_es: "Evaluation provider not configured.",
          overall_confidence: 0,
          strengths: [],
          priority_improvements: [],
          task_performance: [],
          transcript: [],
        }}
        onNewAttempt={vi.fn()}
        onExit={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Práctica completada." }),
    ).toBeInTheDocument();
    expect(screen.getByText("Grabaci\u00f3n completada")).toBeInTheDocument();
    expect(screen.queryByText(/0%/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Grammar & Vocabulary/)).not.toBeInTheDocument();
    expect(screen.queryByText(/No evaluable/)).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Volver al men\u00fa" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Repetir pr\u00e1ctica" }),
    ).toBeInTheDocument();
  });
});
