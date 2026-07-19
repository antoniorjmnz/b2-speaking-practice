"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import Image from "next/image";

import {
  ApiError,
  authorizeUpload,
  completeRecording,
  createSession,
  deleteSession,
  fetchAiPartnerTurn,
  fetchReport,
  fetchSessionStatus,
  fetchTask,
  retrySession,
  uploadRecording,
} from "./api";
import { initialPracticeState, practiceReducer } from "./practiceMachine";
import { ReportView } from "./ReportView";
import {
  clearActiveSession,
  loadActiveSession,
  saveActiveSession,
} from "./sessionRecovery";
import type {
  AiPartnerTurn,
  SessionCapability,
  StudentReport,
  Task,
} from "./types";
import {
  extensionForMime,
  recordForDuration,
  sha256,
  type RecordingResult,
} from "@/features/recording/mediaRecorder";
import {
  requestAndCheckMicrophone,
  stopMicrophone,
} from "@/features/recording/microphone";

const PRACTICE_DURATION_MS = Number(
  process.env.NEXT_PUBLIC_PRACTICE_DURATION_MS ?? 60_000,
);
const POLL_INTERVAL_MS = Number(
  process.env.NEXT_PUBLIC_POLL_INTERVAL_MS ?? 1_500,
);
const MICROPHONE_TEST_DURATION_MS = Number(
  process.env.NEXT_PUBLIC_MICROPHONE_TEST_DURATION_MS ?? 5_000,
);
const MINIMUM_MICROPHONE_LEVEL = 0.06;
const EXAMINER_START_AUDIO =
  "/assets/temporary-part2/examiner-start-now-sonia.mp3";

type MicrophoneCheckStatus = "idle" | "testing" | "passed" | "too-quiet";

function friendlyError(error: unknown, fallback: string): string {
  if (error instanceof DOMException && error.name === "NotAllowedError") {
    return "Necesitamos permiso para usar el micrófono. Revisa el icono de permisos del navegador.";
  }
  if (
    error instanceof Error &&
    error.message &&
    !error.message.includes("Session token")
  ) {
    return error.message;
  }
  return fallback;
}

type SpokenRole = "examiner" | "candidate";

type SpokenTurnResult = {
  voiceName: string;
};

async function availableVoices(
  synth: SpeechSynthesis,
): Promise<SpeechSynthesisVoice[]> {
  const current = synth.getVoices();
  if (current.length > 0) return current;

  return new Promise((resolve) => {
    const finish = () => {
      window.clearTimeout(timeoutId);
      synth.removeEventListener("voiceschanged", onVoicesChanged);
      resolve(synth.getVoices());
    };
    const onVoicesChanged = () => {
      if (synth.getVoices().length > 0) finish();
    };
    const timeoutId = window.setTimeout(finish, 900);
    synth.addEventListener("voiceschanged", onVoicesChanged);
  });
}

function selectBritishVoice(
  voices: SpeechSynthesisVoice[],
  role: SpokenRole,
): SpeechSynthesisVoice | undefined {
  const english = voices.filter((voice) =>
    voice.lang.toLowerCase().startsWith("en"),
  );
  const british = english.filter((voice) =>
    voice.lang.toLowerCase().startsWith("en-gb"),
  );
  const preferredNames =
    role === "examiner" ? ["Sonia"] : ["Ryan", "Libby", "George"];
  const preferred = preferredNames
    .map((name) => british.find((voice) => voice.name.includes(name)))
    .find(Boolean);
  if (preferred) return preferred;
  if (role === "candidate") {
    const distinctCandidate = british.find(
      (voice) => !voice.name.includes("Sonia"),
    );
    if (distinctCandidate) return distinctCandidate;
  }
  return british[0] ?? english[0];
}

async function speakTurn(
  text: string,
  role: SpokenRole,
): Promise<SpokenTurnResult> {
  if (
    typeof window === "undefined" ||
    !window.speechSynthesis ||
    typeof SpeechSynthesisUtterance === "undefined"
  ) {
    throw new Error(
      "Este navegador no ofrece una voz inglesa para continuar automÃ¡ticamente.",
    );
  }
  const synth = window.speechSynthesis;
  const selected = selectBritishVoice(await availableVoices(synth), role);
  return new Promise((resolve, reject) => {
    const utterance = new SpeechSynthesisUtterance(text);
    if (selected) utterance.voice = selected;
    utterance.lang = selected?.lang ?? "en-GB";
    utterance.rate = role === "examiner" ? 0.94 : 0.96;
    utterance.pitch = role === "examiner" ? 1 : 0.98;
    utterance.onend = () =>
      resolve({ voiceName: selected?.name ?? "Voz inglesa del navegador" });
    utterance.onerror = () =>
      reject(new Error("La voz del navegador se ha interrumpido."));
    synth.speak(utterance);
  });
}

function examinerFollowUpText(question: string): string {
  return `Thank you. That's the end of your minute. Candidate B, ${question}`;
}

function examinerFollowUpAudioPath(practiceLabel: string): string {
  const practiceNumber = practiceLabel.match(/\d+/)?.[0] ?? "1";
  return `/assets/temporary-part2/examiner-p2-${practiceNumber.padStart(3, "0")}-followup-sonia.mp3`;
}

function playAudioAsset(audioPath: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const player = new Audio(audioPath);
    player.preload = "auto";
    player.addEventListener("ended", () => resolve(), { once: true });
    player.addEventListener(
      "error",
      () => reject(new Error("No se ha podido reproducir el audio.")),
      { once: true },
    );
    void player
      .play()
      .catch(() => reject(new Error("El navegador ha bloqueado el audio.")));
  });
}

