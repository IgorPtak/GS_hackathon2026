import { yaml } from "@codemirror/lang-yaml";
import { Facet } from "@codemirror/state";
import { Decoration, EditorView, GutterMarker, gutter } from "@codemirror/view";
import CodeMirror from "@uiw/react-codemirror";
import { useMemo } from "react";

const errorLineFacet = Facet.define<readonly number[], readonly number[]>({
  combine: (values) => values.flat(),
});

class ErrorMarker extends GutterMarker {
  override toDOM(): Node {
    const el = document.createElement("span");
    el.textContent = "!";
    el.title = "Validation error on this line";
    el.className = "font-bold text-red-600";
    return el;
  }
}
const marker = new ErrorMarker();
const lineDecoration = Decoration.line({ class: "bg-red-50" });

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
  const extensions = useMemo(
    () => [yaml(), EditorView.lineWrapping, ...errorExtensions, errorLineFacet.of(errorLines)],
    [errorLines],
  );
  return (
    <CodeMirror
      value={value}
      height="26rem"
      extensions={extensions}
      basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: false }}
      onChange={onChange}
      aria-label="Rule YAML"
      className="overflow-hidden rounded border border-slate-300 text-sm"
    />
  );
}
