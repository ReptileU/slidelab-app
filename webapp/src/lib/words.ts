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

function ru3(n: number, one: string, few: string, many: string): string {
  const d = n % 10;
  const dd = n % 100;
  if (d === 1 && dd !== 11) return one;
  if (d >= 2 && d <= 4 && (dd < 12 || dd > 14)) return few;
  return many;
}

/** «1 купон», «3 купона», «5 купонов». */
export function couponWord(lang: string, n: number): string {
  if (lang === "uz") return "kupon";
  if (lang === "en") return n === 1 ? "coupon" : "coupons";
  return ru3(n, "купон", "купона", "купонов");
}

/** «1 балл», «2 балла», «50 баллов». */
export function pointsWord(lang: string, n: number): string {
  if (lang === "uz") return "ball";
  if (lang === "en") return n === 1 ? "point" : "points";
  return ru3(n, "балл", "балла", "баллов");
}
