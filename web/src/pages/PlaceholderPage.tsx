interface PlaceholderPageProps {
  title: string;
  teamId: string | null;
}

/** Stand-in content for a tab until its page task lands. */
export function PlaceholderPage({ title, teamId }: PlaceholderPageProps) {
  return (
    <section
      aria-labelledby="page-title"
      className="rounded-lg border border-dashed border-slate-300 bg-white p-6"
    >
      <h2 id="page-title" className="text-xl font-semibold">
        {title}
      </h2>
      <p className="mt-2 text-sm text-slate-600">
        {teamId === null
          ? "Select a team to continue. This page is not built yet."
          : `Team ${teamId} is selected. This page is not built yet.`}
      </p>
    </section>
  );
}