export function Part2Practice({
  taskId,
  practiceLabel = "Práctica 01",
  modeLabel = "Practicar solo",
  withAiPartner = false,
  downloadOnly = false,
  showTimer = false,
  followUpQuestion,
  onExit,
  onCompleted,
}: {
  taskId?: string;
  practiceLabel?: string;
  modeLabel?: string;
  withAiPartner?: boolean;
  downloadOnly?: boolean;
  showTimer?: boolean;
  followUpQuestion?: string;
  onExit?: () => void;
  onCompleted?: () => void;
}) {
  const [state, dispatch] = useReducer(practiceReducer, initialPracticeState);
  const [task, setTask] = useState<Task | null>(null);
  const [session, setSession] = useState<SessionCapability | null>(null);
  const [consent, setConsent] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [micLevel, setMicLevel] = useState(0);
  const [micCheckStatus, setMicCheckStatus] =
    useState<MicrophoneCheckStatus>("idle");
  const [micSecondsRemaining, setMicSecondsRemaining] = useState(
    Math.ceil(MICROPHONE_TEST_DURATION_MS / 1_000),
  );
  const [remainingMs, setRemainingMs] = useState(PRACTICE_DURATION_MS);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [processingStage, setProcessingStage] = useState("queued");
  const [processingCanRetry, setProcessingCanRetry] = useState(false);
  const [processingStartedAt, setProcessingStartedAt] = useState<number | null>(
    null,
  );
  const [processingElapsedMs, setProcessingElapsedMs] = useState(0);
  const [processingHeartbeatAt, setProcessingHeartbeatAt] = useState<
    string | null
  >(null);
  const [processingConnectionIssue, setProcessingConnectionIssue] =
    useState(false);
  const [report, setReport] = useState<StudentReport | null>(null);
  const [finishedRecording, setFinishedRecording] =
    useState<RecordingResult | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [partnerTurn, setPartnerTurn] = useState<AiPartnerTurn | null>(null);
  const [partnerStatus, setPartnerStatus] = useState<
    "idle" | "loading" | "ready" | "error"
  >("idle");
  const [partnerError, setPartnerError] = useState<string | null>(null);
  const [partnerVoice, setPartnerVoice] = useState<string | null>(null);
  const [examinerVoice, setExaminerVoice] = useState<string | null>(null);
  const [partnerSpeaking, setPartnerSpeaking] = useState(false);
  const [partnerSequence, setPartnerSequence] = useState<
    "idle" | "examiner" | "candidate" | "failed"
  >("idle");
  const [sequenceError, setSequenceError] = useState<string | null>(null);
  const [sequenceAttempt, setSequenceAttempt] = useState(0);
  const [instructionCue, setInstructionCue] = useState<"task" | "start">(
    "task",
  );
  const streamRef = useRef<MediaStream | null>(null);
  const recordingRef = useRef<RecordingResult | null>(null);
  const partnerSequenceStartedRef = useRef(false);
  const recoveryAttemptedRef = useRef(false);
  const mountedRef = useRef(true);

  const loadTask = useCallback(async () => {
    setLoadError(null);
    try {
      setTask(await fetchTask(taskId));
    } catch (error) {
      setLoadError(
        friendlyError(error, "No hemos podido cargar la tarea temporal."),
      );
    }
  }, [taskId]);

  useEffect(() => {
    mountedRef.current = true;
    void fetchTask(taskId)
      .then((loadedTask) => {
        if (mountedRef.current) setTask(loadedTask);
      })
      .catch((error: unknown) => {
        if (mountedRef.current) {
          setLoadError(
            friendlyError(error, "No hemos podido cargar la tarea temporal."),
          );
        }
      });
    return () => {
      mountedRef.current = false;
      stopMicrophone(streamRef.current);
      if (typeof window !== "undefined") window.speechSynthesis?.cancel();
    };
  }, [loadTask, taskId]);

  useEffect(() => {
    if (state.stage !== "processing" || processingStartedAt === null) return;
    const update = () =>
      setProcessingElapsedMs(Date.now() - processingStartedAt);
    update();
    const timer = window.setInterval(update, 1_000);
    return () => window.clearInterval(timer);
  }, [processingStartedAt, state.stage]);

  const preparePartnerTurn = useCallback(
    async (capability: SessionCapability) => {
      if (!withAiPartner) return;
      setPartnerStatus("loading");
      setPartnerError(null);
      try {
        const turn = await fetchAiPartnerTurn(capability);
        if (!mountedRef.current) return;
        setPartnerTurn(turn);
        setPartnerStatus("ready");
      } catch (error) {
        if (!mountedRef.current) return;
        setPartnerStatus("error");
        setPartnerError(
          friendlyError(
            error,
            "El candidato IA no ha podido preparar su turno.",
          ),
        );
      }
    },
    [withAiPartner],
  );

  const begin = async () => {
    if (!task || !consent || isBusy) return;
    if (downloadOnly) {
      // Nothing leaves the browser in download mode: no backend session.
      dispatch({ type: "CONSENT_ACCEPTED" });
      return;
    }
    setIsBusy(true);
    try {
      const capability = await createSession(task.id);
      setSession(capability);
      saveActiveSession(task.id, capability);
      if (withAiPartner) void preparePartnerTurn(capability);
      dispatch({ type: "CONSENT_ACCEPTED" });
    } catch (error) {
      setLoadError(
        friendlyError(error, "No se ha podido crear la sesión privada."),
      );
    } finally {
      setIsBusy(false);
    }
  };

  const checkMicrophone = async () => {
    setIsBusy(true);
    setMicCheckStatus("testing");
    setMicLevel(0);
    setMicSecondsRemaining(Math.ceil(MICROPHONE_TEST_DURATION_MS / 1_000));
    stopMicrophone(streamRef.current);
    streamRef.current = null;
    try {
      const check = await requestAndCheckMicrophone({
        durationMs: MICROPHONE_TEST_DURATION_MS,
        onLevel: (level, remaining) => {
          if (!mountedRef.current) return;
          setMicLevel(level);
          setMicSecondsRemaining(Math.max(0, Math.ceil(remaining / 1_000)));
        },
      });
      if (!mountedRef.current) {
        stopMicrophone(check.stream);
        return;
      }
      streamRef.current = check.stream;
      setMicLevel(check.level);
      setMicCheckStatus(
        check.level >= MINIMUM_MICROPHONE_LEVEL ? "passed" : "too-quiet",
      );
    } catch (error) {
      dispatch({
        type: "FAIL",
        retryKind: "microphone",
        message: friendlyError(error, "No se ha podido preparar el micrófono."),
      });
    } finally {
      setIsBusy(false);
    }
  };

  const confirmMicrophone = () => {
    if (micCheckStatus !== "passed" || !streamRef.current) return;
    dispatch({ type: "MICROPHONE_READY" });
  };

  const playInstructions = (audioPath: string): Promise<void> => {
    const resolvedPath = audioPath.endsWith("examiner-instruction.wav")
      ? "/assets/temporary-part2/examiner-instruction-sonia.mp3"
      : audioPath;
    return playAudioAsset(resolvedPath);
  };

  const pollUntilComplete = useCallback(
    async (activeSession: SessionCapability) => {
      const expiresAt = Date.parse(activeSession.expires_at);
      let consecutiveConnectionErrors = 0;
      setProcessingConnectionIssue(false);

      while (mountedRef.current && Date.now() < expiresAt) {
        try {
          const current = await fetchSessionStatus(activeSession);
          consecutiveConnectionErrors = 0;
          setProcessingConnectionIssue(false);
          setProcessingStage(current.processing_stage);
          setProcessingHeartbeatAt(current.heartbeat_at);
          setProcessingCanRetry(current.can_retry);
          if (current.stage_started_at) {
            const stageStartedAt = Date.parse(current.stage_started_at);
            if (Number.isFinite(stageStartedAt)) {
              setProcessingStartedAt((previous) => previous ?? stageStartedAt);
            }
          }
          if (current.status === "completed") {
            const nextReport = await fetchReport(activeSession);
            setReport(nextReport);
            dispatch({ type: "REPORT_READY" });
            onCompleted?.();
            return;
          }
          if (current.status === "failed") {
            throw new ApiError(
              current.error_message_es ??
                "No hemos podido completar el análisis.",
              422,
            );
          }
        } catch (error) {
          const isFatalClientError =
            error instanceof ApiError &&
            error.status >= 400 &&
            error.status < 500;
          if (isFatalClientError) throw error;
          consecutiveConnectionErrors += 1;
          setProcessingConnectionIssue(true);
          const retryDelay = Math.min(
            12_000,
            POLL_INTERVAL_MS * 2 ** Math.min(consecutiveConnectionErrors, 3),
          );
          await new Promise((resolve) => setTimeout(resolve, retryDelay));
          continue;
        }
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      }
      clearActiveSession();
      throw new Error("La sesión temporal ha caducado antes de finalizar.");
    },
    [onCompleted],
  );

  useEffect(() => {
    if (!task || downloadOnly || recoveryAttemptedRef.current) return;
    recoveryAttemptedRef.current = true;
    const savedSession = loadActiveSession(task.id);
    if (!savedSession) return;

    const recover = async () => {
      try {
        const current = await fetchSessionStatus(savedSession);
        if (!mountedRef.current) return;
        setSession(savedSession);
        setProcessingStage(current.processing_stage);
        setProcessingHeartbeatAt(current.heartbeat_at);
        setProcessingCanRetry(current.can_retry);
        if (current.status === "completed") {
          const savedReport = await fetchReport(savedSession);
          if (!mountedRef.current) return;
          setReport(savedReport);
          dispatch({ type: "RESUME_REPORT" });
          return;
        }
        if (current.status === "uploaded" || current.status === "processing") {
          const startedAt = current.stage_started_at
            ? Date.parse(current.stage_started_at)
            : Date.now();
          setProcessingStartedAt(
            Number.isFinite(startedAt) ? startedAt : Date.now(),
          );
          dispatch({ type: "RESUME_PROCESSING" });
          await pollUntilComplete(savedSession);
          return;
        }
        if (current.status === "failed") {
          dispatch({
            type: "FAIL",
            retryKind: "processing",
            message:
              current.error_message_es ??
              "El análisis anterior no pudo completarse.",
          });
          return;
        }
        clearActiveSession();
      } catch (error) {
        if (!mountedRef.current) return;
        if (
          error instanceof ApiError &&
          [401, 404, 410].includes(error.status)
        ) {
          clearActiveSession();
          return;
        }
        dispatch({
          type: "FAIL",
          retryKind: "processing",
          message: friendlyError(
            error,
            "No hemos podido recuperar el análisis anterior.",
          ),
        });
      }
    };
    void recover();
  }, [downloadOnly, pollUntilComplete, task]);

  const uploadAndProcess = useCallback(async () => {
    const activeSession = session;
    const recording = recordingRef.current;
    if (!activeSession || !recording) {
      dispatch({
        type: "FAIL",
        retryKind: "upload",
        message: "La grabación local ya no está disponible.",
      });
      return;
    }
    let uploadCompleted = false;
    try {
      dispatch({ type: "START_UPLOAD" });
      setUploadProgress(0);
      const extension = extensionForMime(recording.mimeType);
      const [grant, hash] = await Promise.all([
        authorizeUpload(activeSession, recording.mimeType, extension),
        sha256(recording.blob),
      ]);
      await uploadRecording(
        grant,
        recording.blob,
        recording.mimeType,
        setUploadProgress,
      );
      await completeRecording(activeSession, grant, recording, hash);
      uploadCompleted = true;
      setProcessingStartedAt(Date.now());
      setProcessingElapsedMs(0);
      setProcessingHeartbeatAt(null);
      setProcessingConnectionIssue(false);
      dispatch({ type: "START_PROCESSING" });
      await pollUntilComplete(activeSession);
    } catch (error) {
      dispatch({
        type: "FAIL",
        retryKind: uploadCompleted ? "processing" : "upload",
        message: friendlyError(error, "No se ha podido completar la práctica."),
      });
    }
  }, [pollUntilComplete, session]);

  const runPractice = async () => {
    if (!task || !streamRef.current || isBusy) return;
    setIsBusy(true);
    try {
      dispatch({ type: "START_INSTRUCTIONS" });
      setInstructionCue("task");
      await playInstructions(task.examiner_audio_path);
      setInstructionCue("start");
      await playAudioAsset(EXAMINER_START_AUDIO);
      dispatch({ type: "START_RECORDING" });
      const recording = await recordForDuration(
        streamRef.current,
        PRACTICE_DURATION_MS,
        setRemainingMs,
      );
      recordingRef.current = recording;
      stopMicrophone(streamRef.current);
      streamRef.current = null;
      if (downloadOnly) {
        setFinishedRecording(recording);
        dispatch({ type: "SHOW_DOWNLOADS" });
        onCompleted?.();
        return;
      }
      if (withAiPartner) {
        dispatch({ type: "SHOW_PARTNER" });
        return;
      }
      await uploadAndProcess();
    } catch (error) {
      stopMicrophone(streamRef.current);
      streamRef.current = null;
      dispatch({
        type: "FAIL",
        retryKind: "microphone",
        message: friendlyError(
          error,
          "La práctica se ha interrumpido antes de guardar el audio.",
        ),
      });
    } finally {
      setIsBusy(false);
    }
  };

  const playPartnerTurn = () => {
    if (!partnerTurn || typeof window === "undefined") return;
    const synth = window.speechSynthesis;
    if (!synth || typeof SpeechSynthesisUtterance === "undefined") {
      setPartnerError(
        "Este navegador no ofrece una voz inglesa. La respuesta sigue disponible por escrito.",
      );
      return;
    }
    const voices = synth.getVoices();
    const preferredNames = ["Ryan", "Libby", "George", "Sonia"];
    const british = voices.filter((voice) =>
      voice.lang.toLowerCase().startsWith("en-gb"),
    );
    const selected =
      preferredNames
        .map((name) => british.find((voice) => voice.name.includes(name)))
        .find(Boolean) ??
      british[0] ??
      voices.find((voice) => voice.lang.toLowerCase().startsWith("en"));
    const utterance = new SpeechSynthesisUtterance(partnerTurn.spoken_text);
    if (selected) utterance.voice = selected;
    utterance.lang = selected?.lang ?? "en-GB";
    utterance.rate = 0.96;
    utterance.pitch = 0.98;
    utterance.onend = () => setPartnerSpeaking(false);
    utterance.onerror = () => {
      setPartnerSpeaking(false);
      setPartnerError(
        "La voz del navegador ha fallado; puedes leer la intervenci\u00f3n y continuar.",
      );
    };
    synth.cancel();
    setPartnerVoice(selected?.name ?? "Voz inglesa del navegador");
    setPartnerSpeaking(true);
    synth.speak(utterance);
  };

  const continueAfterPartner = useCallback(async () => {
    if (typeof window !== "undefined") window.speechSynthesis?.cancel();
    setPartnerSpeaking(false);
    await uploadAndProcess();
  }, [uploadAndProcess]);

  useEffect(() => {
    if (
      state.stage !== "partner" ||
      partnerStatus !== "ready" ||
      !partnerTurn ||
      partnerSequenceStartedRef.current
    ) {
      return;
    }
    partnerSequenceStartedRef.current = true;
    let cancelled = false;
    const runSequence = async () => {
      try {
        window.speechSynthesis?.cancel();
        setSequenceError(null);
        setPartnerSequence("examiner");
        await playAudioAsset(examinerFollowUpAudioPath(practiceLabel));
        if (cancelled) return;
        setExaminerVoice("Sonia · audio pregrabado");
        setPartnerSequence("candidate");
        const candidate = await speakTurn(partnerTurn.spoken_text, "candidate");
        if (cancelled) return;
        setPartnerVoice(candidate.voiceName);
        await continueAfterPartner();
      } catch (error) {
        if (cancelled) return;
        setPartnerSequence("failed");
        setSequenceError(
          friendlyError(
            error,
            "No se ha podido reproducir la transiciÃ³n automÃ¡tica.",
          ),
        );
      }
    };
    void runSequence();
    return () => {
      cancelled = true;
      window.speechSynthesis?.cancel();
    };
  }, [
    continueAfterPartner,
    partnerStatus,
    partnerTurn,
    practiceLabel,
    sequenceAttempt,
    state.stage,
  ]);

  const retryPartnerSequence = () => {
    if (typeof window !== "undefined") window.speechSynthesis?.cancel();
    partnerSequenceStartedRef.current = false;
    setSequenceError(null);
    setPartnerSequence("idle");
    setSequenceAttempt((current) => current + 1);
  };

  const retry = async () => {
    dispatch({ type: "RETRY" });
    if (state.retryKind === "microphone") {
      setMicCheckStatus("idle");
      setMicLevel(0);
      await checkMicrophone();
      return;
    }
    if (state.retryKind === "upload") {
      await uploadAndProcess();
      return;
    }
    if (!session) return;
    if (!processingCanRetry) return;
    try {
      await retrySession(session);
      dispatch({ type: "START_PROCESSING" });
      await pollUntilComplete(session);
    } catch (error) {
      dispatch({
        type: "FAIL",
        retryKind: "processing",
        message: friendlyError(
          error,
          "El análisis sigue sin estar disponible.",
        ),
      });
    }
  };

  const newAttempt = async () => {
    if (session) {
      try {
        await deleteSession(session);
      } catch {
        // Expiry cleanup remains a server-side safety net if deletion cannot finish.
      }
    }
    stopMicrophone(streamRef.current);
    streamRef.current = null;
    recordingRef.current = null;
    clearActiveSession();
    setProcessingCanRetry(false);
    setProcessingStartedAt(null);
    setProcessingElapsedMs(0);
    setProcessingHeartbeatAt(null);
    setProcessingConnectionIssue(false);
    setSession(null);
    setReport(null);
    setConsent(false);
    setMicLevel(0);
    setMicCheckStatus("idle");
    setMicSecondsRemaining(Math.ceil(MICROPHONE_TEST_DURATION_MS / 1_000));
    setRemainingMs(PRACTICE_DURATION_MS);
    setUploadProgress(0);
    setProcessingStage("queued");
    setPartnerTurn(null);
    setPartnerStatus("idle");
    setPartnerError(null);
    setPartnerVoice(null);
    setExaminerVoice(null);
    setPartnerSpeaking(false);
    setPartnerSequence("idle");
    setSequenceError(null);
    setSequenceAttempt(0);
    setInstructionCue("task");
    partnerSequenceStartedRef.current = false;
    dispatch({ type: "RESET" });
  };

  const exitPractice = async () => {
    if (session) {
      try {
        await deleteSession(session);
      } catch {
        // Server expiry remains the fallback if the local cleanup cannot finish.
      }
    }
    stopMicrophone(streamRef.current);
    streamRef.current = null;
    clearActiveSession();
    if (typeof window !== "undefined") window.speechSynthesis?.cancel();
    onExit?.();
  };

  if (report && state.stage === "report")
    return (
      <ReportView
        report={report}
        onNewAttempt={newAttempt}
        onExit={onExit ? () => void exitPractice() : undefined}
      />
    );

  const seconds = Math.ceil(remainingMs / 1_000);
  const currentErrorCanRetry =
    state.retryKind !== "processing" || processingCanRetry;
  const progress = Math.max(
    0,
    Math.min(1, 1 - remainingMs / PRACTICE_DURATION_MS),
  );

  return (
    <main className="practice-shell">
      <header className="site-header">
        {onExit ? (
          <button
            type="button"
            className="practice-back"
            onClick={() => void exitPractice()}
          >
            ← Cambiar práctica
          </button>
        ) : (
          <a href="#main" className="brand">
            B2 Speaking <em>Room</em>
          </a>
        )}
        <div className="header-meta">
          <span>{modeLabel}</span>
          <span className="header-part">Part 2 · {practiceLabel}</span>
        </div>
      </header>

      <div className="part-marker" aria-hidden="true">
        02
      </div>
      <section id="main" className="practice-content">
        {state.stage === "intro" && (
          <Intro
            task={task}
            loadError={loadError}
            consent={consent}
            setConsent={setConsent}
            begin={begin}
            retryLoad={loadTask}
            isBusy={isBusy}
            withAiPartner={withAiPartner}
            downloadOnly={downloadOnly}
          />
        )}

        {state.stage === "microphone" && (
          <StageFrame
            step="01 / Preparación"
            title="Primero, tu voz."
            aside={
              micCheckStatus === "testing"
                ? `Escuchando · ${micSecondsRemaining} s`
                : micCheckStatus === "passed"
                  ? "Micrófono listo"
                  : micCheckStatus === "too-quiet"
                    ? "Señal insuficiente"
                    : "Chrome o Edge · ordenador"
            }
          >
            <p className="lead">
              Tendrás cinco segundos para hablar a volumen normal. Verás la
              señal en directo y esta pantalla no avanzará hasta que tú lo
              confirmes.
            </p>
            <div
              className={`mic-test-visual mic-test-${micCheckStatus}`}
              role="meter"
              aria-label="Nivel de entrada del micrófono"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.round(micLevel * 100)}
            >
              {Array.from({ length: 18 }, (_, index) => (
                <i
                  key={index}
                  style={{
                    height: `${18 + ((index * 17) % 54)}%`,
                    opacity:
                      micLevel >= (index + 1) / 18
                        ? 1
                        : micCheckStatus === "testing"
                          ? 0.2
                          : 0.12,
                  }}
                />
              ))}
            </div>
            <div
              className={`mic-check-result mic-check-result-${micCheckStatus}`}
              role="status"
              aria-live="polite"
            >
              <strong>
                {micCheckStatus === "testing"
                  ? "Habla ahora…"
                  : micCheckStatus === "passed"
                    ? "Se oye bien."
                    : micCheckStatus === "too-quiet"
                      ? "No te hemos oído con claridad."
                      : "Cuando quieras, inicia la comprobación."}
              </strong>
              <span>
                {micCheckStatus === "testing"
                  ? "Di una frase completa y observa cómo se mueve el nivel."
                  : micCheckStatus === "passed"
                    ? `Señal detectada · ${Math.max(1, Math.round(micLevel * 4))}/4. Puedes repetirla o continuar.`
                    : micCheckStatus === "too-quiet"
                      ? "Acércate al micrófono, comprueba la entrada seleccionada y repite la prueba."
                      : "El sonido solo se utiliza para esta prueba; todavía no guardamos tu respuesta."}
              </span>
            </div>
            <div className="button-row mic-check-actions">
              <button
                className={`button ${micCheckStatus === "passed" ? "button-quiet" : "button-primary"}`}
                onClick={checkMicrophone}
                disabled={isBusy}
              >
                {isBusy
                  ? `Escuchando… ${micSecondsRemaining} s`
                  : micCheckStatus === "idle"
                    ? "Probar micrófono"
                    : "Repetir prueba"}
              </button>
              {micCheckStatus === "passed" && (
                <button
                  className="button button-primary"
                  onClick={confirmMicrophone}
                  disabled={isBusy}
                >
                  Continuar a las fotografías
                </button>
              )}
            </div>
          </StageFrame>
        )}

        {state.stage === "ready" && task && (
          <StageFrame
            step="02 / Tarea"
            title="Mira, compara, responde."
            aside={`Señal del micrófono · ${Math.max(1, Math.round(micLevel * 4))}/4`}
          >
            <p className="lead">
              Escucharás la tarea y después «Your time starts now». La grabación
              comenzará al terminar esa frase y se detendrá sola al cumplirse un
              minuto.
            </p>
            <TaskBoard
              task={task}
              practiceLabel={practiceLabel}
              followUpQuestion={followUpQuestion}
            />
            <button
              className="button button-primary"
              onClick={runPractice}
              disabled={isBusy}
            >
              Escuchar y empezar
            </button>
          </StageFrame>
        )}

        {state.stage === "instructions" && task && (
          <StageFrame
            step="03 / Instrucciones"
            title={
              instructionCue === "task"
                ? "Escucha la tarea."
                : "Prepárate: empieza tu minuto."
            }
            aside="La grabación aún no ha empezado"
          >
            <TaskBoard
              task={task}
              practiceLabel={practiceLabel}
              followUpQuestion={followUpQuestion}
              compact
            />
            <div className="listening-line">
              <span />
              {instructionCue === "task"
                ? "El examinador está presentando la tarea…"
                : "Tu tiempo comienza al terminar esta frase…"}
            </div>
          </StageFrame>
        )}

        {state.stage === "recording" && task && (
          <StageFrame step="04 / Tu turno" title="Speak now." aside="Grabando">
            <TaskBoard
              task={task}
              practiceLabel={practiceLabel}
              followUpQuestion={followUpQuestion}
              compact
            />
            {showTimer ? (
              <div className="timer-row">
                <div className="timer" aria-live="polite">
                  <span>{seconds}</span>
                  <small>segundos</small>
                </div>
                <div className="timer-track" aria-hidden="true">
                  <span style={{ transform: `scaleX(${progress})` }} />
                </div>
                <p>No necesitas pulsar nada. La grabación se detendrá sola.</p>
              </div>
            ) : (
              <div className="timer-hidden-state" role="status">
                <span aria-hidden="true" />
                <div>
                  <strong>Grabando tu respuesta</strong>
                  <p>
                    Modo examen: el contador está oculto. Te avisaremos al
                    terminar el minuto.
                  </p>
                </div>
              </div>
            )}
          </StageFrame>
        )}

        {state.stage === "partner" && (
          <StageFrame
            step="05 / Candidato B"
            title={
              partnerSequence === "examiner"
                ? "El examinador cierra tu minuto."
                : partnerSequence === "candidate"
                  ? "Candidate B responde."
                  : "Preparando el siguiente turno."
            }
            aside={"Autom\u00e1tico \u00b7 no pulses nada"}
          >
            <div className="partner-turn-card" aria-live="polite">
              <div className="partner-turn-heading">
                <div>
                  <p className="eyebrow">Pregunta breve</p>
                  <h2>{followUpQuestion ?? partnerTurn?.follow_up_question}</h2>
                </div>
                <span>{"8\u201312 s"}</span>
              </div>
              {partnerStatus === "loading" && (
                <div className="partner-loading">
                  <span aria-hidden="true" />
                  {"Preparando una respuesta B2 breve\u2026"}
                </div>
              )}
              {partnerTurn && partnerSequence !== "idle" && (
                <div className="spoken-sequence">
                  <article
                    className={
                      partnerSequence === "examiner" ? "is-speaking" : ""
                    }
                  >
                    <div>
                      <strong>Examiner</strong>
                      {examinerVoice && <small>{examinerVoice}</small>}
                    </div>
                    <p>
                      {examinerFollowUpText(partnerTurn.follow_up_question)}
                    </p>
                  </article>
                  <article
                    className={
                      partnerSequence === "candidate" ? "is-speaking" : ""
                    }
                  >
                    <div>
                      <strong>Candidate B</strong>
                      {partnerVoice && <small>{partnerVoice}</small>}
                    </div>
                    <p>
                      {partnerSequence === "candidate" ||
                      partnerSequence === "failed"
                        ? partnerTurn.spoken_text
                        : "Waiting for the examiner..."}
                    </p>
                  </article>
                </div>
              )}
              {partnerTurn &&
                (partnerSequence === "candidate" ||
                  partnerSequence === "failed") && (
                  <>
                    <p className="partner-disclaimer">
                      {partnerTurn.disclaimer_es}
                    </p>
                    {partnerSequence === "failed" && (
                      <div className="partner-actions">
                        <button
                          className="button button-quiet"
                          type="button"
                          onClick={playPartnerTurn}
                          disabled={partnerSpeaking}
                        >
                          {partnerSpeaking
                            ? "Reproduciendo\u2026"
                            : "Escuchar solo Candidate B"}
                        </button>
                      </div>
                    )}
                  </>
                )}
              {partnerStatus === "error" && (
                <div className="inline-error partner-error">
                  <p>{partnerError}</p>
                  <button
                    type="button"
                    onClick={() => session && void preparePartnerTurn(session)}
                  >
                    Reintentar candidato IA
                  </button>
                </div>
              )}
              {partnerStatus === "ready" && partnerError && (
                <p className="partner-voice-warning">{partnerError}</p>
              )}
              {partnerSequence === "failed" && (
                <div className="inline-error partner-error">
                  <p>{sequenceError}</p>
                  <button type="button" onClick={retryPartnerSequence}>
                    Reintentar secuencia de voz
                  </button>
                </div>
              )}
            </div>
            {(partnerStatus === "error" || partnerSequence === "failed") && (
              <button
                className="button button-primary"
                type="button"
                onClick={() => void continueAfterPartner()}
                disabled={isBusy}
              >
                Continuar al anÃ¡lisis sin audio
              </button>
            )}
          </StageFrame>
        )}

        {state.stage === "downloads" && task && finishedRecording && (
          <DownloadsStage
            task={task}
            practiceLabel={practiceLabel}
            recording={finishedRecording}
            followUpQuestion={followUpQuestion}
            onRepeat={() => {
              recordingRef.current = null;
              setFinishedRecording(null);
              dispatch({ type: "RESET" });
            }}
            onExit={onExit}
          />
        )}

        {state.stage === "uploading" && (
          <ProgressStage
            number="05"
            eyebrow="Guardando"
            title="Tu audio viaja cifrado."
            detail="La grabación solo se conserva mientras se genera este informe temporal."
            progress={uploadProgress}
            label={`${uploadProgress}% subido`}
          />
        )}

        {state.stage === "processing" && (
          <AnalysisProgress
            stage={processingStage}
            elapsedMs={processingElapsedMs}
            heartbeatAt={processingHeartbeatAt}
            connectionIssue={processingConnectionIssue}
            evaluationAvailable={task?.evaluation_available ?? true}
          />
        )}

        {state.stage === "error" && (
          <StageFrame
            step={
              currentErrorCanRetry ? "Pausa recuperable" : "Análisis detenido"
            }
            title={
              currentErrorCanRetry
                ? "Nada se ha perdido."
                : "No vamos a repetir el mismo error."
            }
            aside={
              currentErrorCanRetry
                ? "Puedes continuar"
                : "Nuevo intento necesario"
            }
          >
            <p className="lead">{state.errorMessage}</p>
            {state.retryKind === "upload" && (
              <p className="recovery-note">
                La grabación sigue en este navegador; no tienes que repetir el
                minuto.
              </p>
            )}
            <div className="button-row">
              {currentErrorCanRetry && (
                <button className="button button-primary" onClick={retry}>
                  Reintentar
                </button>
              )}
              <button className="button button-quiet" onClick={newAttempt}>
                Empezar de nuevo
              </button>
            </div>
          </StageFrame>
        )}
      </section>

      <footer className="site-footer">
        <span>Práctica formativa · no oficial</span>
        <span>Sin cuenta · datos temporales</span>
      </footer>
    </main>
  );
}

