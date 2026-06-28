import { CheckCircle2 } from "lucide-react"

interface SuccessMessageProps {
  children: React.ReactNode
  className?: string
}

export default function SuccessMessage({ children, className = "" }: SuccessMessageProps) {
  const text =
    typeof children === "string" ? children.replace(/^✅\s*/, "") : children

  return (
    <div
      role="status"
      aria-live="polite"
      className={`inline-flex items-center gap-2 rounded-full border border-green-200 bg-green-50 px-3 py-1 text-sm font-medium text-green-700 ${className}`}
    >
      <CheckCircle2 className="h-4 w-4" />
      <span>{text}</span>
    </div>
  )
}
