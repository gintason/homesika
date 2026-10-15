import { tokens } from "./theme/tokens";

const SWATCHES = [
  ["Navy", tokens.color.primary[800]],
  ["Blue", tokens.color.primary[600]],
  ["Sky", tokens.color.sky[300]],
  ["Gold", tokens.color.gold[400]],
  ["Ink", tokens.color.ink[800]],
  ["Emergency", tokens.color.emergency.base],
] as const;

/** Phase 0 shell: brand + design foundations. The landlord dashboard is built in Phase 1. */
export default function App() {
  return (
    <div className="min-h-screen">
      <header className="bg-primary-800 text-white">
        <div className="mx-auto flex max-w-[1120px] items-center gap-3 px-6 py-4">
          <img src="/homesika-logo.jpg" alt="" className="h-10 w-10 rounded-md bg-white object-cover" />
          <span className="font-display text-xl font-bold">Homesika</span>
          <span className="ml-auto rounded-pill bg-primary-700 px-3 py-1 text-sm">Phase 0 · foundations</span>
        </div>
      </header>
      <main className="mx-auto max-w-[1120px] space-y-8 px-6 py-10">
        <section className="space-y-2">
          <h1 className="font-display text-3xl font-bold text-ink-900">Estate management, rent and everyday life</h1>
          <p className="max-w-2xl text-base text-ink-600">
            Landlords, agents, tenants, estates and artisans in one place, with WhatsApp as the front door.
            The dashboard arrives in Phase 1.
          </p>
        </section>
        <section aria-labelledby="palette" className="rounded-lg bg-surface-card p-6 shadow-md">
          <h2 id="palette" className="font-display text-lg font-semibold text-ink-900">
            Brand palette
          </h2>
          <ul className="mt-4 grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
            {SWATCHES.map(([name, hex]) => (
              <li key={name} className="space-y-2">
                <div className="h-16 rounded-md" style={{ backgroundColor: hex }} />
                <p className="text-sm font-medium text-ink-800">{name}</p>
                <p className="font-mono text-xs text-ink-500">{hex}</p>
              </li>
            ))}
          </ul>
        </section>
      </main>
    </div>
  );
}
