/** «2 презентации», «10 презентаций» — подпись под крупной цифрой. */
export function presWord(lang: string, n: number): string {
  if (lang === "uz") return "taqdimot";
  if (lang === "en") return n === 1 ? "presentation" : "presentations";
  const d = n % 10;
  const dd = n % 100;
  if (d === 1 && dd !== 11) return "презентация";
  if (d >= 2 && d <= 4 && (dd < 12 || dd > 14)) return "презентации";
  return "презентаций";
}
