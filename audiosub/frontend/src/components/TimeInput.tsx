"use client";

import { useEffect, useState } from "react";
import { formatTime, parseTime } from "@/lib/format";

export function TimeInput({
  value,
  onCommit,
  label,
}: {
  value: number;
  onCommit: (seconds: number) => boolean;
  label: string;
}) {
  const [text, setText] = useState(formatTime(value));
  const [invalid, setInvalid] = useState(false);

  useEffect(() => {
    setText(formatTime(value));
    setInvalid(false);
  }, [value]);

  function commit() {
    const parsed = parseTime(text);
    if (parsed === null) {
      setInvalid(true);
      return;
    }
    if (Math.abs(parsed - value) < 0.0005) {
      setText(formatTime(value));
      setInvalid(false);
      return;
    }
    const ok = onCommit(parsed);
    setInvalid(!ok);
    if (ok) setText(formatTime(parsed));
  }

  return (
    <input
      aria-label={label}
      value={text}
      onChange={(e) => setText(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
        if (e.key === "Escape") {
          setText(formatTime(value));
          setInvalid(false);
        }
      }}
      className={`w-[5.8rem] rounded border px-1.5 py-0.5 font-mono text-xs ${
        invalid ? "border-red-400 bg-red-50" : "border-transparent bg-transparent hover:border-gray-300 focus:border-indigo-500 focus:bg-white"
      } focus:outline-none`}
    />
  );
}
