import { useLang } from "../lib/app";
import type { Lang } from "../lib/types";
import { Cell, Group } from "../ui";

const LANGS: { code: Lang; name: string; hello: string }[] = [
  { code: "ru", name: "Русский", hello: "Привет!" },
  { code: "uz", name: "O‘zbekcha", hello: "Salom!" },
  { code: "en", name: "English", hello: "Hello!" },
];

export function LangPick() {
  const { lang, setLang } = useLang();
  return (
    <div className="page no-tabbar" style={{ display: "grid", minHeight: "100vh", alignContent: "center" }}>
      <div className="center" style={{ marginBottom: 32 }}>
        <div className="footnote accent" style={{ fontWeight: 600, letterSpacing: 2 }}>
          SLIDELAB
        </div>
        <h1 className="title1 mt-8">Выберите язык</h1>
        <p className="subhead secondary">Tilni tanlang · Choose language</p>
      </div>
      <Group>
        {LANGS.map((l) => (
          <Cell key={l.code} title={l.name} subtitle={l.hello} checked={l.code === lang} onClick={() => setLang(l.code)} />
        ))}
      </Group>
    </div>
  );
}
