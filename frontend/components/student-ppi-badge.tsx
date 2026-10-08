export default function StudentPpiBadge({ active }: { active: boolean }) {
  if (!active) return null
  return (
    <span
      className="absolute right-3 top-3 inline-flex rounded-full border border-violet-200 bg-violet-50 px-2 py-0.5 text-[11px] font-semibold tracking-wide text-violet-800"
      title="PPI — acompañamiento psicopedagógico"
      aria-label="PPI: acompañamiento psicopedagógico"
    >
      PPI
    </span>
  )
}