function Intro({
  task,
  loadError,
  consent,
  setConsent,
  begin,
  retryLoad,
  isBusy,
  withAiPartner,
  downloadOnly = false,
}: {
  task: Task | null;
  loadError: string | null;
  consent: boolean;
  setConsent: (value: boolean) => void;
  begin: () => void;
  retryLoad: () => Promise<void>;
  isBusy: boolean;
  withAiPartner: boolean;
  downloadOnly?: boolean;
}) {
  return (
    <div className="intro-layout">
      <div className="intro-copy">
        <p className="eyebrow">Práctica individual · Cambridge-inspired</p>
        <h1>
          Un minuto.
          <br />
          <em>Dos fotografías.</em>
          <br />
          Tu voz.
        </h1>
        <p className="lead">
          {downloadOnly
            ? "Practica el turno largo con tiempos reales. Aquí no evalúa la IA: al terminar descargas tu audio y las fotos para revisarlos donde quieras."
            : task?.evaluation_available
              ? "Practica el turno largo de B2 First Speaking Part 2 con tiempos reales y feedback basado en evidencia."
              : "Practica el turno largo de B2 First Speaking Part 2 con tiempos reales. Este entorno está en modo demo y no evaluará tu respuesta."}
        </p>
      </div>
      <aside className="start-panel">
        <p className="panel-index">Antes de empezar</p>
        <ol>
          <li>
            <span>01</span> Comprueba el micrófono
          </li>
          <li>
            <span>02</span> Escucha la instrucción
          </li>
          <li>
            <span>03</span> Habla durante un minuto
          </li>
          <li>
            <span>04</span>{" "}
            {downloadOnly
              ? "Descarga tu audio y las fotos"
              : withAiPartner
                ? "Escucha al examinador y la respuesta de Candidate B"
                : "Revisa tu informe"}
          </li>
          {withAiPartner && (
            <li>
              <span>05</span> Revisa tu informe
            </li>
          )}
        </ol>
        <label className="consent-check">
          <input
            type="checkbox"
            checked={consent}
            onChange={(event) => setConsent(event.target.checked)}
          />
          <span>
            {downloadOnly
              ? "Acepto grabar mi voz. En este modo la grabación no se sube: queda solo en este navegador."
              : "Acepto que se grabe mi voz temporalmente para generar este informe."}
          </span>
        </label>
        {task?.content_notice && (
          <p className="content-notice">{task.content_notice}</p>
        )}
        {task && !task.evaluation_available && !downloadOnly && (
          <p className="content-notice">
            MODO DEMO — SIN EVALUACIÓN: se probará la grabación y el flujo, pero
            no se generará feedback sobre tu inglés.
          </p>
        )}
        {loadError && (
          <div className="inline-error">
            <p>{loadError}</p>
            <button onClick={() => void retryLoad()}>Volver a cargar</button>
          </div>
        )}
        <button
          className="button button-primary button-wide"
          onClick={begin}
          disabled={!task || !consent || isBusy}
        >
          {isBusy ? "Preparando…" : "Preparar mi práctica"}
        </button>
        <p className="browser-note">
          Diseñado para Chrome y Edge en ordenador.
        </p>
      </aside>
    </div>
  );
}

