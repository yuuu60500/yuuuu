"use client";

import { useEffect, useState } from "react";
import { api, Meta } from "./api";

let cached: Meta | null = null;
let pending: Promise<Meta> | null = null;

export function useMeta(): Meta | null {
  const [meta, setMeta] = useState<Meta | null>(cached);
  useEffect(() => {
    if (cached) return;
    pending ??= api.meta();
    pending.then((m) => {
      cached = m;
      setMeta(m);
    }).catch(() => {
      pending = null;
    });
  }, []);
  return meta;
}

export function languageName(meta: Meta | null, code: string | null | undefined): string {
  if (!code) return "—";
  const all = [...(meta?.source_languages ?? []), ...(meta?.target_languages ?? [])];
  return all.find((l) => l.code === code)?.name ?? code;
}

export function domainName(meta: Meta | null, code: string): string {
  return meta?.domains.find((d) => d.code === code)?.name ?? code;
}
