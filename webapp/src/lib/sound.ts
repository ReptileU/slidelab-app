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

/** Хруст ломающейся карты: короткий шум + глухой удар. */
export function playCrack(): void {
  const c = context();
  if (!c) return;
  try {
    if (c.state === "suspended") void c.resume();
    const now = c.currentTime + 0.01;
    const len = Math.floor(c.sampleRate * 0.25);
    const buf = c.createBuffer(1, len, c.sampleRate);
    const data = buf.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 3);
    const noise = c.createBufferSource();
    noise.buffer = buf;
    const hp = c.createBiquadFilter();
    hp.type = "highpass";
    hp.frequency.value = 1800;
    const ng = c.createGain();
    ng.gain.value = 0.35;
    noise.connect(hp).connect(ng).connect(c.destination);
    noise.start(now);
    const osc = c.createOscillator();
    const og = c.createGain();
    osc.type = "triangle";
    osc.frequency.setValueAtTime(160, now);
    osc.frequency.exponentialRampToValueAtTime(55, now + 0.25);
    og.gain.setValueAtTime(0.3, now);
    og.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
    osc.connect(og).connect(c.destination);
    osc.start(now);
    osc.stop(now + 0.32);
  } catch {
    /* без звука — не страшно */
  }
}

/** Короткий «тук» по пакету; чем ближе к открытию, тем выше тон. */
export function playTap(step: number): void {
  const c = context();
  if (!c) return;
  try {
    if (c.state === "suspended") void c.resume();
    const now = c.currentTime + 0.01;
    const osc = c.createOscillator();
    const gain = c.createGain();
    osc.type = "triangle";
    osc.frequency.setValueAtTime(320 + step * 140, now);
    osc.frequency.exponentialRampToValueAtTime(160 + step * 70, now + 0.12);
    gain.gain.setValueAtTime(0.2, now);
    gain.gain.exponentialRampToValueAtTime(0.0008, now + 0.16);
    osc.connect(gain).connect(c.destination);
    osc.start(now);
    osc.stop(now + 0.18);
  } catch {
    /* без звука — не страшно */
  }
}

/** Пакет открылся: восходящий аккорд, для крупного приза — длиннее и ярче. */
export function playReveal(big: boolean): void {
  const c = context();
  if (!c) return;
  try {
    if (c.state === "suspended") void c.resume();
    const now = c.currentTime + 0.02;
    const notes = big ? [523.25, 659.25, 783.99, 1046.5, 1318.5] : [659.25, 783.99, 1046.5];
    notes.forEach((freq, i) => {
      const at = i * 0.085;
      const osc = c.createOscillator();
      const gain = c.createGain();
      osc.type = "sine";
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0, now + at);
      gain.gain.linearRampToValueAtTime(0.18, now + at + 0.015);
      gain.gain.exponentialRampToValueAtTime(0.0008, now + at + (big ? 1.1 : 0.7));
      osc.connect(gain).connect(c.destination);
      osc.start(now + at);
      osc.stop(now + at + (big ? 1.2 : 0.8));
    });
  } catch {
    /* без звука — не страшно */
  }
}