export function StageFrame({
  step,
  title,
  aside,
  children,
}: {
  step: string;
  title: string;
  aside: string;
  children: React.ReactNode;
}) {
  return (
    <section className="stage-frame">
      <div className="stage-heading">
        <div>
          <p className="eyebrow">{step}</p>
          <h1>{title}</h1>
        </div>
        <p className="stage-aside">{aside}</p>
      </div>
      {children}
    </section>
  );
}

function TaskBoard({
  task,
  practiceLabel,
  followUpQuestion,
  compact = false,
}: {
  task: Task;
  practiceLabel: string;
  followUpQuestion?: string;
  compact?: boolean;
}) {
  const practiceNumber = practiceLabel.match(/\d+/)?.[0] ?? "01";
  return (
    <div className={`task-board${compact ? " compact" : ""}`}>
      <div className="task-sheet-brand">
        <strong>B2 First</strong>
        <span>Speaking · Part 2</span>
      </div>
      <div className="task-sheet-topline">
        <div className="task-question">
          <strong>{task.question}</strong>
        </div>
        <span className="task-sheet-number">{practiceNumber}</span>
      </div>
      <div className="task-sheet-photos">
        <figure>
          <Image
            src={task.image_one_path}
            width={1200}
            height={760}
            sizes="(max-width: 720px) 46vw, 44vw"
            alt="Primera fotografía de la tarea de comparación."
            priority
          />
        </figure>
        <figure>
          <Image
            src={task.image_two_path}
            width={1200}
            height={760}
            sizes="(max-width: 720px) 46vw, 44vw"
            alt="Segunda fotografía de la tarea de comparación."
            priority
          />
        </figure>
      </div>
      <div className="task-sheet-divider" aria-hidden="true" />
      {followUpQuestion && (
        <div className="task-sheet-follow-up">
          <strong>Candidate B</strong>
          <span>— {followUpQuestion}</span>
        </div>
      )}
      <p className="task-sheet-footnote">
        Material de práctica interna · evaluación no oficial
      </p>
    </div>
  );
}

