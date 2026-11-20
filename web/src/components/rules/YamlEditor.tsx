import { yaml } from "@codemirror/lang-yaml";
import { Facet, Prec } from "@codemirror/state";
import { Decoration, EditorView, GutterMarker, gutter } from "@codemirror/view";
import CodeMirror from "@uiw/react-codemirror";
import { useMemo } from "react";

import { useIsDarkTheme } from "./useIsDarkTheme";

const errorLineFacet = Facet.define<readonly number[], readonly number[]>({
  combine: (values) => values.flat(),
});

class ErrorMarker extends GutterMarker {
  override toDOM(): Node {
    const el = document.createElement("span");
    el.textContent = "!";
    el.title = "Validation error on this line";
    el.className = "font-semibold text-critical-ink";
    return el;
  }
}
const marker = new ErrorMarker();
const lineDecoration = Decoration.line({ class: "bg-critical/12" });

/** Maps the editor onto the Beacon tokens so it follows light and dark. */
const beaconTheme = EditorView.theme({
  "&": { backgroundColor: "var(--fill)", color: "var(--ink)", fontSize: "13px" },
  ".cm-gutters": { backgroundColor: "var(--fill)", color: "var(--ink-3)", border: "none" },
  ".cm-content": { caretColor: "var(--ink)" },
  ".cm-cursor": { borderLeftColor: "var(--ink)" },
  "&.cm-focused": { outline: "2px solid var(--accent)", outlineOffset: "2px" },
  "&.cm-focused .cm-selectionBackground, .cm-selectionBackground": {
    backgroundColor: "color-mix(in srgb, var(--accent) 25%, transparent)",
  },
});

const errorExtensions = [
  gutter({
    class: "w-4",
    lineMarker(view, line) {
      const number = view.state.doc.lineAt(line.from).number;
      return view.state.facet(errorLineFacet).includes(number) ? marker : null;
    },
  }),
  EditorView.decorations.compute(["doc", errorLineFacet], (state) => {
    const lines = state.facet(errorLineFacet).filter((n) => n >= 1 && n <= state.doc.lines);
    const unique = [...new Set(lines)].sort((a, b) => a - b);
    return Decoration.set(unique.map((n) => lineDecoration.range(state.doc.line(n).from)));
  }),
];

interface YamlEditorProps {
  readonly value: string;
  readonly errorLines: readonly number[];
  readonly onChange: (value: string) => void;
}

/** CodeMirror 6 YAML editor with line numbers; lines with validation errors are marked. */
export function YamlEditor({ value, errorLines, onChange }: YamlEditorProps) {
  const isDark = useIsDarkTheme();
  const extensions = useMemo(
    () => [
      yaml(),
      Prec.highest(beaconTheme),
      EditorView.lineWrapping,
      ...errorExtensions,
      errorLineFacet.of(errorLines),
    ],
    [errorLines],
  );
  return (
    <CodeMirror
      value={value}
      height="22rem"
      extensions={extensions}
      basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: false }}
      onChange={onChange}
      aria-label="Rule YAML"
      theme={isDark ? "dark" : "light"}
      className="overflow-hidden rounded-input"
    />
  );
}
