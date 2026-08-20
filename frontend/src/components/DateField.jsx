import { useRef } from "react";
import { formatDateInput } from "../utils/format";
import Icon from "./Icon";

function toIso(value) {
  const m = String(value || "").match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!m) return "";
  return `${m[3]}-${m[2]}-${m[1]}`;
}

export default function DateField({ label, value, onChange, required = false }) {
  const dateInputRef = useRef(null);

  function handleTextChange(e) {
    onChange(formatDateInput(e.target.value));
  }

  function handleNativeChange(e) {
    const iso = e.target.value;
    if (!iso) return;
    const [y, m, d] = iso.split("-");
    onChange(`${d}/${m}/${y}`);
  }

  function openPicker() {
    const el = dateInputRef.current;
    if (!el) return;
    if (typeof el.showPicker === "function") {
      el.showPicker();
    } else {
      el.focus();
      el.click();
    }
  }

  return (
    <div className="field">
      {label && <label>{label}</label>}
      <div style={{ position: "relative" }}>
        <input
          placeholder="dd/mm/aaaa"
          value={value}
          onChange={handleTextChange}
          required={required}
          style={{ paddingRight: 42, width: "100%" }}
        />
        <button
          type="button"
          onClick={openPicker}
          title="Abrir calendario"
          style={{
            position: "absolute",
            right: 4,
            top: "50%",
            transform: "translateY(-50%)",
            width: 30,
            height: 30,
            padding: 0,
            background: "transparent",
            border: "none",
            fontSize: 15,
            color: "var(--muted)",
            cursor: "pointer",
          }}
        >
          <Icon name="calendar" size={16} />
        </button>
        <input
          ref={dateInputRef}
          type="date"
          value={toIso(value)}
          onChange={handleNativeChange}
          tabIndex={-1}
          aria-hidden="true"
          style={{ position: "absolute", top: 0, right: 4, width: 30, height: 30, opacity: 0, pointerEvents: "none" }}
        />
      </div>
    </div>
  );
}