export function ProgressStage({
  number,
  eyebrow,
  title,
  detail,
  progress,
  label,
}: {
  number: string;
  eyebrow: string;
  title: string;
  detail: string;
  progress?: number;
  label: string;
}) {
  return (
    <section className="progress-stage">
      <p className="progress-number">{number}</p>
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="lead">{detail}</p>
        <div
          className={`processing-rule${progress === undefined ? " indeterminate" : ""}`}
        >
          <span
            style={
              progress === undefined
                ? undefined
                : { transform: `scaleX(${progress / 100})` }
            }
          />
        </div>
        <p className="processing-label" aria-live="polite">
          {label}
        </p>
      </div>
    </section>
  );
}

const ANALYSIS_STAGES = [
  {
    key: "validating_audio",
    label: "Comprobación del audio",
    detail: "Duración, formato y calidad mínima",
  },
  {
    key: "transcribing",
    label: "Transcripción",
    detail: "Tus palabras y sus marcas de tiempo",
  },
  {
    key: "evaluating",
    label: "Análisis lingüístico",
    detail: "Evidencias, tarea y pronunciación",
  },
  {
    key: "reviewing",
    label: "Segunda revisión",
    detail: "Contraste independiente de observaciones",
  },
  {
    key: "building_report",
    label: "Informe",
    detail: "Solo conservamos conclusiones justificadas",
  },
] as const;

