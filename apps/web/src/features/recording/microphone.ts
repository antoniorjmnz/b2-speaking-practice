export type MicrophoneCheck = {
  stream: MediaStream;
  level: number;
};

export type MicrophoneCheckOptions = {
  durationMs?: number;
  onLevel?: (level: number, remainingMs: number) => void;
};

export async function requestAndCheckMicrophone(
  options: MicrophoneCheckOptions = {},
): Promise<MicrophoneCheck> {
  if (
    !navigator.mediaDevices?.getUserMedia ||
    typeof MediaRecorder === "undefined"
  ) {
    throw new Error(
      "Este navegador no ofrece la grabación necesaria para la práctica.",
    );
  }

  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
    video: false,
  });

  let context: AudioContext | null = null;
  let source: MediaStreamAudioSourceNode | null = null;
  try {
    context = new AudioContext();
    if (context.state === "suspended") await context.resume();
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    source = context.createMediaStreamSource(stream);
    source.connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    let peak = 0;
    const durationMs = Math.max(500, options.durationMs ?? 5_000);
    const end = performance.now() + durationMs;
    while (performance.now() < end) {
      analyser.getByteTimeDomainData(samples);
      const rms = Math.sqrt(
        samples.reduce((sum, value) => sum + ((value - 128) / 128) ** 2, 0) /
          samples.length,
      );
      const level = Math.min(1, rms * 8);
      peak = Math.max(peak, level);
      options.onLevel?.(level, Math.max(0, end - performance.now()));
      await new Promise((resolve) => setTimeout(resolve, 60));
    }
    options.onLevel?.(peak, 0);
    return { stream, level: peak };
  } catch (error) {
    stopMicrophone(stream);
    throw new Error(
      "El navegador ha dado acceso al micrófono, pero no hemos podido medir su señal. Recarga la página y vuelve a probar.",
      { cause: error },
    );
  } finally {
    source?.disconnect();
    if (context && context.state !== "closed") {
      await context.close().catch(() => undefined);
    }
  }
}

export function stopMicrophone(stream: MediaStream | null): void {
  stream?.getTracks().forEach((track) => track.stop());
}
