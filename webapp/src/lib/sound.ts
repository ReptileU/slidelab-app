// Короткий «звон» об оплате — синтезируем сами (WebAudio), без файлов.
// iOS разрешает звук только после касания: unlockAudio() вызываем на первом касании экрана.

type Ctx = AudioContext;
let ctx: Ctx | null = null;

function context(): Ctx | null {
  try {
    if (!ctx) {
      const C = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
      if (!C) return null;
      ctx = new C();
    }
    return ctx;
  } catch {
    return null;
  }
}

export function unlockAudio(): void {
  const c = context();
  if (!c) return;
  try {
    if (c.state === "suspended") void c.resume();
    // беззвучный буфер «разогревает» вывод на iOS
    const b = c.createBuffer(1, 1, 22050);
    const s = c.createBufferSource();
    s.buffer = b;
    s.connect(c.destination);
    s.start(0);
  } catch {
    /* без звука — не страшно */
  }
}

/** Два мягких тона вверх, как подтверждение оплаты. */
export function playPaid(): void {
  const c = context();
  if (!c) return;
  try {
    if (c.state === "suspended") void c.resume();
    const now = c.currentTime + 0.02;
    const notes: [number, number][] = [
      [1174.66, 0], // D6
      [1567.98, 0.11], // G6
    ];
    for (const [freq, at] of notes) {
      const osc = c.createOscillator();
      const gain = c.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0, now + at);
      gain.gain.linearRampToValueAtTime(0.22, now + at + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.0008, now + at + 0.55);
      osc.connect(gain).connect(c.destination);
      osc.start(now + at);
      osc.stop(now + at + 0.6);
    }
  } catch {
    /* без звука — не страшно */
  }
}
