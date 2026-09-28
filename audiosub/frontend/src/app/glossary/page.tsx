"use client";

import { FormEvent, useEffect, useState } from "react";
import { api, GlossaryTerm } from "@/lib/api";
import { languageName, useMeta } from "@/lib/meta";

type Draft = Omit<GlossaryTerm, "id">;
const EMPTY: Draft = { term: "", translation: "", target_language: null, project_id: null, note: null };

export default function GlossaryPage() {
  const meta = useMeta();
  const [terms, setTerms] = useState<GlossaryTerm[] | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [editing, setEditing] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listGlossary().then(setTerms).catch((e) => setError(e.message));
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (editing) {
        const updated = await api.updateGlossary(editing, draft);
        setTerms((list) => list?.map((t) => (t.id === editing ? updated : t)) ?? null);
      } else {
        const created = await api.createGlossary(draft);
        setTerms((list) => [...(list ?? []), created].sort((a, b) => a.term.localeCompare(b.term)));
      }
      setDraft(EMPTY);
      setEditing(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function remove(t: GlossaryTerm) {
    await api.deleteGlossary(t.id);
    setTerms((list) => list?.filter((x) => x.id !== t.id) ?? null);
  }

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <h1 className="text-xl font-semibold">Glossary</h1>
      <p className="mt-1 text-sm text-gray-500">
        Terms here are sent with every translation and take priority over domain terminology and normal AI translation.
        Changing the glossary only needs “Retranslate” — speech recognition is not re-run.
      </p>

      <form onSubmit={submit} className="card mt-6 grid gap-3 p-4 sm:grid-cols-[1fr_1fr_180px_auto] sm:items-end">
        <div>
          <label className="label" htmlFor="term">Term</label>
          <input id="term" className="input" required value={draft.term} placeholder="e.g. AT"
            onChange={(e) => setDraft({ ...draft, term: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="translation">Translation</label>
          <input id="translation" className="input" required value={draft.translation} placeholder="e.g. Autoridade Tributária"
            onChange={(e) => setDraft({ ...draft, translation: e.target.value })} />
        </div>
        <div>
          <label className="label" htmlFor="lang">For target language</label>
          <select id="lang" className="input" value={draft.target_language ?? ""}
            onChange={(e) => setDraft({ ...draft, target_language: e.target.value || null })}>
            <option value="">All languages</option>
            {meta?.target_languages.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
          </select>
        </div>
        <div className="flex gap-2">
          <button className="btn-primary" type="submit">{editing ? "Save" : "Add"}</button>
          {editing && (
            <button className="btn-secondary" type="button" onClick={() => { setEditing(null); setDraft(EMPTY); }}>Cancel</button>
          )}
        </div>
      </form>
      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

      <div className="card mt-4 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-4 py-2">Term</th>
              <th className="px-4 py-2">Translation</th>
              <th className="px-4 py-2">Language</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {terms?.length === 0 && (
              <tr><td colSpan={4} className="px-4 py-6 text-center text-gray-500">No terms yet.</td></tr>
            )}
            {terms?.map((t) => (
              <tr key={t.id}>
                <td className="px-4 py-2 font-medium">{t.term}</td>
                <td className="px-4 py-2">{t.translation}</td>
                <td className="px-4 py-2 text-gray-500">{t.target_language ? languageName(meta, t.target_language) : "All"}</td>
                <td className="px-4 py-2 text-right">
                  <button className="btn-icon" title="Edit" onClick={() => {
                    setEditing(t.id);
                    setDraft({ term: t.term, translation: t.translation, target_language: t.target_language, project_id: t.project_id, note: t.note });
                  }}>✎</button>
                  <button className="btn-icon" title="Delete" onClick={() => remove(t)}>✕</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
