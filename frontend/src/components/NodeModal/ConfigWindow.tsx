import type { SchemaProperty } from "../../lib/api";
import { useDagStore } from "../../store/dagStore";

function Field({
  name,
  prop,
  value,
  onChange,
}: {
  name: string;
  prop: SchemaProperty;
  value: unknown;
  onChange: (name: string, value: unknown) => void;
}) {
  const title = prop.title || name;
  if (prop.enum) {
    return (
      <label>
        {title}
        <select value={String(value ?? "")} onChange={(e) => onChange(name, e.target.value)}>
          <option value="">—</option>
          {prop.enum.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
    );
  }
  if (prop.type === "boolean") {
    return (
      <label className="checkbox">
        <input
          type="checkbox"
          checked={Boolean(value)}
          onChange={(e) => onChange(name, e.target.checked)}
        />
        {title}
      </label>
    );
  }
  if (prop.format === "textarea" || prop.type === "object") {
    return (
      <label>
        {title}
        <textarea
          rows={8}
          value={typeof value === "string" ? value : JSON.stringify(value ?? "", null, 2)}
          onChange={(e) => onChange(name, e.target.value)}
        />
      </label>
    );
  }
  const inputType = prop.type === "integer" || prop.type === "number" ? "number" : "text";
  return (
    <label>
      {title}
      {prop.description ? <small>{prop.description}</small> : null}
      <input
        type={inputType}
        value={value === undefined || value === null ? "" : String(value)}
        onChange={(e) =>
          onChange(
            name,
            inputType === "number" ? (e.target.value === "" ? "" : Number(e.target.value)) : e.target.value
          )
        }
      />
    </label>
  );
}

export function ConfigWindow() {
  const selectedNodeId = useDagStore((s) => s.selectedNodeId);
  const nodes = useDagStore((s) => s.nodes);
  const updateNodeParams = useDagStore((s) => s.updateNodeParams);
  const node = nodes.find((n) => n.id === selectedNodeId);
  const properties = node?.data.schema?.properties || {};

  if (!node) {
    return (
      <section className="inspector-pane">
        <header>
          <h3>Config</h3>
        </header>
        <div className="empty">Sélectionnez un nœud.</div>
      </section>
    );
  }

  return (
    <section className="inspector-pane">
      <header>
        <h3>Config</h3>
        <p>{node.data.schema?.description || node.data.nodeType}</p>
      </header>
      <form className="config-form" onSubmit={(e) => e.preventDefault()}>
        {Object.entries(properties).map(([name, prop]) => (
          <Field
            key={name}
            name={name}
            prop={prop}
            value={node.data.params[name]}
            onChange={(key, value) => updateNodeParams(node.id, { [key]: value })}
          />
        ))}
      </form>
    </section>
  );
}
