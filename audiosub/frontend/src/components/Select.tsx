import { Option } from "@/lib/api";

export function Select({
  label,
  value,
  options,
  onChange,
  disabled,
  id,
}: {
  label?: string;
  value: string;
  options: Option[];
  onChange: (value: string) => void;
  disabled?: boolean;
  id?: string;
}) {
  return (
    <div>
      {label && (
        <label className="label" htmlFor={id}>
          {label}
        </label>
      )}
      <select id={id} className="input" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        {options.map((o) => (
          <option key={o.code} value={o.code}>
            {o.native_name && o.native_name !== o.name ? `${o.name} — ${o.native_name}` : o.name}
          </option>
        ))}
      </select>
    </div>
  );
}