function normalizedAnalysisStage(stage: string): string {
  const aliases: Record<string, string> = {
    pending: "validating_audio",
    queued: "validating_audio",
    uploaded: "validating_audio",
    processing: "transcribing",
    running: "transcribing",
    completed: "building_report",
  };
  return aliases[stage] ?? stage;
}

function formatElapsed(milliseconds: number): string {
  const totalSeconds = Math.max(0, Math.floor(milliseconds / 1_000));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

export function AnalysisProgress({
  stage,
  elapsedMs,
  heartbeatAt,
  connectionIssue,
  evaluationAvailable,
}: {
  stage: string;
  elapsedMs: number;
  heartbeatAt: string | null;
  connectionIssue: boolean;
  evaluationAvailable: boolean;
}) {
  const normalizedStage = normalizedAnalysisStage(stage);
  const activeIndex = Math.max(
    0,
    ANALYSIS_STAGES.findIndex((item) => item.key === normalizedStage),
  );
  const workerActive = heartbeatAt !== null;
  const takingLonger = elapsedMs >= 120_000;

  return (
    <section className="analysis-progress">
      <header>
        <div>
          <p className="eyebrow">06 / Análisis</p>
          <h1>Buscando evidencia, no una nota rápida.</h1>
        </div>
        <div className="analysis-elapsed" aria-label="Tiempo de análisis">
          <span>{formatElapsed(elapsedMs)}</span>
          <small>transcurrido</small>
        </div>
      </header>
      <p className="lead">
        {evaluationAvailable
          ? "Transcribimos primero, revisamos el contenido dos veces y solo mostramos observaciones respaldadas por tus propias palabras."
          : "Este entorno está en modo demostración y no generará una evaluación de tu inglés."}
      </p>
      <ol className="analysis-steps" aria-live="polite">
        {ANALYSIS_STAGES.map((item, index) => {
          const state =
            index < activeIndex
              ? "complete"
              : index === activeIndex
                ? "active"
                : "waiting";
          return (
            <li key={item.key} className={`analysis-step is-${state}`}>
              <span className="analysis-step-mark" aria-hidden="true">
                {state === "complete" ? "✓" : index + 1}
              </span>
              <div>
                <strong>{item.label}</strong>
                <small>{item.detail}</small>
              </div>
              {state === "active" && <em>En curso</em>}
            </li>
          );
        })}
      </ol>
      <div
        className={`analysis-status${connectionIssue ? " has-connection-issue" : ""}`}
        role="status"
      >
        <span aria-hidden="true" />
        <p>
          {connectionIssue
            ? "La conexión se ha interrumpido. Reintentamos automáticamente; el audio sigue guardado."
            : workerActive
              ? "El analizador sigue activo. Puedes dejar esta pestaña abierta."
              : "Esperando la siguiente actualización del analizador…"}
          {takingLonger && !connectionIssue && (
            <small>
              Está tardando más de dos minutos, pero no lo hemos cancelado ni
              has perdido la grabación.
            </small>
          )}
        </p>
      </div>
    </section>
  );
}

function buildExternalReviewPrompt(
  task: Task,
  followUpQuestion?: string,
): string {
  const followUp = followUpQuestion
    ? `\nFollow-up question asked to Candidate B: "${followUpQuestion}"`
    : "";
  return [
    "You are an experienced Cambridge B2 First (FCE) speaking examiner.",
    "I am attaching my 1-minute audio answer for Speaking Part 2 (long turn) and the two photographs of the task.",
    "",
    `Task instruction read by the examiner: "${task.question}"${followUp}`,
    "",
    "Please:",
    "1. Transcribe my answer briefly.",
    "2. Evaluate it with the official B2 First analytic scales (Grammar and Vocabulary, Discourse Management, Pronunciation) from 0 to 5, judging against B2 level, not native perfection. Errors that do not impede communication are expected at B2.",
    "3. Check the task: did I compare both photos (not just describe them), answer the question, speculate, and use the full minute?",
    "4. Quote my exact words as evidence for every observation.",
    "5. Give me two priority improvements with corrected example sentences.",
  ].join("\n");
}

function DownloadsStage({
  task,
  practiceLabel,
  recording,
  followUpQuestion,
  onRepeat,
  onExit,
}: {
  task: Task;
  practiceLabel: string;
  recording: RecordingResult;
  followUpQuestion?: string;
  onRepeat: () => void;
  onExit?: () => void;
}) {
  const [copied, setCopied] = useState(false);
  const practiceNumber = practiceLabel.match(/\d+/)?.[0] ?? "01";
  const extension = extensionForMime(recording.mimeType);
  const prompt = buildExternalReviewPrompt(task, followUpQuestion);
  const audioUrl = useMemo(
    () => URL.createObjectURL(recording.blob),
    [recording],
  );

  useEffect(() => {
    return () => URL.revokeObjectURL(audioUrl);
  }, [audioUrl]);

  const copyPrompt = async () => {
    try {
      await navigator.clipboard.writeText(prompt);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2_500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <StageFrame
      step="04 / Descargas"
      title="Tu grabación está lista para revisarla donde quieras."
      aside="Nada se ha subido · todo queda en tu navegador"
    >
      <div className="downloads-card">
        <p className="eyebrow">Escucha tu respuesta</p>
        {audioUrl && (
          <audio controls preload="metadata" src={audioUrl}>
            Tu navegador no permite reproducir esta grabación.
          </audio>
        )}
        <div className="downloads-grid">
          {audioUrl && (
            <a
              className="button button-primary"
              href={audioUrl}
              download={`b2-part2-practica-${practiceNumber}.${extension}`}
            >
              Descargar audio
            </a>
          )}
          <a
            className="button button-quiet"
            href={task.image_one_path}
            download={`b2-part2-practica-${practiceNumber}-foto-1.jpg`}
          >
            Descargar foto 1
          </a>
          <a
            className="button button-quiet"
            href={task.image_two_path}
            download={`b2-part2-practica-${practiceNumber}-foto-2.jpg`}
          >
            Descargar foto 2
          </a>
        </div>
        <div className="downloads-prompt">
          <div className="downloads-prompt-heading">
            <p className="eyebrow">Prompt para otra IA</p>
            <button
              className="button button-quiet"
              type="button"
              onClick={copyPrompt}
            >
              {copied ? "Copiado ✓" : "Copiar prompt"}
            </button>
          </div>
          <p className="downloads-help">
            Pega este texto en la IA que prefieras y adjunta el audio y las dos
            fotos descargadas.
          </p>
          <textarea readOnly value={prompt} rows={10} />
        </div>
        <div className="button-row">
          {onExit && (
            <button
              className="button button-quiet"
              type="button"
              onClick={onExit}
            >
              Volver al menú
            </button>
          )}
          <button
            className="button button-primary"
            type="button"
            onClick={onRepeat}
          >
            Repetir práctica
          </button>
        </div>
      </div>
    </StageFrame>
  );
}
